import os
import time
import threading
import queue
import base64
import logging

import dearpygui.dearpygui as dpg
import pyaudio
import numpy as np
import dashscope

from dashscope.audio.qwen_omni import *
from dashscope.audio.qwen_omni.omni_realtime import TranscriptionParams

from write_words_hershey import draw_text_with_robot


# ============================================================
# Global style, passend zur alten gui_node.py
# ============================================================

screen_width = 1280
screen_height = 720

white_color = (255, 255, 255)
pku_red_color = (139, 0, 18)

font_path = "/home/acir/TinyWings_AISR/assets/SimSun.ttf"

OUTPUT_FILE = "./output/text_trail.txt"


# ============================================================
# Robot writing parameters
# Diese Werte kommen aus deinem aktuellen write_words.py-Test
# ============================================================

DEFAULT_START_X = 10.0
DEFAULT_START_Y = 70.0

# Hershey stroke-font parameters
# Gute Startwerte fuer deinen Roboter:
# - futural: klar, stabil, wenig Doppelstrich
# - scripts/scriptc: handschriftlicher, aber manchmal mehr Linien
#DEFAULT_FONT_NAME = "futural"
#DEFAULT_FONT_SIZE = 10
#DEFAULT_CHAR_SPACING = 1.2
#DEFAULT_WORD_SPACING = 4.0
#DEFAULT_LINE_SPACING = 18.0

DEFAULT_FONT_NAME = "timesi" 
DEFAULT_FONT_SIZE = 14
DEFAULT_CHAR_SPACING = 1.0
DEFAULT_WORD_SPACING = 3.0
DEFAULT_LINE_SPACING = 15.0

# Robot coordinate parameters
# Wichtig bei deinem System:
# - x0 steuert hoch/runter auf Papier
# - y0 steuert links/rechts auf Papier
DEFAULT_X0 = 300.0
DEFAULT_Y0 = -200.0
DEFAULT_WRITE_H = 0.623
DEFAULT_DH = 50.0
DEFAULT_IMAGE_SIZE = 1.5
DEFAULT_SPEED = 1
DEFAULT_DRY_RUN = False


# ============================================================
# ASR settings
# Orientiert an deiner asr.py:
# - DashScope realtime
# - Mikrofon-Thread
# - Reconnect bei geschlossener Verbindung
# ============================================================

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")


ASR_LANGUAGE = "zh"          # bei chinesischen Befehlen so lassen
VOLUME_THRESHOLD = 400

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 3200


# ============================================================
# Voice command words
# ============================================================

CONFIRM_WORDS = [
    "确认", "确定", "可以写", "开始写", "开始写字", "写吧", "对", "好的",
    "yes", "Yes", "start writing", "Start writing", "write it", "Write it",
    "ok", "OK", "okay", "Okay"
]

CLEAR_WORDS = [
    "清空", "取消", "重来", "重新来", "删除", "不要了",
    "clear", "Clear", "cancel", "Cancel", "redo", "Redo"
]

WRITE_PREFIXES = [
    "写下", "写字", "写", "请写", "我要写", "帮我写",
    "write", "Write", "write down", "Write down",
    "schreib", "Schreib", "schreibe", "Schreibe"
]

EXIT_WORDS = [
    "退出", "关闭程序", "结束程序",
    "exit", "Exit", "quit", "Quit"
]

# ============================================================
# Global states
# ============================================================

is_drawing = False
status_queue = queue.Queue()
asr_queue = queue.Queue()
asr_controller = None


def set_status(text):
    status_queue.put(text)


def get_supported_chars_text():
    """
    Hershey-Fonts sind Stroke-Fonts. Sie koennen viele normale ASCII-Zeichen
    zeichnen, aber keine chinesischen Zeichen.
    """
    return (
        "Try fonts: futural, rowmans, romans, scripts, scriptc, gothiceng...\n"
        "中文可以显示，但 Hershey 暂时不能自然绘制中文。"
    )


def validate_drawable_text(text):
    """
    Prueft nur grob, ob der Text fuer Hershey geeignet ist.
    Chinesische Zeichen werden nicht an den Roboter geschickt, weil Hershey
    dafuer keine natuerliche Stroke-Order hat.
    """
    unsupported = []

    for ch in text:
        if ch in [" ", "\n", "\t"]:
            continue

        # Hershey in dieser Version ist fuer normale ASCII-Zeichen gedacht.
        if not (32 <= ord(ch) <= 126):
            unsupported.append(ch)

    return sorted(set(unsupported))


def normalize_draw_text(text):
    """
    Fuer Hershey nicht automatisch upper-case machen.
    So bleiben Kleinbuchstaben und handschriftlichere Fonts erhalten.
    Anfang/Ende wird nicht abgeschnitten, damit Newlines nicht verschwinden.
    """
    return text

def convert_spoken_newlines(text):
    """
    Wandelt gesprochene Newline-Befehle in echte Zeilenumbrüche um.
    """
    replacements = [
        "neue zeile",
        "Neue Zeile",
        "new line",
        "New line",
        "下一行",
        "换行",
        "新的一行",
    ]

    result = text

    for word in replacements:
        result = result.replace(word, "\n")

    return result


def parse_voice_command(text):
    """
    Wandelt erkannten ASR-Text in eine GUI-Aktion um.

    Rückgabe:
    - ("confirm", None)  -> aktuellen Input schreiben
    - ("clear", None)    -> Input löschen
    - ("text", content)  -> erkannten Schreibtext ins Feld setzen
    - ("raw_text", text) -> keine klare Befehlsform, aber als Schreibtext übernehmen
    """
    raw = text.strip()

    if raw == "":
        return None, None

    lower_raw = raw.lower()

    # 1. Confirm command
    for word in CONFIRM_WORDS:
        if word.lower() in lower_raw:
            return "confirm", None

    # 2. Clear / cancel command
    for word in CLEAR_WORDS:
        if word.lower() in lower_raw:
            return "clear", None
        
    # Exit
    for word in EXIT_WORDS:
        if word.lower() in lower_raw:
            return "exit", None

    # 3. Text nach Prefix extrahieren
    # Beispiele:
    # "写 HELLO ROBOT" -> "HELLO ROBOT"
    # "请写 A+B=10" -> "A+B=10"
    # "write HELLO" -> "HELLO"
    for prefix in WRITE_PREFIXES:
        if raw.startswith(prefix):
            content = raw[len(prefix):].strip()
            if content:
                return "text", content

    # 4. Fallback:
    # Wenn kein spezieller Befehl erkannt wird,
    # nehmen wir den ganzen Satz als zu schreibenden Text.
    return "raw_text", raw


def draw_worker(text):
    global is_drawing

    try:
        is_drawing = True
        set_status(
            f"机器人确认要写：{text}\n"
            f"Robot confirmed writing: {text}\n"
            f"Font: {DEFAULT_FONT_NAME}, size={DEFAULT_FONT_SIZE}, char_spacing={DEFAULT_CHAR_SPACING}"
        )

        ok = draw_text_with_robot(
            text,
            output_file=OUTPUT_FILE,
            font_name=DEFAULT_FONT_NAME,
            font_size=DEFAULT_FONT_SIZE,
            start_x=DEFAULT_START_X,
            start_y=DEFAULT_START_Y,
            char_spacing=DEFAULT_CHAR_SPACING,
            word_spacing=DEFAULT_WORD_SPACING,
            line_spacing=DEFAULT_LINE_SPACING,
            x0=DEFAULT_X0,
            y0=DEFAULT_Y0,
            write_h=DEFAULT_WRITE_H,
            dh=DEFAULT_DH,
            image_size=DEFAULT_IMAGE_SIZE,
            speed=DEFAULT_SPEED,
            dry_run=DEFAULT_DRY_RUN
        )

        if ok:
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
        set_status("请先输入或说出要写的文字。\nPlease enter or say text first.")
        return

    draw_text = normalize_draw_text(text)
    unsupported = validate_drawable_text(draw_text)

    if unsupported:
        dpg.set_value("preview_text", draw_text)
        set_status(
            "这些字符目前只能显示，不能用 Hershey 自然绘制：\n"
            + " ".join(unsupported)
            + "\n\n当前支持：\n"
            + get_supported_chars_text()
            + "\n\nThe GUI can display these characters, but Hershey cannot draw them naturally yet."
        )
        return

    dpg.set_value("preview_text", draw_text)
    set_status("已确认文字，机器人准备开始写。\nText confirmed. Robot starts writing.")

    thread = threading.Thread(target=draw_worker, args=(draw_text,))
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
    global asr_controller

    if asr_controller is not None:
        asr_controller.stop()

    dpg.stop_dearpygui()


# ============================================================
# ASR Controller
# Kein ROS2 nötig: ASR schreibt direkt in asr_queue.
# Deine alte ASR-Datei hat über /asr_result nur a/b veröffentlicht;
# hier brauchen wir aber den vollständigen erkannten Text.
# ============================================================

class ASRController:
    def __init__(self):
        self.is_running = False
        self.reconnect_lock = threading.Lock()
        self.conversation = None
        self.mic_thread = None

        self.rms_display_interval = 0.4
        self.last_rms_time = time.time()
        self.silence_count = 0
        self.total_chunks = 0

    def start(self):
        if self.is_running:
            set_status("语音识别已经在运行。\nASR is already running.")
            return

        if not DASHSCOPE_API_KEY:
            set_status(
                "缺少 DASHSCOPE_API_KEY。\n"
                "Bitte zuerst im Terminal setzen:\n"
                "export DASHSCOPE_API_KEY='dein_key'"
            )
            return

        self.is_running = True

        logger = logging.getLogger("dashscope")
        logger.setLevel(logging.WARNING)
        logger.propagate = False

        dashscope.api_key = DASHSCOPE_API_KEY

        try:
            self.conversation = self.create_conversation()
        except Exception as e:
            self.is_running = False
            set_status(f"ASR 启动失败：{e}\nASR start failed: {e}")
            return

        self.mic_thread = threading.Thread(target=self.microphone_thread)
        self.mic_thread.daemon = True
        self.mic_thread.start()

        set_status(
            "语音识别已启动。\n"
            "请说：写 HELLO ROBOT\n"
            "然后可以手动修改，或说：确认 / 开始写"
        )

    def stop(self):
        self.is_running = False

        try:
            if self.conversation is not None:
                self.conversation.close()
        except Exception:
            pass

        self.conversation = None
        set_status("语音识别已停止。\nASR stopped.")

    def create_conversation(self):
        conversation = OmniRealtimeConversation(
            model="qwen3-asr-flash-realtime",
            url="wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
            callback=self.ASRCallback(self)
        )

        conversation.callback.conversation = conversation
        conversation.connect()

        transcription_params = TranscriptionParams(
            language=ASR_LANGUAGE,
            sample_rate=RATE,
            input_audio_format="pcm"
        )

        conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            enable_input_audio_transcription=True,
            transcription_params=transcription_params
        )

        return conversation

    def reconnect_asr(self):
        with self.reconnect_lock:
            if not self.is_running:
                return False

            set_status("ASR 连接已关闭，正在重连...\nASR connection closed. Reconnecting...")

            try:
                if self.conversation is not None:
                    self.conversation.close()
            except Exception:
                pass

            time.sleep(1)

            try:
                self.conversation = self.create_conversation()
                set_status("ASR 重连成功。\nASR reconnected.")
                return True
            except Exception as e:
                set_status(f"ASR 重连失败：{e}\nASR reconnect failed: {e}")
                return False

    def calculate_rms(self, audio_data):
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_array ** 2))
        return rms, audio_array

    def apply_silence_filter(self, audio_array, rms):
        if rms < VOLUME_THRESHOLD:
            silenced_array = np.zeros_like(audio_array, dtype=np.int16)
            return silenced_array.tobytes(), True

        return audio_array.astype(np.int16).tobytes(), False
    
    def calculate_rms(self, audio_data):
        """
        Berechnet die Lautstärke des aktuellen Audio-Chunks.
        """
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_array ** 2))
        return rms, audio_array


    def apply_silence_filter(self, audio_array, rms):
        """
        Wenn die Lautstärke unter VOLUME_THRESHOLD liegt,
        wird der Audio-Chunk durch Stille ersetzt.
        """
        if rms < VOLUME_THRESHOLD:
            silenced_array = np.zeros_like(audio_array, dtype=np.int16)
            return silenced_array.tobytes(), True

        return audio_array.astype(np.int16).tobytes(), False

    def microphone_thread(self):
        p = pyaudio.PyAudio()
        stream = None

        try:
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK
            )

            print("🎤 ASR microphone started.")

            while self.is_running:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    rms, audio_array = self.calculate_rms(data)
                    filtered_audio, is_silenced = self.apply_silence_filter(audio_array, rms)

                    current_time = time.time()
                    if current_time - self.last_rms_time >= self.rms_display_interval:
                        print(
                            f"\rASR RMS: {rms:6.0f} "
                            f"{'filtered' if is_silenced else 'passed'} "
                            f"(threshold={VOLUME_THRESHOLD})",
                            end="",
                            flush=True
                        )
                        self.last_rms_time = current_time

                    audio_b64 = base64.b64encode(filtered_audio).decode("ascii")
                    
                    try:
                        if self.conversation is not None:
                            self.conversation.append_audio(audio_b64)
                    except Exception as e:
                        print(f"\n❌ ASR send error: {e}")
                        ok = self.reconnect_asr()
                        if not ok:
                            time.sleep(2)
                        continue

                except Exception as e:
                    print(f"\n❌ Microphone read error: {e}")
                    time.sleep(1)
                    continue

        finally:
            try:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
            except Exception:
                pass

            try:
                p.terminate()
            except Exception:
                pass

            print("\n🎤 ASR microphone stopped.")

    def handle_final_text(self, text):
        text = text.strip()

        if text == "":
            return

        print(f"\n🎤 ASR final text: {text}")

        action, payload = parse_voice_command(text)
        asr_queue.put((action, payload, text))

    class ASRCallback(OmniRealtimeCallback):
        def __init__(self, controller):
            self.controller = controller
            self.conversation = None

        def on_open(self):
            set_status("ASR 连接已打开。\nASR connection opened.")

        def on_close(self, code, msg):
            set_status(f"ASR 连接关闭：code={code}, msg={msg}")

        def on_event(self, response):
            try:
                if response["type"] == "conversation.item.input_audio_transcription.completed":
                    text = response["transcript"]
                    self.controller.handle_final_text(text)
            except Exception as e:
                set_status(f"ASR 事件处理异常：{e}\nASR event error: {e}")


# ============================================================
# GUI ASR callbacks
# ============================================================

def start_asr_callback(sender=None, app_data=None):
    global asr_controller

    if asr_controller is None:
        asr_controller = ASRController()

    asr_controller.start()


def stop_asr_callback(sender=None, app_data=None):
    global asr_controller

    if asr_controller is not None:
        asr_controller.stop()


def update_gui_from_queue():
    while not status_queue.empty():
        text = status_queue.get()
        dpg.set_value("status_text", text)

    while not asr_queue.empty():
        action, payload, raw_text = asr_queue.get()

        #dpg.set_value("asr_text", raw_text)

        if action in ["text", "raw_text"]:
            payload = convert_spoken_newlines(payload)
            draw_text = normalize_draw_text(payload)
            dpg.set_value("input_text", draw_text)
            dpg.set_value("preview_text", draw_text)
            set_status(
                "识别到要写的内容：\n"
                + draw_text
                + "\n\n你可以手动修改，或说：确认 / 开始写。"
            )

        elif action == "confirm":
            set_status("收到确认语音，准备写当前输入框内容。\nVoice confirmed. Writing current input.")
            start_writing_callback()

        elif action == "clear":
            clear_callback()

        elif action == "exit":
            set_status("收到语音命令：退出程序。\nVoice command: Exit.")
            exit_callback()


# ============================================================
# Main GUI
# ============================================================

def main():
    dpg.create_context()

    # ============================================================
    # Font: wichtig gegen ??? bei chinesischen Zeichen
    # ============================================================

    default_font = None
    small_font = None

    if os.path.exists(font_path):
        with dpg.font_registry():
            with dpg.font(font_path, size=30) as default_font:
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)

            with dpg.font(font_path, size=22) as small_font:
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)

    # ============================================================
    # Theme ähnlich gui_node.py
    # ============================================================

    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(
                dpg.mvThemeCol_WindowBg,
                white_color,
                category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_Text,
                pku_red_color,
                category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_Button,
                white_color,
                category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_style(
                dpg.mvStyleVar_FrameBorderSize,
                3,
                category=dpg.mvThemeCat_Core
            )

    dpg.bind_theme(global_theme)

    with dpg.theme() as input_theme:
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(
                dpg.mvThemeCol_Text,
                (255, 255, 255),
                category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_FrameBg,
                pku_red_color,
                category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_FrameBgHovered,
                pku_red_color,
                category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_FrameBgActive,
                pku_red_color,
                category=dpg.mvThemeCat_Core
            )

    # ============================================================
    # Main window
    # ============================================================

    with dpg.window(
        tag="entry window",
        label="entry window",
        width=screen_width,
        height=screen_height,
        pos=(0, 0)
    ):
        dpg.add_text(
            default_value="请说出或输入要写的内容 / Say or type what the robot should write",
            tag="main_prompt",
            pos=[40, 30]
        )

        dpg.add_text(
            default_value=(
                "GUI 会显示识别结果，可以手动修改\n"
                "说：确认 / 开始写，或者点击 Start Writing\n\n"
                #"当前支持绘制 / Supported characters: Eng Alph, Numbers,\n"
                + get_supported_chars_text()
            ),
            tag="sub_prompt",
            pos=[40, 80],
            wrap=1150
        )


        dpg.add_input_text(
            tag="input_text",
            hint='Example: hello robot 2026!',
            width=750,
            height=70,
            pos=[40, 230],
            multiline=True
        )

        dpg.add_button(
            label="启动语音识别 / Start ASR",
            tag="start_asr_button",
            width=370,
            height=70,
            pos=[840, 150],
            callback=start_asr_callback
        )

        dpg.add_button(
            label="停止语音识别 / Stop ASR",
            tag="stop_asr_button",
            width=370,
            height=70,
            pos=[840, 230],
            callback=stop_asr_callback
        )

        dpg.add_button(
            label="开始写字 / Start Writing",
            tag="start_button",
            width=400,
            height=70,
            pos=[40, 330],
            callback=start_writing_callback
        )

        dpg.add_button(
            label="清空 / Clear",
            tag="clear_button",
            width=200,
            height=70,
            pos=[470, 330],
            callback=clear_callback
        )

        dpg.add_button(
            label="退出 / Exit",
            tag="exit_button",
            width=180,
            height=70,
            pos=[700, 330],
            callback=exit_callback
        )

        dpg.add_text(
            default_value="预览 / Preview:",
            tag="preview_label",
            pos=[40, 425]
        )

        dpg.add_text(
            default_value="",
            tag="preview_text",
            pos=[40, 460],
            wrap=1100
        )

        dpg.add_text(
            default_value="状态 / Status:",
            tag="status_label",
            pos=[40, 525]
        )

        dpg.add_text(
            default_value="等待输入或语音识别 / Waiting for input or ASR.",
            tag="status_text",
            pos=[40, 560],
            wrap=1100
        )

        if default_font is not None:
            dpg.bind_font(default_font)

        if small_font is not None:
            dpg.bind_item_font("sub_prompt", small_font)
            #dpg.bind_item_font("asr_label", small_font)
            #dpg.bind_item_font("asr_text", small_font)
            dpg.bind_item_font("input_text", small_font)
            dpg.bind_item_font("preview_text", small_font)
            dpg.bind_item_font("status_text", small_font)

        dpg.bind_item_theme("input_text", input_theme)

    dpg.create_viewport(
        title="Robot Writing GUI with ASR",
        width=screen_width,
        height=screen_height
    )

    dpg.setup_dearpygui()
    dpg.toggle_viewport_fullscreen()
    dpg.show_viewport()
    dpg.set_primary_window("entry window", True)

    start_asr_callback()

    while dpg.is_dearpygui_running():
        update_gui_from_queue()
        dpg.render_dearpygui_frame()
        time.sleep(0.01)

    if asr_controller is not None:
        asr_controller.stop()

    dpg.destroy_context()


if __name__ == "__main__":
    main()
