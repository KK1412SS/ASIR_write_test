import os
from typing import List, Tuple

import numpy as np
from tqdm import tqdm

from robot_safety import (
    connect_robot,
    emergency_stop_robot,
    get_robot_interface,
    get_robot_position,
    reset_stop_flag,
    restore_stop_handlers,
    setup_stop_handlers,
    stop_requested,
)

output_file = './output/grid_calibration.txt'
global_speed = 1

# ----------------------------
# Blatt-/Zeichenbereich-Konfig
# ----------------------------
A4_W_MM = 210.0
A4_H_MM = 297.0
MARGIN_LEFT_MM = 30.0
MARGIN_RIGHT_MM = 30.0
MARGIN_TOP_MM = 30.0
TOP_FRACTION = 0.75

X_MIN_MM = MARGIN_LEFT_MM
X_MAX_MM = A4_W_MM - MARGIN_RIGHT_MM
Y_MIN_MM = MARGIN_TOP_MM
Y_MAX_MM = A4_H_MM * TOP_FRACTION

# Robot-Basisparameter
ROBOT_X0_MM = 300.0
ROBOT_Y0_MM = -200.0
WRITE_H_M = 0.623
PEN_LIFT_MM = 15.0


def ensure_output_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def clamp_to_allowed_box(x: float, y: float) -> Tuple[float, float]:
    x = max(X_MIN_MM, min(x, X_MAX_MM))
    y = max(Y_MIN_MM, min(y, Y_MAX_MM))
    return x, y


def fit_points_to_a4_top_area(points: List[Tuple[float, float]]):
    """
    Passt beliebige Rohpunkte in die feste Zeichenfläche ein:
    - A4 Hochformat
    - links/rechts/oben je 30 mm Rand
    - nur oberes 3/4 des Blatts
    """
    if not points:
        raise ValueError("Keine Punkte zum Einpassen gefunden.")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    draw_w = max_x - min_x
    draw_h = max_y - min_y

    if draw_w <= 0 or draw_h <= 0:
        raise ValueError(
            f"Ungültige Zeichnungsgröße: draw_w={draw_w}, draw_h={draw_h}"
        )

    usable_w = X_MAX_MM - X_MIN_MM
    usable_h = Y_MAX_MM - Y_MIN_MM
    scale = min(usable_w / draw_w, usable_h / draw_h)

    fitted_w = draw_w * scale
    fitted_h = draw_h * scale

    offset_x = X_MIN_MM + (usable_w - fitted_w) / 2.0
    offset_y = Y_MIN_MM + (usable_h - fitted_h) / 2.0

    fitted = []
    for x, y in points:
        x_new = (x - min_x) * scale + offset_x
        y_new = (y - min_y) * scale + offset_y
        x_new, y_new = clamp_to_allowed_box(x_new, y_new)
        fitted.append((x_new, y_new))

    info = {
        'scale': scale,
        'draw_w': draw_w,
        'draw_h': draw_h,
        'usable_w': usable_w,
        'usable_h': usable_h,
        'x_min': X_MIN_MM,
        'x_max': X_MAX_MM,
        'y_min': Y_MIN_MM,
        'y_max': Y_MAX_MM,
        'offset_x': offset_x,
        'offset_y': offset_y,
    }
    return fitted, info


def generate_grid(grid_size: int = 10, spacing: int = 30):
    """
    Generate a calibration grid with horizontal and vertical lines.

    Args:
        grid_size: Number of lines in each direction
        spacing: Spacing between lines in raw grid units

    Returns:
        List of line segments as coordinate points
    """
    grid_lines = []

    # Horizontal lines
    for i in range(grid_size):
        y = i * spacing
        line_points = []
        step = max(1, spacing // 2)
        for x in range(0, grid_size * spacing + 1, step):
            line_points.append((float(x), float(y)))
        grid_lines.append(line_points)

    # Vertical lines
    for i in range(grid_size):
        x = i * spacing
        line_points = []
        step = max(1, spacing // 2)
        for y in range(0, grid_size * spacing + 1, step):
            line_points.append((float(x), float(y)))
        grid_lines.append(line_points)

    return grid_lines


def create_grid_file(file_path: str, grid_size: int = 10, spacing: int = 30):
    """Create grid calibration file with coordinates already fitted to the allowed A4 area."""
    del file_path  # wird aktuell nicht verwendet, wir schreiben direkt output_file
    ensure_output_dir(output_file)

    grid_lines = generate_grid(grid_size, spacing)

    all_points: List[Tuple[float, float]] = []
    for line in grid_lines:
        all_points.extend(line)

    fitted_points, info = fit_points_to_a4_top_area(all_points)

    print("=== FIT INFO ===")
    for k, v in info.items():
        print(f"{k}: {v}")

    fitted_lines = []
    idx = 0
    for line in grid_lines:
        new_line = []
        for _ in line:
            new_line.append(fitted_points[idx])
            idx += 1
        fitted_lines.append(new_line)

    with open(output_file, 'w', encoding='utf-8') as file_out:
        for line in fitted_lines:
            if not line:
                continue

            start_x, start_y = clamp_to_allowed_box(*line[0])
            file_out.write(f"{start_x:.3f} {start_y:.3f} -33\n")

            for p in line[1:]:
                x_mm, y_mm = clamp_to_allowed_box(float(p[0]), float(p[1]))
                file_out.write(f"{x_mm:.3f} {y_mm:.3f} 0\n")

            end_x, end_y = clamp_to_allowed_box(*line[-1])
            file_out.write(f"{end_x:.3f} {end_y:.3f} 33\n")

    print(f"Grid-Datei erstellt: {output_file}")


def paper_point_to_robot_pose(paper_x_mm: float, paper_y_mm: float, z_code: float, last_z: float):
    """
    Papierkoordinaten (mm) -> Roboterkoordinaten (m).
    Bestehende Achsenlogik wird beibehalten:
      robot_x_mm = ROBOT_X0_MM + paper_y_mm
      robot_y_mm = ROBOT_Y0_MM - paper_x_mm
    """
    paper_x_mm, paper_y_mm = clamp_to_allowed_box(paper_x_mm, paper_y_mm)

    if z_code == 0:
        z_m = last_z
    elif z_code < 0:
        z_m = WRITE_H_M
    else:
        z_m = WRITE_H_M + PEN_LIFT_MM / 1000.0

    robot_x_mm = ROBOT_X0_MM + paper_y_mm
    robot_y_mm = ROBOT_Y0_MM - paper_x_mm

    robot_x_m = robot_x_mm / 1000.0
    robot_y_m = robot_y_mm / 1000.0

    return [robot_x_m, robot_y_m, z_m], z_m


def build_robot_trail(file_path: str):
    """
    Baut die Roboter-Trajektorie aus der Datei,
    ohne den Arm zu bewegen (Dry-Run).
    """
    trail = []
    last_z = WRITE_H_M + PEN_LIFT_MM / 1000.0

    with open(file_path, 'r', encoding='utf-8') as ff:
        for line in ff:
            d = line.strip().split()
            if len(d) < 3:
                continue

            paper_x_mm = float(d[0])
            paper_y_mm = float(d[1])
            z_code = float(d[2])

            pose, last_z = paper_point_to_robot_pose(
                paper_x_mm=paper_x_mm,
                paper_y_mm=paper_y_mm,
                z_code=z_code,
                last_z=last_z,
            )
            trail.append(pose)

    trail_np = np.array(trail, dtype=float).reshape([-1, 3])

    print("=== DRY RUN INFO ===")
    print(f"Anzahl Punkte: {len(trail_np)}")
    print("Erste 5 Punkte:")
    print(trail_np[:5])

    return trail_np


def draw_grid_with_robot(file_path: str, grid_size: int = 10, spacing: int = 30):
    """Generate grid file and draw with robot arm."""
    reset_stop_flag()
    connect_robot()
    create_grid_file(file_path, grid_size, spacing)

    trail_text = []
    last_z = WRITE_H_M + PEN_LIFT_MM / 1000.0

    with open(output_file, 'r', encoding='utf-8') as ff:
        for line in ff:
            d = line.strip().split()
            if len(d) < 3:
                continue

            paper_x_mm = float(d[0])
            paper_y_mm = float(d[1])
            z_code = float(d[2])

            pose, last_z = paper_point_to_robot_pose(
                paper_x_mm=paper_x_mm,
                paper_y_mm=paper_y_mm,
                z_code=z_code,
                last_z=last_z,
            )
            trail_text.append(pose)

    data = np.array(trail_text, dtype=float).reshape([-1, 3])

    print(f"Zeichne Grid mit {len(data)} Punkten...")
    print("Not-Stopp: Gib im Terminal 'q' ein und drücke Enter.")

    old_handler, _listener_thread = setup_stop_handlers()
    robot = get_robot_interface()

    try:
        for i in tqdm(range(len(data))):
            if stop_requested():
                pos = emergency_stop_robot()
                print("❌ Zeichnen durch Not-Abbruch beendet.")
                print(f"Letzte bekannte Position: {pos}")
                return {
                    'status': 'aborted',
                    'position': pos,
                    'completed_points': i,
                    'total_points': len(data),
                }

            y, x, z = data[i, :]
            robot.set_position(x=x, y=y, z=z, speed=global_speed, wait=True)

        final_pos = get_robot_position()
        print("Grid zeichnen abgeschlossen!")
        print(f"Endposition: {final_pos}")
        return {
            'status': 'finished',
            'position': final_pos,
            'completed_points': len(data),
            'total_points': len(data),
        }

    except KeyboardInterrupt:
        pos = emergency_stop_robot()
        print("❌ Zeichnen durch KeyboardInterrupt beendet.")
        print(f"Letzte bekannte Position: {pos}")
        return {
            'status': 'aborted',
            'position': pos,
            'completed_points': None,
            'total_points': len(data),
        }

    finally:
        restore_stop_handlers(old_handler)


if __name__ == "__main__":
    # 1️⃣ Nur Grid erzeugen
    create_grid_file("results/test.txt", grid_size=10, spacing=30)

    # 2️⃣ Dry-Run: Trajektorie berechnen (ohne Roboter)
    trail = build_robot_trail(output_file)

    # 3️⃣ Echte Ausführung (nur wenn sicher!)
    # Während des echten Zeichnens kannst du im Terminal 'q' + Enter eingeben.
    # Dann wird ein Not-Abbruch versucht und die aktuelle Position ausgegeben.
    # Ctrl+C bleibt zusätzlich als Fallback erhalten.
    # draw_grid_with_robot("results/test.txt", grid_size=10, spacing=30)
