import numpy as np
from tqdm import tqdm
import json

output_file = './output/trail_sign.txt'
trail_text = []
from arm_trigger.mode_intf.xarm_interface import XarmInterface
uarm_interface = XarmInterface()
if_connect = uarm_interface.connect()
global_speed = 1

print(if_connect)
def uarm_draw(file):
        dh = 15.
        x0=300.   #初始基准位置
        y0=-200.
        write_h = 0.623
        last_z=write_h+dh/1000
        image_size = 1.5
        raw_p = []
        for l in file:
            d = l.split(' ')
            
            p = [140.0 - float(d[0])*image_size,140.0 - float(d[1])*image_size]
            z=float(d[2])
            if z==0:
                z=last_z
            elif z<0:
                z=write_h
            else:
                z=write_h+dh/1000
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
            trail_text.append([x,y,z])
        
        return True  


def get_draw_mat():
        # with open(os.getcwd()+"/src/tad-ros2/tad_robot/pyscript/drawbot/trail_test.txt",'r') as ff: 
        # with open('/mnt/ros2/src/trail.txt','r') as ff: 
        record_info = '000'
        with open(output_file,'r') as ff: 
        # with open("trail.txt",'r') as ff:
            file_org = ff.readlines()
            file=file_org[:]
            date_info = file_org[-1]
            print("date_info:",date_info)
            print("record_info:",record_info)
            if record_info != date_info:
                record_info = date_info
                if uarm_draw(file):
                    print('绘画轨迹获取完成')
                    return 1
                else:
                    print('绘画轨迹获取失败1')
                    record_info = '000'
                    return -2
            else:
                print('绘画轨迹获取失败2')
                record_info = '000'

                return -2
        return -2

def draw(data):
    for i in tqdm(list(range(len(data)))):
            prdrawogress_rate = ((i+1)/len(data))*100 
            progress_rate = 0
            if int(progress_rate)%2==0:
                msg = {}
                # msg['progress_rate'] = int(self.progress_rate)
                msg = json.dumps(msg,ensure_ascii=False)
                #publisher.publish(pub_msg)
            # print(f"======{msg}  {i} / {len(data)}")
            # time.sleep(0.1)
            # continue
            # if stop_flag:
            #     print("=====stop.....")
            #     self.record_info = '000'
            #     self.reset_flag()
            #     # uarm_interface.set_head_reset() #  恢复
            #     return -1

            y, x, z = data[i, :]
            current_h = z
            #if xforce_data is None:
            uarm_interface.set_position(
                x=x, y=y, z=z, speed=global_speed, wait=True)
            # else:
            #     if data[i, 2]==uarm_interface.action_hight+15/1000:
            #         uarm_interface.set_position(x=x, y=y, z=current_h)
            #     else:
            #         if i>0 and  data[i-1, 2]==uarm_interface.action_hight+dh/1000 and data[i, 2]==uarm_interface.action_hight:
            #             # z_2 = z + 4/1000
            #             # uarm_interface.set_position(x=x, y=y, z=z_2)
            #             current_h = uarm_interface.set_position_2(x=x, y=y, z=z, xforce_data=xforce_data)

            #         else:
            #             # uarm_interface.set_position_2(x=x, y=y, z=z, xforce_data=xforce_data)
            #             uarm_interface.set_position(x=x, y=y, z=current_h)

                
    print("绘画完成！")


if __name__ == "__main__":
    get_draw_mat()
    data = np.array(trail_text)
    data = data.reshape([-1, 3])
    print(data)
    with open("./output/draw_point_test.csv","w") as f:
        for i in range(len(data)):
            f.write("%f,%f,%f\n"%(data[i,0],data[i,1],data[i,2])) 
    draw(data)