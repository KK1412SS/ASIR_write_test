import os


class UarmState():
    idle = "idle"
    working = "working"
    start = "start"
    finish = "finish"
    invalid_pos = "invalid_pos"
    eat = "eating"
    error = "error"
    poweroff = "poweroff"
    disconnect = "disconnect"


class ArmTriggerMode():
    idle = "idle"
    chess = "chess"
    draw = "draw"
    caligraphy = "caligraphy"
    reset = "reset"
    stop = "stop"
    reload_uarm = "reload_uarm"
    reload_locnpy = "reload_locnpy"
    head_rise = "head_rise"
    head_rise = "submit_rise"


enum_uarm_state = UarmState()
enum_arm_mode = ArmTriggerMode()


class ArmTriggerNodeState():
    def __init__(self):
        self.arm_state = enum_uarm_state.idle
        self.arm_mode = enum_arm_mode.idle

    def set_arm_state(self, state):
        self.arm_state = state

    def set_arm_mode(self, mode):
        self.arm_mode = mode

    def get_arm_state(self):
        return self.arm_state

    def get_arm_mode(self):
        return self.arm_mode
