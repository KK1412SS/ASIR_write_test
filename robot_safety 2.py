import signal
import sys
import threading
from typing import Any, Optional

uarm_interface = None
_emergency_stop_requested = False


def _handle_sigint(signum, frame):
    del signum, frame
    global _emergency_stop_requested
    _emergency_stop_requested = True
    print("\n⚠️ Not-Abbruch angefordert (Ctrl+C erkannt). Bewegung wird gestoppt...")


def _keyboard_stop_listener():
    """
    Wartet im Hintergrund auf ein manuelles Not-Stopp-Kommando.
    Standard: im Terminal einfach 'q' + Enter eingeben.
    """
    global _emergency_stop_requested
    while not _emergency_stop_requested:
        try:
            user_input = input().strip().lower()
        except EOFError:
            break
        except Exception as e:
            print(f"Keyboard-Listener Fehler: {e}")
            break

        if user_input in {"q", "quit", "stop", "abort"}:
            _emergency_stop_requested = True
            print("\n⚠️ Manueller Not-Abbruch angefordert. Bewegung wird gestoppt...")
            break


def reset_stop_flag() -> None:
    global _emergency_stop_requested
    _emergency_stop_requested = False


def stop_requested() -> bool:
    return _emergency_stop_requested


def connect_robot():
    global uarm_interface
    if uarm_interface is not None:
        return uarm_interface

    from arm_trigger.mode_intf.xarm_interface import XarmInterface

    uarm_interface = XarmInterface()
    if_connect = uarm_interface.connect()
    print(f"Roboter verbunden: {if_connect}")
    return uarm_interface


def get_robot_interface():
    return uarm_interface


def get_robot_position() -> Optional[Any]:
    """
    Liest die aktuelle Arm-Position best effort aus und gibt sie zurück.
    Rückgabe möglichst als [x, y, z] oder None, wenn das Interface es nicht unterstützt.
    """
    if uarm_interface is None:
        return None

    try:
        if hasattr(uarm_interface, 'get_position'):
            pos = uarm_interface.get_position()
            print(f"Aktuelle Roboterposition: {pos}")
            return pos
    except Exception as e:
        print(f"Konnte Position nicht lesen: {e}")

    print("Aktuelle Roboterposition konnte nicht vom Interface gelesen werden.")
    return None


def emergency_stop_robot() -> Optional[Any]:
    """
    Versucht den Arm sofort zu stoppen und gibt danach die aktuelle Position zurück.
    Nutzt best effort, weil je nach Interface andere Methoden verfügbar sein können.
    """
    if uarm_interface is None:
        print("Kein Roboter verbunden – Not-Abbruch nur lokal markiert.")
        return None

    stop_errors = []

    for method_name, kwargs in [
        ('emergency_stop', {}),
        ('stop_move', {}),
        ('set_state', {'state': 4}),
        ('motion_enable', {'enable': False}),
    ]:
        try:
            if hasattr(uarm_interface, method_name):
                method = getattr(uarm_interface, method_name)
                method(**kwargs)
                print(f"Not-Stopp über {method_name} ausgelöst.")
                break
        except Exception as e:
            stop_errors.append(f"{method_name}: {e}")

    if stop_errors:
        print("Not-Stopp Hinweise:")
        for msg in stop_errors:
            print(f"  - {msg}")

    return get_robot_position()


def setup_stop_handlers():
    """
    Installiert Ctrl+C-Handler und startet optional den q-Listener im Terminal.
    Rückgabe: (alter_signal_handler, listener_thread)
    """
    old_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _handle_sigint)

    listener_thread = None
    if sys.stdin and sys.stdin.isatty():
        listener_thread = threading.Thread(target=_keyboard_stop_listener, daemon=True)
        listener_thread.start()

    return old_handler, listener_thread


def restore_stop_handlers(old_handler) -> None:
    signal.signal(signal.SIGINT, old_handler)
