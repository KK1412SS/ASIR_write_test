from shutil import copyfile
import numpy as np
from tqdm import tqdm
import os

from arm_trigger.mode_intf.xarm_interface import XarmInterface
from robot_safety import SafetyBounds, check_position_or_raise, find_first_invalid_position
# ----------------------------------------------------------------------
# Single‑stroke uppercase alphabet (A-Z)
# ----------------------------------------------------------------------
from letter_strokes import LETTER_STROKES, letter_width

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
# Draw text with robot (corrected)
# ----------------------------------------------------------------------
def draw_text_with_robot(text, output_file='./output/text_trail.txt',
                         start_x=10, start_y=70, scale=0.08, letter_spacing=15,
                         x0=300.0, y0=-200.0, write_h=0.623, dh=50.0, image_size=1.5,
                         speed=1):
    uarm_interface = XarmInterface()
    if not uarm_interface.connect():
        print("Failed to connect to robot")
        return False
    
    bounds = SafetyBounds(
        x_min=0.15,
        x_max=0.45,
        y_min=-0.35,
        y_max=0.05,
        z_min=write_h - 0.01,
        z_max=write_h + dh / 1000.0 + 0.01
    )

    # Generate trail file
    with open(output_file, 'w') as f:
        f.write("# Text trail\n")
    create_text_file(text, output_file, start_x, start_y, scale, letter_spacing)

    # Read and transform (same as grid code)
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
    for x_img, y_img, z_robot in trail_commands:
        x_world = (x0 + y_img) / 1000.0
        y_world = (y0 - x_img) / 1000.0
        z_world = z_robot
        data.append([x_world, y_world, z_world])

    print(f"Drawing '{text}' with {len(data)} points...")
    for i in tqdm(range(len(data))):
        y, x, z = data[i]
        uarm_interface.set_position(x=x, y=y, z=z, speed=speed, wait=True)

    print("Text drawing finished.")
    return True

# ----------------------------------------------------------------------
if __name__ == "__main__":
    draw_text_with_robot("Hello\nI am aisr\n from pku",
                         output_file='./output/text_trail.txt',
                         start_x=10, start_y=70, scale=0.08, letter_spacing=15,
                         x0=300.0, y0=-200.0, write_h=0.623, dh=50.0, image_size=1.5,
                         speed=1)