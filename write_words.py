from shutil import copyfile
import numpy as np
import os

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable):
        return iterable

from robot_safety import SafetyBounds, check_position_or_raise
from letter_strokes import LETTER_STROKES, letter_width


# ----------------------------------------------------------------------
# Tilt / Calibration parameters
# change if needed, same as in draw_grid_calibration.py
# ----------------------------------------------------------------------

VERTICAL_TILT_FACTOR = -0.12 
VERTICAL_TILT_CENTER = 70.0

HORIZONTAL_TILT_FACTOR = -0.06
HORIZONTAL_TILT_CENTER = (-0.35 + -0.15) / 2.0   # = -0.25


# ----------------------------------------------------------------------
# Generate trail file (same Z codes as original)
# ----------------------------------------------------------------------
def create_text_file(text, output_file, start_x=10, start_y=70, scale=0.08, letter_spacing=15):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'a') as f:
        current_x = start_x
        baseline_y = start_y

        for ch in text.upper():
            if ch == '\n':
                baseline_y -= 150 * scale
                current_x = start_x
                continue

            if ch == ' ':
                current_x += letter_spacing * scale * 3
                continue

            strokes = LETTER_STROKES.get(ch)
            if strokes is None:
                continue

            width = letter_width(ch)

            for stroke in strokes:
                if not stroke:
                    continue

                first_x = stroke[0][0] * scale + current_x
                first_y = stroke[0][1] * scale + baseline_y
                f.write(f"{first_x} {first_y} 0\n")
                f.write(f"{first_x} {first_y} -33\n")

                for p in stroke[1:]:
                    x = p[0] * scale + current_x
                    y = p[1] * scale + baseline_y
                    f.write(f"{x} {y} 0\n")

                last_x = stroke[-1][0] * scale + current_x
                last_y = stroke[-1][1] * scale + baseline_y
                f.write(f"{last_x} {last_y} 33\n")

            current_x += width * scale + letter_spacing * scale


# ----------------------------------------------------------------------
# Draw text with robot
# ----------------------------------------------------------------------

def print_motion_range(data):
    xs = []
    ys = []
    zs = []

    for robot_y, robot_x, robot_z in data:
        xs.append(robot_x)
        ys.append(robot_y)
        zs.append(robot_z)

    print(f"x range: {min(xs):.4f} .. {max(xs):.4f}")
    print(f"y range: {min(ys):.4f} .. {max(ys):.4f}")
    print(f"z range: {min(zs):.4f} .. {max(zs):.4f}")


def compensate_tilt(x_img, y_img, y_center=VERTICAL_TILT_CENTER, tilt_factor=VERTICAL_TILT_FACTOR):
    """
    Korrigiert die Hardware-Neigung direkt in der Trajectory.

    Bei deinem Roboter gilt:
    - x0 / x_img beeinflusst hoch-runter
    - y0 / y_img beeinflusst rechts-links

    Deshalb korrigieren wir x_img abhängig von y_img.
    """
    corrected_x_img = x_img + tilt_factor * (y_img - y_center)
    corrected_y_img = y_img
    return corrected_x_img, corrected_y_img


def draw_text_with_robot(text, output_file='./output/text_trail.txt',
                         start_x=10, start_y=70, scale=0.08, letter_spacing=15,
                         x0=300.0, y0=-200.0, write_h=0.623, dh=50.0, image_size=1.5,
                         speed=1, dry_run=False):
    bounds = SafetyBounds(
        x_min=-0.35,  # change y0
        x_max=-0.15,
        y_min=0.30,  # change x0
        y_max=0.478,
        z_min=write_h - 0.01,
        z_max=write_h + dh / 1000.0 + 0.01
    )

    # Generate trail file
    with open(output_file, 'w') as f:
        f.write("# Text trail\n")
    create_text_file(text, output_file, start_x, start_y, scale, letter_spacing)



    # Read and transform
    trail_commands = []
    last_z = write_h
    with open(output_file, 'r') as ff:
        for line in ff:
            if line.startswith('#'):
                continue

            d = line.strip().split()
            if len(d) != 3:
                continue

            x_img = float(d[0])
            y_img = float(d[1])
            z_code = float(d[2])

            x_img, y_img = compensate_tilt(
                x_img,
                y_img
            )

            p = [140.0 - x_img * image_size, 140.0 - y_img * image_size]

            if z_code == 0:
                z = last_z
            elif z_code < 0:
                z = write_h
            else:
                z = write_h + dh / 1000.0

            last_z = z
            trail_commands.append((p[0], p[1], z))

    # Convert to world coordinates
    data = []

    # horizontaler Mittelpunkt deines sicheren Bereichs
    horizontal_center = HORIZONTAL_TILT_CENTER

    # rechte Seite ist 0.6 cm näher am unteren Rand als linke Seite
    # 0.6 cm = 0.006 m
    # Breite ungefähr: -0.15 - (-0.35) = 0.20 m
    # factor = -0.006 / 0.20 = -0.03
    horizontal_tilt_factor = HORIZONTAL_TILT_FACTOR

    for x_img, y_img, z_robot in trail_commands:
        vertical_world = (x0 + y_img) / 1000.0      # hoch/runter auf Papier
        horizontal_world = (y0 - x_img) / 1000.0    # links/rechts auf Papier

        # Korrektur:
        # rechts ist aktuell zu tief, also rechte Seite leicht nach oben ziehen.
        vertical_world = vertical_world + horizontal_tilt_factor * (
            horizontal_world - horizontal_center
        )

        z_world = z_robot
        data.append([vertical_world, horizontal_world, z_world])

    print(f"VERTICAL_TILT_FACTOR = {VERTICAL_TILT_FACTOR}")
    print(f"HORIZONTAL_TILT_FACTOR = {HORIZONTAL_TILT_FACTOR}")

    print_motion_range(data)

    # Safety check before any movement
    for i in range(len(data)):
        robot_y, robot_x, robot_z = data[i]
        check_position_or_raise(robot_x, robot_y, robot_z, bounds)

    if dry_run:
        print("DRY RUN OK: safety check passed. Robot was not moved.")
        return True

    from arm_trigger.mode_intf.xarm_interface import XarmInterface

    uarm_interface = XarmInterface()
    if not uarm_interface.connect():
        print("Failed to connect to robot")
        return False

    print(f"Drawing '{text}' with {len(data)} points...")
    for i in tqdm(range(len(data))):
        robot_y, robot_x, robot_z = data[i]
        check_position_or_raise(robot_x, robot_y, robot_z, bounds)
        uarm_interface.set_position(x=robot_x, y=robot_y, z=robot_z, speed=speed, wait=True)

    print("Text drawing finished.")
    return True


# ----------------------------------------------------------------------
if __name__ == "__main__":
    draw_text_with_robot("hi",
                         output_file='./output/text_trail.txt',
                         start_x=10, start_y=70, scale=0.08, letter_spacing=15,
                         x0=290.0, y0=-220.0, write_h=0.623, dh=50.0, image_size=1.5,
                         speed=1)
