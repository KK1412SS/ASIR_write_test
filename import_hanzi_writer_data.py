import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from chinese_font_provider import clear_font_cache


SOURCE_URLS = [
    "https://cdn.jsdelivr.net/npm/hanzi-writer-data@latest/{encoded}.json",
    "https://raw.githubusercontent.com/chanind/hanzi-writer-data/master/data/{encoded}.json",
]
DEFAULT_FONT_PATH = Path(__file__).resolve().parent / "fonts" / "chinese" / "hanziwriter.json"


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
    normalized = [(float(x), float(y)) for x, y in points]
    normalized = collapse_close_points(normalized, min_distance)
    normalized = rdp(normalized, epsilon)
    if len(normalized) == 1:
        normalized.append(normalized[0])
    return normalized


def fetch_character_data(char):
    encoded_char = quote(char)
    errors = []
    for template in SOURCE_URLS:
        url = template.format(encoded=encoded_char)
        try:
            with urlopen(url, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            errors.append(f"{url} -> HTTP {exc.code}")
        except URLError as exc:
            errors.append(f"{url} -> {exc}")

    raise RuntimeError(
        f"Failed to fetch character '{char}'. Tried: " + "; ".join(errors)
    )


def glyph_from_hanzi_writer(char, data, min_distance, epsilon):
    medians = data.get("medians")
    if not medians:
        raise ValueError(f"No medians present for character: {char}")

    strokes = []
    for stroke in medians:
        simplified = simplify_stroke(stroke, min_distance=min_distance, epsilon=epsilon)
        strokes.append([[round(x, 3), round(y, 3)] for x, y in simplified])

    return {
        "advance": 1024,
        "strokes": strokes,
        "source": "hanzi-writer-data",
    }


def import_single_character(char, min_distance, epsilon):
    character_data = fetch_character_data(char)
    glyph = glyph_from_hanzi_writer(
        char,
        character_data,
        min_distance=min_distance,
        epsilon=epsilon,
    )
    return char, glyph


def load_or_create_font(font_path):
    if font_path.exists():
        with font_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "font_name": "hanziwriter",
        "display_name": "Hanzi Writer Median",
        "description": (
            "Imported from hanzi-writer-data. Uses median paths in proper stroke order, "
            "simplified for robot trajectory output."
        ),
        "units_per_em": 1024,
        "glyphs": {},
    }


def find_missing_chars(text, font_path):
    font_data = load_or_create_font(font_path)
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


def save_font(font_path, data):
    font_path.parent.mkdir(parents=True, exist_ok=True)
    with font_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    clear_font_cache()


def import_text_to_font(text, font_path, min_distance, epsilon, skip_missing, max_workers):
    unique_chars = []
    seen = set()
    for char in text:
        if char in [" ", "\n", "\t"]:
            continue
        if char in seen:
            continue
        seen.add(char)
        unique_chars.append(char)

    font_data = load_or_create_font(font_path)
    glyphs = font_data.setdefault("glyphs", {})

    imported = []
    skipped = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_char = {
            executor.submit(import_single_character, char, min_distance, epsilon): char
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


def ensure_text_in_font(
    text,
    font_path=DEFAULT_FONT_PATH,
    min_distance=8.0,
    epsilon=6.0,
    skip_missing=True,
    max_workers=8,
):
    font_path = Path(font_path).resolve()
    missing = find_missing_chars(text, font_path)
    if not missing:
        return [], []

    return import_text_to_font(
        text="".join(missing),
        font_path=font_path,
        min_distance=min_distance,
        epsilon=epsilon,
        skip_missing=skip_missing,
        max_workers=max_workers,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import Hanzi Writer median stroke data into the local Chinese font format."
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
        "--font-path",
        default=str(DEFAULT_FONT_PATH),
        help="Target JSON font file. Defaults to fonts/chinese/hanziwriter.json",
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
        default=6.0,
        help="Ramer-Douglas-Peucker epsilon in source coordinate units.",
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
    font_path = Path(args.font_path).resolve()
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        text = args.text

    imported, skipped = import_text_to_font(
        text=text,
        font_path=font_path,
        min_distance=args.min_distance,
        epsilon=args.epsilon,
        skip_missing=args.skip_missing,
        max_workers=args.max_workers,
    )
    print(f"Imported {len(imported)} characters into {font_path}")
    print("Characters:", "".join(imported))
    if skipped:
        print(f"Skipped {len(skipped)} characters:", "".join(skipped))


if __name__ == "__main__":
    main()
