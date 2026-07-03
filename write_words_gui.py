import json
import os
import queue
import threading
import time
from pathlib import Path

import dearpygui.dearpygui as dpg

from chinese_font_provider import list_fonts, list_supported_chars
from letter_strokes import LETTER_STROKES
from write_chinese import (
    auto_import_missing_hanziwriter_glyphs,
    draw_chinese_text_with_robot,
    validate_chinese_text,
)
from write_words import draw_text_with_robot


screen_width = 1280
screen_height = 720

white_color = (255, 255, 255)
pku_red_color = (139, 0, 18)

OUTPUT_FILE_ENGLISH = "./output/text_trail.txt"
OUTPUT_FILE_CHINESE = "./output/text_trail_chinese.txt"

MODE_ENGLISH = "English Strokes"
MODE_CHINESE = "Chinese Strokes"
WRITING_MODES = [MODE_ENGLISH, MODE_CHINESE]

ALL_CHINESE_FONT_NAMES = list_fonts()


def get_font_glyph_count(font_name):
    font_path = Path(__file__).resolve().parent / "fonts" / "chinese" / f"{font_name}.json"
    try:
        data = json.loads(font_path.read_text(encoding="utf-8"))
        return len(data.get("glyphs", {}))
    except Exception:
        return 0


def get_gui_chinese_font_names():
    names = []
    for font_name in ALL_CHINESE_FONT_NAMES:
        glyph_count = get_font_glyph_count(font_name)
        if font_name == "hanziwriter" or glyph_count >= 100:
            names.append(font_name)
    return names


CHINESE_FONT_NAMES = get_gui_chinese_font_names()
DEFAULT_CHINESE_FONT = "hanziwriter" if "hanziwriter" in CHINESE_FONT_NAMES else (
    CHINESE_FONT_NAMES[0] if CHINESE_FONT_NAMES else ""
)


DEFAULT_START_X = 10
DEFAULT_START_Y = 70
DEFAULT_SCALE = 0.08
DEFAULT_LETTER_SPACING = 15

DEFAULT_CHINESE_START_X = 10.0
DEFAULT_CHINESE_START_Y = 70.0
DEFAULT_CHINESE_CHAR_SIZE = 9.0
DEFAULT_CHINESE_CHAR_SPACING = 2.0
DEFAULT_CHINESE_LINE_SPACING = 14.0

DEFAULT_X0 = 290.0
DEFAULT_Y0 = -220.0
DEFAULT_WRITE_H = 0.623
DEFAULT_DH = 50.0
DEFAULT_IMAGE_SIZE = 1.5
DEFAULT_SPEED = 1


is_drawing = False
status_queue = queue.Queue()


def pick_gui_font_path():
    candidates = [
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def add_chinese_font_ranges():
    dpg.add_font_range(0x0020, 0x00FF)
    dpg.add_font_range(0x2000, 0x206F)
    dpg.add_font_range(0x3000, 0x303F)
    dpg.add_font_range(0x4E00, 0x9FFF)
    dpg.add_font_range(0xFF00, 0xFFEF)


def set_status(text):
    status_queue.put(text)


def get_current_mode():
    if dpg.does_item_exist("mode_select"):
        return dpg.get_value("mode_select")
    return MODE_ENGLISH


def get_current_font():
    if dpg.does_item_exist("font_select"):
        return dpg.get_value("font_select")
    return DEFAULT_CHINESE_FONT


def get_english_supported_chars_text():
    chars = sorted([ch for ch in LETTER_STROKES.keys() if ch != " "])
    letters = [ch for ch in chars if ch.isalpha()]
    numbers = [ch for ch in chars if ch.isdigit()]
    symbols = [ch for ch in chars if not ch.isalpha() and not ch.isdigit()]

    parts = []
    if letters:
        parts.append("Letters: " + " ".join(letters))
    if numbers:
        parts.append("Numbers: " + " ".join(numbers))
    if symbols:
        parts.append("Symbols: " + " ".join(symbols))
    parts.append("Space and newline are also supported.")
    return "\n".join(parts)


def get_chinese_supported_chars_text(font_name):
    if not CHINESE_FONT_NAMES:
        return "No Chinese stroke fonts are available in ./fonts/chinese."

    chars = list_supported_chars(font_name)
    preview = " ".join(chars[:12])
    extra = ""
    if len(chars) > 12:
        extra = f" ... (+{len(chars) - 12} more)"

    return (
        f"Selected font: {font_name}\n"
        f"Local Hanzi cache ({len(chars)} glyphs): {preview}{extra}\n"
        "Space, newline, and common Chinese punctuation are also supported.\n"
        "Only production-ready Chinese fonts are shown in this GUI."
    )


def validate_english_text(text):
    unsupported = []
    for ch in text:
        if ch in [" ", "\n"]:
            continue

        check_ch = ch.upper()
        if check_ch not in LETTER_STROKES:
            unsupported.append(ch)

    return sorted(set(unsupported))


def normalize_draw_text(text, mode):
    if mode == MODE_CHINESE:
        return text
    return text.upper()


def draw_worker(text, mode, font_name, dry_run):
    global is_drawing

    try:
        is_drawing = True
        if mode == MODE_CHINESE:
            if font_name == "hanziwriter":
                set_status(
                    f"检查并补全中文笔画缓存（字体: {font_name}）...\n"
                    f"Checking and extending cached Hanzi strokes ({font_name})..."
                )
                imported, skipped = auto_import_missing_hanziwriter_glyphs(
                    text=text,
                    font_name=font_name,
                    skip_missing=True,
                )
                if imported:
                    set_status(
                        "已自动导入新汉字："
                        + "".join(imported)
                        + "\nAuto-imported Hanzi: "
                        + "".join(imported)
                    )
                unsupported = validate_chinese_text(text, font_name)
                if unsupported:
                    raise ValueError(
                        "These Chinese characters could not be imported automatically: "
                        + " ".join(unsupported)
                    )

            set_status(
                f"正在准备写中文（字体: {font_name}）：{text}\n"
                f"Preparing Chinese writing ({font_name}): {text}"
            )
            ok = draw_chinese_text_with_robot(
                text=text,
                output_file=OUTPUT_FILE_CHINESE,
                font_name=font_name,
                start_x=DEFAULT_CHINESE_START_X,
                start_y=DEFAULT_CHINESE_START_Y,
                char_size=DEFAULT_CHINESE_CHAR_SIZE,
                char_spacing=DEFAULT_CHINESE_CHAR_SPACING,
                line_spacing=DEFAULT_CHINESE_LINE_SPACING,
                x0=DEFAULT_X0,
                y0=DEFAULT_Y0,
                write_h=DEFAULT_WRITE_H,
                dh=DEFAULT_DH,
                image_size=DEFAULT_IMAGE_SIZE,
                speed=DEFAULT_SPEED,
                dry_run=dry_run,
                auto_import_missing=False,
            )
        else:
            set_status(f"正在准备写字：{text}\nPreparing to write: {text}")
            ok = draw_text_with_robot(
                text=text,
                output_file=OUTPUT_FILE_ENGLISH,
                start_x=DEFAULT_START_X,
                start_y=DEFAULT_START_Y,
                scale=DEFAULT_SCALE,
                letter_spacing=DEFAULT_LETTER_SPACING,
                x0=DEFAULT_X0,
                y0=DEFAULT_Y0,
                write_h=DEFAULT_WRITE_H,
                dh=DEFAULT_DH,
                image_size=DEFAULT_IMAGE_SIZE,
                speed=DEFAULT_SPEED,
                dry_run=dry_run,
            )

        if ok and dry_run:
            set_status(
                "Dry run finished. Trail and safety check passed.\n"
                "机器人未移动。"
            )
        elif ok:
            set_status("写字完成！\nWriting finished.")
        else:
            set_status("写字失败：机器人连接失败或绘制失败。\nWriting failed.")

    except Exception as e:
        set_status(f"发生错误：{e}\nError: {e}")

    finally:
        is_drawing = False


def start_writing_callback(sender=None, app_data=None):
    global is_drawing

    if is_drawing:
        set_status("机器人正在写字，请等待。\nRobot is already writing.")
        return

    text = dpg.get_value("input_text")
    if text.strip() == "":
        set_status("请先输入要写的文字。\nPlease enter text first.")
        return

    mode = get_current_mode()
    font_name = get_current_font()
    draw_text = normalize_draw_text(text, mode)

    if mode == MODE_CHINESE:
        if not CHINESE_FONT_NAMES:
            set_status("没有可用的中文笔画字体数据。\nNo Chinese stroke fonts are available.")
            return
        supported_text = get_chinese_supported_chars_text(font_name)
        if font_name == "hanziwriter":
            unsupported = []
        else:
            unsupported = validate_chinese_text(draw_text, font_name)
    else:
        unsupported = validate_english_text(draw_text)
        supported_text = get_english_supported_chars_text()

    if unsupported:
        dpg.set_value("preview_text", draw_text)
        set_status(
            "这些字符目前不能绘制：\n"
            + " ".join(unsupported)
            + "\n\n当前支持：\n"
            + supported_text
        )
        return

    dpg.set_value("preview_text", draw_text)

    dry_run = dpg.get_value("dry_run_checkbox")
    if dry_run:
        set_status("开始 dry run：将只生成轨迹并做安全检查。\nStarting dry run.")
    else:
        set_status("已收到文字，准备启动机器人。\nText received. Starting robot...")

    thread = threading.Thread(target=draw_worker, args=(draw_text, mode, font_name, dry_run))
    thread.daemon = True
    thread.start()


def clear_callback(sender=None, app_data=None):
    if is_drawing:
        set_status("机器人正在写字，不能清空。\nCannot clear while robot is writing.")
        return

    dpg.set_value("input_text", "")
    dpg.set_value("preview_text", "")
    set_status("已清空。\nCleared.")


def exit_callback(sender=None, app_data=None):
    dpg.stop_dearpygui()


def update_gui_from_queue():
    while not status_queue.empty():
        text = status_queue.get()
        if dpg.does_item_exist("status_text"):
            dpg.set_value("status_text", text)


def refresh_mode_ui(sender=None, app_data=None):
    mode = get_current_mode()
    font_name = get_current_font()

    if mode == MODE_CHINESE:
        dpg.set_value("main_prompt", "请输入要写的中文 / Type the Chinese text to write")
        dpg.set_value(
            "sub_prompt",
            "当前支持中文笔画字体 / Supported Chinese stroke fonts:\n"
            + get_chinese_supported_chars_text(font_name),
        )
        dpg.configure_item("font_group", show=True)
        dpg.configure_item("input_text", hint="Example: 你好！")
    else:
        dpg.set_value("main_prompt", "请输入要写的英文单词 / Type the text to write")
        dpg.set_value(
            "sub_prompt",
            "当前支持绘制 / Supported characters:\n"
            + get_english_supported_chars_text(),
        )
        dpg.configure_item("font_group", show=False)
        dpg.configure_item("input_text", hint="Example: HELLO & ROBOT 2026!")


def main():
    dpg.create_context()

    default_font = None
    small_font = None
    gui_font_path = pick_gui_font_path()
    if gui_font_path is not None:
        with dpg.font_registry():
            with dpg.font(gui_font_path, size=30) as default_font:
                add_chinese_font_ranges()

            with dpg.font(gui_font_path, size=22) as small_font:
                add_chinese_font_ranges()
    else:
        set_status(
            "No GUI font with Chinese coverage was found.\n"
            "Chinese text display may be incomplete."
        )

    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, white_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Text, pku_red_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Button, white_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 3, category=dpg.mvThemeCat_Core)

    dpg.bind_theme(global_theme)

    with dpg.theme() as input_theme:
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, pku_red_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, pku_red_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, pku_red_color, category=dpg.mvThemeCat_Core)

    with dpg.window(
        tag="entry window",
        label="entry window",
        width=screen_width,
        height=screen_height,
        pos=(0, 0),
    ):
        dpg.add_text(
            default_value="请输入要写的英文单词 / Type the text to write",
            tag="main_prompt",
            pos=[40, 40],
        )

        dpg.add_text(
            default_value=(
                "当前支持绘制 / Supported characters:\n"
                + get_english_supported_chars_text()
            ),
            tag="sub_prompt",
            pos=[40, 90],
            wrap=1100,
        )

        with dpg.group(tag="mode_group", horizontal=True):
            dpg.add_combo(
                items=WRITING_MODES,
                default_value=MODE_ENGLISH,
                width=260,
                tag="mode_select",
                callback=refresh_mode_ui,
            )

            dpg.add_checkbox(
                label="Dry Run Only / Nur prüfen",
                default_value=True,
                tag="dry_run_checkbox",
            )

        dpg.set_item_pos("mode_group", [40, 195])

        with dpg.group(tag="font_group", horizontal=True, show=False):
            dpg.add_text(default_value="字体 / Font:")
            dpg.add_combo(
                items=CHINESE_FONT_NAMES if CHINESE_FONT_NAMES else [""],
                default_value=DEFAULT_CHINESE_FONT,
                width=220,
                tag="font_select",
                callback=refresh_mode_ui,
            )

        dpg.set_item_pos("font_group", [40, 230])

        dpg.add_input_text(
            tag="input_text",
            hint="Example: HELLO & ROBOT 2026!",
            width=630,
            height=60,
            pos=[40, 275],
            multiline=True,
        )

        dpg.add_button(
            label="开始写字 / Start Writing",
            tag="start_button",
            width=400,
            height=85,
            pos=[40, 350],
            callback=start_writing_callback,
        )

        dpg.add_button(
            label="清空 / Clear",
            tag="clear_button",
            width=200,
            height=85,
            pos=[470, 350],
            callback=clear_callback,
        )

        dpg.add_button(
            label="退出 / Exit",
            tag="exit_button",
            width=180,
            height=85,
            pos=[700, 350],
            callback=exit_callback,
        )

        dpg.add_text(default_value="预览 / Preview:", tag="preview_label", pos=[40, 460])
        dpg.add_text(default_value="", tag="preview_text", pos=[40, 490], wrap=1100)

        dpg.add_text(default_value="状态 / Status:", tag="status_label", pos=[40, 580])
        dpg.add_text(
            default_value="等待输入 / Waiting for input.",
            tag="status_text",
            pos=[40, 630],
            wrap=1100,
        )

        if default_font is not None:
            dpg.bind_font(default_font)
        if small_font is not None:
            dpg.bind_item_font("sub_prompt", small_font)
            dpg.bind_item_font("input_text", small_font)
            dpg.bind_item_font("preview_text", small_font)
            dpg.bind_item_font("status_text", small_font)
            dpg.bind_item_font("mode_select", small_font)
            if dpg.does_item_exist("font_select"):
                dpg.bind_item_font("font_select", small_font)

        dpg.bind_item_theme("input_text", input_theme)

    dpg.create_viewport(title="Robot Writing GUI", width=screen_width, height=screen_height)
    dpg.setup_dearpygui()
    dpg.toggle_viewport_fullscreen()
    dpg.show_viewport()
    dpg.set_primary_window("entry window", True)
    refresh_mode_ui()

    while dpg.is_dearpygui_running():
        update_gui_from_queue()
        dpg.render_dearpygui_frame()
        time.sleep(0.01)

    dpg.destroy_context()


if __name__ == "__main__":
    main()
