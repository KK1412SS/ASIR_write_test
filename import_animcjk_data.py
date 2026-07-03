import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from chinese_font_provider import clear_font_cache


SOURCE_VARIANTS = {
    "zhhans": {
        "folder": "svgsZhHans",
        "font_name": "animcjk_zhhans",
        "display_name": "AnimCJK Simplified Chinese",
        "description": (
            "Imported from AnimCJK simplified Chinese SVG median paths. "
            "Uses language-specific stroke medians and stroke order."
        ),
    },
    "zhhant": {
        "folder": "svgsZhHant",
        "font_name": "animcjk_zhhant",
        "display_name": "AnimCJK Traditional Chinese",
        "description": (
            "Imported from AnimCJK traditional Chinese SVG median paths. "
            "Uses language-specific stroke medians and stroke order."
        ),
    },
}

SOURCE_URL_TEMPLATES = [
    "https://raw.githubusercontent.com/parsimonhi/animCJK/master/{folder}/{codepoint}.svg",
    "https://cdn.jsdelivr.net/gh/parsimonhi/animCJK@master/{folder}/{codepoint}.svg",
]

FONT_DIR = Path(__file__).resolve().parent / "fonts" / "chinese"
DEFAULT_FONT_PATHS = {
    variant_name: FONT_DIR / f"{variant['font_name']}.json"
    for variant_name, variant in SOURCE_VARIANTS.items()
}

TOKEN_RE = re.compile(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")


def distance(point_a, point_b):
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def perpendicular_distance(point, line_start, line_end):
    if line_start == line_end:
        return distance(point, line_start)

    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    numerator = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    denominator = math.hypot(y2 - y1, x2 - x1)
    return numerator / denominator


def rdp(points, epsilon):
    if len(points) < 3:
        return points

    start = points[0]
    end = points[-1]
    max_distance = -1.0
    split_index = -1

    for index in range(1, len(points) - 1):
        candidate_distance = perpendicular_distance(points[index], start, end)
        if candidate_distance > max_distance:
            max_distance = candidate_distance
            split_index = index

    if max_distance <= epsilon:
        return [start, end]

    left = rdp(points[: split_index + 1], epsilon)
    right = rdp(points[split_index:], epsilon)
    return left[:-1] + right


def collapse_close_points(points, min_distance):
    if not points:
        return []

    collapsed = [points[0]]
    for point in points[1:]:
        if distance(point, collapsed[-1]) >= min_distance:
            collapsed.append(point)

    if collapsed[-1] != points[-1]:
        collapsed.append(points[-1])
    return collapsed


def simplify_stroke(points, min_distance, epsilon):
    normalized = collapse_close_points(points, min_distance=min_distance)
    normalized = rdp(normalized, epsilon=epsilon)
    if len(normalized) == 1:
        normalized.append(normalized[0])
    return normalized


def cubic_bezier(p0, p1, p2, p3, t):
    mt = 1.0 - t
    return (
        mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0],
        mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1],
    )


def quadratic_bezier(p0, p1, p2, t):
    mt = 1.0 - t
    return (
        mt ** 2 * p0[0] + 2 * mt * t * p1[0] + t ** 2 * p2[0],
        mt ** 2 * p0[1] + 2 * mt * t * p1[1] + t ** 2 * p2[1],
    )


def sample_svg_path(path_d, curve_steps=12):
    tokens = TOKEN_RE.findall(path_d)
    if not tokens:
        return []

    index = 0
    command = None
    current = (0.0, 0.0)
    start_point = None
    last_cubic_control = None
    last_quadratic_control = None
    points = []

    def read_number():
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def read_point(relative):
        x = read_number()
        y = read_number()
        if relative:
            return current[0] + x, current[1] + y
        return x, y

    while index < len(tokens):
        token = tokens[index]
        if re.fullmatch(r"[A-Za-z]", token):
            command = token
            index += 1
        elif command is None:
            raise ValueError(f"SVG path data starts without a command: {path_d[:80]}")

        absolute = command.upper()
        relative = command.islower()

        if absolute == "M":
            first = True
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                point = read_point(relative)
                current = point
                if first:
                    start_point = point
                    points.append(point)
                    first = False
                else:
                    points.append(point)
                command = "l" if relative else "L"
                absolute = "L"
            last_cubic_control = None
            last_quadratic_control = None
            continue

        if absolute == "L":
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                point = read_point(relative)
                current = point
                points.append(point)
            last_cubic_control = None
            last_quadratic_control = None
            continue

        if absolute == "H":
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                x = read_number()
                current = (current[0] + x, current[1]) if relative else (x, current[1])
                points.append(current)
            last_cubic_control = None
            last_quadratic_control = None
            continue

        if absolute == "V":
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                y = read_number()
                current = (current[0], current[1] + y) if relative else (current[0], y)
                points.append(current)
            last_cubic_control = None
            last_quadratic_control = None
            continue

        if absolute == "C":
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                p0 = current
                c1 = read_point(relative)
                c2 = read_point(relative)
                p3 = read_point(relative)
                for step in range(1, curve_steps + 1):
                    points.append(cubic_bezier(p0, c1, c2, p3, step / curve_steps))
                current = p3
                last_cubic_control = c2
                last_quadratic_control = None
            continue

        if absolute == "S":
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                p0 = current
                if last_cubic_control is None:
                    c1 = current
                else:
                    c1 = (
                        2.0 * current[0] - last_cubic_control[0],
                        2.0 * current[1] - last_cubic_control[1],
                    )
                c2 = read_point(relative)
                p3 = read_point(relative)
                for step in range(1, curve_steps + 1):
                    points.append(cubic_bezier(p0, c1, c2, p3, step / curve_steps))
                current = p3
                last_cubic_control = c2
                last_quadratic_control = None
            continue

        if absolute == "Q":
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                p0 = current
                c1 = read_point(relative)
                p2 = read_point(relative)
                for step in range(1, curve_steps + 1):
                    points.append(quadratic_bezier(p0, c1, p2, step / curve_steps))
                current = p2
                last_quadratic_control = c1
                last_cubic_control = None
            continue

        if absolute == "T":
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                p0 = current
                if last_quadratic_control is None:
                    c1 = current
                else:
                    c1 = (
                        2.0 * current[0] - last_quadratic_control[0],
                        2.0 * current[1] - last_quadratic_control[1],
                    )
                p2 = read_point(relative)
                for step in range(1, curve_steps + 1):
                    points.append(quadratic_bezier(p0, c1, p2, step / curve_steps))
                current = p2
                last_quadratic_control = c1
                last_cubic_control = None
            continue

        if absolute == "A":
            while index < len(tokens) and not re.fullmatch(r"[A-Za-z]", tokens[index]):
                _rx = read_number()
                _ry = read_number()
                _rotation = read_number()
                _large_arc = read_number()
                _sweep = read_number()
                point = read_point(relative)
                current = point
                points.append(point)
            last_cubic_control = None
            last_quadratic_control = None
            continue

        if absolute == "Z":
            if start_point is not None and current != start_point:
                current = start_point
                points.append(current)
            last_cubic_control = None
            last_quadratic_control = None
            continue

        raise ValueError(f"Unsupported SVG path command '{command}' in: {path_d[:80]}")

    return [(float(x), float(y)) for x, y in points]


def load_or_create_font(font_path, variant_name):
    variant = SOURCE_VARIANTS[variant_name]
    if font_path.exists():
        with font_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "font_name": variant["font_name"],
        "display_name": variant["display_name"],
        "description": variant["description"],
        "units_per_em": 1024,
        "glyphs": {},
    }


def save_font(font_path, data):
    font_path.parent.mkdir(parents=True, exist_ok=True)
    with font_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    clear_font_cache()


def find_missing_chars(text, font_path, variant_name):
    font_data = load_or_create_font(font_path, variant_name)
    glyphs = font_data.setdefault("glyphs", {})

    missing = []
    seen = set()
    for char in text:
        if char in [" ", "\n", "\t"]:
            continue
        if char in seen:
            continue
        seen.add(char)
        if char not in glyphs:
            missing.append(char)

    return missing


def fetch_animcjk_svg(char, variant_name):
    variant = SOURCE_VARIANTS[variant_name]
    codepoint = ord(char)
    errors = []
    for template in SOURCE_URL_TEMPLATES:
        url = template.format(folder=variant["folder"], codepoint=codepoint)
        try:
            with urlopen(url, timeout=30) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            errors.append(f"{url} -> HTTP {exc.code}")
        except URLError as exc:
            errors.append(f"{url} -> {exc}")

    raise RuntimeError(
        f"Failed to fetch AnimCJK SVG for '{char}' ({variant_name}). Tried: "
        + "; ".join(errors)
    )


def glyph_from_animcjk_svg(char, svg_text, min_distance, epsilon, curve_steps):
    root = ET.fromstring(svg_text)
    median_paths = []
    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        if "clip-path" not in element.attrib:
            continue
        path_d = element.attrib.get("d", "").strip()
        if path_d:
            median_paths.append(path_d)

    if not median_paths:
        raise ValueError(f"No median paths found in AnimCJK SVG for character: {char}")

    strokes = []
    for path_d in median_paths:
        points = sample_svg_path(path_d, curve_steps=curve_steps)
        if len(points) < 2:
            continue
        simplified = simplify_stroke(points, min_distance=min_distance, epsilon=epsilon)
        strokes.append([[round(x, 3), round(y, 3)] for x, y in simplified])

    if not strokes:
        raise ValueError(f"No usable strokes extracted from AnimCJK SVG for character: {char}")

    return {
        "advance": 1024,
        "strokes": strokes,
        "source": "animcjk",
    }


def import_single_character(char, variant_name, min_distance, epsilon, curve_steps):
    svg_text = fetch_animcjk_svg(char, variant_name)
    glyph = glyph_from_animcjk_svg(
        char,
        svg_text,
        min_distance=min_distance,
        epsilon=epsilon,
        curve_steps=curve_steps,
    )
    return char, glyph


def import_text_to_font(
    text,
    font_path,
    variant_name,
    min_distance,
    epsilon,
    curve_steps,
    skip_missing,
    max_workers,
):
    unique_chars = []
    seen = set()
    for char in text:
        if char in [" ", "\n", "\t"]:
            continue
        if char in seen:
            continue
        seen.add(char)
        unique_chars.append(char)

    font_data = load_or_create_font(font_path, variant_name)
    glyphs = font_data.setdefault("glyphs", {})

    imported = []
    skipped = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_char = {
            executor.submit(
                import_single_character,
                char,
                variant_name,
                min_distance,
                epsilon,
                curve_steps,
            ): char
            for char in unique_chars
        }

        completed = {}
        for future in as_completed(future_to_char):
            char = future_to_char[future]
            try:
                imported_char, glyph = future.result()
                completed[imported_char] = glyph
            except Exception:
                if not skip_missing:
                    raise
                skipped.append(char)

    for char in unique_chars:
        glyph = completed.get(char)
        if glyph is None:
            continue
        glyphs[char] = glyph
        imported.append(char)

    save_font(font_path, font_data)
    return imported, skipped


def ensure_text_in_animcjk_font(
    text,
    variant_name="zhhans",
    font_path=None,
    min_distance=8.0,
    epsilon=4.0,
    curve_steps=12,
    skip_missing=True,
    max_workers=8,
):
    if variant_name not in SOURCE_VARIANTS:
        raise KeyError(f"Unknown AnimCJK variant: {variant_name}")

    if font_path is None:
        font_path = DEFAULT_FONT_PATHS[variant_name]
    font_path = Path(font_path).resolve()

    missing = find_missing_chars(text, font_path, variant_name)
    if not missing:
        return [], []

    return import_text_to_font(
        text="".join(missing),
        font_path=font_path,
        variant_name=variant_name,
        min_distance=min_distance,
        epsilon=epsilon,
        curve_steps=curve_steps,
        skip_missing=skip_missing,
        max_workers=max_workers,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import AnimCJK SVG median paths into the local Chinese font format."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--text",
        help="Characters to import. Spaces and newlines are ignored.",
    )
    source_group.add_argument(
        "--text-file",
        help="Path to a UTF-8 text file. Unique characters from the file will be imported.",
    )
    parser.add_argument(
        "--variant",
        choices=sorted(SOURCE_VARIANTS.keys()),
        default="zhhans",
        help="AnimCJK source variant.",
    )
    parser.add_argument(
        "--font-path",
        help="Target JSON font file. Defaults to the variant-specific file in fonts/chinese.",
    )
    parser.add_argument(
        "--min-distance",
        type=float,
        default=8.0,
        help="Minimum point spacing during simplification in source coordinate units.",
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        default=4.0,
        help="Ramer-Douglas-Peucker epsilon in source coordinate units.",
    )
    parser.add_argument(
        "--curve-steps",
        type=int,
        default=12,
        help="Number of samples for each bezier segment in a median path.",
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip characters that cannot be fetched instead of stopping the import.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Number of parallel downloads during bulk import.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.text is not None:
        text = args.text
    else:
        text = Path(args.text_file).read_text(encoding="utf-8")

    font_path = (
        Path(args.font_path).expanduser()
        if args.font_path
        else DEFAULT_FONT_PATHS[args.variant]
    )

    imported, skipped = ensure_text_in_animcjk_font(
        text=text,
        variant_name=args.variant,
        font_path=font_path,
        min_distance=args.min_distance,
        epsilon=args.epsilon,
        curve_steps=args.curve_steps,
        skip_missing=args.skip_missing,
        max_workers=args.max_workers,
    )

    print(f"Imported {len(imported)} character(s) into {font_path}.")
    if imported:
        print("Imported:", "".join(imported))
    if skipped:
        print("Skipped:", "".join(skipped))


if __name__ == "__main__":
    main()
