import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

import dearpygui.dearpygui as dpg

from chinese_font_provider import list_supported_chars
from letter_strokes import LETTER_STROKES
from write_chinese import (
    DEFAULT_FONT_NAME as DEFAULT_CHINESE_FONT,
    SUPPORTED_CHINESE_FONT_NAMES,
    SUPPORTED_CHINESE_STYLE_NAME as DEFAULT_CHINESE_STYLE,
    auto_import_missing_chinese_glyphs,
    draw_chinese_text_with_robot,
    validate_chinese_text,
)
from write_words import draw_text_with_robot


screen_width = 1280
screen_height = 720

paper_bg_color = (244, 238, 230)
card_bg_color = (252, 249, 245)
ink_color = (72, 42, 36)
muted_ink_color = (113, 88, 80)
accent_color = (139, 0, 18)
accent_hover_color = (170, 28, 46)
accent_active_color = (116, 0, 14)
soft_accent_color = (232, 214, 209)
secondary_button_color = (232, 224, 215)
secondary_button_hover_color = (217, 206, 195)
secondary_button_active_color = (205, 194, 183)
danger_button_color = (111, 88, 83)
danger_button_hover_color = (132, 106, 100)
danger_button_active_color = (92, 70, 66)

OUTPUT_FILE_ENGLISH = "./output/text_trail.txt"
OUTPUT_FILE_CHINESE = "./output/text_trail_chinese.txt"

MODE_ENGLISH = "English Strokes"
MODE_CHINESE = "Chinese Strokes"
WRITING_MODES = [MODE_ENGLISH, MODE_CHINESE]
AVAILABLE_CHINESE_FONT_NAMES = [
    font_name
    for font_name in SUPPORTED_CHINESE_FONT_NAMES
    if (Path(__file__).resolve().parent / "fonts" / "chinese" / f"{font_name}.json").is_file()
]
CHINESE_FONT_AVAILABLE = bool(AVAILABLE_CHINESE_FONT_NAMES)


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


GUI_FONT_FILENAMES = [
    "SimSun.ttf",
    "MSYH.TTF",
    "msyh.ttc",
    "SimHei.ttf",
    "Arial Unicode.ttf",
    "NotoSansCJK-Regular.ttc",
    "NotoSansCJK-Regular.otf",
    "NotoSansSC-Regular.otf",
    "SourceHanSansSC-Regular.otf",
    "wqy-microhei.ttc",
    "uming.ttc",
]


def get_fc_match_font_paths():
    fc_match = shutil.which("fc-match")
    if not fc_match:
        return []

    matched_paths = []
    for query in ["sans:lang=zh-cn", "serif:lang=zh-cn"]:
        try:
            result = subprocess.run(
                [fc_match, "-f", "%{file}\n", query],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except Exception:
            continue

        candidate = result.stdout.strip().splitlines()
        if candidate:
            matched_paths.append(candidate[0])
    return matched_paths


def iter_existing_font_paths(paths):
    seen = set()
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if not path.is_file():
            continue
        normalized = str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        yield normalized


def get_project_font_candidates():
    base_dir = Path(__file__).resolve().parent
    search_dirs = [
        base_dir,
        base_dir / "assets",
        base_dir / "fonts",
        base_dir / "fonts" / "gui",
        base_dir / "fonts" / "system",
    ]

    candidates = []
    for directory in search_dirs:
        for filename in GUI_FONT_FILENAMES:
            candidates.append(directory / filename)
    return candidates


def get_system_font_candidates():
    home = Path.home()
    return [
        home / "Library" / "Fonts" / "Arial Unicode.ttf",
        home / "Library" / "Fonts" / "SimSun.ttf",
        home / "Library" / "Fonts" / "MSYH.TTF",
        "/home/acir/TinyWings_AISR/assets/SimSun.ttf",
        "/home/acir/TinyWings_AISR/assets/MSYH.TTF",
        "/home/acir/TinyWings_AISR/assets/SimHei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
        "/usr/share/fonts/opentype/adobe-source-han-sans/SourceHanSansSC-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]


def get_gui_font_candidates():
    override_path = os.environ.get("AISR_GUI_FONT_PATH", "").strip()
    candidates = []
    if override_path:
        candidates.append(override_path)

    candidates.extend(get_project_font_candidates())
    candidates.extend(get_system_font_candidates())
    candidates.extend(get_fc_match_font_paths())
    return list(iter_existing_font_paths(candidates))


def pick_gui_font_path():
    candidates = get_gui_font_candidates()
    return candidates[0] if candidates else None


def add_chinese_font_ranges():
    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
    dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
    dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)
    dpg.add_font_range(0x0020, 0x00FF)
    dpg.add_font_range(0x3400, 0x4DBF)
    dpg.add_font_range(0x2000, 0x206F)
    dpg.add_font_range(0x3000, 0x303F)
    dpg.add_font_range(0x4E00, 0x9FFF)
    dpg.add_font_range(0xF900, 0xFAFF)
    dpg.add_font_range(0xFF00, 0xFFEF)


def load_gui_fonts():
    candidates = get_gui_font_candidates()
    gui_font_path = candidates[0] if candidates else None
    if gui_font_path is None:
        return (
            None,
            None,
            None,
            "No compatible GUI font was found. Checked project fonts, legacy Hershey paths, and common system font locations.",
        )

    try:
        with dpg.font_registry():
            with dpg.font(gui_font_path, size=30) as default_font:
                add_chinese_font_ranges()

            with dpg.font(gui_font_path, size=22) as small_font:
                add_chinese_font_ranges()

        print(f"Using GUI font: {gui_font_path}")
        font_kind = Path(gui_font_path).suffix.lower()
        return (
            gui_font_path,
            default_font,
            small_font,
            f"GUI font: {gui_font_path} ({font_kind or 'unknown'})",
        )
    except Exception as exc:
        print(f"Failed to load GUI font '{gui_font_path}': {exc}")
        return None, None, None, f"Failed to load GUI font: {gui_font_path} ({exc})"


def set_status(text):
    status_queue.put(text)


def get_current_mode():
    if dpg.does_item_exist("mode_select"):
        return dpg.get_value("mode_select")
    return MODE_ENGLISH


def get_current_chinese_font():
    if dpg.does_item_exist("font_select"):
        return dpg.get_value("font_select")
    return DEFAULT_CHINESE_FONT


def get_mode_title(mode):
    if mode == MODE_CHINESE:
        return "Chinese Stroke Writer"
    return "English Stroke Writer"


def get_mode_subtitle(mode, font_name):
    if mode == MODE_CHINESE:
        glyph_count = len(list_supported_chars(font_name)) if CHINESE_FONT_AVAILABLE else 0
        return f"{font_name} · {glyph_count} cached glyphs"
    return "Latin letters, numbers, and symbols"


def get_mode_note(mode, font_name):
    if mode == MODE_CHINESE:
        glyph_count = len(list_supported_chars(font_name)) if CHINESE_FONT_AVAILABLE else 0
        return (
            f"Chinese stroke source: {font_name}\n"
            f"Regular style · {glyph_count} cached glyphs"
        )
    return "Robot output uses uppercase Latin strokes."


def get_compact_gui_font_message(gui_font_message):
    if gui_font_message.startswith("GUI font: "):
        font_path = gui_font_message[len("GUI font: "):].split(" (", 1)[0]
        return f"UI font: {Path(font_path).name}"
    return gui_font_message


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
    if not CHINESE_FONT_AVAILABLE:
        return "No supported Chinese stroke fonts are available in ./fonts/chinese."

    chars = list_supported_chars(font_name)
    preview = " ".join(chars[:12])
    extra = ""
    if len(chars) > 12:
        extra = f" ... (+{len(chars) - 12} more)"

    return (
        f"Chinese stroke source: {font_name}\n"
        f"Style profile: {DEFAULT_CHINESE_STYLE} (fixed)\n"
        f"Local Hanzi cache ({len(chars)} glyphs): {preview}{extra}\n"
        "Space, newline, and common Chinese punctuation are also supported.\n"
        "Available Chinese sources in this GUI: hanziwriter, animcjk_zhhans.\n"
        "AnimCJK output is intentionally narrower and taller than HanziWriter."
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
            set_status(
                f"检查并补全中文笔画缓存（字体: {font_name}）...\n"
                f"Checking and extending cached Hanzi strokes ({font_name})..."
            )
            imported, skipped = auto_import_missing_chinese_glyphs(
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
                style_name=DEFAULT_CHINESE_STYLE,
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
    draw_text = normalize_draw_text(text, mode)
    font_name = get_current_chinese_font()

    if mode == MODE_CHINESE:
        if not CHINESE_FONT_AVAILABLE:
            set_status("没有可用的中文笔画字体数据。\nNo Chinese stroke fonts are available.")
            return
        supported_text = get_chinese_supported_chars_text(font_name)
        unsupported = []
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

    thread = threading.Thread(
        target=draw_worker,
        args=(draw_text, mode, font_name, dry_run),
    )
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
    font_name = get_current_chinese_font()

    dpg.set_value("main_prompt", get_mode_title(mode))
    dpg.set_value("sub_prompt", get_mode_subtitle(mode, font_name))

    if mode == MODE_CHINESE:
        dpg.configure_item("font_group", show=True)
        dpg.configure_item("input_text", hint="Example: 你好！")
        dpg.set_value("mode_note_text", get_mode_note(mode, font_name))
    else:
        dpg.configure_item("font_group", show=False)
        dpg.configure_item("input_text", hint="Example: HELLO & ROBOT 2026!")
        dpg.set_value("mode_note_text", get_mode_note(mode, font_name))


def main():
    dpg.create_context()

    gui_font_path, default_font, small_font, gui_font_message = load_gui_fonts()
    gui_font_message = get_compact_gui_font_message(gui_font_message)
    if gui_font_path is None:
        set_status(
            "No GUI font with Chinese coverage was found.\n"
            "Chinese text display may be incomplete.\n"
            "Set AISR_GUI_FONT_PATH to a working TTF/TTC font if needed."
        )

    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, paper_bg_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Text, ink_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border, soft_accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 20, 20, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 12, 12, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 12, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 18, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0, category=dpg.mvThemeCat_Core)

    dpg.bind_theme(global_theme)

    with dpg.theme() as panel_theme:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, card_bg_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border, soft_accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 18, 18, category=dpg.mvThemeCat_Core)

    with dpg.theme() as input_theme:
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, accent_hover_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, accent_active_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border, accent_active_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 14, 12, category=dpg.mvThemeCat_Core)

    with dpg.theme() as primary_button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Button, accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, accent_hover_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, accent_active_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 14, 12, category=dpg.mvThemeCat_Core)

    with dpg.theme() as secondary_button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Text, ink_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Button, secondary_button_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, secondary_button_hover_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, secondary_button_active_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 14, 12, category=dpg.mvThemeCat_Core)

    with dpg.theme() as danger_button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Button, danger_button_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, danger_button_hover_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, danger_button_active_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 14, 12, category=dpg.mvThemeCat_Core)

    with dpg.theme() as selector_theme:
        with dpg.theme_component(dpg.mvCombo):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, card_bg_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, soft_accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, soft_accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Text, ink_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border, soft_accent_color, category=dpg.mvThemeCat_Core)

    with dpg.theme() as subtle_text_theme:
        with dpg.theme_component(dpg.mvText):
            dpg.add_theme_color(dpg.mvThemeCol_Text, muted_ink_color, category=dpg.mvThemeCat_Core)

    with dpg.window(
        tag="entry window",
        label="entry window",
        width=screen_width,
        height=screen_height,
        pos=(0, 0),
    ):
        dpg.add_text(
            default_value="AISR Robot Writer",
            tag="app_title",
            pos=[40, 28],
        )

        dpg.add_text(
            default_value="English Stroke Writer",
            tag="main_prompt",
            pos=[40, 62],
        )

        dpg.add_text(
            default_value="Latin letters, numbers, and symbols",
            tag="sub_prompt",
            pos=[40, 92],
            wrap=500,
        )

        with dpg.child_window(
            tag="left_panel",
            pos=[40, 128],
            width=570,
            height=540,
            border=True,
            no_scrollbar=True,
        ):
            dpg.add_text("Compose", tag="compose_title")

            with dpg.group(tag="mode_group", horizontal=True):
                dpg.add_combo(
                    items=WRITING_MODES,
                    default_value=MODE_ENGLISH,
                    width=220,
                    tag="mode_select",
                    callback=refresh_mode_ui,
                )

                dpg.add_checkbox(
                    label="Dry Run",
                    default_value=True,
                    tag="dry_run_checkbox",
                )

            with dpg.group(tag="font_group", horizontal=True, show=False):
                dpg.add_text(default_value="Source", tag="font_label")
                dpg.add_combo(
                    items=AVAILABLE_CHINESE_FONT_NAMES if AVAILABLE_CHINESE_FONT_NAMES else [DEFAULT_CHINESE_FONT],
                    default_value=DEFAULT_CHINESE_FONT,
                    width=220,
                    tag="font_select",
                    callback=refresh_mode_ui,
                )

            dpg.add_text(default_value="", tag="mode_note_text", wrap=520)
            dpg.bind_item_theme("mode_note_text", subtle_text_theme)

            dpg.add_spacer(height=4)
            dpg.add_text("Text")
            dpg.add_input_text(
                tag="input_text",
                hint="Example: HELLO & ROBOT 2026!",
                width=520,
                height=165,
                multiline=True,
            )

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Start Writing",
                    tag="start_button",
                    width=250,
                    height=54,
                    callback=start_writing_callback,
                )
                dpg.add_button(
                    label="Clear",
                    tag="clear_button",
                    width=120,
                    height=54,
                    callback=clear_callback,
                )
                dpg.add_button(
                    label="Exit",
                    tag="exit_button",
                    width=120,
                    height=54,
                    callback=exit_callback,
                )

            dpg.add_spacer(height=4)
            dpg.add_text(default_value=gui_font_message, tag="font_info_text", wrap=520)
            dpg.bind_item_theme("font_info_text", subtle_text_theme)

        with dpg.child_window(
            tag="preview_panel",
            pos=[650, 128],
            width=590,
            height=245,
            border=True,
            no_scrollbar=True,
        ):
            dpg.add_text(default_value="Preview", tag="preview_label")
            dpg.add_spacer(height=6)
            dpg.add_text(default_value="", tag="preview_text", wrap=540)

        with dpg.child_window(
            tag="status_panel",
            pos=[650, 393],
            width=590,
            height=275,
            border=True,
            no_scrollbar=True,
        ):
            dpg.add_text(default_value="Status", tag="status_label")
            dpg.add_spacer(height=6)
            dpg.add_text(
                default_value="等待输入 / Waiting for input.",
                tag="status_text",
                wrap=540,
            )

        if default_font is not None:
            dpg.bind_font(default_font)
        if small_font is not None:
            dpg.bind_item_font("app_title", default_font)
            dpg.bind_item_font("main_prompt", small_font)
            dpg.bind_item_font("sub_prompt", small_font)
            dpg.bind_item_font("font_info_text", small_font)
            dpg.bind_item_font("compose_title", small_font)
            dpg.bind_item_font("mode_note_text", small_font)
            dpg.bind_item_font("dry_run_checkbox", small_font)
            dpg.bind_item_font("input_text", small_font)
            dpg.bind_item_font("start_button", small_font)
            dpg.bind_item_font("clear_button", small_font)
            dpg.bind_item_font("exit_button", small_font)
            dpg.bind_item_font("preview_label", small_font)
            dpg.bind_item_font("preview_text", small_font)
            dpg.bind_item_font("status_label", small_font)
            dpg.bind_item_font("status_text", small_font)
            dpg.bind_item_font("mode_select", small_font)
            dpg.bind_item_font("font_label", small_font)
            if dpg.does_item_exist("font_select"):
                dpg.bind_item_font("font_select", small_font)

        dpg.bind_item_theme("left_panel", panel_theme)
        dpg.bind_item_theme("preview_panel", panel_theme)
        dpg.bind_item_theme("status_panel", panel_theme)
        dpg.bind_item_theme("start_button", primary_button_theme)
        dpg.bind_item_theme("clear_button", secondary_button_theme)
        dpg.bind_item_theme("exit_button", danger_button_theme)
        dpg.bind_item_theme("mode_select", selector_theme)
        if dpg.does_item_exist("font_select"):
            dpg.bind_item_theme("font_select", selector_theme)
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
