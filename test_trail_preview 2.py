import matplotlib.pyplot as plt

# === A4 + deine Zeichenzone ===
A4_W = 210.0
A4_H = 297.0

X_MIN = 30.0
X_MAX = 180.0

Y_MIN = 30.0
Y_MAX = 222.75


def load_trail(file_path):
    points = []
    with open(file_path, "r") as f:
        for line in f:
            d = line.strip().split()
            if len(d) != 3:
                continue
            x = float(d[0])
            y = float(d[1])
            z = float(d[2])
            points.append((x, y, z))
    return points


def check_safety(points):
    print("=== SAFETY CHECK ===")

    ok = True

    for i, (x, y, z) in enumerate(points):

        # 🔴 außerhalb vom Blatt
        if not (X_MIN <= x <= X_MAX and Y_MIN <= y <= Y_MAX):
            print(f"❌ Punkt {i} außerhalb: ({x:.2f}, {y:.2f})")
            ok = False

        # 🔴 zu große Sprünge
        if i > 0:
            x_prev, y_prev, _ = points[i - 1]
            dx = abs(x - x_prev)
            dy = abs(y - y_prev)

            if dx > 50 or dy > 50:
                print(f"⚠️ großer Sprung bei {i}: dx={dx:.2f}, dy={dy:.2f}")

    if ok:
        print("✅ Alle Punkte innerhalb der sicheren Zone")

    return ok


def plot_trail(points):
    plt.figure(figsize=(6, 9))

    # 🧾 A4 Blatt
    plt.gca().add_patch(
        plt.Rectangle((0, 0), A4_W, A4_H, fill=False, linewidth=2)
    )

    # 🟢 erlaubte Zone
    plt.gca().add_patch(
        plt.Rectangle((X_MIN, Y_MIN),
                      X_MAX - X_MIN,
                      Y_MAX - Y_MIN,
                      fill=False,
                      linestyle='--',
                      linewidth=2)
    )

    # ✏️ Pfad zeichnen
    current_x = []
    current_y = []

    for x, y, z in points:
        if z == -33:  # pen down
            current_x = [x]
            current_y = [y]

        elif z == 0:
            current_x.append(x)
            current_y.append(y)

        elif z == 33:  # pen up
            current_x.append(x)
            current_y.append(y)
            plt.plot(current_x, current_y)
            current_x = []
            current_y = []

    # 🔵 Punkte anzeigen
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    plt.scatter(xs, ys, s=5)

    plt.xlim(0, A4_W)
    plt.ylim(0, A4_H)

    plt.gca().invert_yaxis()  # wichtig: Papier-Ansicht

    plt.title("Trail Preview (Dry Run)")
    plt.xlabel("mm")
    plt.ylabel("mm")

    plt.show()


if __name__ == "__main__":
    file_path = "./output/trail_sign.txt"

    points = load_trail(file_path)

    print(f"Geladene Punkte: {len(points)}")

    safe = check_safety(points)

    plot_trail(points)

    if safe:
        print("\n🚀 SAFE → Kann vom Roboter gezeichnet werden")
    else:
        print("\n🛑 UNSAFE → NICHT starten!")