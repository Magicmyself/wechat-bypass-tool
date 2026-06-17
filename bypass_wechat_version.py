import ctypes
import ctypes.wintypes
import sys
import os

# ==================== Windows API 声明 ====================
PROCESS_ALL_ACCESS = 0x000F0000 | 0x00100000 | 0xFFFF
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ('dwSize', ctypes.wintypes.DWORD),
        ('cntUsage', ctypes.wintypes.DWORD),
        ('th32ProcessID', ctypes.wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.c_void_p),
        ('th32ModuleID', ctypes.wintypes.DWORD),
        ('cntThreads', ctypes.wintypes.DWORD),
        ('th32ParentProcessID', ctypes.wintypes.DWORD),
        ('pcPriClassBase', ctypes.wintypes.LONG),
        ('dwFlags', ctypes.wintypes.DWORD),
        ('szExeFile', ctypes.c_char * 260)
    ]

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ('dwSize', ctypes.wintypes.DWORD),
        ('th32ModuleID', ctypes.wintypes.DWORD),
        ('th32ProcessID', ctypes.wintypes.DWORD),
        ('GlblcntUsage', ctypes.wintypes.DWORD),
        ('ProccntUsage', ctypes.wintypes.DWORD),
        ('modBaseAddr', ctypes.c_void_p),
        ('modBaseSize', ctypes.wintypes.DWORD),
        ('hModule', ctypes.wintypes.HMODULE),
        ('szModule', ctypes.c_char * 256),
        ('szExePath', ctypes.c_char * 260)
    ]

PAGE_READWRITE = 0x04
PAGE_EXECUTE_READWRITE = 0x40

# ==================== 显式声明 Windows API 参数类型 (防止 64 位基址整数溢出) ====================
ctypes.windll.kernel32.OpenProcess.argtypes = [
    ctypes.wintypes.DWORD,
    ctypes.wintypes.BOOL,
    ctypes.wintypes.DWORD
]
ctypes.windll.kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE

ctypes.windll.kernel32.ReadProcessMemory.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)
]
ctypes.windll.kernel32.ReadProcessMemory.restype = ctypes.wintypes.BOOL

ctypes.windll.kernel32.WriteProcessMemory.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)
]
ctypes.windll.kernel32.WriteProcessMemory.restype = ctypes.wintypes.BOOL

ctypes.windll.kernel32.VirtualProtectEx.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.wintypes.DWORD,
    ctypes.POINTER(ctypes.wintypes.DWORD)
]
ctypes.windll.kernel32.VirtualProtectEx.restype = ctypes.wintypes.BOOL

# ==================== 核心逻辑 ====================

def get_pid_by_name(process_name):
    """根据进程名获取 PID"""
    hProcessSnap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if hProcessSnap == -1:
        return None
        
    pe32 = PROCESSENTRY32()
    pe32.dwSize = ctypes.sizeof(PROCESSENTRY32)
    
    if not ctypes.windll.kernel32.Process32First(hProcessSnap, ctypes.byref(pe32)):
        ctypes.windll.kernel32.CloseHandle(hProcessSnap)
        return None
        
    pids = []
    while True:
        exe_file = pe32.szExeFile.decode('gbk', errors='ignore')
        if exe_file.lower() == process_name.lower():
            pids.append(pe32.th32ProcessID)
        if not ctypes.windll.kernel32.Process32Next(hProcessSnap, ctypes.byref(pe32)):
            break
            
    ctypes.windll.kernel32.CloseHandle(hProcessSnap)
    return pids

def get_module_info(pid, module_name):
    """获取进程中特定模块的基址和大小"""
    hModuleSnap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    if hModuleSnap == -1:
        return None, None
        
    me32 = MODULEENTRY32()
    me32.dwSize = ctypes.sizeof(MODULEENTRY32)
    
    if not ctypes.windll.kernel32.Module32First(hModuleSnap, ctypes.byref(me32)):
        ctypes.windll.kernel32.CloseHandle(hModuleSnap)
        return None, None
        
    base_addr = None
    base_size = None
    
    while True:
        sz_module = me32.szModule.decode('gbk', errors='ignore')
        if sz_module.lower() == module_name.lower():
            base_addr = me32.modBaseAddr
            base_size = me32.modBaseSize
            break
        if not ctypes.windll.kernel32.Module32Next(hModuleSnap, ctypes.byref(me32)):
            break
            
    ctypes.windll.kernel32.CloseHandle(hModuleSnap)
    return base_addr, base_size

def patch_wechat_version(pid):
    """在 WeChat 内存中查找并替换版本号"""
    print(f"正在分析进程 PID: {pid}")
    
    # 获取 WeChatWin.dll 基址和大小
    base_addr, base_size = get_module_info(pid, "WeChatWin.dll")
    if not base_addr or not base_size:
        print("[错误] 未能找到 WeChatWin.dll 模块，请确认微信是否已完全启动并处于登录界面！")
        return False
        
    print(f"找到 WeChatWin.dll -> 基址: {hex(base_addr)} | 大小: {base_size / 1024 / 1024:.2f} MB")
    
    # 打开进程
    h_process = ctypes.windll.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        print("[错误] 打开微信进程失败，请尝试“右键 -> 以管理员身份运行”此脚本！")
        return False
        
    # 定义搜索特征值 (3.9.12.17 在内存中的 hex 值：0x63090c11，little-endian 就是 11 0C 09 63)
    target_bytes = b'\x11\x0c\x09\x63'
    # 替换目标值 (修改为 3.9.15.15 的 hex 值：0x63090f0f，little-endian 就是 0F 0F 09 63)
    replace_bytes = b'\x0f\x0f\x09\x63'
    
    # 一次性读取 WeChatWin.dll 对应的整块内存进行搜索
    buffer = ctypes.create_string_buffer(base_size)
    bytes_read = ctypes.c_size_t(0)
    
    if not ctypes.windll.kernel32.ReadProcessMemory(h_process, base_addr, buffer, base_size, ctypes.byref(bytes_read)):
        print("[错误] 读取微信内存失败！")
        ctypes.windll.kernel32.CloseHandle(h_process)
        return False
        
    data = buffer.raw
    offset = 0
    match_count = 0
    
    print("正在搜索版本特征值并进行热修改...")
    while True:
        # 在读取的内存数据中查找特征字节
        offset = data.find(target_bytes, offset)
        if offset == -1:
            break
            
        target_addr = base_addr + offset
        print(f"发现版本标识地址: {hex(target_addr)}")
        
        # 尝试写入新版本号
        bytes_written = ctypes.c_size_t(0)
        old_protect = ctypes.wintypes.DWORD(0)
        
        # 修改内存属性为可写
        ctypes.windll.kernel32.VirtualProtectEx(h_process, target_addr, 4, PAGE_EXECUTE_READWRITE, ctypes.byref(old_protect))
        
        # 写入新版本数据
        res = ctypes.windll.kernel32.WriteProcessMemory(h_process, target_addr, replace_bytes, 4, ctypes.byref(bytes_written))
        
        # 还原内存属性
        ctypes.windll.kernel32.VirtualProtectEx(h_process, target_addr, 4, old_protect, ctypes.byref(old_protect))
        
        if res and bytes_written.value == 4:
            match_count += 1
            print(f" -> 修改成功！版本伪装 3.9.12.17 -> 3.9.15.15")
        else:
            print(f" -> 修改失败！")
            
        offset += 4  # 继续往后寻找
        
    ctypes.windll.kernel32.CloseHandle(h_process)
    
    if match_count > 0:
        print(f"\n[成功] 内存修改完毕，共替换了 {match_count} 处版本标识！")
        print("现在请在电脑微信界面上重新点击“扫码登录”或“切换账号”，扫码即可顺利登录！")
        return True
    else:
        print("\n[提示] 未在内存中搜寻到 3.9.12.17 的特征码。")
        print("这通常是因为：")
        print("1. 您当前的微信不是 3.9.12.17 版本，请确认。")
        print("2. 内存修改已经成功执行过一次了，请直接扫码登录测试。")
        return False

def main():
    print("=" * 60)
    print("      微信 3.9.12.17 登录版本过低限制绕过脚本")
    print("=" * 60)
    
    # 查找微信进程
    pids = get_pid_by_name("WeChat.exe")
    if not pids:
        print("[提示] 未检测到运行中的 WeChat.exe。")
        print("请先手动打开微信，让其停留在“扫码登录/登录”界面，然后重新运行本脚本！")
        input("\n按回车键退出...")
        return
        
    for pid in pids:
        patch_wechat_version(pid)
        
    print("=" * 60)

if __name__ == "__main__":
    main()
