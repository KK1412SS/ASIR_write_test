import numpy as np
import cv2
import json
import datetime
from shutil import copyfile
from std_msgs.msg import String
from tqdm import tqdm

# from aisr-v1 chessbot
class Config:
    write_h = 0.623 
config = Config()


class DrawInterface(object):
    def __init__(self):
        self.trail_text = []
        self.record_info = '000'
        self.image_size = 1.5
        self.stop_flag = False
        self.progress_rate=0 

    def get_progress_rate(self):
        res = int(self.progress_rate/10)*10
        return res
    def stop_writting(self):
        self.stop_flag = True

    def reset_flag(self):
        self.stop_flag = False

    def check_stop_flag(self):
        return self.stop_flag



    def uarm_draw(self,file):
        dh = 15.
        x0=300.   #初始基准位置
        y0=-200.
        last_z=config.write_h+dh/1000
        if len(self.trail_text)!=0:
            self.trail_text=[]

        raw_p = []
        for l in file:
            d = l.split(' ')
            
            p = [140.0 - float(d[0])*self.image_size,140.0 - float(d[1])*self.image_size]
            z=float(d[2])
            if z==0:
                z=last_z
            elif z<0:
                z=config.write_h
            else:
                z=config.write_h+dh/1000
            last_z=z
            p.append(z)
            raw_p.append(p)

        for i in range(len(raw_p)):
            x=x0+raw_p[i][1]
            y=y0-raw_p[i][0]
            x = x*1.0/1000
            y = y*1.0/1000
            z = raw_p[i][2]
            #print(x,y,z)
            #  print(str(x)+' '+str(y)+' '+str(z))
            self.trail_text.append([x,y,z])
        
        return True  

    def get_draw_mat(self):
        # with open(os.getcwd()+"/src/tad-ros2/tad_robot/pyscript/drawbot/trail_test.txt",'r') as ff: 
        # with open('/mnt/ros2/src/trail.txt','r') as ff: 
        with open('/home/acir/TinyWings_AISR/drawbot/trail_sign.txt','r') as ff: 
        # with open("trail.txt",'r') as ff:
            file_org = ff.readlines()
            file=file_org[:]
            date_info = file_org[-1]
            print("date_info:",date_info)
            print("self.record_info:",self.record_info)
            if self.record_info != date_info:
                self.record_info = date_info
                if self.uarm_draw(file):
                    print('绘画轨迹获取完成')
                    return 1
                else:
                    print('绘画轨迹获取失败1')
                    self.record_info = '000'
                    return -2
            else:
                print('绘画轨迹获取失败2')
                self.record_info = '000'

                return -2
        return -2

    def draw(self, data, uarm_interface, publisher, stop_event,xforce_data=None):
        # self.uarm_sign()
        self.uarm_sign_by_aisr()
        res = self.get_draw_mat()
        if res ==-2:
            print('绘画失败')
            return -2
        data = np.array(self.trail_text)
        data = data.reshape([-1, 3])
        print("draw:", data[0, :])

        with open("/home/acir/TinyWings_AISR/drawbot/draw_point_test.csv","w") as f:
            for i in range(len(data)):
                f.write("%f,%f,%f\n"%(data[i,0],data[i,1],data[i,2]))        
        # return
        uarm_interface.set_head_nod() #  低头
        dh = 15.
        if not xforce_data is None:
            uarm_interface.auto_record_high(xforce_data)
            z=config.write_h
            for i in range(len(data)):
                if data[i,2] == config.write_h:
                     data[i,2] = uarm_interface.action_hight
                if data[i,2] == config.write_h+dh/1000:
                     data[i,2] = uarm_interface.action_hight+dh/1000
        # i = 0
        # if 1:
        for i in tqdm(list(range(len(data)))):
            if stop_event.is_set():
                break
            self.progress_rate = ((i+1)/len(data))*100 
            if int(self.progress_rate)%2==0:
                msg = {}
                # msg['progress_rate'] = int(self.progress_rate)
                msg = json.dumps(msg,ensure_ascii=False)
                pub_msg = String(data=msg)
                #publisher.publish(pub_msg)
            # print(f"======{msg}  {i} / {len(data)}")
            # time.sleep(0.1)
            # continue
            if self.stop_flag:
                print("=====stop.....")
                self.record_info = '000'
                self.reset_flag()
                # uarm_interface.set_head_reset() #  恢复
                return -1

            y, x, z = data[i, :]
            current_h = z
            if xforce_data is None:
                uarm_interface.set_position(
                    x=x, y=y, z=z, speed=uarm_interface.global_speed, wait=True)
            else:
                if data[i, 2]==uarm_interface.action_hight+15/1000:
                    uarm_interface.set_position(x=x, y=y, z=current_h)
                else:
                    if i>0 and  data[i-1, 2]==uarm_interface.action_hight+dh/1000 and data[i, 2]==uarm_interface.action_hight:
                        # z_2 = z + 4/1000
                        # uarm_interface.set_position(x=x, y=y, z=z_2)
                        current_h = uarm_interface.set_position_2(x=x, y=y, z=z, xforce_data=xforce_data)

                    else:
                        # uarm_interface.set_position_2(x=x, y=y, z=z, xforce_data=xforce_data)
                        uarm_interface.set_position(x=x, y=y, z=current_h)

                # if i>0 and  data[i-1, 2]==uarm_interface.action_hight+15/1000 and data[i, 2]==uarm_interface.action_hight:
                #     z_2 = z + 4/1000
                #     import pdb;pdb.set_trace()
                #     uarm_interface.set_position(x=x, y=y, z=z_2)    
                # uarm_interface.set_position_2(x=x, y=y, z=z, xforce_data=xforce_data)
        # print("====current z",z)
        # self.uarm_sign(uarm_interface)
        print("绘画完成！")
        self.record_info = '000'
        self.reset_flag()
        # uarm_interface.set_head_reset() #  恢复
        return 1

    def uarm_sign_by_aisr(self):
        by_aisr = [
            [(56, 50), (56, 116)], 
            [(59, 49), (74, 47), (92, 50), (98, 57), (99, 66), (89, 76), (71, 79), (60, 80), (73, 80), (85, 80), (96, 85), (103, 94), (99, 109), (90, 113), (77, 114), (56, 115)], 
            [(122, 45), (147, 82), (148, 114)], 
            [(178, 44), (149, 83)], 
            [(239, 49), (211, 114)], 
            [(240, 51), (268, 114)], 
            [(221, 92), (256, 89)], 
            [(291, 46), (290, 114)], 
            [(357, 62), (339, 46), (323, 53), (322, 73), (336, 80), (350, 83), (364, 96), (358, 107), (341, 116), (326, 116), (313, 101)], 
            [(385, 54), (385, 116)],
            [(387, 49), (423, 49), (431, 54), (437, 69), (430, 78), (421, 83), (399, 83), (390, 81), (413, 82), (427, 101), (440, 116)]
        ]
        by_aisr = [ [ [490 - p[0],p[1]] for p in ps  ] for ps in by_aisr ]


        copyfile('/home/acir/TinyWings_AISR/drawbot/trail.txt', '/home/acir/TinyWings_AISR/drawbot/trail_sign.txt')
        file3 = open('/home/acir/TinyWings_AISR/drawbot/trail_sign.txt', 'a')
        # file3 = open('/mnt/ros2/src/trail_sign.txt', 'w')
        contours = by_aisr
        dx = 10
        dy = 70
        f = 0.08
        for c in contours:

            print(str(c[0][0]) + ' '+str(c[0][1])+' '+'0'+'\n')
            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f + dy)+' '+'0'+'\n')
            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f + dy)+' '+'-33'+'\n')

            for p in c[1:]:
                file3.write(str(p[0]*f+dx) + ' '+str(p[1]*f+dy)+' '+'0'+'\n')

            file3.write(str(p[0]*f+dx) + ' '+str(p[1]*f+dy)+' '+'33'+'\n')

        file3.close()
        return

    def uarm_sign(self):
        # 叠加logo
        today = str(datetime.date.today()).split('-')
        img_g = np.zeros((200, 512))
        font = cv2.FONT_HERSHEY_SIMPLEX
        # img = cv2.putText(img_g, 'by PKU-AIIT LAIR', (0, 790),
        #                   font, 2, (255, 255, 255), 1).copy()
        img = cv2.putText(img_g, '     By PKU AISR     ', (0, 180), font, 2, (255, 255, 255), 1).copy()
        img = cv2.flip(img,1)
        cv2.imwrite('/home/acir/TinyWings_AISR/drawbot/signimg.jpg',img)
        imgb = img.astype(np.uint8)
        _, cont, h = cv2.findContours(
            imgb, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
        out = np.zeros(imgb.shape, np.uint8)
        contours = []
        for c in cont:
            tmp = [tuple(x[0]) for x in c]
            contours.append(tmp)
        h = h[0]
        id = 0
        C = []
        flag = [0]*len(cont)
        for i in range(len(cont)):
            if h[i][0] == -1:
                flag[i] = -1
                flag[h[i][3]] = 1
        while id != -1:
            c = contours[id]
            next = h[id][0]
            if len(c) > 0 and flag[id] == 0:
                C.append(c)
            elif len(c) > 0 and flag[id] == 1:
                C.append(c)
            id = next

        contours = C




        for c in contours:
            for i in range(len(c)-1):
                cv2.line(out, c[i], c[i+1], (255), 1)
            cv2.line(out, c[0], c[-1], (255), 1)

        # print(len(contours))
        copyfile('/home/acir/TinyWings_AISR/drawbot/trail.txt', '/home/acir/TinyWings_AISR/drawbot/trail_sign.txt')
        file3 = open('/home/acir/TinyWings_AISR/drawbot/trail_sign.txt', 'a')
        contours = contours[::-1]

        dx = 0
        dy = 50
        f = 0.125
        for c in contours:

            print(str(c[0][0]) + ' '+str(c[0][1])+' '+'0'+'\n')
            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f + dy)+' '+'0'+'\n')
            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f + dy)+' '+'-33'+'\n')

            for p in c[1:]:

                file3.write(str(p[0]*f+dx) + ' '+str(p[1]*f+dy)+' '+'0'+'\n')

            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f+dy)+' '+'0'+'\n')

            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f+dy)+' '+'0'+'\n')
            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f+dy)+' '+'33'+'\n')

        file3.close()
        return


if __name__ == "__main__":
    drawer = DrawInterface()
    print('==================================')
    data = None
    uarm_interface = None
    drawer.draw(data,uarm_interface)
