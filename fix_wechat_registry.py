import os
import subprocess
import winreg
import sys

def get_running_wechat_path():
    """尝试通过当前正在运行的微信进程获取其安装路径"""
    try:
        # 使用 powershell 查询运行中的 WeChat 进程路径
        cmd = ["powershell", "-NoProfile", "-Command", "Get-Process WeChat -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Path"]
        result = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        path = result.stdout.strip()
        if path and os.path.exists(path):
            # 返回 WeChat.exe 所在的文件夹路径
            return os.path.dirname(path)
    except Exception as e:
        print(f"尝试通过进程查找微信失败: {e}")
    return None

def find_default_paths():
    """在电脑常见默认安装路径中寻找微信"""
    common_paths = [
        r"C:\Program Files (x86)\Tencent\WeChat",
        r"C:\Program Files\Tencent\WeChat",
        r"D:\Program Files (x86)\Tencent\WeChat",
        r"D:\Program Files\Tencent\WeChat",
        r"E:\Program Files (x86)\Tencent\WeChat",
        r"E:\Program Files\Tencent\WeChat",
    ]
    for path in common_paths:
        exe_path = os.path.join(path, "WeChat.exe")
        if os.path.exists(exe_path):
            return path
    return None

def write_registry(install_path):
    """将微信安装路径写入注册表"""
    try:
        # 创建或打开微信注册表项
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Tencent\WeChat", 0, winreg.KEY_WRITE)
        # 写入 InstallPath 字符串值
        winreg.SetValueEx(key, "InstallPath", 0, winreg.REG_SZ, install_path)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"写入注册表失败: {e}")
        return False

def main():
    print("=" * 60)
    print("      WeChatFerry 微信注册表路径修复工具")
    print("=" * 60)
    
    # 步骤1：尝试自动获取微信路径
    wechat_dir = get_running_wechat_path()
    if wechat_dir:
        print(f"[自动检测] 发现正在运行的微信，路径为:\n  {wechat_dir}")
    else:
        print("[提示] 未检测到运行中的微信，正在搜索常见默认安装目录...")
        wechat_dir = find_default_paths()
        if wechat_dir:
            print(f"[自动检测] 在默认目录中找到了微信，路径为:\n  {wechat_dir}")
            
    # 步骤2：若自动获取失败，让用户手动输入
    if not wechat_dir:
        print("\n[警告] 自动搜索微信安装路径失败！")
        print("请在下方手动输入您的微信安装目录（必须包含 WeChat.exe 文件）。")
        print("（例如：C:\\Program Files (x86)\\Tencent\\WeChat）")
        
        while True:
            user_input = input("\n请输入微信安装路径: ").strip()
            # 去掉两侧的引号（如果有）
            user_input = user_input.replace('"', '').replace("'", "")
            
            if not user_input:
                continue
            
            # 判断输入的路径是否合法
            exe_check = os.path.join(user_input, "WeChat.exe")
            if os.path.exists(user_input) and os.path.exists(exe_check):
                wechat_dir = user_input
                break
            else:
                print(f"[错误] 路径无效！在该路径下未找到 WeChat.exe，请重新输入。")
                
    # 步骤3：写入注册表
    print("\n正在写入注册表...")
    if write_registry(wechat_dir):
        print("\n" + "=" * 60)
        print("【修复成功！】")
        print(f"已将微信安装路径成功写入注册表：\n  {wechat_dir}")
        print("现在您可以重新运行微信助手，尝试连接了！")
        print("=" * 60)
    else:
        print("\n[错误] 修复失败，请尝试以“管理员身份”打开命令行重新运行此脚本。")

if __name__ == "__main__":
    main()
