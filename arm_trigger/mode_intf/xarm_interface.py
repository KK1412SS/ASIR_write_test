from arm_trigger.xarm_sdk.aisr_model import AisrModel,draw_cirlce,draw_square,get_word_strokes,get_arm_strokes
from arm_trigger.xarm_sdk.xarm_control import Xarm
from arm_trigger.arm_state import enum_uarm_state
import numpy as np

class XarmInterface:
    def __init__(self):
        # self.aisr_model=AisrModel(display=False)
        self.aisr_model=AisrModel(display=False)
        
        self.aisr_real = Xarm()
        self.current_end_pos = None
        self.global_speed = None
        self.unit_m = True #单位为米
        # 侧面写字位置
        self.write_pos_0 = [-0.045639153623098165, 0.03535114846012756, 1.447306770922173585, 1.6883658483256834, 0.06359064934620756]
        self.write_pos_0 = [v*180.0/np.pi for v in self.write_pos_0]
        self.write_pos_0 = self.aisr_model.model_values_to_real_values(list(self.write_pos_0))

        # 正面写字位置
        self.write_pos_1 =  [-0.04550782250951578, 0.036207955081834775, -0.04766717802744291, 1.68826650708693, 0.29]
        self.write_pos_1 = [v*180.0/np.pi for v in self.write_pos_1]
        # print("========self.write_pos_1:",self.write_pos_1)
        self.write_pos_1 = self.aisr_model.model_values_to_real_values(list(self.write_pos_1))

        # 低头位置：
        self.nod_pos = [-20.0,-25.0]
        self.head_reset = [0.0, 0.0]
        self.action_hight = None
        #self.connect()
        
    def set_head_up(self,set_angle):
        if set_angle[0]>30 or set_angle[0]<-30:
            return
        if set_angle[1]>30 or set_angle[1]<-30:
            return
        if self.aisr_real.arm is None:
            return 
        self.aisr_real.set_head_angles(angles = set_angle)

        res_values = self.aisr_real.get_head_angles()            
        res = ((res_values[0]-set_angle[0])**2 + (res_values[1]-set_angle[1])**2)**0.5
        while res>0.1:
            res_values = self.aisr_real.get_head_angles()            
            res = ((res_values[0]-set_angle[0])**2 + (res_values[1]-set_angle[1])**2)**0.5

    def set_head_nod_increast(self, is_increast, angle):
        current_values = self.aisr_real.get_head_angles()            

        new_values = current_values
        if is_increast:
            new_values[-1] += angle
        else:
            new_values[-1] -= angle
        print("====new_values：",new_values)
        self.set_head_up(set_angle = new_values)
        

    def set_head_shake_increast(self, is_increast, angle):
        current_values = self.aisr_real.get_head_angles()            
        new_values = current_values
        if is_increast:
            new_values[0] += angle
        else:
            new_values[0] -= angle
        print("====new_values：",new_values)
        self.set_head_up(set_angle = new_values)

    def set_head_increast(self, angle_shake, angle_nod):
        current_values = self.aisr_real.get_head_angles()            
        new_values = current_values
        new_values[0] += angle_shake
        new_values[1] += angle_nod
        print("====new_values：",new_values)
        self.set_head_up(set_angle = new_values)        
    

    #self.nod_pos 2 vector
    def set_head_nod(self):
        if self.aisr_real.arm is None:
            return 
        self.aisr_real.set_head_angles(angles = self.nod_pos)
        res_values = self.aisr_real.get_head_angles()            
        res = ((res_values[0]-self.nod_pos[0])**2 + (res_values[1]-self.nod_pos[1])**2)**0.5
        while res>0.1:
            res_values = self.aisr_real.get_head_angles()            
            res = ((res_values[0]-self.nod_pos[0])**2 + (res_values[1]-self.nod_pos[1])**2)**0.5
            # print("==set_head_nod  res:",res,res_values)

    def set_head_reset(self):
        if self.aisr_real.arm is None:
            return 
        self.aisr_real.set_head_angles(angles = self.head_reset)
        res_values = self.aisr_real.get_head_angles()            
        res = ((res_values[0]-self.head_reset[0])**2 + (res_values[1]-self.head_reset[1])**2)**0.5
        while res>0.1:
            res_values = self.aisr_real.get_head_angles()            
            res = ((res_values[0]-self.head_reset[0])**2 + (res_values[1]-self.head_reset[1])**2)**0.5
            # print("==set_head_reset  res:",res,res_values)

    def prepare_write(self):
        if self.aisr_real.arm is None:
            return 
        res_values = self.aisr_real.get_angles()
        res_values_np = np.array(res_values)
        values_np = np.array(self.write_pos_1)
        res = np.sqrt(np.sum((values_np - res_values_np)**2))
        print("===check hand pose res:",res)
        if res >10:
            self.set_all_angles(self.write_pos_0)
            self.set_all_angles(self.write_pos_1)
        return

    def uarm_reset(self):
        if self.aisr_real.arm is None:
            return 
        # self.set_all_angles(self.write_pos_0)
        self.set_all_angles(self.write_pos_1)
        pass

    def is_state_ok(self):
        print("!!!!  XarmInterface is_state_ok 未实现。。。。")
        return enum_uarm_state.idle

    def reload_uarm(self):
        self.connect()
        return

    def connect(self):
        if not self.aisr_real.is_connected():
            res = self.aisr_real.connect()
            if res:
                print("连接成功")
                real_values = self.aisr_real.get_angles()[0:5]
                print("real_values",real_values)
                self.aisr_model.set_white_joints(real_values = real_values)
                self.updata_current_end_pos()
            else:
                print("连接失败,请重新连接")
            return res

    def updata_current_end_pos(self):
            end_pos = self.aisr_model.get_end_pos()
            self.current_end_pos = end_pos
            pos_str = 'X:%3.3f Y:%3.3f Z:%3.3f'%(end_pos[0],end_pos[1],end_pos[2])
            # print(pos_str)

    def set_all_angles(self,values):
        if self.aisr_real.arm is None:
            return 
        self.aisr_real.set_angles(angles = values)
        res_values = self.aisr_real.get_angles()
        res_values_np = np.array(res_values)
        values_np = np.array(values)
        res = np.sqrt(np.sum((values_np - res_values_np)**2))
        while res>0.01:
            self.aisr_model.set_white_joints(real_values = res_values)
            res_values = self.aisr_real.get_angles()
            res_values_np = np.array(res_values)
            res = np.sqrt(np.sum((values_np - res_values_np)**2))
            # print("===res:",res)
        self.updata_current_end_pos()
        return

    def set_position(self, x, y, z, speed=None, wait=False):
            target_pos = [y, x, z]
            values = self.aisr_model.get_ik_angle(target_pos)
            #print("===！！！values:",target_pos,values)
            self.set_all_angles(values)
            return
    
    def get_position(self):
        if self.aisr_real.arm is None:
            return [0]*5
        res_values = self.aisr_real.get_angles()
        self.aisr_model.set_white_joints(real_values = res_values)
        current_pos = self.aisr_model.get_end_pos()
        return current_pos

    def check_xforce(self,target_pos,current_h,xforce_data):
        while 1: 
            target_pos[2] = current_h           
            current_force = xforce_data.getdata()[0] #fx        
            if current_force < -1.3:   #笔尖压迫,手臂上抬
                target_pos[2] += 0.0003 
                current_h = target_pos[2]
                values = self.aisr_model.get_ik_angle(target_pos)
                self.set_all_angles(values)
                print(f"============笔尖压力过大 抬手 current_force:{current_force}  {target_pos[2]}")
                continue
            current_force = xforce_data.getdata()[0] #fx        
            if np.abs(current_force) < 0.6:   #笔尖没有压力，手臂下台
                target_pos[2] -= 0.0003   
                values = self.aisr_model.get_ik_angle(target_pos)
                self.set_all_angles(values)
                current_h = target_pos[2]
                print(f"============笔尖压力过小 压手 current_force:{current_force}  {target_pos[2]}")
                continue
            current_h = target_pos[2]
            print(f"============压力正常 current_force:{current_force}  {current_h}")
            break
        return target_pos,current_h

    def set_position_2(self, x, y, z, xforce_data):
            target_pos = [y, x, z]
            # current_pos = self.get_position() #这里还没更新...返回值不对
            current_h = target_pos[2] 
            # print("=====current_pos:",current_pos)
            print("=====target_pos:",target_pos)
            # import pdb;pdb.set_trace()
            target_pos,current_h = self.check_xforce(target_pos,current_h,xforce_data)
            values = self.aisr_model.get_ik_angle(target_pos)
            # print("===！！！values:",target_pos,values)
            self.set_all_angles(values)
            return current_h
    
    def auto_record_high(self,xforce_data):
        init_pos = self.get_position()
        print("=====init_pos:",init_pos)
        while 1:        
            current_pos = self.get_position()
            print("=====current_pos:",current_pos)
            # if current_pos[2]<0.5:
            #     import pdb;pdb.set_trace()    
            next_pos = current_pos
            # next_pos[2] += 0.005     # z
            next_pos[2] -= 0.003
            values = self.aisr_model.get_ik_angle(next_pos)
            self.set_all_angles(values)
            self.start_pos = self.aisr_model.get_end_pos()
            current_force = xforce_data.getdata()[0] #fx        
            print(f"============current_force:{current_force}")
            if current_force < -0.8:
                break    
        print("=====ok")        
        end_pos = self.aisr_model.get_end_pos()
        self.action_hight = end_pos[2]
        # 恢复原来高度
        values = self.aisr_model.get_ik_angle(init_pos)
        self.set_all_angles(values)


