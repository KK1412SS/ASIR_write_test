# stroke_text_generator.py
from HersheyFonts import HersheyFonts
import os
import math


def _dist(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _same_point(p1, p2, eps=0.001):
    return _dist(p1, p2) <= eps


def _connect_segments(segments, eps=0.001):
    """
    Verbindet Hershey-Liniensegmente zu längeren Strokes.
    Input:
        [((x1,y1),(x2,y2)), ...]
    Output:
        [[(x,y), (x,y), ...], ...]
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
            # direkt weiterzeichnen
            last_stroke.append(p2)
        elif _same_point(last_point, p2, eps):
            # Segment ist andersherum, also drehen
            last_stroke.append(p1)
        else:
            # neuer getrennter Stroke
            strokes.append([p1, p2])

    return strokes


def create_stroke_text_file(
    text,
    output_file="./output/text_trail.txt",
    font_name="futural",
    font_size=10,
    line_spacing=18,
    letter_spacing=1.0,
    start_x=10,
    start_y=70,
):
    """
    Single-Line-Text-Trajectory im alten trail.txt Format.

    z > 0 = pen up
    z < 0 = pen down

    Verbesserte Version:
    - verbindet zusammenhängende Font-Segmente
    - hebt den Stift nicht nach jedem Mini-Segment
    - schreibt längere Strokes flüssiger
    """

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    font = HersheyFonts()
    try:
        font.load_default_font(font_name)
    except Exception:
        print(f"⚠️ Font '{font_name}' nicht gefunden. Nutze default font.")
        font.load_default_font()

    font.normalize_rendering(font_size)

    points = []
    cursor_y = start_y

    for line in text.split("\n"):
        if line.strip() == "":
            cursor_y -= line_spacing
            continue

        raw_segments = list(font.lines_for_text(line))

        # Segmente zuerst in deine Textkoordinaten bringen
        transformed_segments = []
        for (x1, y1), (x2, y2) in raw_segments:
            p1 = (start_x + x1 * letter_spacing, cursor_y + y1)
            p2 = (start_x + x2 * letter_spacing, cursor_y + y2)
            transformed_segments.append((p1, p2))

        strokes = _connect_segments(transformed_segments)

        for stroke in strokes:
            if len(stroke) < 2:
                continue

            first_x, first_y = stroke[0]

            # 1. Zum Startpunkt mit Stift oben
            points.append((first_x, first_y, 33))

            # 2. Stift runter
            points.append((first_x, first_y, -33))

            # 3. Alle Punkte im Stroke mit Stift unten zeichnen
            for x, y in stroke[1:]:
                points.append((x, y, -33))

            # 4. Am Ende Stift hoch
            last_x, last_y = stroke[-1]
            points.append((last_x, last_y, 33))

        cursor_y -= line_spacing

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Stroke text trail\n")
        for x, y, z in points:
            f.write(f"{x:.4f} {y:.4f} {z}\n")

    print(f"✅ Stroke text trajectory saved to: {output_file}")
    print(f"✅ Points: {len(points)}")
    print(f"✅ Font: {font_name}, font_size={font_size}")

    return output_file