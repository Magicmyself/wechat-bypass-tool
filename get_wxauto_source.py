import urllib.request
import zipfile
import io
import os
import shutil

def main():
    zip_url = "https://ghp.ci/https://github.com/cluic/wxauto/archive/refs/heads/master.zip"
    target_dir = "wxauto"
    
    print("=" * 60)
    print("      wxauto 源码自动获取与配置脚本")
    print("=" * 60)
    
    if os.path.exists(target_dir):
        print(f"[提示] 目标文件夹 {target_dir} 已存在，正在清理以准备全新安装...")
        shutil.rmtree(target_dir)
        
    # 尝试多个镜像源以提高成功率
    urls = [
        "https://ghp.ci/https://github.com/cluic/wxauto/archive/refs/heads/master.zip",
        "https://ghproxy.net/https://github.com/cluic/wxauto/archive/refs/heads/master.zip",
        "https://github.com/cluic/wxauto/archive/refs/heads/master.zip"
    ]
    
    zip_data = None
    for url in urls:
        print(f"正在从源 {url} 下载最新 wxauto 源码...")
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                zip_data = response.read()
            print("[成功] 下载完成！")
            break
        except Exception as e:
            print(f"源下载失败: {e}，正在尝试下一个...")
            
    if not zip_data:
        print("\n[错误] 所有镜像源均下载失败，请检查您的网络连接或尝试手动下载。")
        return
        
    try:
        print("正在解压...")
        # 解压 ZIP
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            # 找到解压文件夹下的 wxauto 目录并复制出来
            # GitHub zip 解压后默认最外层是 wxauto-main 文件夹
            for file_info in z.infolist():
                if "wxauto-main/wxauto/" in file_info.filename:
                    # 获取相对路径
                    rel_path = file_info.filename.split("wxauto-main/wxauto/")[1]
                    if not rel_path:  # 文件夹自身
                        continue
                    
                    dest_file = os.path.join(target_dir, rel_path)
                    
                    # 如果是目录，创建之
                    if file_info.is_dir():
                        os.makedirs(dest_file, exist_ok=True)
                    else:
                        # 确保父目录存在
                        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                        # 写入文件
                        with z.open(file_info) as src, open(dest_file, "wb") as dest:
                            shutil.copyfileobj(src, dest)
                            
        print("\n" + "=" * 60)
        print("【配置成功！】")
        print(f"已将最新版 `wxauto` 源码成功配置到您的项目目录：\n  {os.path.abspath(target_dir)}")
        print("现在您可以直接运行新版秒回助手：")
        print("  python wechat_gui_wxauto.py")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[错误] 配置失败: {e}")
        print("请检查您的网络连接或尝试手动下载解压。")

if __name__ == "__main__":
    main()
