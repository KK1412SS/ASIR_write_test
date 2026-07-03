import requests
import os
import time
from pathlib import Path
import json
from PIL import Image
import io

class AISRClient:
    def __init__(self, server_url="http://localhost:5000"):
        """
        初始化AISR客户端
        
        Args:
            server_url: 服务器地址，默认为本地5000端口
        """
        self.server_url = server_url.rstrip('/')
        self.endpoint = f"{self.server_url}/AISR"
        self.res_dict = None
    
    def upload_image(self, image_path, flipp):
        """
        上传图片到AISR服务进行处理
        
        Args:
            image_path: 要上传的图片路径
        
        Returns:
            dict: 服务器返回的结果，包含status、imgPath和traiPath
        """
        # 检查文件是否存在
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        # 加载图片
        with Image.open(image_path) as img:
            if flipp:
                # 水平翻转图片
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
                print(f"图片已翻转")
            
            # 保存为字节流用于上传
            img_byte_arr = io.BytesIO()
            # 使用 JPEG 格式直接保存
            img.save(img_byte_arr, format='JPEG')
            img_byte_arr.seek(0)
        
        # 准备文件上传
        files = {
            'file': (os.path.basename(image_path), img_byte_arr, 'image/jpeg')
        }
        
        # try:
            # 发送POST请求
        print(f"正在上传图片: {image_path}")
        start_time = time.time()
        
        response = requests.post(
            self.endpoint,
            files=files,
            timeout=30  # 设置30秒超时
        )
        self.res_dict = json.loads(response.text)
        duration = time.time() - start_time
        print(f"请求耗时: {duration*1000:.0f}ms")
        
        # 检查响应状态
        if response.status_code == 200:
            result = response.json()
            print(f"服务器响应: {result}")
            return result
        else:
            print(f"请求失败，状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return None
                
        # except requests.exceptions.Timeout:
        #     print("请求超时")
        #     return None
        # except requests.exceptions.ConnectionError:
        #     print("连接服务器失败，请检查服务器地址")
        #     return None
        # except Exception as e:
        #     print(f"请求发生异常: {e}")
        #     return None
        # finally:
        #     files['file'][1].close()  # 关闭文件
    
    def download_result(self, result, save_dir="./downloaded_results"):
        """
        下载处理结果图片和轨迹文件
        
        Args:
            result: upload_image返回的结果字典
            save_dir: 保存下载文件的目录
        """
        if not result or result.get('status') != 200:
            print("无效的结果，无法下载")
            return
        
        # 创建保存目录
        os.makedirs(save_dir, exist_ok=True)
        
        img_path = result.get('imgPath')
        trai_path = result.get('traiPath')
        
        if img_path:
            # 构建图片下载URL
            img_url = self.server_url + "/get_file/" + self.res_dict['imgPath']
            img_save_path = os.path.join(save_dir, img_path)
            
            try:
                img_response = requests.get(img_url, timeout=10)
                if img_response.status_code == 200:
                    with open(img_save_path, 'wb') as f:
                        f.write(img_response.content)
                    print(f"图片已保存: {img_save_path}")
                else:
                    print(f"下载图片失败: {img_url}")
            except Exception as e:
                print(f"下载图片异常: {e}")
        
        if trai_path:
            # 构建轨迹文件下载URL
            trai_url = self.server_url + "/get_file/" + self.res_dict['traiPath']
            trai_save_path = os.path.join(save_dir, trai_path)
            
            try:
                trai_response = requests.get(trai_url, timeout=10)
                if trai_response.status_code == 200:
                    with open(trai_save_path, 'wb') as f:
                        f.write(trai_response.content)
                    print(f"轨迹文件已保存: {trai_save_path}")
                else:
                    print(f"下载轨迹文件失败: {trai_url}")
            except Exception as e:
                print(f"下载轨迹文件异常: {e}")


def main():
    """使用示例"""
    # 创建客户端实例
    client = AISRClient("http://localhost:5555")  # 根据实际服务器地址修改
    
    # 要上传的图片路径
    image_path = "./222.jpg"  # 替换为您的图片路径
    flipp = False  # 是否水平翻转图片，默认为False
    
    # 如果需要批量处理多个图片
    image_paths = [
        "./image1.jpg",
        "./image2.jpg", 
        # 添加更多图片路径
    ]
    
    # 示例1: 单张图片处理
    print("=== 处理单张图片 ===")
    if os.path.exists(image_path):
        result = client.upload_image(image_path, flipp)
        if result and result.get('status') == 200:
            print(f"处理成功!")
            print(f"图片路径: {result.get('imgPath')}")
            print(f"轨迹路径: {result.get('traiPath')}")
            
            # 下载处理结果
            client.download_result(result, "./results")
        else:
            print("处理失败")
    else:
        print(f"测试图片不存在: {image_path}")
    
    # 示例2: 批量处理图片
    # print("\n=== 批量处理图片 ===")
    # for img_path in image_paths:
    #     if os.path.exists(img_path):
    #         print(f"\n处理: {img_path}")
    #         result = client.upload_image(img_path)
    #         if result and result.get('status') == 200:
    #             # 为每张图片创建单独的保存目录
    #             img_name = Path(img_path).stem
    #             save_dir = f"./batch_results/{img_name}"
    #             client.download_result(result, save_dir)
    #         else:
    #             print(f"处理失败: {img_path}")
            
    #         # 添加短暂延迟，避免请求过于频繁
    #         time.sleep(1)
    #     else:
    #         print(f"图片不存在: {img_path}")


if __name__ == "__main__":
    main()