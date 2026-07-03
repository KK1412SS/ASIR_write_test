import math
from dataclasses import dataclass

from chinese_font_provider import ChineseGlyph


@dataclass(frozen=True)
class ChineseStyleProfile:
    name: str
    display_name: str
    description: str
    x_scale: float = 1.0
    y_scale: float = 1.0
    slant: float = 0.0
    sway: float = 0.0
    arch: float = 0.0
    end_flick: float = 0.0
    advance_scale: float = 1.0


STYLE_PROFILES = {
    "regular": ChineseStyleProfile(
        name="regular",
        display_name="Regular",
        description="Neutral stroke geometry based on the imported median paths.",
    ),
    "kaiti": ChineseStyleProfile(
        name="kaiti",
        display_name="KaiTi-like",
        description="Slightly taller, gently slanted, with more calligraphic stroke endings.",
        x_scale=0.98,
        y_scale=1.04,
        slant=-0.10,
        sway=0.018,
        arch=0.010,
        end_flick=22.0,
        advance_scale=1.01,
    ),
    "heiti": ChineseStyleProfile(
        name="heiti",
        display_name="HeiTi-like",
        description="More upright and wider, aiming for a firmer block-style appearance.",
        x_scale=1.06,
        y_scale=0.97,
        slant=0.0,
        sway=0.0,
        arch=0.0,
        end_flick=0.0,
        advance_scale=1.05,
    ),
    "songti": ChineseStyleProfile(
        name="songti",
        display_name="SongTi-like",
        description="More serif-like proportion with mild horizontal spread and lighter terminal flicks.",
        x_scale=1.02,
        y_scale=1.01,
        slant=0.03,
        sway=0.008,
        arch=0.004,
        end_flick=10.0,
        advance_scale=1.03,
    ),
}

DEFAULT_STYLE_NAME = "regular"


def list_style_names():
    return list(STYLE_PROFILES.keys())


def get_style_profile(style_name):
    if style_name not in STYLE_PROFILES:
        raise KeyError(f"Unknown Chinese style profile: {style_name}")
    return STYLE_PROFILES[style_name]


def get_style_metadata(style_name):
    profile = get_style_profile(style_name)
    return {
        "name": profile.name,
        "display_name": profile.display_name,
        "description": profile.description,
    }


def _collect_points(strokes):
    return [point for stroke in strokes for point in stroke]


def _transform_point(x, y, min_x, max_x, min_y, max_y, profile):
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    x_ratio = (x - min_x) / width
    y_ratio = (y - min_y) / height

    dx = (x - center_x) * profile.x_scale
    dy = (y - center_y) * profile.y_scale

    dx += (0.5 - y_ratio) * width * profile.slant
    dx += math.sin(math.pi * y_ratio) * width * profile.sway
    dy += math.sin(math.pi * x_ratio) * height * profile.arch

    return center_x + dx, center_y + dy


def _apply_end_flick(stroke, end_flick):
    if end_flick <= 0.0 or len(stroke) < 2:
        return stroke

    x1, y1 = stroke[-2]
    x2, y2 = stroke[-1]
    dx = x2 - x1
    dy = y2 - y1
    segment_length = math.hypot(dx, dy)
    if segment_length < 1e-6:
        return stroke

    extension_x = dx / segment_length * end_flick
    extension_y = dy / segment_length * end_flick
    return stroke[:-1] + ((x2 + extension_x, y2 + extension_y),)


def transform_glyph(glyph, style_name=DEFAULT_STYLE_NAME):
    profile = get_style_profile(style_name)
    if style_name == DEFAULT_STYLE_NAME:
        return glyph

    points = _collect_points(glyph.strokes)
    if not points:
        return glyph

    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    transformed_strokes = []
    for stroke in glyph.strokes:
        transformed = tuple(
            _transform_point(x, y, min_x, max_x, min_y, max_y, profile)
            for x, y in stroke
        )
        transformed = _apply_end_flick(transformed, profile.end_flick)
        transformed_strokes.append(transformed)

    return ChineseGlyph(
        advance=glyph.advance * profile.advance_scale,
        strokes=tuple(transformed_strokes),
    )
