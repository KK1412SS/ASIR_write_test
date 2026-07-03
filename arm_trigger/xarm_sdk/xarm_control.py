import time
import numpy as np
from arm_trigger.xarm.wrapper import XArmAPI

class Xarm:
    def __init__(self):
        self.ip = "192.168.1.217"
        self.arm = None
        # self.connect()
        #这里调整速度
        self.speed = 1000
        # self.arm.set_servo_angle(angle=[-168, 68, 114, 58, 179, 54.5, -26], speed=speed, is_radian=False, wait=True)
        # print(self.arm.get_servo_angle())
    def is_connected(self):
        if self.arm is None:
            return False
        else:
            return True

    def connect(self):
        try:
            self.arm = XArmAPI(self.ip)
            import sys
            import os
            print(os.path.abspath(sys.modules[XArmAPI.__module__].__file__))
            
            # time.sleep(2)
            self.arm.clean_warn()
            self.arm.clean_error()
            self.arm.motion_enable(enable=True)
            self.arm.set_mode(0)
            self.arm.set_state(state=0)
            # self.arm.set_collision_sensitivity(0)

            # print(self.arm.get_servo_angle())
            # print(self.arm.last_used_angles)
            return True
        except Exception:
            print("机械臂连接失败")
            self.arm = None
            return False

    def set_angles(self,angles = [-162.4, 83.5, 114, 150, 208]):#[-168,68,114,58,200]
        # self.arm.motion_enable(enable=True)
        # self.arm.set_mode(0)
        # self.arm.set_state(state=0)
        res = self.arm.get_servo_angle()[1]
        #angles[3]+=90
        angles_7 = angles+[res[5],res[6]]
        # print(angles_7)
        res = self.arm.set_servo_angle(angle=angles_7, speed=self.speed, is_radian=False, wait=False)
        angles = self.arm.get_servo_angle(is_radian=False)
        # print("set_angles  get_servo_angle:",angles)
        angles = angles[1]
        # print("set_angles:",res)
        return angles[0:5] 
    
    def get_head_angles(self):
        res = self.arm.get_servo_angle()[1]
        angles = [res[5]-54.5,res[6]+26]
        return angles

    def get_angles(self):
        angles_7 = self.arm.get_servo_angle(is_radian=False)[1][0:5]
        # print("get_angles:",angles_7)
        return angles_7

    def set_head_angles(self,angles=[0.0,0.0]):
        angles_0 =  angles[0] + 54.5  #固定偏差
        angles_1 =  angles[1] - 26
        res = self.arm.get_servo_angle()[1]
        angles_7 = [res[0],res[1],res[2],res[3],res[4],angles_0,angles_1]
        res = self.arm.set_servo_angle(angle=angles_7, speed=self.speed, is_radian=False, wait=False)
        angles = self.arm.get_servo_angle(is_radian=False)
        # print("set_head_angles  get_servo_angle:",angles)
        angles = angles[1]
        # print("set_angles:",res)
        return angles[5:] 



if __name__ == "__main__":
    arm = Xarm()  
    res = arm.connect()
    arm.set_angles()
    print(res)