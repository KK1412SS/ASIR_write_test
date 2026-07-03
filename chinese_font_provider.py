import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


FONT_DIR = Path(__file__).resolve().parent / "fonts" / "chinese"
FALLBACK_PUNCTUATION_FONTS = ("kaiti", "heiti")


@dataclass(frozen=True)
class ChineseGlyph:
    advance: float
    strokes: tuple


def _font_path(font_name):
    return FONT_DIR / f"{font_name}.json"


@lru_cache(maxsize=None)
def _load_font_data(font_name):
    font_path = _font_path(font_name)
    if not font_path.exists():
        raise FileNotFoundError(f"Chinese stroke font not found: {font_path}")

    with font_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "glyphs" not in data:
        raise ValueError(f"Invalid font file, missing 'glyphs': {font_path}")

    return data


def clear_font_cache():
    _load_font_data.cache_clear()


def list_fonts():
    return sorted(path.stem for path in FONT_DIR.glob("*.json"))


def get_font_metadata(font_name):
    data = _load_font_data(font_name)
    return {
        "font_name": data.get("font_name", font_name),
        "display_name": data.get("display_name", font_name),
        "description": data.get("description", ""),
        "units_per_em": data.get("units_per_em", 1000),
    }


def get_units_per_em(font_name):
    return get_font_metadata(font_name)["units_per_em"]


def list_supported_chars(font_name):
    data = _load_font_data(font_name)
    return list(data["glyphs"].keys())


def has_glyph(font_name, char):
    data = _load_font_data(font_name)
    return char in data["glyphs"]


def has_glyph_with_fallback(font_name, char, fallback_font_names=FALLBACK_PUNCTUATION_FONTS):
    if has_glyph(font_name, char):
        return True

    for fallback_font_name in fallback_font_names:
        if fallback_font_name == font_name:
            continue
        try:
            if has_glyph(fallback_font_name, char):
                return True
        except FileNotFoundError:
            continue

    return False


def get_glyph(font_name, char):
    data = _load_font_data(font_name)
    glyph_data = data["glyphs"].get(char)
    if glyph_data is None:
        raise KeyError(f"Character '{char}' is not available in font '{font_name}'")

    strokes = tuple(
        tuple((float(x), float(y)) for x, y in stroke)
        for stroke in glyph_data.get("strokes", [])
    )
    return ChineseGlyph(
        advance=float(glyph_data.get("advance", data.get("units_per_em", 1000))),
        strokes=strokes,
    )


def get_glyph_with_fallback(font_name, char, fallback_font_names=FALLBACK_PUNCTUATION_FONTS):
    try:
        return get_glyph(font_name, char)
    except KeyError:
        for fallback_font_name in fallback_font_names:
            if fallback_font_name == font_name:
                continue
            try:
                return get_glyph(fallback_font_name, char)
            except (FileNotFoundError, KeyError):
                continue
        raise
