import win32api
import win32con
import win32clipboard
import time
import uiautomation as uia
import win32gui
import win32process
import psutil

def get_wechat_hwnd():
    wechat_hwnd = None
    def callback(hwnd, extra):
        nonlocal wechat_hwnd
        classname = win32gui.GetClassName(hwnd)
        is_qt_wechat = classname.startswith('Qt') and classname.endswith('QWindowIcon')
        is_legacy_wechat = classname == 'WeChatMainWndForPC'
        if is_qt_wechat or is_legacy_wechat:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                if proc.name().lower() == 'weixin.exe':
                    title = win32gui.GetWindowText(hwnd)
                    if '微信' in title or title == '微信' or 'WeChat' in title:
                        wechat_hwnd = hwnd
            except Exception:
                pass
    win32gui.EnumWindows(callback, None)
    return wechat_hwnd

def set_clipboard_text(text):
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()

def test():
    hwnd = get_wechat_hwnd()
    if not hwnd:
        print("未找到微信窗口")
        return
        
    print("连接成功！正在获取输入框...")
    control = uia.ControlFromHandle(hwnd)
    input_field = control.EditControl(AutomationId='chat_input_field')
    if not input_field.Exists(2):
        print("请打开微信聊天窗口")
        return
        
    input_field.SetFocus()
    time.sleep(0.1) # 给予窗口系统微调对焦的时间
    
    msg = "这是测试消息：直接通过 Win32 API 极速写入并发送！"
    set_clipboard_text(msg)
    
    print("开始发送...")
    start = time.time()
    
    # 模拟 Ctrl+A
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord('A'), 0, 0, 0)
    win32api.keybd_event(ord('A'), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    # 模拟 Delete
    win32api.keybd_event(win32con.VK_DELETE, 0, 0, 0)
    win32api.keybd_event(win32con.VK_DELETE, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    # 模拟 Ctrl+V
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord('V'), 0, 0, 0)
    win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    # 模拟 Enter
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    end = time.time()
    print(f"发送操作执行完毕，纯操作耗时: {(end - start)*1000:.2f} 毫秒")

if __name__ == '__main__':
    test()
