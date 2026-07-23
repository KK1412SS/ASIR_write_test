import base64
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

import dashscope
import dearpygui.dearpygui as dpg
import numpy as np
import pyaudio
try:
    import cv2 as cv
except Exception:
    cv = None
try:
    import rclpy
    from cv_bridge import CvBridge
    from rclpy.node import Node
    from sensor_msgs.msg import Image as RosImage
    from std_msgs.msg import String as RosString
    ROS2_AVAILABLE = True
except Exception:
    rclpy = None
    CvBridge = None
    Node = None
    RosImage = None
    RosString = None
    ROS2_AVAILABLE = False
from dashscope.audio.qwen_omni import (
    MultiModality,
    OmniRealtimeCallback,
    OmniRealtimeConversation,
)
from dashscope.audio.qwen_omni.omni_realtime import TranscriptionParams

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
success_button_color = (73, 121, 95)
success_button_hover_color = (87, 141, 110)
success_button_active_color = (60, 102, 80)

OUTPUT_FILE_ENGLISH = "./output/text_trail.txt"
OUTPUT_FILE_CHINESE = "./output/text_trail_chinese.txt"
DRAW_RESULTS_DIR = "./results"
DRAW_CAPTURE_DIR = "./results"

MODE_ENGLISH = "English Strokes"
MODE_CHINESE = "Chinese Strokes"
WRITING_MODES = [MODE_ENGLISH, MODE_CHINESE]
AVAILABLE_CHINESE_FONT_NAMES = [
    font_name
    for font_name in SUPPORTED_CHINESE_FONT_NAMES
    if (Path(__file__).resolve().parent / "fonts" / "chinese" / f"{font_name}.json").is_file()
]
CHINESE_FONT_AVAILABLE = bool(AVAILABLE_CHINESE_FONT_NAMES)

SCREEN_HOME = "home"
SCREEN_WRITE = "write"
SCREEN_DRAW = "draw"

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

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
ASR_LANGUAGE = os.environ.get("AISR_ASR_LANGUAGE", "").strip()
ASR_MODEL = os.environ.get("AISR_ASR_MODEL", "qwen3-asr-flash-realtime")
ASR_URL = os.environ.get("AISR_ASR_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime")
AISR_SERVER_URL = os.environ.get("AISR_SERVER_URL", "http://localhost:5555")
VOLUME_THRESHOLD = 400
CAMERA_BACKEND = os.environ.get("AISR_CAMERA_BACKEND", "auto").strip().lower()
DRAW_BACKEND = os.environ.get("AISR_DRAW_BACKEND", "auto").strip().lower()
ROS_IMAGE_TOPIC = os.environ.get(
    "AISR_ROS_IMAGE_TOPIC",
    "/camera/realsense2_camera_node/color/image_raw",
).strip()
ROS_PHOTO_TOPIC = os.environ.get("AISR_ROS_PHOTO_TOPIC", "/photo_msg").strip()
ROS_DRAW_TOPIC = os.environ.get("AISR_ROS_DRAW_TOPIC", "/draw_msg").strip()
ROS_FINISH_TOPIC = os.environ.get("AISR_ROS_FINISH_TOPIC", "/finish").strip()
ROS_PHOTO_SIGNAL = os.environ.get("AISR_ROS_PHOTO_SIGNAL", "S").strip() or "S"
ROS_DRAW_SIGNAL = os.environ.get("AISR_ROS_DRAW_SIGNAL", "l").strip() or "l"
DRAW_FINISH_TIMEOUT_SECONDS = int(os.environ.get("AISR_DRAW_FINISH_TIMEOUT_SECONDS", "900"))

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 3200

DRAW_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DRAW_EXCLUDED_PREFIXES = ("flipped_",)
DRAW_PREVIEW_WIDTH = 420
DRAW_PREVIEW_HEIGHT = 300

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

HOME_WRITE_WORDS = [
    "写字",
    "写",
    "写中文",
    "写英文",
    "书写",
    "write",
    "writing",
    "go to write",
    "open writing",
    "start writing",
    "schreiben",
    "schreib",
]

HOME_DRAW_WORDS = [
    "画画",
    "画",
    "绘画",
    "素描",
    "malen",
    "zeichnen",
    "draw",
    "drawing",
    "open drawing",
    "start drawing",
]

HOME_WORDS = [
    "首页",
    "主页",
    "home",
    "main menu",
    "start screen",
]

BACK_WORDS = [
    "返回",
    "回去",
    "zuruck",
    "zurück",
    "back",
    "go back",
]

EXIT_WORDS = [
    "退出",
    "关闭程序",
    "结束程序",
    "exit",
    "quit",
    "close program",
]

CONFIRM_WORDS = [
    "确认",
    "确定",
    "可以写",
    "开始写",
    "开始写字",
    "写吧",
    "对",
    "好的",
    "yes",
    "start writing",
    "write it",
    "ok",
    "okay",
]

CLEAR_WORDS = [
    "清空",
    "取消",
    "重来",
    "重新来",
    "删除",
    "不要了",
    "clear",
    "cancel",
    "redo",
]

CHINESE_MODE_WORDS = [
    "中文",
    "中文模式",
    "汉字模式",
    "写中文",
    "chinese mode",
    "switch to chinese",
    "write chinese",
]

ENGLISH_MODE_WORDS = [
    "英文",
    "英文模式",
    "英语模式",
    "写英文",
    "english mode",
    "switch to english",
    "write english",
]

WRITE_PREFIXES = [
    "写下",
    "写字",
    "写",
    "请写",
    "我要写",
    "帮我写",
    "please write",
    "write down",
    "write",
    "schreib",
    "schreibe",
]

LATEST_IMAGE_WORDS = [
    "最新图片",
    "最近图片",
    "最新照片",
    "最近照片",
    "latest image",
    "latest photo",
    "use latest image",
]

DRAW_GENERATE_WORDS = [
    "生成素描",
    "生成轨迹",
    "生成绘画",
    "generate sketch",
    "generate drawing",
    "prepare drawing",
]

DRAW_START_WORDS = [
    "开始画画",
    "开始绘画",
    "开始画",
    "draw now",
    "start drawing now",
    "draw it",
    "mal jetzt",
]

DRAW_FLIP_ON_WORDS = [
    "翻转图片",
    "左右翻转",
    "开启翻转",
    "flip image",
    "turn on flip",
]

DRAW_FLIP_OFF_WORDS = [
    "关闭翻转",
    "不要翻转",
    "不用翻转",
    "stop flipping",
    "turn off flip",
]

DRAW_TAKE_PHOTO_WORDS = [
    "拍照",
    "拍一张",
    "拍照片",
    "take photo",
    "take a photo",
    "take picture",
    "photo now",
]

DRAW_RETAKE_WORDS = [
    "重新拍照",
    "再拍一张",
    "重拍",
    "redo photo",
    "retake photo",
    "retake picture",
    "take another photo",
]

DRAW_CONFIRM_WORDS = [
    "确认画画",
    "确认开始",
    "开始画画",
    "开始绘制",
    "好的开始",
    "confirm drawing",
    "confirm draw",
    "yes draw",
    "start painting",
    "start drawing",
]

EXPLICIT_GO_WRITE_WORDS = [
    "go to write",
    "open writing",
    "switch to writing",
    "打开写字界面",
    "去写字界面",
]

EXPLICIT_GO_DRAW_WORDS = [
    "go to draw",
    "open drawing",
    "switch to drawing",
    "打开画画界面",
    "去画画界面",
]


current_screen = SCREEN_HOME
active_job = None
status_queue = queue.Queue()
asr_queue = queue.Queue()
draw_state_dirty = True
asr_controller = None
camera_controller = None
legacy_ros_bridge = None
draw_state = {
    "selected_image_path": "",
    "captured_image_path": "",
    "generated_image_path": "",
    "generated_traj_path": "",
    "flip_image": True,
    "phase": "camera",
}

VOICE_FILE_MAP = {
    "confirm": "confirm.wav",
    "countdown_3": "3.wav",
    "countdown_2": "2.wav",
    "countdown_1": "1.wav",
    "sketch_success": "success_photo_new.wav",
    "sketch_fail": "fail_photo_new.wav",
    "draw_wait": "wait_draw_new.wav",
    "draw_finish": "finish_new.wav",
}


def list_voice_dir_candidates():
    base_dir = Path(__file__).resolve().parent
    env_dir = os.environ.get("AISR_VOICE_DIR", "").strip()
    return [
        Path(env_dir).expanduser() if env_dir else None,
        base_dir / "voice",
        Path("/home/acir/TinyWings_AISR/voice"),
    ]


def find_voice_file(key):
    filename = VOICE_FILE_MAP.get(key, "")
    if not filename:
        return None

    for directory in list_voice_dir_candidates():
        if directory is None:
            continue
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def play_wav_file(path, volume=1.5):
    audio = pyaudio.PyAudio()
    stream = None

    try:
        with wave.open(str(path), "rb") as wf:
            sample_width = wf.getsampwidth()
            channels = wf.getnchannels()
            rate = wf.getframerate()

            stream = audio.open(
                format=audio.get_format_from_width(sample_width),
                channels=channels,
                rate=rate,
                frames_per_buffer=1024,
                output=True,
            )

            silence_frames = int(rate * 0.08)
            silence_bytes = b"\x00" * silence_frames * channels * sample_width
            stream.write(silence_bytes)

            while True:
                frames = wf.readframes(1024)
                if not frames:
                    break

                audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
                if volume != 1.0:
                    audio_data = audio_data * volume
                    limit = 30000.0
                    audio_data = limit * np.tanh(audio_data / limit)

                stream.write(audio_data.astype(np.int16).tobytes())

            tail_silence_frames = int(rate * 0.15)
            tail_silence_bytes = b"\x00" * tail_silence_frames * channels * sample_width
            stream.write(tail_silence_bytes)
            time.sleep(0.05)

    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        audio.terminate()


def play_feedback(key, volume=1.5, asynchronous=True):
    path = find_voice_file(key)
    if path is None:
        return False

    if asynchronous:
        thread = threading.Thread(
            target=play_wav_file,
            args=(path, volume),
            daemon=True,
        )
        thread.start()
    else:
        play_wav_file(path, volume)
    return True


def should_use_ros_camera_backend():
    return ROS2_AVAILABLE and CAMERA_BACKEND in {"auto", "ros"}


def should_use_ros_draw_backend():
    return ROS2_AVAILABLE and DRAW_BACKEND in {"auto", "ros"}


def get_camera_backend_label():
    if should_use_ros_camera_backend():
        return f"ROS topic: {ROS_IMAGE_TOPIC}"
    camera_index = os.environ.get("AISR_CAMERA_INDEX", "0")
    return f"OpenCV camera index: {camera_index}"


def get_draw_backend_label():
    if should_use_ros_draw_backend():
        return f"ROS draw: {ROS_DRAW_TOPIC} -> {ROS_FINISH_TOPIC}"
    return "Local draw_trail execution"


if ROS2_AVAILABLE:
    class LegacyRosBridgeNode(Node):
        def __init__(self):
            super().__init__("aisr_gui_bridge")
            self.bridge = CvBridge()
            self.lock = threading.Lock()
            self.latest_frame = None
            self.latest_preview_frame = None
            self.draw_finish_event = threading.Event()
            self.image_subscriber = self.create_subscription(
                RosImage,
                ROS_IMAGE_TOPIC,
                self.image_callback,
                10,
            )
            self.finish_subscriber = self.create_subscription(
                RosString,
                ROS_FINISH_TOPIC,
                self.finish_callback,
                10,
            )
            self.photo_publisher = self.create_publisher(RosString, ROS_PHOTO_TOPIC, 10)
            self.draw_publisher = self.create_publisher(RosString, ROS_DRAW_TOPIC, 10)

        def image_callback(self, msg):
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            preview_frame = frame.copy()

            if cv is not None:
                height, width = preview_frame.shape[:2]
                x1 = int(width * 0.41)
                y1 = int(height * 0.31)
                x2 = int(width * 0.57)
                y2 = int(height * 0.59)
                cv.rectangle(preview_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            with self.lock:
                self.latest_frame = frame.copy()
                self.latest_preview_frame = preview_frame

        def finish_callback(self, msg):
            self.draw_finish_event.set()

        def get_latest_frame(self):
            with self.lock:
                if self.latest_frame is None:
                    return None
                return self.latest_frame.copy()

        def get_latest_preview_frame(self):
            with self.lock:
                if self.latest_preview_frame is None:
                    return None
                return self.latest_preview_frame.copy()

        def notify_photo_prepare(self):
            self.photo_publisher.publish(RosString(data=ROS_PHOTO_SIGNAL))

        def request_draw(self):
            self.draw_finish_event.clear()
            self.draw_publisher.publish(RosString(data=ROS_DRAW_SIGNAL))

        def wait_for_draw_finish(self, timeout_seconds):
            return self.draw_finish_event.wait(timeout_seconds)


class LegacyRosController:
    def __init__(self):
        self.node = None
        self.thread = None
        self.running = False
        self.did_init = False

    def start(self):
        if not ROS2_AVAILABLE:
            return False, "ROS 2 dependencies are not available in this Python environment."

        if self.running and self.node is not None:
            return True, ""

        try:
            if not rclpy.ok():
                rclpy.init(args=None)
                self.did_init = True
        except Exception as exc:
            return False, f"ROS 2 init failed: {exc}"

        try:
            self.node = LegacyRosBridgeNode()
        except Exception as exc:
            if self.did_init and rclpy.ok():
                rclpy.shutdown()
                self.did_init = False
            return False, f"ROS 2 bridge creation failed: {exc}"

        self.running = True
        self.thread = threading.Thread(target=self._spin_loop, daemon=True)
        self.thread.start()
        return True, ""

    def _spin_loop(self):
        while self.running and self.node is not None:
            try:
                rclpy.spin_once(self.node, timeout_sec=0.1)
            except Exception:
                time.sleep(0.1)

    def get_latest_frame(self):
        if self.node is None:
            return None
        return self.node.get_latest_preview_frame()

    def capture_photo(self, output_dir):
        if self.node is None:
            raise RuntimeError("ROS camera bridge is not running.")

        frame = self.node.get_latest_frame()
        if frame is None:
            raise RuntimeError("ROS camera topic has not delivered a frame yet.")

        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time())
        output_path = os.path.join(output_dir, f"{timestamp}_cam.jpg")
        if cv is None or not cv.imwrite(output_path, frame):
            raise RuntimeError("Could not save the ROS camera photo.")
        return output_path

    def prepare_capture(self):
        if self.node is not None:
            self.node.notify_photo_prepare()

    def request_draw(self):
        if self.node is None:
            raise RuntimeError("ROS draw bridge is not running.")
        self.node.request_draw()

    def wait_for_draw_finish(self, timeout_seconds):
        if self.node is None:
            raise RuntimeError("ROS draw bridge is not running.")
        return self.node.wait_for_draw_finish(timeout_seconds)

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
        if self.node is not None:
            try:
                self.node.destroy_node()
            except Exception:
                pass
            self.node = None
        if self.did_init and rclpy is not None:
            try:
                if rclpy.ok():
                    rclpy.shutdown()
            except Exception:
                pass
            self.did_init = False


class CameraController:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.capture = None
        self.thread = None
        self.running = False
        self.lock = threading.Lock()
        self.latest_frame = None

    def start(self):
        if cv is None:
            return False, "OpenCV is not available in this Python environment."

        if self.running:
            return True, ""

        capture = cv.VideoCapture(self.camera_index)
        if not capture.isOpened():
            try:
                capture.release()
            except Exception:
                pass
            return False, f"Could not open camera index {self.camera_index}."

        self.capture = capture
        self.running = True
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()
        return True, ""

    def _reader_loop(self):
        while self.running and self.capture is not None:
            ok, frame = self.capture.read()
            if ok and frame is not None:
                with self.lock:
                    self.latest_frame = frame.copy()
            else:
                time.sleep(0.05)

    def get_latest_frame(self):
        with self.lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def capture_photo(self, output_dir):
        frame = self.get_latest_frame()
        if frame is None:
            raise RuntimeError("Camera is not ready yet.")

        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time())
        output_path = os.path.join(output_dir, f"{timestamp}_cam.jpg")
        if not cv.imwrite(output_path, frame):
            raise RuntimeError("Could not save the captured photo.")
        return output_path

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
        if self.capture is not None:
            try:
                self.capture.release()
            except Exception:
                pass
            self.capture = None


def set_status(text):
    status_queue.put(text)


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
            "No compatible GUI font was found. Checked project fonts, legacy paths, and common system font locations.",
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


def get_compact_gui_font_message(gui_font_message):
    if gui_font_message.startswith("GUI font: "):
        font_path = gui_font_message[len("GUI font: "):].split(" (", 1)[0]
        return f"UI font: {Path(font_path).name}"
    return gui_font_message


def get_current_mode():
    if dpg.does_item_exist("mode_select"):
        return dpg.get_value("mode_select")
    return MODE_ENGLISH


def get_current_chinese_font():
    if dpg.does_item_exist("font_select"):
        return dpg.get_value("font_select")
    return DEFAULT_CHINESE_FONT


def normalize_draw_text(text, mode):
    if mode == MODE_CHINESE:
        return text
    return text.upper()


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
        "Available Chinese sources in this GUI: hanziwriter, animcjk_zhhans."
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


def get_mode_title(mode):
    if mode == MODE_CHINESE:
        return "Chinese Stroke Writer"
    return "English Stroke Writer"


def get_mode_note(mode, font_name):
    if mode == MODE_CHINESE:
        glyph_count = len(list_supported_chars(font_name)) if CHINESE_FONT_AVAILABLE else 0
        return (
            f"Chinese stroke source: {font_name}\n"
            f"Regular style · {glyph_count} cached glyphs\n"
            "Voice: say 中文模式 / English mode, 写 你好, 确认, 清空, 返回首页"
        )
    return (
        "Robot output uses uppercase Latin strokes.\n"
        "Voice: say English mode, write hello robot, start writing, clear, go home"
    )


def convert_spoken_newlines(text):
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


def mark_draw_state_dirty():
    global draw_state_dirty
    draw_state_dirty = True


def set_draw_image_path(path):
    previous_path = draw_state.get("selected_image_path", "")
    draw_state["selected_image_path"] = path
    draw_state["captured_image_path"] = path
    if path != previous_path:
        draw_state["generated_image_path"] = ""
        draw_state["generated_traj_path"] = ""
    mark_draw_state_dirty()


def set_generated_draw_outputs(image_path="", traj_path=""):
    draw_state["generated_image_path"] = image_path
    draw_state["generated_traj_path"] = traj_path
    mark_draw_state_dirty()


def set_draw_phase(phase):
    draw_state["phase"] = phase
    mark_draw_state_dirty()


def set_draw_flip_enabled(enabled):
    enabled = bool(enabled)
    previous_value = draw_state.get("flip_image", True)
    draw_state["flip_image"] = enabled
    if enabled != previous_value:
        draw_state["generated_image_path"] = ""
        draw_state["generated_traj_path"] = ""
    if dpg.does_item_exist("draw_flip_checkbox"):
        dpg.set_value("draw_flip_checkbox", enabled)
    mark_draw_state_dirty()


def make_blank_preview_frame():
    return np.full((DRAW_PREVIEW_HEIGHT, DRAW_PREVIEW_WIDTH, 3), 235, dtype=np.uint8)


def frame_to_texture_data(frame):
    if cv is None or frame is None:
        frame = make_blank_preview_frame()
    else:
        frame = cv.resize(frame, (DRAW_PREVIEW_WIDTH, DRAW_PREVIEW_HEIGHT))

    rgba = cv.cvtColor(frame, cv.COLOR_BGR2RGBA) if cv is not None else np.dstack(
        [frame, np.full((DRAW_PREVIEW_HEIGHT, DRAW_PREVIEW_WIDTH), 255, dtype=np.uint8)]
    )
    return np.true_divide(rgba.astype(np.float32).ravel(), 255.0)


def load_preview_frame_from_image(path):
    if cv is None or not path or not os.path.exists(path):
        return make_blank_preview_frame()

    frame = cv.imread(path)
    if frame is None:
        return make_blank_preview_frame()
    return frame


def ensure_legacy_ros_bridge():
    global legacy_ros_bridge

    if legacy_ros_bridge is None:
        legacy_ros_bridge = LegacyRosController()
    return legacy_ros_bridge


def ensure_camera_controller():
    global camera_controller, legacy_ros_bridge

    if camera_controller is None:
        if should_use_ros_camera_backend():
            legacy_ros_bridge = ensure_legacy_ros_bridge()
            camera_controller = legacy_ros_bridge
        else:
            camera_index = int(os.environ.get("AISR_CAMERA_INDEX", "0"))
            camera_controller = CameraController(camera_index=camera_index)
    return camera_controller


def ensure_camera_started():
    controller = ensure_camera_controller()
    ok, message = controller.start()
    if not ok and message:
        set_status(
            message
            + "\nCamera preview is unavailable. You can still use the fallback latest-image workflow."
        )
    return ok


def ensure_draw_backend_ready():
    if not should_use_ros_draw_backend():
        return True

    bridge = ensure_legacy_ros_bridge()
    ok, message = bridge.start()
    if not ok and message:
        set_status(
            message
            + "\nFalling back to the local draw execution path if available."
        )
    return ok


def reset_draw_workflow(keep_selected_image=False):
    if not keep_selected_image:
        draw_state["selected_image_path"] = ""
        draw_state["captured_image_path"] = ""
    draw_state["generated_image_path"] = ""
    draw_state["generated_traj_path"] = ""
    draw_state["phase"] = "camera"
    mark_draw_state_dirty()


def refresh_draw_preview():
    selected_image_path = draw_state.get("selected_image_path", "")
    captured_image_path = draw_state.get("captured_image_path", "")
    generated_image_path = draw_state.get("generated_image_path", "")
    generated_traj_path = draw_state.get("generated_traj_path", "")
    flip_image = draw_state.get("flip_image", True)
    phase = draw_state.get("phase", "camera")

    selected_preview_path = generated_image_path or captured_image_path or selected_image_path

    if phase in {"camera", "countdown", "capturing", "generating"}:
        camera_ready = ensure_camera_started()
        latest_frame = ensure_camera_controller().get_latest_frame() if camera_ready else None
        texture_data = frame_to_texture_data(latest_frame)
    else:
        texture_data = frame_to_texture_data(load_preview_frame_from_image(selected_preview_path))

    if dpg.does_item_exist("draw_preview_texture"):
        dpg.set_value("draw_preview_texture", texture_data)

    phase_text_map = {
        "camera": "Camera live view. Say take photo / 拍照.",
        "countdown": "Photo countdown is running.",
        "capturing": "Capturing the current camera frame.",
        "generating": "Generating sketch from the captured photo.",
        "review": "Review the sketch. Say retake photo or confirm draw.",
        "drawing": "Robot drawing is in progress.",
        "done": "Drawing finished. You can retake a new photo.",
    }

    preview_lines = [
        f"Phase: {phase}",
        phase_text_map.get(phase, "Draw workflow ready."),
        f"Camera backend: {get_camera_backend_label()}",
        f"Draw backend: {get_draw_backend_label()}",
        f"Captured photo: {captured_image_path or '(none)'}",
        f"Flip before upload: {'ON' if flip_image else 'OFF'}",
        f"Generated sketch: {generated_image_path or '(not generated)'}",
        f"Trajectory: {generated_traj_path or '(not generated)'}",
        "",
        "Voice commands:",
        "take photo / 拍照",
        "retake photo / 重新拍照",
        "confirm draw / 确认画画",
        "flip image / stop flipping",
        "latest image / 最新图片 (fallback)",
        "go home / 返回首页",
    ]

    if dpg.does_item_exist("draw_preview_text"):
        dpg.set_value("draw_preview_text", "\n".join(preview_lines))


def update_voice_state_text():
    state = "Voice: waiting for start"
    if asr_controller is not None and asr_controller.is_running:
        state = "Voice: listening (Chinese + English)"
    elif DASHSCOPE_API_KEY:
        state = "Voice: stopped"
    else:
        state = "Voice: missing DASHSCOPE_API_KEY"

    if dpg.does_item_exist("voice_state_text"):
        dpg.set_value("voice_state_text", state)


def update_all_status_texts(text):
    for tag in ["home_status_text", "write_status_text", "draw_status_text"]:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, text)


def find_latest_image_path():
    base_dir = Path(__file__).resolve().parent
    search_dirs = [
        base_dir,
        base_dir / "results",
        base_dir / "temp_images",
    ]

    candidates = []
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in DRAW_IMAGE_EXTENSIONS:
                continue
            if path.name.startswith(DRAW_EXCLUDED_PREFIXES):
                continue
            candidates.append(path)

    if not candidates:
        return ""

    latest_path = max(candidates, key=lambda candidate: candidate.stat().st_mtime)
    return str(latest_path)


def set_screen(screen):
    global current_screen
    current_screen = screen

    if dpg.does_item_exist("home_screen"):
        dpg.configure_item("home_screen", show=(screen == SCREEN_HOME))
    if dpg.does_item_exist("write_screen"):
        dpg.configure_item("write_screen", show=(screen == SCREEN_WRITE))
    if dpg.does_item_exist("draw_screen"):
        dpg.configure_item("draw_screen", show=(screen == SCREEN_DRAW))

    if screen == SCREEN_WRITE:
        refresh_mode_ui()
    if screen == SCREEN_DRAW:
        ensure_camera_started()
        refresh_draw_preview()


def is_busy():
    return active_job is not None


def refresh_mode_ui(sender=None, app_data=None):
    mode = get_current_mode()
    font_name = get_current_chinese_font()

    if dpg.does_item_exist("compose_title"):
        dpg.set_value("compose_title", get_mode_title(mode))

    if mode == MODE_CHINESE:
        if dpg.does_item_exist("font_group"):
            dpg.configure_item("font_group", show=True)
        if dpg.does_item_exist("input_text"):
            dpg.configure_item("input_text", hint="Example: 你好，今天快乐！")
        if dpg.does_item_exist("mode_note_text"):
            dpg.set_value("mode_note_text", get_mode_note(mode, font_name))
    else:
        if dpg.does_item_exist("font_group"):
            dpg.configure_item("font_group", show=False)
        if dpg.does_item_exist("input_text"):
            dpg.configure_item("input_text", hint="Example: HELLO & ROBOT 2026!")
        if dpg.does_item_exist("mode_note_text"):
            dpg.set_value("mode_note_text", get_mode_note(mode, font_name))


def select_latest_image_callback(sender=None, app_data=None):
    if is_busy():
        set_status("The robot is busy. Wait before changing the selected image.")
        return

    latest_image_path = find_latest_image_path()
    if not latest_image_path:
        set_status("No local image was found in the project or results folders.")
        return

    start_draw_generation_job(latest_image_path, job_name="draw-latest")


def retake_photo_callback(sender=None, app_data=None):
    if is_busy():
        set_status("The robot is busy. Wait before retaking the photo.")
        return

    reset_draw_workflow(keep_selected_image=False)
    ensure_camera_started()
    set_status("Ready to take a new photo.")


def clear_callback(sender=None, app_data=None):
    if is_busy():
        set_status("A robot task is running. Clear is disabled until it finishes.")
        return

    if dpg.does_item_exist("input_text"):
        dpg.set_value("input_text", "")
    if dpg.does_item_exist("preview_text"):
        dpg.set_value("preview_text", "")
    set_status("Cleared.")


def clear_draw_outputs(clear_selected=False):
    if clear_selected:
        draw_state["selected_image_path"] = ""
    draw_state["generated_image_path"] = ""
    draw_state["generated_traj_path"] = ""
    mark_draw_state_dirty()


def normalize_draw_image_path(image_path):
    raw_path = str(image_path or "").strip().strip('"').strip("'")
    if not raw_path:
        return ""

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return str(path)


def start_draw_generation_job(image_path, job_name="draw-image"):
    global active_job

    if is_busy():
        set_status("The robot is busy. Wait before starting another drawing job.")
        return False

    normalized_path = normalize_draw_image_path(image_path)
    if not normalized_path:
        set_status("No image path is available for sketch generation.")
        return False
    if not os.path.exists(normalized_path):
        set_status(f"Image file not found:\n{normalized_path}")
        return False

    flip_image = dpg.get_value("draw_flip_checkbox") if dpg.does_item_exist("draw_flip_checkbox") else True
    set_draw_flip_enabled(flip_image)
    active_job = job_name
    thread = threading.Thread(
        target=generate_from_existing_image_worker,
        args=(normalized_path, flip_image),
        daemon=True,
    )
    thread.start()
    return True


def go_home_callback(sender=None, app_data=None):
    if is_busy():
        set_status("A robot task is still running. Wait until it finishes before leaving this screen.")
        return
    set_screen(SCREEN_HOME)
    set_status("Returned to the main menu.")


def go_write_callback(sender=None, app_data=None):
    if is_busy() and current_screen == SCREEN_DRAW:
        set_status("Wait for the current drawing task to finish before switching to writing.")
        return
    set_screen(SCREEN_WRITE)
    set_status("Writing screen opened. Voice commands work in Chinese and English.")


def go_draw_callback(sender=None, app_data=None):
    if is_busy() and current_screen == SCREEN_WRITE:
        set_status("Wait for the current writing task to finish before switching to drawing.")
        return
    set_screen(SCREEN_DRAW)
    set_status("Drawing screen opened. Say take photo / 拍照 to create a new sketch.")


def exit_callback(sender=None, app_data=None):
    if asr_controller is not None:
        asr_controller.stop()
    if camera_controller is not None:
        camera_controller.stop()
    if legacy_ros_bridge is not None and legacy_ros_bridge is not camera_controller:
        legacy_ros_bridge.stop()
    dpg.stop_dearpygui()


def draw_worker(text, mode, font_name, dry_run):
    global active_job

    try:
        if mode == MODE_CHINESE:
            set_status(
                f"Checking and extending cached Hanzi strokes ({font_name})..."
            )
            imported, skipped = auto_import_missing_chinese_glyphs(
                text=text,
                font_name=font_name,
                skip_missing=True,
            )
            if imported:
                set_status(
                    "Auto-imported Hanzi: "
                    + "".join(imported)
                )
            unsupported = validate_chinese_text(text, font_name)
            if unsupported:
                raise ValueError(
                    "These Chinese characters could not be imported automatically: "
                    + " ".join(unsupported)
                )

            set_status(
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
            set_status(f"Preparing English writing: {text}")
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
            set_status("Dry run finished. Trail and safety check passed. Robot was not moved.")
        elif ok:
            set_status("Writing finished.")
        else:
            set_status("Writing failed. Robot connection or drawing execution failed.")

    except Exception as exc:
        set_status(f"Writing error: {exc}")

    finally:
        active_job = None


def start_writing_callback(sender=None, app_data=None):
    global active_job

    if is_busy():
        set_status("The robot is already busy.")
        return

    text = dpg.get_value("input_text")
    if text.strip() == "":
        set_status("Please type or say the text first.")
        return

    mode = get_current_mode()
    draw_text = normalize_draw_text(text, mode)
    font_name = get_current_chinese_font()

    if mode == MODE_CHINESE:
        if not CHINESE_FONT_AVAILABLE:
            set_status("No Chinese stroke font data is available in ./fonts/chinese.")
            return
        unsupported = []
    else:
        unsupported = validate_english_text(draw_text)

    if unsupported:
        dpg.set_value("preview_text", draw_text)
        set_status(
            "These characters are not drawable yet:\n"
            + " ".join(unsupported)
            + "\n\nSupported now:\n"
            + get_english_supported_chars_text()
        )
        return

    dpg.set_value("preview_text", draw_text)
    dry_run = dpg.get_value("dry_run_checkbox")
    active_job = "write"

    if dry_run:
        set_status("Starting dry run for the writing path.")
    else:
        set_status("Starting robot writing.")

    thread = threading.Thread(
        target=draw_worker,
        args=(draw_text, mode, font_name, dry_run),
        daemon=True,
    )
    thread.start()


def run_aisr_generation(image_path, flip_image):
    from call_AIsketcher import AISRClient

    client = AISRClient(AISR_SERVER_URL)
    result = client.upload_image(image_path, flip_image)
    if not result or result.get("status") != 200:
        raise RuntimeError("AISR sketch generation failed.")

    os.makedirs(DRAW_RESULTS_DIR, exist_ok=True)
    client.download_result(result, DRAW_RESULTS_DIR)

    image_name = result.get("imgPath", "")
    traj_name = result.get("traiPath", "")
    generated_image_path = os.path.join(DRAW_RESULTS_DIR, image_name) if image_name else ""
    generated_traj_path = os.path.join(DRAW_RESULTS_DIR, traj_name) if traj_name else ""

    if generated_traj_path and not os.path.exists(generated_traj_path):
        raise FileNotFoundError(f"Generated trajectory file not found: {generated_traj_path}")

    return generated_image_path, generated_traj_path


def run_robot_draw_from_traj(traj_path):
    from sign_aisr import uarm_sign_by_aisr

    set_status("Preparing signed trajectory for robot drawing.")
    uarm_sign_by_aisr(traj_path)

    if should_use_ros_draw_backend() and ensure_draw_backend_ready():
        bridge = ensure_legacy_ros_bridge()
        set_status(
            "Signed trajectory is ready.\n"
            f"Starting legacy ROS draw via {ROS_DRAW_TOPIC} and waiting for {ROS_FINISH_TOPIC}."
        )
        bridge.request_draw()
        if not bridge.wait_for_draw_finish(DRAW_FINISH_TIMEOUT_SECONDS):
            raise TimeoutError(
                "Timed out while waiting for the legacy ROS draw completion signal."
            )
        return

    import draw_trail

    draw_trail.trail_text = []
    status = draw_trail.get_draw_mat()
    if status != 1:
        raise RuntimeError("Failed to convert sketch trajectory into robot coordinates.")

    data = np.array(draw_trail.trail_text)
    if data.size == 0:
        raise RuntimeError("No robot trajectory points were generated.")

    data = data.reshape([-1, 3])
    draw_result = draw_trail.draw(data)
    if draw_result == -1:
        raise RuntimeError("Robot draw aborted due to safety checks.")


def generate_from_existing_image_worker(image_path, flip_image):
    global active_job

    try:
        if not image_path:
            raise ValueError("No fallback image is available.")
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        set_draw_image_path(image_path)
        set_draw_phase("generating")
        set_status(
            "Using the latest local image as fallback input.\n"
            f"{image_path}\n"
            f"Flip image: {'ON' if flip_image else 'OFF'}"
        )

        generated_image_path, generated_traj_path = run_aisr_generation(image_path, flip_image)
        set_generated_draw_outputs(generated_image_path, generated_traj_path)
        set_draw_phase("review")
        play_feedback("sketch_success", volume=1.3)
        set_status(
            "Fallback sketch generation finished.\n"
            "If you are satisfied, say confirm draw / 确认画画.\n"
            "If not, retake a new photo."
        )

    except Exception as exc:
        set_draw_phase("camera")
        play_feedback("sketch_fail", volume=1.3)
        set_status(f"Drawing error: {exc}")

    finally:
        active_job = None


def take_photo_and_generate_worker(flip_image):
    global active_job

    try:
        if not ensure_camera_started():
            raise RuntimeError("Camera preview is not available.")

        set_draw_phase("countdown")
        set_status("Preparing to take a photo.")
        play_feedback("confirm", volume=1.2)
        if hasattr(ensure_camera_controller(), "prepare_capture"):
            ensure_camera_controller().prepare_capture()

        for number in [3, 2, 1]:
            set_status(f"Taking photo in {number}...")
            play_feedback(f"countdown_{number}", volume=1.0)
            time.sleep(1.0)

        set_draw_phase("capturing")
        image_path = ensure_camera_controller().capture_photo(DRAW_CAPTURE_DIR)
        set_draw_image_path(image_path)

        set_draw_phase("generating")
        set_status(
            f"Photo taken.\nGenerating sketch from:\n{image_path}\nFlip image: {'ON' if flip_image else 'OFF'}"
        )

        generated_image_path, generated_traj_path = run_aisr_generation(image_path, flip_image)
        set_generated_draw_outputs(generated_image_path, generated_traj_path)
        set_draw_phase("review")
        play_feedback("sketch_success", volume=1.3)
        set_status(
            "Sketch generation finished.\n"
            "If you are satisfied, say confirm draw / 确认画画.\n"
            "If not, say retake photo / 重新拍照."
        )

    except Exception as exc:
        set_draw_phase("camera")
        play_feedback("sketch_fail", volume=1.3)
        set_status(f"Drawing error: {exc}")

    finally:
        active_job = None


def confirm_draw_worker():
    global active_job

    try:
        generated_traj_path = draw_state.get("generated_traj_path", "")
        if not generated_traj_path:
            raise RuntimeError("No generated sketch is ready yet. Take a photo first.")
        if not os.path.exists(generated_traj_path):
            raise FileNotFoundError(f"Generated trajectory file not found: {generated_traj_path}")

        set_draw_phase("drawing")
        set_status("Starting robot drawing from the confirmed sketch.")
        play_feedback("draw_wait", volume=1.2)
        run_robot_draw_from_traj(generated_traj_path)
        set_draw_phase("done")
        play_feedback("draw_finish", volume=1.2)
        set_status("Robot drawing finished. You can retake a new photo at any time.")

    except Exception as exc:
        set_draw_phase("review" if draw_state.get("generated_traj_path") else "camera")
        set_status(f"Drawing error: {exc}")

    finally:
        active_job = None


def take_photo_callback(sender=None, app_data=None):
    global active_job

    if is_busy():
        set_status("The robot is already busy.")
        return

    flip_image = dpg.get_value("draw_flip_checkbox") if dpg.does_item_exist("draw_flip_checkbox") else True
    set_draw_flip_enabled(flip_image)
    active_job = "draw-photo"
    thread = threading.Thread(
        target=take_photo_and_generate_worker,
        args=(flip_image,),
        daemon=True,
    )
    thread.start()


def start_robot_draw_callback(sender=None, app_data=None):
    global active_job

    if is_busy():
        set_status("The robot is already busy.")
        return

    generated_traj_path = draw_state.get("generated_traj_path", "")
    if not generated_traj_path:
        set_status("No generated sketch is ready yet. Take a photo first.")
        return

    active_job = "draw-confirm"
    thread = threading.Thread(
        target=confirm_draw_worker,
        daemon=True,
    )
    thread.start()


def start_asr_callback(sender=None, app_data=None):
    global asr_controller

    if asr_controller is None:
        asr_controller = ASRController()

    asr_controller.start()
    update_voice_state_text()


def stop_asr_callback(sender=None, app_data=None):
    if asr_controller is not None:
        asr_controller.stop()
    update_voice_state_text()


def parse_navigation_voice_command(text):
    normalized = text.lower().strip()

    if any(word in normalized for word in EXIT_WORDS):
        return "exit", None
    if any(word in normalized for word in HOME_WORDS):
        return "go_home", None
    if any(word in normalized for word in BACK_WORDS):
        return "go_home", None

    return None, None


def parse_screen_selection_voice_command(text):
    normalized = text.lower().strip()

    if any(word in normalized for word in HOME_WRITE_WORDS):
        return "go_write", None
    if any(word in normalized for word in HOME_DRAW_WORDS):
        return "go_draw", None

    return None, None


def parse_write_voice_command(text):
    raw = text.strip()
    if not raw:
        return None, None

    lower_raw = raw.lower()

    for word in CHINESE_MODE_WORDS:
        if word.lower() in lower_raw:
            return "switch_chinese", None

    for word in ENGLISH_MODE_WORDS:
        if word.lower() in lower_raw:
            return "switch_english", None

    for word in CONFIRM_WORDS:
        if word.lower() in lower_raw:
            return "confirm_write", None

    for word in CLEAR_WORDS:
        if word.lower() in lower_raw:
            return "clear_write", None

    for word in EXPLICIT_GO_DRAW_WORDS:
        if word.lower() in lower_raw:
            return "go_draw", None

    for prefix in WRITE_PREFIXES:
        if raw.startswith(prefix):
            payload = raw[len(prefix):].strip()
            if payload:
                return "set_write_text", payload

    return "set_write_text", raw


def parse_draw_voice_command(text):
    raw = text.strip()
    if not raw:
        return None, None

    lower_raw = raw.lower()

    for word in DRAW_TAKE_PHOTO_WORDS:
        if word.lower() in lower_raw:
            return "draw_take_photo", None

    for word in DRAW_RETAKE_WORDS:
        if word.lower() in lower_raw:
            return "draw_retake_photo", None

    for word in DRAW_CONFIRM_WORDS:
        if word.lower() in lower_raw:
            return "draw_confirm", None

    for word in DRAW_GENERATE_WORDS:
        if word.lower() in lower_raw:
            return "draw_regenerate", None

    for word in LATEST_IMAGE_WORDS:
        if word.lower() in lower_raw:
            return "draw_latest_image", None

    for word in DRAW_FLIP_ON_WORDS:
        if word.lower() in lower_raw:
            return "draw_flip_on", None

    for word in DRAW_FLIP_OFF_WORDS:
        if word.lower() in lower_raw:
            return "draw_flip_off", None

    for word in DRAW_START_WORDS:
        if word.lower() in lower_raw:
            return "draw_confirm", None

    for word in EXPLICIT_GO_WRITE_WORDS:
        if word.lower() in lower_raw:
            return "go_write", None

    if any(ext in lower_raw for ext in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]):
        return "draw_path_text", raw

    return None, None


def parse_voice_command(text):
    action, payload = parse_navigation_voice_command(text)
    if action:
        return action, payload

    if current_screen == SCREEN_WRITE:
        action, payload = parse_write_voice_command(text)
        if action:
            return action, payload
        return parse_screen_selection_voice_command(text)

    if current_screen == SCREEN_DRAW:
        action, payload = parse_draw_voice_command(text)
        if action:
            return action, payload
        return parse_screen_selection_voice_command(text)

    return parse_screen_selection_voice_command(text)


def handle_voice_action(action, payload, raw_text):
    if not action:
        set_status(f"Voice heard but not mapped on this screen:\n{raw_text}")
        return

    if action == "exit":
        set_status("Voice command: exit.")
        exit_callback()
        return

    if action == "go_home":
        go_home_callback()
        return

    if action == "go_write":
        go_write_callback()
        return

    if action == "go_draw":
        go_draw_callback()
        return

    if action == "switch_chinese":
        go_write_callback()
        if dpg.does_item_exist("mode_select"):
            dpg.set_value("mode_select", MODE_CHINESE)
        refresh_mode_ui()
        set_status("Switched writing mode to Chinese strokes.")
        return

    if action == "switch_english":
        go_write_callback()
        if dpg.does_item_exist("mode_select"):
            dpg.set_value("mode_select", MODE_ENGLISH)
        refresh_mode_ui()
        set_status("Switched writing mode to English strokes.")
        return

    if action == "confirm_write":
        set_status("Voice confirmed the current writing text.")
        start_writing_callback()
        return

    if action == "clear_write":
        clear_callback()
        return

    if action == "set_write_text":
        if is_busy():
            set_status("The robot is busy. Wait before replacing the writing text.")
            return
        go_write_callback()
        text = convert_spoken_newlines(payload or raw_text)
        mode = get_current_mode()
        draw_text = normalize_draw_text(text, mode)
        if dpg.does_item_exist("input_text"):
            dpg.set_value("input_text", draw_text)
        if dpg.does_item_exist("preview_text"):
            dpg.set_value("preview_text", draw_text)
        set_status(
            "Voice updated the writing text.\n"
            "You can still edit it manually or say confirm / 开始写."
        )
        return

    if action == "draw_latest_image":
        go_draw_callback()
        select_latest_image_callback()
        return

    if action == "draw_flip_on":
        if is_busy():
            set_status("The robot is busy. Wait before changing draw settings.")
            return
        go_draw_callback()
        set_draw_flip_enabled(True)
        set_status("Image flip is now ON.")
        return

    if action == "draw_flip_off":
        if is_busy():
            set_status("The robot is busy. Wait before changing draw settings.")
            return
        go_draw_callback()
        set_draw_flip_enabled(False)
        set_status("Image flip is now OFF.")
        return

    if action == "draw_take_photo":
        go_draw_callback()
        take_photo_callback()
        return

    if action == "draw_retake_photo":
        go_draw_callback()
        retake_photo_callback()
        return

    if action == "draw_confirm":
        go_draw_callback()
        start_robot_draw_callback()
        return

    if action == "draw_regenerate":
        go_draw_callback()
        selected_image_path = draw_state.get("selected_image_path") or find_latest_image_path()
        if not selected_image_path:
            set_status("No image is available yet. Take a photo first or use the latest image fallback.")
            return
        start_draw_generation_job(selected_image_path, job_name="draw-regenerate")
        return

    if action == "draw_path_text":
        go_draw_callback()
        start_draw_generation_job(payload or raw_text, job_name="draw-path")
        return


class ASRController:
    def __init__(self):
        self.is_running = False
        self.reconnect_lock = threading.Lock()
        self.conversation = None
        self.mic_thread = None
        self.rms_display_interval = 0.4
        self.last_rms_time = time.time()

    def start(self):
        if self.is_running:
            set_status("Voice recognition is already running.")
            return

        if not DASHSCOPE_API_KEY:
            set_status(
                "Missing DASHSCOPE_API_KEY.\n"
                "Please set the environment variable first."
            )
            return

        self.is_running = True
        logger = logging.getLogger("dashscope")
        logger.setLevel(logging.WARNING)
        logger.propagate = False
        dashscope.api_key = DASHSCOPE_API_KEY

        try:
            self.conversation = self.create_conversation()
        except Exception as exc:
            self.is_running = False
            set_status(f"ASR start failed: {exc}")
            return

        self.mic_thread = threading.Thread(target=self.microphone_thread, daemon=True)
        self.mic_thread.start()
        set_status(
            "Voice recognition started.\n"
            "Home: malen / draw / schreiben / write\n"
            "Write: 写 你好 / write hello robot\n"
            "Draw: take photo / retake photo / confirm draw"
        )

    def stop(self):
        self.is_running = False

        try:
            if self.conversation is not None:
                self.conversation.close()
        except Exception:
            pass

        self.conversation = None
        set_status("Voice recognition stopped.")

    def create_conversation(self):
        conversation = OmniRealtimeConversation(
            model=ASR_MODEL,
            url=ASR_URL,
            callback=self.ASRCallback(self),
        )
        conversation.callback.conversation = conversation
        conversation.connect()

        transcription_kwargs = {
            "sample_rate": RATE,
            "input_audio_format": "pcm",
        }
        if ASR_LANGUAGE:
            transcription_kwargs["language"] = ASR_LANGUAGE

        transcription_params = TranscriptionParams(**transcription_kwargs)

        conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            enable_turn_detection=True,
            turn_detection_type="server_vad",
            turn_detection_threshold=0.0,
            turn_detection_silence_duration_ms=400,
            enable_input_audio_transcription=True,
            transcription_params=transcription_params,
        )
        return conversation

    def reconnect_asr(self):
        with self.reconnect_lock:
            if not self.is_running:
                return False

            set_status("ASR connection closed. Reconnecting...")

            try:
                if self.conversation is not None:
                    self.conversation.close()
            except Exception:
                pass

            time.sleep(1)

            try:
                self.conversation = self.create_conversation()
                set_status("ASR reconnected.")
                return True
            except Exception as exc:
                set_status(f"ASR reconnect failed: {exc}")
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

    def microphone_thread(self):
        p = pyaudio.PyAudio()
        stream = None

        try:
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )

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
                            flush=True,
                        )
                        self.last_rms_time = current_time

                    audio_b64 = base64.b64encode(filtered_audio).decode("ascii")

                    try:
                        if self.conversation is not None:
                            self.conversation.append_audio(audio_b64)
                    except Exception as exc:
                        print(f"\nASR send error: {exc}")
                        ok = self.reconnect_asr()
                        if not ok:
                            time.sleep(2)
                        continue

                except Exception as exc:
                    print(f"\nMicrophone read error: {exc}")
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

    def handle_final_text(self, text):
        text = text.strip()
        if not text:
            return

        print(f"\nASR final text: {text}")
        action, payload = parse_voice_command(text)
        asr_queue.put((action, payload, text))

    class ASRCallback(OmniRealtimeCallback):
        def __init__(self, controller):
            self.controller = controller
            self.conversation = None

        def on_open(self):
            set_status("ASR connection opened.")

        def on_close(self, code, msg):
            set_status(f"ASR connection closed: code={code}, msg={msg}")

        def on_event(self, response):
            try:
                if response["type"] == "conversation.item.input_audio_transcription.completed":
                    text = response["transcript"]
                    self.controller.handle_final_text(text)
            except Exception as exc:
                set_status(f"ASR event error: {exc}")


def update_gui_from_queue():
    while not status_queue.empty():
        text = status_queue.get()
        update_all_status_texts(text)

    while not asr_queue.empty():
        action, payload, raw_text = asr_queue.get()
        handle_voice_action(action, payload, raw_text)


def refresh_runtime_ui():
    global draw_state_dirty

    update_voice_state_text()
    if draw_state_dirty:
        refresh_draw_preview()
        draw_state_dirty = False


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

    with dpg.theme() as success_button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Button, success_button_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, success_button_hover_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, success_button_active_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 14, 12, category=dpg.mvThemeCat_Core)

    with dpg.theme() as selector_theme:
        with dpg.theme_component(dpg.mvCombo):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, card_bg_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, soft_accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, soft_accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Text, ink_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border, soft_accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, card_bg_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Header, soft_accent_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, secondary_button_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, secondary_button_active_color, category=dpg.mvThemeCat_Core)

    with dpg.theme() as subtle_text_theme:
        with dpg.theme_component(dpg.mvText):
            dpg.add_theme_color(dpg.mvThemeCol_Text, muted_ink_color, category=dpg.mvThemeCat_Core)

    with dpg.texture_registry(show=False):
        dpg.add_raw_texture(
            DRAW_PREVIEW_WIDTH,
            DRAW_PREVIEW_HEIGHT,
            frame_to_texture_data(make_blank_preview_frame()),
            tag="draw_preview_texture",
            format=dpg.mvFormat_Float_rgba,
        )

    with dpg.window(
        tag="entry window",
        label="entry window",
        width=screen_width,
        height=screen_height,
        pos=(0, 0),
    ):
        dpg.add_text(default_value="AISR Robot Studio", tag="app_title", pos=[40, 28])
        dpg.add_text(default_value="Voice: waiting for start", tag="voice_state_text", pos=[840, 32])

        with dpg.group(tag="home_screen", show=True):
            with dpg.child_window(
                tag="home_panel",
                pos=[40, 86],
                width=1200,
                height=540,
                border=True,
                no_scrollbar=True,
            ):
                dpg.add_text("Choose a robot workflow", tag="home_title")
                dpg.add_text(
                    default_value=(
                        "The whole app can be controlled by voice in Chinese and English.\n"
                        "Say: 写字 / write, 画画 / draw, 返回首页 / go home, 退出 / exit"
                    ),
                    tag="home_intro",
                    wrap=1120,
                )
                dpg.bind_item_theme("home_intro", subtle_text_theme)

                with dpg.group(horizontal=True):
                    with dpg.child_window(
                        tag="home_write_card",
                        width=560,
                        height=360,
                        border=True,
                        no_scrollbar=True,
                    ):
                        dpg.add_text("Write", tag="home_write_title")
                        dpg.add_spacer(height=8)
                        dpg.add_text(
                            default_value=(
                                "Chinese and English stroke writing\n"
                                "Voice examples:\n"
                                "写 你好世界\n"
                                "write hello robot\n"
                                "中文模式 / English mode"
                            ),
                            tag="home_write_text",
                            wrap=500,
                        )
                        dpg.add_spacer(height=24)
                        dpg.add_button(
                            label="Open Writing",
                            tag="home_write_button",
                            width=220,
                            height=60,
                            callback=go_write_callback,
                        )

                    with dpg.child_window(
                        tag="home_draw_card",
                        width=560,
                        height=360,
                        border=True,
                        no_scrollbar=True,
                    ):
                        dpg.add_text("Draw", tag="home_draw_title")
                        dpg.add_spacer(height=8)
                        dpg.add_text(
                            default_value=(
                                "Take photo, review sketch, then confirm draw\n"
                                "Voice examples:\n"
                                "take photo\n"
                                "retake photo\n"
                                "confirm draw"
                            ),
                            tag="home_draw_text",
                            wrap=500,
                        )
                        dpg.add_spacer(height=24)
                        dpg.add_button(
                            label="Open Drawing",
                            tag="home_draw_button",
                            width=220,
                            height=60,
                            callback=go_draw_callback,
                        )

            with dpg.child_window(
                tag="home_status_panel",
                pos=[40, 646],
                width=1200,
                height=54,
                border=True,
                no_scrollbar=True,
            ):
                dpg.add_text(default_value="Waiting for your choice.", tag="home_status_text", wrap=1140)

        with dpg.group(tag="write_screen", show=False):
            with dpg.child_window(
                tag="write_left_panel",
                pos=[40, 86],
                width=710,
                height=540,
                border=True,
                no_scrollbar=True,
            ):
                dpg.add_text("English Stroke Writer", tag="compose_title")

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

                dpg.add_text(default_value="", tag="mode_note_text", wrap=650)
                dpg.bind_item_theme("mode_note_text", subtle_text_theme)

                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Start Voice",
                        tag="write_start_voice_button",
                        width=150,
                        height=42,
                        callback=start_asr_callback,
                    )
                    dpg.add_button(
                        label="Stop Voice",
                        tag="write_stop_voice_button",
                        width=150,
                        height=42,
                        callback=stop_asr_callback,
                    )
                    dpg.add_button(
                        label="Back Home",
                        tag="write_home_button",
                        width=150,
                        height=42,
                        callback=go_home_callback,
                    )

                dpg.add_spacer(height=4)
                dpg.add_text("Text")
                dpg.add_input_text(
                    tag="input_text",
                    hint="Example: HELLO & ROBOT 2026!",
                    width=650,
                    height=165,
                    multiline=True,
                )

                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Start Writing",
                        tag="start_button",
                        width=230,
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
                        tag="write_exit_button",
                        width=120,
                        height=54,
                        callback=exit_callback,
                    )

                dpg.add_spacer(height=4)
                dpg.add_text(default_value=gui_font_message, tag="font_info_text", wrap=650)
                dpg.bind_item_theme("font_info_text", subtle_text_theme)

            with dpg.child_window(
                tag="write_preview_panel",
                pos=[780, 86],
                width=460,
                height=220,
                border=True,
                no_scrollbar=True,
            ):
                dpg.add_text(default_value="Preview", tag="preview_label")
                dpg.add_spacer(height=6)
                dpg.add_text(default_value="", tag="preview_text", wrap=410)

            with dpg.child_window(
                tag="write_status_panel",
                pos=[780, 326],
                width=460,
                height=300,
                border=True,
                no_scrollbar=True,
            ):
                dpg.add_text(default_value="Status", tag="write_status_label")
                dpg.add_spacer(height=6)
                dpg.add_text(default_value="Waiting for writing input.", tag="write_status_text", wrap=410)

        with dpg.group(tag="draw_screen", show=False):
            with dpg.child_window(
                tag="draw_left_panel",
                pos=[40, 86],
                width=710,
                height=540,
                border=True,
                no_scrollbar=True,
            ):
                dpg.add_text("Robot Sketch Drawer", tag="draw_title")
                dpg.add_text(
                    default_value=(
                        "Workflow: take photo -> generate sketch -> review -> confirm draw.\n"
                        "If the sketch is not good, retake the photo and try again."
                    ),
                    tag="draw_note_text",
                    wrap=650,
                )
                dpg.bind_item_theme("draw_note_text", subtle_text_theme)

                with dpg.group(horizontal=True):
                    dpg.add_checkbox(
                        label="Flip Image",
                        default_value=True,
                        tag="draw_flip_checkbox",
                        callback=lambda s, a: set_draw_flip_enabled(a),
                    )
                    dpg.add_button(
                        label="Start Voice",
                        tag="draw_start_voice_button",
                        width=150,
                        height=42,
                        callback=start_asr_callback,
                    )
                    dpg.add_button(
                        label="Stop Voice",
                        tag="draw_stop_voice_button",
                        width=150,
                        height=42,
                        callback=stop_asr_callback,
                    )

                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Take Photo",
                        tag="draw_take_photo_button",
                        width=210,
                        height=54,
                        callback=take_photo_callback,
                    )
                    dpg.add_button(
                        label="Retake Photo",
                        tag="draw_retake_button",
                        width=210,
                        height=54,
                        callback=retake_photo_callback,
                    )
                    dpg.add_button(
                        label="Confirm Draw",
                        tag="draw_confirm_button",
                        width=210,
                        height=54,
                        callback=start_robot_draw_callback,
                    )

                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Use Latest Image",
                        tag="draw_latest_button",
                        width=180,
                        height=50,
                        callback=select_latest_image_callback,
                    )
                    dpg.add_button(
                        label="Back Home",
                        tag="draw_home_button",
                        width=180,
                        height=50,
                        callback=go_home_callback,
                    )
                    dpg.add_button(
                        label="Exit",
                        tag="draw_exit_button",
                        width=180,
                        height=50,
                        callback=exit_callback,
                    )

                dpg.add_spacer(height=8)
                dpg.add_text(
                    default_value=(
                        f"AISR server: {AISR_SERVER_URL}\n"
                        "Voice examples:\n"
                        "take photo / 拍照\n"
                        "retake photo / 重新拍照\n"
                        "confirm draw / 确认画画\n"
                        "latest image / 最新图片 (fallback)"
                    ),
                    tag="draw_server_text",
                    wrap=650,
                )
                dpg.bind_item_theme("draw_server_text", subtle_text_theme)

            with dpg.child_window(
                tag="draw_preview_panel",
                pos=[780, 86],
                width=460,
                height=220,
                border=True,
                no_scrollbar=True,
            ):
                dpg.add_text(default_value="Drawing Preview", tag="draw_preview_label")
                dpg.add_spacer(height=6)
                dpg.add_image("draw_preview_texture", tag="draw_preview_image")
                dpg.add_spacer(height=10)
                dpg.add_text(default_value="", tag="draw_preview_text", wrap=410)

            with dpg.child_window(
                tag="draw_status_panel",
                pos=[780, 326],
                width=460,
                height=300,
                border=True,
                no_scrollbar=True,
            ):
                dpg.add_text(default_value="Status", tag="draw_status_label")
                dpg.add_spacer(height=6)
                dpg.add_text(default_value="Waiting for a drawing command.", tag="draw_status_text", wrap=410)

        if default_font is not None:
            dpg.bind_font(default_font)

        if small_font is not None:
            for tag in [
                "voice_state_text",
                "home_title",
                "home_intro",
                "home_write_title",
                "home_write_text",
                "home_draw_title",
                "home_draw_text",
                "home_status_text",
                "compose_title",
                "mode_note_text",
                "dry_run_checkbox",
                "font_label",
                "input_text",
                "start_button",
                "clear_button",
                "write_exit_button",
                "write_status_label",
                "write_status_text",
                "preview_label",
                "preview_text",
                "font_info_text",
                "mode_select",
                "write_start_voice_button",
                "write_stop_voice_button",
                "write_home_button",
                "draw_title",
                "draw_note_text",
                "draw_flip_checkbox",
                "draw_take_photo_button",
                "draw_retake_button",
                "draw_confirm_button",
                "draw_latest_button",
                "draw_home_button",
                "draw_exit_button",
                "draw_server_text",
                "draw_preview_label",
                "draw_preview_text",
                "draw_status_label",
                "draw_status_text",
                "draw_start_voice_button",
                "draw_stop_voice_button",
            ]:
                if dpg.does_item_exist(tag):
                    dpg.bind_item_font(tag, small_font)

            if dpg.does_item_exist("font_select"):
                dpg.bind_item_font("font_select", small_font)

        if dpg.does_item_exist("app_title") and default_font is not None:
            dpg.bind_item_font("app_title", default_font)

        for tag in [
            "home_panel",
            "home_write_card",
            "home_draw_card",
            "home_status_panel",
            "write_left_panel",
            "write_preview_panel",
            "write_status_panel",
            "draw_left_panel",
            "draw_preview_panel",
            "draw_status_panel",
        ]:
            if dpg.does_item_exist(tag):
                dpg.bind_item_theme(tag, panel_theme)

        for tag in [
            "home_write_button",
            "home_draw_button",
            "start_button",
            "write_start_voice_button",
            "draw_start_voice_button",
            "draw_take_photo_button",
            "draw_latest_button",
        ]:
            if dpg.does_item_exist(tag):
                dpg.bind_item_theme(tag, primary_button_theme)

        for tag in [
            "clear_button",
            "write_home_button",
            "draw_home_button",
            "draw_stop_voice_button",
            "write_stop_voice_button",
            "draw_retake_button",
        ]:
            if dpg.does_item_exist(tag):
                dpg.bind_item_theme(tag, secondary_button_theme)

        for tag in ["write_exit_button", "draw_exit_button"]:
            if dpg.does_item_exist(tag):
                dpg.bind_item_theme(tag, danger_button_theme)

        if dpg.does_item_exist("draw_confirm_button"):
            dpg.bind_item_theme("draw_confirm_button", success_button_theme)

        for tag in ["mode_select", "font_select"]:
            if dpg.does_item_exist(tag):
                dpg.bind_item_theme(tag, selector_theme)

        for tag in ["input_text"]:
            if dpg.does_item_exist(tag):
                dpg.bind_item_theme(tag, input_theme)

    dpg.create_viewport(title="AISR Robot Studio", width=screen_width, height=screen_height)
    dpg.setup_dearpygui()
    dpg.toggle_viewport_fullscreen()
    dpg.show_viewport()
    dpg.set_primary_window("entry window", True)

    refresh_mode_ui()
    refresh_draw_preview()
    update_voice_state_text()
    start_asr_callback()

    while dpg.is_dearpygui_running():
        update_gui_from_queue()
        refresh_runtime_ui()
        dpg.render_dearpygui_frame()
        time.sleep(0.01)

    if asr_controller is not None:
        asr_controller.stop()
    if camera_controller is not None:
        camera_controller.stop()
    if legacy_ros_bridge is not None and legacy_ros_bridge is not camera_controller:
        legacy_ros_bridge.stop()

    dpg.destroy_context()


if __name__ == "__main__":
    main()
