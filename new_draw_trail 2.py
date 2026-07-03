import os
import json

import numpy as np
from tqdm import tqdm

output_file = './output/trail_sign.txt'
global_speed = 1

from arm_trigger.mode_intf.xarm_interface import XarmInterface
uarm_interface = XarmInterface()
if_connect = uarm_interface.connect()

print(if_connect)

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

trail_text = []


def clamp_to_allowed_box(x: float, y: float):
    x = max(X_MIN_MM, min(x, X_MAX_MM))
    y = max(Y_MIN_MM, min(y, Y_MAX_MM))
    return x, y


def paper_point_to_robot_pose(paper_x_mm: float, paper_y_mm: float, z_code: float, last_z: float):
    """
    Erwartet, dass die Eingabedatei bereits Papierkoordinaten in mm enthält.
    Erlaubte Zeichenfläche:
    - A4 Hochformat
    - links/rechts/oben je 30 mm Rand
    - nur oberes 3/4 des Blatts
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


def uarm_draw(file_lines):
    last_z = WRITE_H_M + PEN_LIFT_MM / 1000.0
    raw_traj = []

    for line in file_lines:
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
        raw_traj.append(pose)

    trail_text.clear()
    trail_text.extend(raw_traj)
    return True


def get_draw_mat():
    ensure_dir = os.path.dirname(output_file)
    if ensure_dir:
        os.makedirs(ensure_dir, exist_ok=True)

    record_info = '000'
    with open(output_file, 'r', encoding='utf-8') as ff:
        file_org = ff.readlines()
        if not file_org:
            print('绘画轨迹获取失败：文件为空')
            return -2

        date_info = file_org[-1]
        print("date_info:", date_info)
        print("record_info:", record_info)

        if record_info != date_info:
            record_info = date_info
            if uarm_draw(file_org):
                print('绘画轨迹获取完成')
                return 1
            print('绘画轨迹获取失败1')
            record_info = '000'
            return -2

        print('绘画轨迹获取失败2')
        record_info = '000'
        return -2


def draw(data):
    for i in tqdm(range(len(data))):
        progress_rate = ((i + 1) / len(data)) * 100
        if int(progress_rate) % 2 == 0:
            msg = {}
            json.dumps(msg, ensure_ascii=False)

        y, x, z = data[i, :]
        uarm_interface.set_position(x=x, y=y, z=z, speed=global_speed, wait=True)

    print("绘画完成！")


if __name__ == "__main__":
    get_draw_mat()
    data = np.array(trail_text, dtype=float).reshape([-1, 3])
    print(data)

    os.makedirs("./output", exist_ok=True)
    with open("./output/draw_point_test.csv", "w", encoding='utf-8') as f:
        for i in range(len(data)):
            f.write("%f,%f,%f\n" % (data[i, 0], data[i, 1], data[i, 2]))

    draw(data)
