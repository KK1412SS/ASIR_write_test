import numpy as np
from tqdm import tqdm
import json

output_file = './output/trail_sign.txt'
trail_text = []

from arm_trigger.mode_intf.xarm_interface import XarmInterface
uarm_interface = XarmInterface()
if_connect = uarm_interface.connect()
global_speed = 1

print(if_connect)

# =========================
# SICHERHEITSRAHMEN (in mm)
# =========================
SAFE_X_MIN = 290.0
SAFE_X_MAX = 440.0
SAFE_Y_MIN = -250.0
SAFE_Y_MAX = -100.0

# Verhalten:
# True  -> sofort abbrechen, wenn ein Punkt außerhalb liegt
# False -> Punkte auf Rand begrenzen
ABORT_ON_OUT_OF_RANGE = True


def is_inside_safe_frame(x_mm, y_mm):
    return SAFE_X_MIN <= x_mm <= SAFE_X_MAX and SAFE_Y_MIN <= y_mm <= SAFE_Y_MAX


def clamp_to_safe_frame(x_mm, y_mm):
    x_mm = max(SAFE_X_MIN, min(SAFE_X_MAX, x_mm))
    y_mm = max(SAFE_Y_MIN, min(SAFE_Y_MAX, y_mm))
    return x_mm, y_mm


def uarm_draw(file):
    global trail_text
    trail_text = []

    dh = 15.
    x0 = 300.   # 初始基准位置
    y0 = -200.
    write_h = 0.623
    last_z = write_h + dh / 1000
    image_size = 1.8
    raw_p = []

    for l in file:
        d = l.strip().split(' ')
        if len(d) < 3:
            continue

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

    for i in range(len(raw_p)):
        x_mm = x0 + raw_p[i][1]
        y_mm = y0 - raw_p[i][0]
        z = raw_p[i][2]

        if not is_inside_safe_frame(x_mm, y_mm):
            msg = f"[WARN] Punkt {i} außerhalb Sicherheitsrahmen: x={x_mm:.2f}, y={y_mm:.2f}"

            if ABORT_ON_OUT_OF_RANGE:
                print(msg)
                print("[ABBRUCH] Trajectory enthält unsichere Punkte.")
                return False
            else:
                print(msg + " -> wird auf Rand begrenzt")
                x_mm, y_mm = clamp_to_safe_frame(x_mm, y_mm)

        x = x_mm / 1000.0
        y = y_mm / 1000.0

        trail_text.append([x, y, z])

    print('绘画轨迹获取完成')
    return True


def get_draw_mat():
    record_info = '000'
    with open(output_file, 'r') as ff:
        file_org = ff.readlines()
        file = file_org[:]
        date_info = file_org[-1]

        print("date_info:", date_info)
        print("record_info:", record_info)

        if record_info != date_info:
            record_info = date_info
            if uarm_draw(file):
                return 1
            else:
                print('绘画轨迹获取失败1')
                record_info = '000'
                return -2
        else:
            print('绘画轨迹获取失败2')
            record_info = '000'
            return -2

    return -2


def draw(data):
    for i in tqdm(list(range(len(data)))):
        progress_rate = ((i + 1) / len(data)) * 100

        if int(progress_rate) % 2 == 0:
            msg = {}
            msg = json.dumps(msg, ensure_ascii=False)

        y, x, z = data[i, :]
        current_h = z

        # zusätzliche Sicherheitsprüfung direkt vor dem Fahren
        x_mm = x * 1000.0
        y_mm = y * 1000.0

        if not is_inside_safe_frame(x_mm, y_mm):
            print(f"[ABBRUCH] Fahrpunkt außerhalb Sicherheitsrahmen: x={x_mm:.2f}, y={y_mm:.2f}")
            return -1

        uarm_interface.set_position(
            x=x, y=y, z=z, speed=global_speed, wait=True
        )

    print("绘画完成！")
    return 1


if __name__ == "__main__":
    status = get_draw_mat()

    if status == 1:
        data = np.array(trail_text)
        data = data.reshape([-1, 3])
        print(data)

        with open("./output/draw_point_test.csv", "w") as f:
            for i in range(len(data)):
                f.write("%f,%f,%f\n" % (data[i, 0], data[i, 1], data[i, 2]))

        draw(data)
    else:
        print("未执行绘画，因为轨迹生成失败或超出安全范围。")