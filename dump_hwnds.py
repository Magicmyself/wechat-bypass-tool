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

def main():
    hwnd = get_wechat_hwnd()
    if not hwnd:
        print("未找到微信窗口")
        return
        
    print(f"微信主窗口 HWND: {hwnd}, Title: {win32gui.GetWindowText(hwnd)}, Class: {win32gui.GetClassName(hwnd)}")
    
    children = []
    def child_callback(child_hwnd, extra):
        children.append(child_hwnd)
    
    try:
        win32gui.EnumChildWindows(hwnd, child_callback, None)
    except Exception as e:
        print(f"枚举子窗口失败: {e}")
        return
        
    print(f"找到 {len(children)} 个子窗口:")
    for ch in children:
        print(f"  HWND: {ch}, Class: {win32gui.GetClassName(ch)}, Title: {win32gui.GetWindowText(ch)}")

if __name__ == '__main__':
    main()
