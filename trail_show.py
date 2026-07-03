import matplotlib.pyplot as plt
import numpy as np
import os

def plot_continuous_trajectory_by_z(file_path):
    """
    从文本文件（空格分隔）或CSV文件（逗号分隔）读取轨迹点，按z值绘制连续轨迹
    - TXT文件：仅Y轴翻转（上下颠倒）
    - CSV文件：逆时针旋转90度 + 镜像反转 + Y轴翻转
    仅连接同z值的连续点，无中文图例
    
    参数:
        file_path: 轨迹点文件路径（.txt 或 .csv）
    """
    # 设置中文字体（防止偶发的中文显示问题）
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    
    # 1. 自动识别文件类型并读取数据
    try:
        file_ext = os.path.splitext(file_path)[1].lower()
        is_csv = (file_ext == '.csv')
        
        if is_csv:
            # 读取CSV文件（逗号分隔）
            data = np.loadtxt(file_path, dtype=np.float64, delimiter=',')
        elif file_ext == '.txt':
            # 读取文本文件（空格分隔）
            data = np.loadtxt(file_path, dtype=np.float64)
        else:
            raise ValueError(f"Unsupported file format: {file_ext} (only .txt and .csv are supported)")
        
        if data.ndim != 2 or data.shape[1] != 3:
            raise ValueError("File format error: each line must contain 3 values (x y z)")
    except FileNotFoundError:
        print(f"Error: File {file_path} not found")
        return
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    # 2. 对CSV文件执行坐标变换：逆时针旋转90度 + 镜像反转
    if is_csv:
        # 提取x、y坐标（z坐标不变）
        x = data[:, 0].copy()
        y = data[:, 1].copy()
        
        # 步骤1：逆时针旋转90度（坐标变换公式：x' = -y, y' = x）
        rotated_x = -y
        rotated_y = -x
        
        # 步骤2：镜像反转（以Y轴为对称轴，x坐标取反）
        mirrored_x = rotated_x
        mirrored_y = rotated_y
        
        # 更新数据中的坐标
        data[:, 0] = mirrored_x
        data[:, 1] = mirrored_y
    
    # 3. 按z值分组，并提取连续的轨迹段
    z_values = np.unique(data[:, 2])
    if len(z_values) == 0:
        print("Error: No valid data in file")
        return
    
    # 4. 创建画布
    n_plots = len(z_values)
    fig, axes = plt.subplots(nrows=1, ncols=n_plots, figsize=(5*n_plots, 5))
    if n_plots == 1:
        axes = [axes]
    
    # 5. 为每个z值绘制连续轨迹段
    colors = plt.cm.Set1(np.linspace(0, 1, n_plots))
    for idx, z in enumerate(z_values):
        ax = axes[idx]
        z_mask = data[:, 2] == z
        
        # 识别连续段
        diff = np.diff(np.concatenate([[False], z_mask, [False]]))
        start_indices = np.where(diff[:-1])[0]
        end_indices = np.where(diff[1:])[0]
        
        segment_count = 0
        for start, end in zip(start_indices, end_indices):
            segment = data[start:end]
            if len(segment) == 0:
                continue
            
            x = segment[:, 0]
            y = segment[:, 1]
            segment_count += 1
            
            # 绘制轨迹（细线条+小标记点）
            ax.plot(x, y, 'o-', color=colors[idx], linewidth=3, markersize=3,
                    label=f'Z = {z}' if segment_count == 1 else "")
            
            # 标记起点/终点
            if len(x) > 0:
                ax.plot(x[0], y[0], 'rs', markersize=3, label='Start' if segment_count == 1 else "")
                if len(x) > 1:
                    ax.plot(x[-1], y[-1], 'gd', markersize=3, label='End' if segment_count == 1 else "")
        
        # 无有效点提示
        if segment_count == 0:
            ax.text(0.5, 0.5, f'No valid points for Z={z}', ha='center', va='center', transform=ax.transAxes)
        
        # 翻转Y轴（上下颠倒，所有文件都生效）
        ax.invert_yaxis()
        
        # 设置子图样式
        ax.set_title(f'Trajectory (Z = {z})', fontsize=14, pad=10)
        ax.set_xlabel('X coordinate', fontsize=12)
        ax.set_ylabel('Y coordinate', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', fontsize=10)
        ax.axis('equal')
    
    # 6. 保存并显示图片
    plt.tight_layout()
    output_path = 'continuous_trajectory_by_z.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Trajectory plot saved to: {os.path.abspath(output_path)}")
    plt.show()

# ------------------- 主程序 -------------------
if __name__ == "__main__":
    # 替换为你的文件路径（支持 .txt 或 .csv）
    FILE_PATH = "output/draw_point_test.csv"  # CSV文件会执行旋转+镜像，TXT文件仅Y轴翻转
    plot_continuous_trajectory_by_z(FILE_PATH)
