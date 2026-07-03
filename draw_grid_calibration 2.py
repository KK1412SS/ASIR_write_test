from shutil import copyfile
import numpy as np
from tqdm import tqdm
import json

output_file = './output/grid_calibration.txt'

# Import Roboter-Interface
from arm_trigger.mode_intf.xarm_interface import XarmInterface
uarm_interface = XarmInterface()
if_connect = uarm_interface.connect()
global_speed = 1
trail_text = []

print(f"Roboter verbunden: {if_connect}")

def generate_grid(grid_size=10, spacing=30):
    """
    Generate a calibration grid with horizontal and vertical lines.
    
    Args:
        grid_size: Number of lines in each direction
        spacing: Spacing between lines in pixels
    
    Returns:
        List of line segments as coordinate points
    """
    grid_lines = []
    
    # Generate horizontal lines
    for i in range(grid_size):
        y = i * spacing
        line_points = []
        for x in range(0, grid_size * spacing + 1, spacing // 2):
            line_points.append((x, y))
        grid_lines.append(line_points)
    
    # Generate vertical lines
    for i in range(grid_size):
        x = i * spacing
        line_points = []
        for y in range(0, grid_size * spacing + 1, spacing // 2):
            line_points.append((x, y))
        grid_lines.append(line_points)
    
    return grid_lines


def create_grid_file(file_path, grid_size=10, spacing=30):
    """Create grid calibration file with coordinate data."""
    grid_lines = generate_grid(grid_size, spacing)
    
    # Neue Datei mit Grid-Punkten schreiben (nicht alte Datei kopieren)
    file_out = open(output_file, 'w')
    
    # Transformation parameters
    dx = 10
    dy = 70
    f = 0.08
    
    for line in grid_lines:
        if len(line) == 0:
            continue
            
        # Start point with pen up (z = -33)
        file_out.write(f"{line[0][0]*f+dx} {line[0][1]*f+dy} -33\n")
        
        # Draw line points
        for p in line[1:]:
            file_out.write(f"{p[0]*f+dx} {p[1]*f+dy} 0\n")
        
        # End point with pen up (z = 33)
        file_out.write(f"{line[-1][0]*f+dx} {line[-1][1]*f+dy} 33\n")
    
    file_out.close()
    print(f"Grid-Datei erstellt: {output_file}")


def draw_grid_with_robot(file_path, grid_size=10, spacing=30):
    """Generate grid file and draw with robot arm."""
    
    # Create grid file
    create_grid_file(file_path, grid_size, spacing)
    
    # Read the grid file
    dh = 15.
    x0 = 300.   # Basis Position
    y0 = -200.
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
    
    # Draw with robot
    data = np.array(trail_text)
    data = data.reshape([-1, 3])
    
    print(f"Zeichne Grid mit {len(data)} Punkten...")
    for i in tqdm(list(range(len(data)))):
        y, x, z = data[i, :]
        uarm_interface.set_position(x=x, y=y, z=z, speed=global_speed, wait=True)
    
    print("Grid zeichnen abgeschlossen!")
    return 1


if __name__ == "__main__":
    # Zeichne 10x10 Grid mit 30 Pixel Abstand
    draw_grid_with_robot("results/test.txt", grid_size=10, spacing=30)
