import os

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable):
        return iterable

from chinese_font_provider import (
    get_glyph_with_fallback,
    get_units_per_em,
    has_glyph_with_fallback,
)
from chinese_style_profiles import DEFAULT_STYLE_NAME, get_style_profile, transform_glyph
from import_animcjk_data import ensure_text_in_animcjk_font
from import_hanzi_writer_data import DEFAULT_FONT_PATH, ensure_text_in_font
from robot_safety import SafetyBounds, check_position_or_raise


VERTICAL_TILT_FACTOR = -0.12
VERTICAL_TILT_CENTER = 70.0

HORIZONTAL_TILT_FACTOR = -0.06
HORIZONTAL_TILT_CENTER = (-0.35 + -0.15) / 2.0

DEFAULT_FONT_NAME = "hanziwriter"
SUPPORTED_CHINESE_FONT_NAMES = ("hanziwriter", "animcjk_zhhans")
SUPPORTED_CHINESE_STYLE_NAME = DEFAULT_STYLE_NAME


def require_supported_chinese_font(font_name):
    resolved_font_name = font_name or DEFAULT_FONT_NAME
    if resolved_font_name not in SUPPORTED_CHINESE_FONT_NAMES:
        raise ValueError(
            f"Unsupported Chinese font '{resolved_font_name}'. "
            f"Supported Chinese fonts: {', '.join(SUPPORTED_CHINESE_FONT_NAMES)}."
        )
    return resolved_font_name


def require_supported_chinese_style(style_name):
    resolved_style_name = style_name or SUPPORTED_CHINESE_STYLE_NAME
    if resolved_style_name != SUPPORTED_CHINESE_STYLE_NAME:
        raise ValueError(
            f"Unsupported Chinese style '{resolved_style_name}'. "
            f"Only '{SUPPORTED_CHINESE_STYLE_NAME}' is enabled in this project."
        )
    return resolved_style_name


def validate_chinese_text(text, font_name):
    font_name = require_supported_chinese_font(font_name)
    unsupported = []
    for ch in text:
        if ch in [" ", "\n"]:
            continue
        if not has_glyph_with_fallback(font_name, ch):
            unsupported.append(ch)
    return sorted(set(unsupported))


def auto_import_missing_chinese_glyphs(text, font_name, skip_missing=True):
    font_name = require_supported_chinese_font(font_name)

    unresolved_chars = []
    seen = set()
    for ch in text:
        if ch in [" ", "\n", "\t"]:
            continue
        if ch in seen:
            continue
        seen.add(ch)
        if not has_glyph_with_fallback(font_name, ch):
            unresolved_chars.append(ch)

    if not unresolved_chars:
        return [], []

    unresolved_text = "".join(unresolved_chars)
    if font_name == "animcjk_zhhans":
        return ensure_text_in_animcjk_font(
            text=unresolved_text,
            variant_name="zhhans",
            skip_missing=skip_missing,
        )

    return ensure_text_in_font(
        text=unresolved_text,
        font_path=DEFAULT_FONT_PATH,
        skip_missing=skip_missing,
    )


def auto_import_missing_hanziwriter_glyphs(text, font_name, skip_missing=True):
    return auto_import_missing_chinese_glyphs(
        text=text,
        font_name=font_name,
        skip_missing=skip_missing,
    )


def compute_default_max_line_width(start_x, y0, image_size, bounds, right_margin=4.0):
    min_x_img = (1000.0 * bounds.x_min - y0 + 140.0) / image_size
    max_x_img = (1000.0 * bounds.x_max - y0 + 140.0) / image_size

    usable_start_x = max(start_x, min_x_img)
    width = max_x_img - usable_start_x - right_margin
    return max(width, 0.0)


def create_chinese_text_file(
    text,
    output_file="./output/text_trail_chinese.txt",
    font_name=DEFAULT_FONT_NAME,
    style_name=SUPPORTED_CHINESE_STYLE_NAME,
    start_x=10.0,
    start_y=70.0,
    char_size=9.0,
    char_spacing=2.0,
    line_spacing=14.0,
    space_advance_ratio=0.55,
    auto_wrap=True,
    max_line_width=None,
):
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    font_name = require_supported_chinese_font(font_name)
    style_name = require_supported_chinese_style(style_name)
    get_style_profile(style_name)
    units_per_em = get_units_per_em(font_name)
    scale = char_size / units_per_em
    cursor_x = start_x
    cursor_y = start_y
    line_count = 1

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Chinese stroke text trail\n")
        f.write(f"# font_name={font_name}, style_name={style_name}, char_size={char_size}\n")
        f.write(f"# char_spacing={char_spacing}, line_spacing={line_spacing}\n")
        f.write(f"# auto_wrap={auto_wrap}, max_line_width={max_line_width}\n")

        for ch in text:
            if ch == "\n":
                cursor_x = start_x
                cursor_y -= line_spacing
                line_count += 1
                continue

            if ch == " ":
                space_advance = char_size * space_advance_ratio + char_spacing
                if (
                    auto_wrap
                    and max_line_width is not None
                    and cursor_x > start_x
                    and (cursor_x - start_x + space_advance) > max_line_width
                ):
                    cursor_x = start_x
                    cursor_y -= line_spacing
                    line_count += 1
                else:
                    cursor_x += space_advance
                continue

            glyph = transform_glyph(
                get_glyph_with_fallback(font_name, ch),
                style_name=style_name,
            )
            glyph_advance = glyph.advance * scale + char_spacing

            if (
                auto_wrap
                and max_line_width is not None
                and cursor_x > start_x
                and (cursor_x - start_x + glyph_advance) > max_line_width
            ):
                cursor_x = start_x
                cursor_y -= line_spacing
                line_count += 1

            for stroke in glyph.strokes:
                if len(stroke) < 2:
                    continue

                first_x = cursor_x + stroke[0][0] * scale
                first_y = cursor_y + stroke[0][1] * scale
                f.write(f"{first_x:.4f} {first_y:.4f} 33\n")
                f.write(f"{first_x:.4f} {first_y:.4f} -33\n")

                for x, y in stroke[1:]:
                    stroke_x = cursor_x + x * scale
                    stroke_y = cursor_y + y * scale
                    f.write(f"{stroke_x:.4f} {stroke_y:.4f} 0\n")

                last_x = cursor_x + stroke[-1][0] * scale
                last_y = cursor_y + stroke[-1][1] * scale
                f.write(f"{last_x:.4f} {last_y:.4f} 33\n")

            cursor_x += glyph_advance

    return output_file, line_count


def compensate_vertical_tilt(
    x_img,
    y_img,
    y_center=VERTICAL_TILT_CENTER,
    tilt_factor=VERTICAL_TILT_FACTOR,
):
    corrected_x_img = x_img + tilt_factor * (y_img - y_center)
    corrected_y_img = y_img
    return corrected_x_img, corrected_y_img


def chinese_point_to_robot_world(
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
    x_img, y_img = compensate_vertical_tilt(x_img, y_img)
    p = [140.0 - x_img * image_size, 140.0 - y_img * image_size]

    if z_code == 0:
        z_robot = last_z
    elif z_code < 0:
        z_robot = write_h
    else:
        z_robot = write_h + dh / 1000.0

    vertical_world = (x0 + p[1]) / 1000.0
    horizontal_world = (y0 - p[0]) / 1000.0
    vertical_world = vertical_world + HORIZONTAL_TILT_FACTOR * (
        horizontal_world - HORIZONTAL_TILT_CENTER
    )

    return horizontal_world, vertical_world, z_robot, z_robot


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

            robot_x, robot_y, robot_z, last_z = chinese_point_to_robot_world(
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


def print_motion_range(data):
    if not data:
        print("No motion data generated.")
        return

    xs = [point[0] for point in data]
    ys = [point[1] for point in data]
    zs = [point[2] for point in data]

    print(f"x range: {min(xs):.4f} .. {max(xs):.4f}")
    print(f"y range: {min(ys):.4f} .. {max(ys):.4f}")
    print(f"z range: {min(zs):.4f} .. {max(zs):.4f}")


def suggest_position_fix(data, bounds):
    if not data:
        return

    xs = [point[0] for point in data]
    ys = [point[1] for point in data]

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


def draw_chinese_text_with_robot(
    text,
    output_file="./output/text_trail_chinese.txt",
    font_name=DEFAULT_FONT_NAME,
    style_name=SUPPORTED_CHINESE_STYLE_NAME,
    start_x=10.0,
    start_y=70.0,
    char_size=9.0,
    char_spacing=2.0,
    line_spacing=14.0,
    x0=300.0,
    y0=-200.0,
    write_h=0.623,
    dh=50.0,
    image_size=1.5,
    speed=1,
    dry_run=False,
    auto_import_missing=True,
    auto_wrap=True,
    max_line_width=None,
):
    font_name = require_supported_chinese_font(font_name)
    style_name = require_supported_chinese_style(style_name)
    get_style_profile(style_name)

    if auto_import_missing:
        imported, skipped = auto_import_missing_chinese_glyphs(
            text=text,
            font_name=font_name,
            skip_missing=True,
        )
        if imported:
            print(f"Auto-imported glyphs for font '{font_name}': {''.join(imported)}")
        if skipped:
            print(f"Could not auto-import glyphs for font '{font_name}': {''.join(skipped)}")

    unsupported = validate_chinese_text(text, font_name)
    if unsupported:
        raise ValueError(
            "These Chinese characters are not available in the selected font: "
            + " ".join(unsupported)
        )

    bounds = SafetyBounds(
        x_min=-0.35,
        x_max=-0.15,
        y_min=0.30,
        y_max=0.478,
        z_min=write_h - 0.01,
        z_max=write_h + dh / 1000.0 + 0.01,
    )

    if auto_wrap and max_line_width is None:
        max_line_width = compute_default_max_line_width(
            start_x=start_x,
            y0=y0,
            image_size=image_size,
            bounds=bounds,
        )

    _, line_count = create_chinese_text_file(
            text=text,
            output_file=output_file,
            font_name=font_name,
            style_name=style_name,
            start_x=start_x,
            start_y=start_y,
            char_size=char_size,
            char_spacing=char_spacing,
            line_spacing=line_spacing,
            auto_wrap=auto_wrap,
            max_line_width=max_line_width,
        )

    data = read_trail_and_convert_to_robot(
        output_file=output_file,
        x0=x0,
        y0=y0,
        write_h=write_h,
        dh=dh,
        image_size=image_size,
    )

    print(f"font_name = {font_name}")
    print(f"style_name = {style_name}")
    print(f"VERTICAL_TILT_FACTOR = {VERTICAL_TILT_FACTOR}")
    print(f"HORIZONTAL_TILT_FACTOR = {HORIZONTAL_TILT_FACTOR}")
    print(f"x0 = {x0}, y0 = {y0}, image_size = {image_size}")
    if auto_wrap:
        print(f"auto_wrap = True, max_line_width = {max_line_width:.2f}, line_count = {line_count}")
    print_motion_range(data)

    try:
        for robot_x, robot_y, robot_z in data:
            check_position_or_raise(robot_x, robot_y, robot_z, bounds)
    except ValueError:
        suggest_position_fix(data, bounds)
        raise

    if dry_run:
        print("DRY RUN OK: safety check passed. Robot was not moved.")
        return True

    from arm_trigger.mode_intf.xarm_interface import XarmInterface

    uarm_interface = XarmInterface()
    if not uarm_interface.connect():
        print("Failed to connect to robot")
        return False

    print(f"Drawing Chinese text '{text}' with {len(data)} points...")
    for robot_x, robot_y, robot_z in tqdm(data):
        check_position_or_raise(robot_x, robot_y, robot_z, bounds)
        uarm_interface.set_position(x=robot_x, y=robot_y, z=robot_z, speed=speed, wait=True)

    print("Chinese text drawing finished.")
    return True


if __name__ == "__main__":
    draw_chinese_text_with_robot(
        "你好",
        output_file="./output/text_trail_chinese.txt",
        font_name=DEFAULT_FONT_NAME,
        start_x=10.0,
        start_y=70.0,
        char_size=9.0,
        char_spacing=2.0,
        line_spacing=14.0,
        x0=290.0,
        y0=-220.0,
        write_h=0.623,
        dh=50.0,
        image_size=1.5,
        speed=1,
        dry_run=True,
        auto_import_missing=True,
        auto_wrap=True,
    )
