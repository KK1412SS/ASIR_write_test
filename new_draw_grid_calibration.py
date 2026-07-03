
from shutil import copyfile
import numpy as np
from tqdm import tqdm
import json

output_file = './output/rectangle_calibration.txt'

# Import Roboter-Interface
from arm_trigger.mode_intf.xarm_interface import XarmInterface
uarm_interface = XarmInterface()
if_connect = uarm_interface.connect()
global_speed = 1
trail_text = []

print(f"Roboter verbunden: {if_connect}")


def generate_rectangle_a4(width=210, scale=0.5, step=10):
    """
    Generate a rectangular frame with A4 proportion (210:297), scaled down.

    Args:
        width: Base A4 width in arbitrary units
        scale: Scale factor to make rectangle smaller
        step: Distance between sampled points along the edges

    Returns:
        List of 4 line segments as coordinate points
    """
    rect_width = width * scale
    rect_height = rect_width * 297 / 210  # A4 proportion

    rectangle_lines = []

    # Top edge
    top_line = []
    for x in np.arange(0, rect_width + step, step):
        top_line.append((x, 0))
    rectangle_lines.append(top_line)

    # Right edge
    right_line = []
    for y in np.arange(0, rect_height + step, step):
        right_line.append((rect_width, y))
    rectangle_lines.append(right_line)

    # Bottom edge
    bottom_line = []
    for x in np.arange(rect_width, -step, -step):
        bottom_line.append((x, rect_height))
    rectangle_lines.append(bottom_line)

    # Left edge
    left_line = []
    for y in np.arange(rect_height, -step, -step):
        left_line.append((0, y))
    rectangle_lines.append(left_line)

    return rectangle_lines


def create_rectangle_file(file_path, width=210, scale=0.5, step=10):
    """Create rectangle calibration file with coordinate data."""
    rectangle_lines = generate_rectangle_a4(width, scale, step)

    file_out = open(output_file, 'w')

    # Transformation parameters
    dx = 10
    dy = 70
    f = 0.08

    for line in rectangle_lines:
        if len(line) == 0:
            continue

        # Start point with pen down/up logic as in your original code
        file_out.write(f"{line[0][0]*f+dx} {line[0][1]*f+dy} -33\n")

        for p in line[1:]:
            file_out.write(f"{p[0]*f+dx} {p[1]*f+dy} 0\n")

        file_out.write(f"{line[-1][0]*f+dx} {line[-1][1]*f+dy} 33\n")

    file_out.close()
    print(f"Rechteck-Datei erstellt: {output_file}")


def draw_rectangle_with_robot(file_path, width=210, scale=0.5, step=10):
    """Generate rectangle file and draw with robot arm."""
    global trail_text
    trail_text = []  # wichtig, damit alte Punkte nicht drin bleiben

    create_rectangle_file(file_path, width, scale, step)

    dh = 50.
    x0 = 410.   # Basis Position
    y0 = -210.
    write_h = 0.623
    last_z = write_h + dh / 1000
    image_size = 1.5

    with open(output_file, 'r') as ff:
        file_org = ff.readlines()
        raw_p = []

        for l in file_org:
            d = l.split(' ')

            p = [140.0 - float(d[0]) * image_size, 140.0 - float(d[1]) * image_size]
            z = float(d[2])

            if z == 0:
                z = last_z
            elif z < 0:
                z = write_h
            else:
                z = write_h + dh / 1000
            last_z = z
            p.append(z)
            raw_p.append(p)

        # Convert to world coordinates
        for i in range(len(raw_p)):
            x = x0 + raw_p[i][1]
            y = y0 - raw_p[i][0]
            x = x * 1.0 / 1000
            y = y * 1.0 / 1000
            z = raw_p[i][2]
            trail_text.append([x, y, z])

    data = np.array(trail_text)
    data = data.reshape([-1, 3])

    print(f"Zeichne Rechteck mit {len(data)} Punkten...")
    for i in tqdm(list(range(len(data)))):
        y, x, z = data[i, :]
        uarm_interface.set_position(x=x, y=y, z=z, speed=global_speed, wait=True)

    print("Rechteck zeichnen abgeschlossen!")
    return 1


if __name__ == "__main__":
    # Beispiel: kleiner A4-Rahmen
    draw_rectangle_with_robot("results/test.txt", width=210, scale=0.6, step=10)