import os
import math
from tqdm import tqdm

from HersheyFonts import HersheyFonts
from arm_trigger.mode_intf.xarm_interface import XarmInterface
from robot_safety import SafetyBounds, check_position_or_raise


# ----------------------------------------------------------------------
# Calibration / tilt parameters
# These are kept from your current write_words.py logic.
# ----------------------------------------------------------------------

VERTICAL_TILT_FACTOR = -0.12
VERTICAL_TILT_CENTER = 70.0

HORIZONTAL_TILT_FACTOR = -0.06
HORIZONTAL_TILT_CENTER = (-0.35 + -0.15) / 2.0  # = -0.25


# ----------------------------------------------------------------------
# Hershey stroke-font generation
# ----------------------------------------------------------------------

def _dist(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _same_point(p1, p2, eps=0.001):
    return _dist(p1, p2) <= eps


def _connect_segments(segments, eps=0.001):
    """
    Connects consecutive Hershey line segments into longer strokes.
    This reduces constant pen-up / pen-down movement.

    Input:
        [((x1, y1), (x2, y2)), ...]
    Output:
        [[(x, y), (x, y), ...], ...]
    """
    strokes = []

    for p1, p2 in segments:
        p1 = tuple(p1)
        p2 = tuple(p2)

        if not strokes:
            strokes.append([p1, p2])
            continue

        last_stroke = strokes[-1]
        last_point = last_stroke[-1]

        if _same_point(last_point, p1, eps):
            last_stroke.append(p2)
        elif _same_point(last_point, p2, eps):
            last_stroke.append(p1)
        else:
            strokes.append([p1, p2])

    return strokes


def _glyph_bbox(segments):
    """Returns min_x, max_x, min_y, max_y for a glyph's segments."""
    xs = []
    ys = []
    for (x1, y1), (x2, y2) in segments:
        xs.extend([x1, x2])
        ys.extend([y1, y2])

    if not xs:
        return 0.0, 0.0, 0.0, 0.0

    return min(xs), max(xs), min(ys), max(ys)


def create_hershey_text_file(
    text,
    output_file="./output/text_trail.txt",
    font_name="futural",
    font_size=10,
    start_x=10.0,
    start_y=70.0,
    char_spacing=3.0,
    word_spacing=8.0,
    line_spacing=18.0,
    connect_epsilon=0.001,
):
    """
    Creates a stroke-based trail file using HersheyFonts.

    Output format:
        x y z

    z > 0 = pen up
    z < 0 = pen down

    The output is still in your old image/text coordinate system.
    The robot mapping happens later in draw_text_with_robot().
    """
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    font = HersheyFonts()
    try:
        font.load_default_font(font_name)
    except Exception:
        print(f"WARNING: Font '{font_name}' not found. Falling back to default font.")
        font.load_default_font()

    font.normalize_rendering(font_size)

    points = []
    cursor_y = start_y

    for line in text.split("\n"):
        cursor_x = start_x

        # Keep empty lines as real new lines
        if line == "":
            cursor_y -= line_spacing
            continue

        for ch in line:
            if ch == " ":
                cursor_x += word_spacing
                continue

            raw_segments = list(font.lines_for_text(ch))
            if not raw_segments:
                # Unknown character: skip but leave a little space
                cursor_x += word_spacing
                continue

            min_x, max_x, min_y, max_y = _glyph_bbox(raw_segments)
            glyph_width = max_x - min_x

            # Move each glyph so that its left edge starts at cursor_x.
            transformed_segments = []
            for (x1, y1), (x2, y2) in raw_segments:
                p1 = (cursor_x + (x1 - min_x), cursor_y + y1)
                p2 = (cursor_x + (x2 - min_x), cursor_y + y2)
                transformed_segments.append((p1, p2))

            strokes = _connect_segments(transformed_segments, eps=connect_epsilon)

            for stroke in strokes:
                if len(stroke) < 2:
                    continue

                first_x, first_y = stroke[0]
                last_x, last_y = stroke[-1]

                # Move to stroke start with pen up
                points.append((first_x, first_y, 33))
                # Lower pen
                points.append((first_x, first_y, -33))
                # Draw continuous stroke
                for x, y in stroke[1:]:
                    points.append((x, y, -33))
                # Lift pen
                points.append((last_x, last_y, 33))

            cursor_x += glyph_width + char_spacing

        cursor_y -= line_spacing

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Hershey stroke text trail\n")
        f.write(f"# font_name={font_name}, font_size={font_size}\n")
        f.write(f"# char_spacing={char_spacing}, word_spacing={word_spacing}, line_spacing={line_spacing}\n")
        for x, y, z in points:
            f.write(f"{x:.4f} {y:.4f} {z}\n")

    print(f"Saved trail file: {output_file}")
    print(f"Font: {font_name}, font_size={font_size}")
    print(f"Points: {len(points)}")
    return output_file


# ----------------------------------------------------------------------
# Coordinate mapping and tilt correction
# ----------------------------------------------------------------------

def compensate_vertical_tilt(x_img, y_img, y_center=VERTICAL_TILT_CENTER, tilt_factor=VERTICAL_TILT_FACTOR):
    """
    Corrects hardware tilt in image/text coordinates.

    Your observed coordinate system:
    - x0 / x_img affects up-down movement on paper
    - y0 / y_img affects left-right movement on paper

    Therefore we correct x_img depending on y_img.
    """
    corrected_x_img = x_img + tilt_factor * (y_img - y_center)
    corrected_y_img = y_img
    return corrected_x_img, corrected_y_img


def text_point_to_robot_world(
    x_img,
    y_img,
    z_code,
    last_z,
    x0=300.0,
    y0=-200.0,
    write_h=0.623,
    dh=50.0,
    image_size=1.5,
):
    """
    Converts one text/image point into your robot world coordinate system.

    Important for your setup:
    - y0 controls left/right on paper and maps to robot x.
    - x0 controls up/down on paper and maps to robot y.

    Returns:
        robot_x, robot_y, robot_z, new_last_z
    """
    x_img, y_img = compensate_vertical_tilt(x_img, y_img)

    # Same mapping style as your current write_words.py
    p = [140.0 - x_img * image_size, 140.0 - y_img * image_size]

    if z_code == 0:
        z_robot = last_z
    elif z_code < 0:
        z_robot = write_h
    else:
        z_robot = write_h + dh / 1000.0

    new_last_z = z_robot

    # Your coordinate mapping:
    # vertical_world -> robot y, controlled mainly by x0
    # horizontal_world -> robot x, controlled mainly by y0
    vertical_world = (x0 + p[1]) / 1000.0
    horizontal_world = (y0 - p[0]) / 1000.0

    # Horizontal tilt correction:
    # right side was lower, so lift it slightly via vertical_world.
    vertical_world = vertical_world + HORIZONTAL_TILT_FACTOR * (
        horizontal_world - HORIZONTAL_TILT_CENTER
    )

    robot_x = horizontal_world
    robot_y = vertical_world
    robot_z = z_robot

    return robot_x, robot_y, robot_z, new_last_z


# ----------------------------------------------------------------------
# Diagnostics and safety
# ----------------------------------------------------------------------

def print_motion_range(data):
    if not data:
        print("No motion data generated.")
        return

    xs = [p[0] for p in data]
    ys = [p[1] for p in data]
    zs = [p[2] for p in data]

    print(f"x range: {min(xs):.4f} .. {max(xs):.4f}")
    print(f"y range: {min(ys):.4f} .. {max(ys):.4f}")
    print(f"z range: {min(zs):.4f} .. {max(zs):.4f}")


def suggest_position_fix(data, bounds):
    """Prints simple x0/y0 hints when the generated text is outside bounds."""
    if not data:
        return

    xs = [p[0] for p in data]
    ys = [p[1] for p in data]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    print("\nPosition hint:")
    if min_y < bounds.y_min:
        print(f"- y is too small by {(bounds.y_min - min_y) * 1000:.1f} mm -> increase x0")
    if max_y > bounds.y_max:
        print(f"- y is too large by {(max_y - bounds.y_max) * 1000:.1f} mm -> decrease x0")
    if min_x < bounds.x_min:
        print(f"- x is too small by {(bounds.x_min - min_x) * 1000:.1f} mm -> adjust y0")
    if max_x > bounds.x_max:
        print(f"- x is too large by {(max_x - bounds.x_max) * 1000:.1f} mm -> adjust y0")
    print()


def read_trail_and_convert_to_robot(
    output_file,
    x0=300.0,
    y0=-200.0,
    write_h=0.623,
    dh=50.0,
    image_size=1.5,
):
    data = []
    last_z = write_h + dh / 1000.0

    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) != 3:
                continue

            x_img = float(parts[0])
            y_img = float(parts[1])
            z_code = float(parts[2])

            robot_x, robot_y, robot_z, last_z = text_point_to_robot_world(
                x_img=x_img,
                y_img=y_img,
                z_code=z_code,
                last_z=last_z,
                x0=x0,
                y0=y0,
                write_h=write_h,
                dh=dh,
                image_size=image_size,
            )
            data.append([robot_x, robot_y, robot_z])

    return data


# ----------------------------------------------------------------------
# Main drawing function
# ----------------------------------------------------------------------

def draw_text_with_robot(
    text,
    output_file="./output/text_trail.txt",
    font_name="futural",
    font_size=10,
    start_x=10.0,
    start_y=70.0,
    char_spacing=3.0,
    word_spacing=8.0,
    line_spacing=18.0,
    x0=300.0,
    y0=-200.0,
    write_h=0.623,
    dh=50.0,
    image_size=1.5,
    speed=1,
    dry_run=False,
):
    """
    Generate Hershey stroke text, check safety, and optionally draw with robot.

    dry_run=True:
        only generate trail + print ranges + safety check.
        The robot will not move.
    """

    bounds = SafetyBounds(
        x_min=-0.35,  # robot x / controlled mainly by y0 / paper left-right
        x_max=-0.15,
        y_min=0.30,   # robot y / controlled mainly by x0 / paper up-down
        y_max=0.478,
        z_min=write_h - 0.01,
        z_max=write_h + dh / 1000.0 + 0.01,
    )

    create_hershey_text_file(
        text=text,
        output_file=output_file,
        font_name=font_name,
        font_size=font_size,
        start_x=start_x,
        start_y=start_y,
        char_spacing=char_spacing,
        word_spacing=word_spacing,
        line_spacing=line_spacing,
    )

    data = read_trail_and_convert_to_robot(
        output_file=output_file,
        x0=x0,
        y0=y0,
        write_h=write_h,
        dh=dh,
        image_size=image_size,
    )

    print(f"VERTICAL_TILT_FACTOR = {VERTICAL_TILT_FACTOR}")
    print(f"HORIZONTAL_TILT_FACTOR = {HORIZONTAL_TILT_FACTOR}")
    print(f"x0 = {x0}, y0 = {y0}, image_size = {image_size}")
    print_motion_range(data)

    # Safety pre-check before connecting/moving robot
    try:
        for robot_x, robot_y, robot_z in data:
            check_position_or_raise(robot_x, robot_y, robot_z, bounds)
    except ValueError:
        suggest_position_fix(data, bounds)
        raise

    if dry_run:
        print("DRY RUN OK: safety check passed. Robot was not moved.")
        return True

    uarm_interface = XarmInterface()
    if not uarm_interface.connect():
        print("Failed to connect to robot")
        return False

    print(f"Drawing '{text}' with {len(data)} points...")
    for robot_x, robot_y, robot_z in tqdm(data):
        check_position_or_raise(robot_x, robot_y, robot_z, bounds)
        uarm_interface.set_position(x=robot_x, y=robot_y, z=robot_z, speed=speed, wait=True)

    print("Text drawing finished.")
    return True


# ----------------------------------------------------------------------
# Example usage
# ----------------------------------------------------------------------
if __name__ == "__main__":
    draw_text_with_robot(
        "",
        output_file="./output/text_trail.txt",
        font_name="futural",     # try: futural, rowmans, scripts, scriptc
        font_size=10,
        start_x=10.0,
        start_y=70.0,
        char_spacing=3.0,
        word_spacing=8.0,
        line_spacing=18.0,
        x0=300.0,
        y0=-200.0,
        write_h=0.623,
        dh=50.0,
        image_size=1.5,
        speed=1,
        dry_run=False,            # first test safely; set False to draw
    )
