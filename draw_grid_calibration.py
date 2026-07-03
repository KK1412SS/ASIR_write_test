from shutil import copyfile
import numpy as np
from tqdm import tqdm
import json

output_file = './output/grid_calibration.txt'

# =========================
# KALIBRIER-PARAMETER
# =========================

GRID_SIZE = 4
GRID_SPACING = 70

DX = 10
DY = 70
F = 0.08

X0 = 370.0
Y0 = -180.0

WRITE_H = 0.623
DH = 50.0

IMAGE_SIZE = 1.5

VERTICAL_TILT_ENABLED = True
VERTICAL_TILT_FACTOR = -0.12 # to be changed, also in write_words.py
VERTICAL_TILT_CENTER = 70.0

HORIZONTAL_TILT_ENABLED = True
HORIZONTAL_TILT_FACTOR = -0.06 # to be changed, also in write_words.py
HORIZONTAL_TILT_CENTER = (-0.35 + -0.15) / 2.0

GLOBAL_SPEED = 1


# Import Roboter-Interface
from arm_trigger.mode_intf.xarm_interface import XarmInterface
uarm_interface = XarmInterface()
if_connect = uarm_interface.connect()

print(f"Roboter verbunden: {if_connect}")


def generate_grid(grid_size=10, spacing=30):
    """
    Generate a calibration grid with horizontal and vertical lines.
    """
    grid_lines = []

    # Horizontal lines
    for i in range(grid_size):
        y = i * spacing
        line_points = []
        for x in range(0, grid_size * spacing + 1, spacing // 2):
            line_points.append((x, y))
        grid_lines.append(line_points)

    # Vertical lines
    for i in range(grid_size):
        x = i * spacing
        line_points = []
        for y in range(0, grid_size * spacing + 1, spacing // 2):
            line_points.append((x, y))
        grid_lines.append(line_points)

    return grid_lines


def create_grid_file(grid_size=10, spacing=30):
    """Create grid calibration file with coordinate data."""
    grid_lines = generate_grid(grid_size, spacing)

    with open(output_file, 'w') as file_out:
        for line in grid_lines:
            if len(line) == 0:
                continue

            # Start point: pen down
            file_out.write(f"{line[0][0] * F + DX} {line[0][1] * F + DY} -33\n")

            # Draw line points
            for p in line[1:]:
                file_out.write(f"{p[0] * F + DX} {p[1] * F + DY} 0\n")

            # End point: pen up
            file_out.write(f"{line[-1][0] * F + DX} {line[-1][1] * F + DY} 33\n")

    print(f"Grid-Datei erstellt: {output_file}")


def compensate_vertical_tilt(x_img, y_img):
    """
    Korrigiert vertikale Neigung in der Bild-/Trajectory-Ebene.

    Wichtig bei deinem Mapping:
    x_img beeinflusst später stärker hoch/runter auf Papier.
    """
    if not VERTICAL_TILT_ENABLED:
        return x_img, y_img

    corrected_x_img = x_img + VERTICAL_TILT_FACTOR * (y_img - VERTICAL_TILT_CENTER)
    corrected_y_img = y_img

    return corrected_x_img, corrected_y_img


def compensate_horizontal_tilt(x_robot, y_robot):
    """
    Korrigiert horizontale Neigung direkt in Roboter-Koordinaten.
    """
    if not HORIZONTAL_TILT_ENABLED:
        return x_robot, y_robot

    corrected_x_robot = x_robot + HORIZONTAL_TILT_FACTOR * (y_robot - HORIZONTAL_TILT_CENTER)
    corrected_y_robot = y_robot

    return corrected_x_robot, corrected_y_robot


def draw_grid_with_robot(grid_size=10, spacing=30):
    """Generate grid file and draw with robot arm."""

    trail_text = []

    create_grid_file(grid_size, spacing)

    last_z = WRITE_H + DH / 1000.0

    with open(output_file, 'r') as ff:
        file_org = ff.readlines()

    raw_p = []

    for l in file_org:
        d = l.split()

        x_img = float(d[0])
        y_img = float(d[1])
        z = float(d[2])

        # 1. Vertikale Tilt-Korrektur
        x_img, y_img = compensate_vertical_tilt(x_img, y_img)

        # 2. Bildkoordinaten zu Zwischenkoordinaten
        p = [
            140.0 - x_img * IMAGE_SIZE,
            140.0 - y_img * IMAGE_SIZE
        ]

        # 3. Z-Logik
        if z == 0:
            z = last_z
        elif z < 0:
            z = WRITE_H
        else:
            z = WRITE_H + DH / 1000.0

        last_z = z
        p.append(z)
        raw_p.append(p)

    # 4. Zwischenkoordinaten zu Roboterkoordinaten
    for i in range(len(raw_p)):
        x = X0 + raw_p[i][1]
        y = Y0 - raw_p[i][0]

        x = x / 1000.0
        y = y / 1000.0
        z = raw_p[i][2]

        # 5. Horizontale Tilt-Korrektur
        x, y = compensate_horizontal_tilt(x, y)

        trail_text.append([x, y, z])

    data = np.array(trail_text).reshape([-1, 3])

    print(f"Zeichne Grid mit {len(data)} Punkten...")
    print(f"VERTICAL_TILT_FACTOR   = {VERTICAL_TILT_FACTOR}")
    print(f"HORIZONTAL_TILT_FACTOR = {HORIZONTAL_TILT_FACTOR}")

    for i in tqdm(range(len(data))):
        y, x, z = data[i, :]
        uarm_interface.set_position(
            x=x,
            y=y,
            z=z,
            speed=GLOBAL_SPEED,
            wait=True
        )

    print("Grid zeichnen abgeschlossen!")
    return 1


if __name__ == "__main__":
    draw_grid_with_robot(
        grid_size=GRID_SIZE,
        spacing=GRID_SPACING
    )