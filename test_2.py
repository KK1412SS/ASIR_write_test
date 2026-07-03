import dearpygui.dearpygui as dpg
import os

# 创建上下文
dpg.create_context()

# ==================== 字体配置 ====================
script_dir = os.path.dirname(os.path.abspath(__file__))
font_path = os.path.join(script_dir, "MSYH.TTF")

fonts = {}

with dpg.font_registry():
    with dpg.font(font_path, 36) as fonts["button"]:
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
        dpg.add_font_range(0x0020, 0x00FF)

    with dpg.font(font_path, 32) as fonts["corner"]:
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
        dpg.add_font_range(0x0020, 0x00FF)

# ==================== 加载图片 ====================
bk_path = os.path.join(script_dir, "bk.jpeg")
ok_path = os.path.join(script_dir, "ok.jpeg")

bk_texture = None
ok_texture = None

with dpg.texture_registry():
    if os.path.exists(bk_path):
        width_bk, height_bk, channels, data = dpg.load_image(bk_path)
        bk_texture = dpg.add_static_texture(width_bk, height_bk, data)
        print(f"背景图片加载成功: {width_bk}x{height_bk}")

    if os.path.exists(ok_path):
        width_ok, height_ok, channels, data = dpg.load_image(ok_path)
        ok_texture = dpg.add_static_texture(width_ok, height_ok, data)
        print(f"OK图片加载成功: {width_ok}x{height_ok}")

# 设置窗口尺寸
if bk_texture:
    window_width = width_bk
    window_height = height_bk
else:
    window_width = 1280
    window_height = 720

# 创建无边框全屏视口
dpg.create_viewport(title="爱瑟尔 - 准备就绪",
                    width=window_width,
                    height=window_height,
                    x_pos=0,
                    y_pos=0,
                    resizable=False,
                    decorated=False)
dpg.setup_dearpygui()
dpg.show_viewport()


def on_ready_callback(sender, app_data, user_data):
    dpg.configure_item("ready_button", enabled=False)
    print("用户已准备就绪")


def on_back_callback(sender, app_data, user_data):
    print("返回主页")


# ==================== 右上角按钮主题（透明） ====================
with dpg.theme() as transparent_theme:
    with dpg.theme_component(dpg.mvButton):
        # 设置按钮所有状态为透明
        dpg.add_theme_color(dpg.mvThemeCol_Button, (0, 0, 0, 0))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (0, 0, 0, 0))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (0, 0, 0, 0))
        # 移除边框
        dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
        # 设置文字颜色为蓝色（虽然按钮没有文字，但以防万一）
        dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 100, 255, 255))

# ==================== 创建主窗口 ====================
with dpg.window(label="Main Window",
                width=window_width,
                height=window_height,
                no_title_bar=True,
                no_resize=True,
                no_move=True,
                no_scrollbar=True,
                no_close=True,
                no_collapse=True,
                pos=(0, 0)):
    # 绘制背景图片（最底层）
    with dpg.drawlist(width=window_width, height=window_height, tag="bg_drawlist"):
        if bk_texture:
            dpg.draw_image(bk_texture, pmin=(0, 0), pmax=(window_width, window_height))

    # ==================== 右上角返回按钮（蓝色文字，无边框无背景） ====================
    back_button_x = window_width - 340
    back_button_y = 0
    back_button_width = 340
    back_button_height = 69

    # 1. 先添加蓝色文字
    back_text_cn = dpg.add_text("返回主页",
                                pos=(back_button_x + 10, back_button_y + 25),
                                color=(0, 100, 255, 255))
    dpg.bind_item_font(back_text_cn, fonts["corner"])

    back_text_en = dpg.add_text("Back to home",
                                pos=(back_button_x + 130, back_button_y + 25),
                                color=(0, 100, 255, 255))
    dpg.bind_item_font(back_text_en, fonts["corner"])

    # 2. 添加透明按钮（在文字上方，处理点击）
    back_button = dpg.add_button(label="",
                                 width=back_button_width,
                                 height=back_button_height,
                                 callback=on_back_callback,
                                 pos=(back_button_x, back_button_y),
                                 tag="back_button")
    # 应用透明主题
    dpg.bind_item_theme(back_button, transparent_theme)

    # 中间按钮参数
    button_x = 413
    button_y = 420
    button_width = 446
    button_height = 92

    # 按钮主题
    with dpg.theme() as button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (255, 255, 255, 240))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (230, 240, 255, 250))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (200, 220, 240, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, (0, 100, 255, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)
            dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 100, 150, 255))

    # 按钮阴影
    with dpg.drawlist(width=button_width + 10, height=button_height + 10,
                      pos=(button_x - 5, button_y - 5), tag="shadow_drawlist"):
        dpg.draw_rectangle(pmin=(3, 3), pmax=(button_width + 3, button_height + 3),
                           fill=(0, 0, 0, 60), color=(0, 0, 0, 0), rounding=10)

    # 创建主按钮
    ready_button = dpg.add_button(label="我准备好了 I'm ready",
                                  width=button_width,
                                  height=button_height,
                                  callback=on_ready_callback,
                                  pos=(button_x, button_y),
                                  tag="ready_button")
    dpg.bind_item_font(ready_button, fonts["button"])
    dpg.bind_item_theme(ready_button, button_theme)

    # ==================== 使用 Child Window 放置 OK 图片 ====================
    if ok_texture:
        img_display_width = 50
        img_display_height = 50
        img_x = button_x + 20
        img_y = button_y + (button_height - img_display_height) // 2

        with dpg.child_window(width=img_display_width,
                              height=img_display_height,
                              pos=(img_x, img_y),
                              no_scrollbar=True,
                              border=False,
                              tag="ok_image_container"):
            with dpg.drawlist(width=img_display_width, height=img_display_height):
                dpg.draw_image(ok_texture,
                               pmin=(0, 0),
                               pmax=(img_display_width, img_display_height))

        dpg.move_item_up("ok_image_container")
        print(f"OK图片容器位置: ({img_x}, {img_y}), 尺寸: {img_display_width}x{img_display_height}")

# 启动
dpg.start_dearpygui()
dpg.destroy_context()
