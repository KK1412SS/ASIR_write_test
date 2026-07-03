import os
import pybullet as p
import pybullet_data
import time
import numpy as np
import json
import cv2

from pathlib import Path
path = str(Path(__file__).parent) + "/"
# path = "/mnt/ros2/src/tad-ros2/tad_robot/pyscript/arm_trigger/xarm_sdk/"

def get_word_strokes():
    word_strokes = []
    with open('福.json', encoding='utf-8') as f:
        res = f.read()
        res = json.loads(res)
        medians = np.array(res['medians'])
        for s in medians:
            word_strokes.append(np.array(s))
    return word_strokes

def get_arm_strokes(words_strokes,center_point,w = 0.03):
    center_x,center_y,center_z = center_point[0],center_point[1],center_point[2]
    # w = 0.02
    dst = np.float32([[center_x-w, center_y+w], 
                     [center_x+w, center_y+w],
                     [center_x+w, center_y-w]
                     ])
    src = np.float32([[0, 0], [0,1024], [1024, 1024]])
    T_img2arm = cv2.getAffineTransform(src, dst)

    arm_strokes = []
    for word_id in range(0, len(words_strokes)):
        word = words_strokes[word_id]
        new_word = []
        for stroke in word:
            stroke_ = stroke.reshape([-1, 2])
            ones_ = np.ones([len(stroke_), 1])
            stroke_ = np.hstack([stroke_, ones_]).T
            arm_stroke_ = np.matmul(
                T_img2arm, stroke_).T.reshape([-1, 2])
            x_y = np.array(arm_stroke_).reshape(-1,2)
            z = np.ones((len(x_y),1)) * center_point[2]
            x_y_z = np.hstack([x_y,z])
            new_word.append(x_y_z)
        arm_strokes.append(new_word)
    return arm_strokes


def draw_square(w,center_vector,point_num): #需要注意是单位是米
    center_vector=np.array(center_vector)
    x=np.zeros((point_num*4,1))
    y=np.zeros((point_num*4,1))

    start_pos = center_vector - np.array([w/2, w/2, 0])
    da = w / point_num
    i = 0
    for p in range(point_num):
        x[i,0]=start_pos[0]
        y[i,0]=start_pos[1]+ p*da
        i = i + 1
    start_pos[1] = start_pos[1]+ p*da
    for p in range(point_num):
        x[i,0]=start_pos[0] + p*da
        y[i,0]=start_pos[1]
        i = i + 1
    start_pos[0] = start_pos[0] + p*da
    for p in range(point_num):
        x[i,0]=start_pos[0]
        y[i,0]=start_pos[1] - p*da
        i = i + 1
    start_pos[1] = start_pos[1] - p*da
    for p in range(point_num):
        x[i,0]=start_pos[0] - p*da
        y[i,0]=start_pos[1]
        i = i + 1

    z = np.ones((point_num*4,1)) * center_vector[2]
    all=np.hstack((x,y,z))
    return all  #输出是一个矩阵

def draw_cirlce(r,center_vector,limit_size): #需要注意是单位是米
    center_vector=np.array(center_vector)
    x=np.zeros((limit_size,1))
    y=np.zeros((limit_size,1))
    da = 360 / limit_size
    for i in range(limit_size):
        x[i,0]=center_vector[0]+r*(np.cos(i*da/180*np.pi))
        y[i,0]=center_vector[1]+r*(np.sin(i*da/180*np.pi))

    z = np.ones((limit_size,1)) * center_vector[2]
    all=np.hstack((x,y,z))
    return all  #输出是一个矩阵
start_pos = [0.376,-0.4,0.492]
# circle_xyz=draw_cirlce(0.05,start_pos,72)

class AisrModel:
    def __init__(self,display=True):
        # p.connect(p.GUI,options="--mp4=\"test.mp4\" ")
        if display:
            p.connect(p.GUI)
        else:
            id = p.connect(p.DIRECT)
            print("===============id",id )

        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.resetSimulation()
        p.configureDebugVisualizer(p.COV_ENABLE_RENDERING,1)    
        p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)
        p.resetDebugVisualizerCamera(1, 90, -10, [0, 0, 0.5])

        # 重力
        p.setGravity(0, 0, -10)
        # 实时仿真
        useRealTimeSim = 1
        p.setRealTimeSimulation(useRealTimeSim)
        # 加载地面
        p.loadURDF("plane.urdf")
        # p.loadSDF("stadium.sdf")
        # 加载aisr
        # self.aisr = p.loadURDF("aisr_v3.urdf")
        # self.JOINT_NAME=["white1_joint","white2_joint","white3_joint","white4_joint","white5_joint","white_hand"]
        # self.HAND_END_ID = 5        
        # print("load urdf.....",path + "aisr_v3_pencil.urdf" )
        self.aisr = p.loadURDF(path + "aisr_v3_pencil.urdf")
        self.JOINT_NAME=["white1_joint","white2_joint","white3_joint","white4_joint","white5_joint","white_hand","pencil_joint"]
        self.HAND_END_ID = 6        

        self.joint_ids = []
        numJoints = p.getNumJoints(self.aisr)
        for joint_id in range(numJoints):
            xx= p.getJointInfo(self.aisr,joint_id)
            # print(xx)
            # 设置手的颜色与透明度
            if "white" in xx[1].decode('utf-8'):
                p.changeVisualShape(self.aisr, joint_id, rgbaColor=[1, 1, 1, 0.8])
            elif "black" in xx[1].decode('utf-8'):
                p.changeVisualShape(self.aisr, joint_id, rgbaColor=[0.5, 0.5, 0.5, 0.5])
                
            if (len(self.joint_ids)<len(self.JOINT_NAME) 
                and xx[1].decode('utf-8') == self.JOINT_NAME[len(self.joint_ids)]):
                self.joint_ids.append(joint_id)
        print(self.joint_ids,"=============")
        hand_end_info = p.getLinkState(self.aisr,self.joint_ids[self.HAND_END_ID],computeForwardKinematics = 1)
        self.track_pos = list(hand_end_info[4])

        self.real_zero_values = [-162.4, 83.5,114,58,208]  #模型中关节为0度时,实体关节的角度
        self.real_init_values = [-168, 68, 114, 58, 208, 54.5, -26] #实体初始角度
        self.start_pos = [0.376,-0.4,0.492]

    def get_init_values(self):
        return self.real_init_values[0:5]
    
    def get_end_pos(self):
        hand_end_info = p.getLinkState(self.aisr,self.joint_ids[self.HAND_END_ID],computeForwardKinematics = 1)
        hand_end_pos = list(hand_end_info[4])
        return hand_end_pos


    def real_values_to_model_values(self,real_values = [162.4, 83.5,114,58,200]):
        '''将xarm的实际角度转为模型上的角度, 减去一个初始差值 '''
        model_values = real_values
        model_values[0] -= self.real_zero_values[0]
        model_values[1] -= self.real_zero_values[1]
        model_values[1] *=-1  #注意第二个joint与模型转动方向相反
        model_values[2] -= self.real_zero_values[2]
        model_values[3] -= self.real_zero_values[3]
        model_values[4] -= self.real_zero_values[4]
        return model_values

    def model_values_to_real_values(self,model_values = [0,0,0,0,0]):
        ''' 将模型上的角度转为xarm上的角度 加上一个初始差值 '''
        real_values = model_values
        real_values[0] += self.real_zero_values[0]
        real_values[1] *= -1
        real_values[1] += self.real_zero_values[1]
        real_values[2] += self.real_zero_values[2]
        real_values[3] += self.real_zero_values[3]
        real_values[4] += self.real_zero_values[4]
        return real_values

    def set_white_joints(self,real_values = [-168,68,114,58,200]):
        '''设置aisr真实的角度'''
        # model_values = real_values

        hand_end_info = p.getLinkState(self.aisr,self.joint_ids[self.HAND_END_ID],computeForwardKinematics = 1)
        hand_end_pos = list(hand_end_info[4])
        p.addUserDebugLine(self.track_pos, hand_end_pos, lineColorRGB = [1,0,0],lineWidth=5)
        self.track_pos = hand_end_pos

        debug_str = "%.3f %.3f %.3f"%(hand_end_pos[0],hand_end_pos[1],hand_end_pos[2])
        p.addUserDebugText(debug_str, hand_end_pos, textColorRGB=[1,0,0],textSize=1,lifeTime=0.1)

        model_values = self.real_values_to_model_values(real_values)
        # model_values.append(0) #添加一个手部角度
        model_values = [v*np.pi/180.0 for v in model_values]
        # print("===model_values:",model_values)
        p.setJointMotorControlArray(self.aisr,self.joint_ids[:5],p.POSITION_CONTROL, targetPositions=model_values)  
        #todo 添加末端坐标显示
        return

    def IK(self,body_id, link_id, pos):
        # print("===target:",pos)
        orenitation1=p.getQuaternionFromEuler([0,0,0])
        targetposition=p.calculateInverseKinematics(body_id
                                                    ,link_id
                                                    ,pos
                                                    # ,jointRanges = joint_ids[:-1]
                                                    # ,targetOrientation=orenitation1
                                                    ,maxNumIterations=200
                                                    ,residualThreshold=0.0001
                                                    )
        return targetposition

    def check_pos(self, body_id, link_id, target_pos):
        hand_end_link_info = p.getLinkState(body_id,link_id,computeForwardKinematics = 1)
        hand_end_pos = list(hand_end_link_info[4])
        hand_end_pos_array = np.array(hand_end_pos)
        target_pos_array = np.array(target_pos)
        err = np.sqrt(np.sum((hand_end_pos_array - target_pos_array)**2))
        res = False
        print("==checkPos:",target_pos,hand_end_pos,err)
        if err<=0.01:
            res = True
        return res,hand_end_pos

    def get_ik_angle(self,target_pos):
        targetposition = self.IK(self.aisr, self.joint_ids[self.HAND_END_ID], target_pos)
        targetposition = [v*180.0/np.pi for v in targetposition]
        # print("====targetposition:",targetposition)
        targetposition_real = self.model_values_to_real_values(list(targetposition))
        # print("====targetposition_real:",targetposition_real)
        return targetposition_real

if __name__ == "__main__":
    aisr_model = AisrModel()
    aisr_model.set_white_joints()
    time.sleep(1000)