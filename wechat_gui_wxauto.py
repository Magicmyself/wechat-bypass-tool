import os
import sys
import re
import time
import random
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import uiautomation as uia
import win32gui
import win32process
import win32con
import psutil
import pyperclip
import win32api
import win32clipboard

# 极致优化：将 uiautomation 操作默认的 500ms 睡眠时间压缩至 10ms，极大降低窗口切换和点击后的额外延时
uia.uiautomation.OPERATION_WAIT_TIME = 0.01

def set_clipboard_text(text):
    # 使用 Win32 原生 API 极速写入剪贴板，避免 pyperclip 的库环境检查开销
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()

def is_time_string(s):
    s = s.strip()
    # 1. 匹配 HH:MM 或 H:MM
    if re.match(r'^\d{1,2}[:：]\d{2}$', s):
        return True
    # 2. 匹配 上午/下午/AM/PM + HH:MM
    if re.match(r'^(上午|下午|AM|PM)\s*\d{1,2}[:：]\d{2}$', s):
        return True
    # 3. 匹配 昨天, 前天
    if s in ["昨天", "前天"]:
        return True
    # 4. 匹配 星期一 到 星期日，周一 到 周日
    if re.match(r'^(星期|周)[一二三四五六日]$', s):
        return True
    # 5. 匹配 日期格式 2026/06/29, 2026-06-29, 26/6/29, 6月29日 等
    if re.match(r'^\d{2,4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?$', s):
        return True
    # 6. 匹配仅月日 06-29, 6/29
    if re.match(r'^\d{1,2}[-/.月]\d{1,2}日?$', s):
        return True
    return False

class WeChatNT:
    def __init__(self):
        self.HWND = self.get_wechat_hwnd()
        if not self.HWND:
            raise Exception("未找到微信主窗口。请确保微信PC端已启动并登录。")

        # 如果微信窗口最小化了，自动将其还原
        if win32gui.IsIconic(self.HWND):
            win32gui.ShowWindow(self.HWND, win32con.SW_RESTORE)
            time.sleep(1)

        self.control = uia.ControlFromHandle(self.HWND)
        if not self.control.Exists(1):
            raise Exception("无法绑定微信窗口句柄，可能权限不足，请尝试以管理员身份运行。")

        # 多候选回退：绑定并缓存会话列表 ListControl
        # 新版Qt微信用 AutomationId='session_list'，旧版用 ClassName='SessionList'
        self.session_list = self._find_control_multi(
            [("list", {"AutomationId": "session_list"}),
             ("list", {"ClassName": "SessionList"}),
             ("list", {})],
            timeout=1.5
        ) or self.control

        # 多候选回退：绑定并缓存聊天标题栏
        self.chat_title_bar = self._find_control_multi(
            [("group", {"ClassName": "mmui::ChatTitleBarMasterView"}),
             ("group", {"ClassName": "TitleBarView"}),
             ("group", {"AutomationId": "chat_title_bar"})],
            timeout=1.0
        )

        # 发送端当前群聊状态缓存（无需每次查询 UIA 标题栏）
        self._current_chat = None

    def _find_control_multi(self, candidates, timeout=0.5):
        """多候选回退查询：按优先级依次尝试，找到即返回，全部失败返回 None"""
        for ctrl_type, kwargs in candidates:
            try:
                if ctrl_type == "list":
                    c = self.control.ListControl(**kwargs)
                elif ctrl_type == "group":
                    c = self.control.GroupControl(**kwargs)
                elif ctrl_type == "edit":
                    c = self.control.EditControl(**kwargs)
                else:
                    c = self.control.Control(**kwargs)
                if c.Exists(timeout):
                    return c
            except Exception:
                continue
        return None

    def get_wechat_hwnd(self):
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

    def check_connection(self):
        """检查并自动修复 UIA 连接，确保长效监控稳定性"""
        current_hwnd = self.get_wechat_hwnd()
        if not current_hwnd:
            raise Exception("未找到运行中的微信主窗口")
            
        # 1. 自动恢复最小化的微信窗口，防止其导致 UIA 控件无法被渲染和点击
        if win32gui.IsWindow(self.HWND) and win32gui.IsIconic(self.HWND):
            win32gui.ShowWindow(self.HWND, win32con.SW_RESTORE)
            time.sleep(0.5)
            self.control = uia.ControlFromHandle(self.HWND)
            self.session_list = None
            self.chat_title_bar = None
            self.input_field = None
            
        rebind_needed = False
        if current_hwnd != self.HWND:
            rebind_needed = True
        else:
            try:
                if not self.control.Exists(0):
                    rebind_needed = True
            except Exception:
                rebind_needed = True
                
        if rebind_needed:
            self.HWND = current_hwnd
            if win32gui.IsIconic(self.HWND):
                win32gui.ShowWindow(self.HWND, win32con.SW_RESTORE)
                time.sleep(0.5)
            self.control = uia.ControlFromHandle(self.HWND)
            self.session_list = None
            self.chat_title_bar = None
            self.input_field = None
            
        # 2. 验证并修复 session_list
        session_list_valid = False
        if hasattr(self, 'session_list') and self.session_list:
            try:
                if self.session_list.Exists(0):
                    session_list_valid = True
            except Exception:
                pass
                
        if not session_list_valid:
            self.session_list = self._find_control_multi(
                [("list", {"AutomationId": "session_list"}),
                 ("list", {"ClassName": "SessionList"}),
                 ("list", {})],
                timeout=0
            ) or self.control
            
        # 3. 验证并修复标题栏
        title_valid = False
        if hasattr(self, 'chat_title_bar') and self.chat_title_bar:
            try:
                if self.chat_title_bar.Exists(0):
                    title_valid = True
            except Exception:
                pass
                
        if not title_valid:
            self.chat_title_bar = self._find_control_multi(
                [("group", {"ClassName": "mmui::ChatTitleBarMasterView"}),
                 ("group", {"ClassName": "TitleBarView"}),
                 ("group", {"AutomationId": "chat_title_bar"})],
                timeout=0
            )

    def _find_input_field(self, timeout=0):
        """多候选回退：查找聊天输入框"""
        candidates = [
            {"AutomationId": "chat_input_field"},
            {"ClassName": "mmui::XValidatorTextEdit", "Name": ""},
            {"ClassName": "RichEdit20W"},
        ]
        for kwargs in candidates:
            try:
                f = self.control.EditControl(**{k: v for k, v in kwargs.items() if v != ""})
                if f.Exists(timeout):
                    return f
            except Exception:
                continue
        try:
            f = self.control.EditControl()
            if f.Exists(timeout):
                return f
        except Exception:
            pass
        return None

    def _find_search_box(self, timeout=0):
        """多候选回退：查找微信搜索框"""
        candidates = [
            {"ClassName": "mmui::XValidatorTextEdit", "Name": "搜索"},
            {"ClassName": "mmui::XValidatorTextEdit", "Name": "Search"},
            {"AutomationId": "search_input"},
            {"Name": "搜索"},
        ]
        for kwargs in candidates:
            try:
                f = self.control.EditControl(**{k: v for k, v in kwargs.items()})
                if f.Exists(timeout):
                    return f
            except Exception:
                continue
        return None

    def ChatWith(self, who):
        """切换到指定群/联系人聊天窗口，优先会话列表直接点击，回退到搜索框"""
        try:
            win32gui.SetForegroundWindow(self.HWND)
        except Exception:
            pass

        # 路径1：从 session_list 直接按 AutomationId 点击（新版Qt微信）
        try:
            session = self.session_list.ListItemControl(AutomationId=f'session_item_{who}')
            if session.Exists(0):
                rect = session.BoundingRectangle
                if rect.width > 0 and rect.height > 0:
                    session.Click(simulateMove=False, waitTime=0)
                    self._current_chat = who
                    return True
        except Exception:
            pass

        # 路径2：从 session_list 按 Name 匹配（旧版微信或 AutomationId 不存在时）
        try:
            who_clean = re.sub(r'\s+', '', who).lower()
            items = self.session_list.GetChildren()
            for item in items:
                try:
                    name_clean = re.sub(r'\s+', '', item.Name).lower()
                    if who_clean in name_clean:
                        rect = item.BoundingRectangle
                        if rect.width > 0 and rect.height > 0:
                            item.Click(simulateMove=False, waitTime=0)
                            self._current_chat = who
                            return True
                except Exception:
                    continue
        except Exception:
            pass

        # 路径3：使用搜索框（多候选查找搜索框）
        search_box = self._find_search_box(timeout=0.05)
        if search_box:
            try:
                search_box.Click(simulateMove=False, waitTime=0)
                search_box.SendKeys('{Ctrl}a{Delete}', waitTime=0)
                set_clipboard_text(who)
                search_box.SendKeys('{Ctrl}v', waitTime=0)
                time.sleep(0.05) # 50ms 等待搜索结果渲染
                search_box.SendKeys('{Enter}', waitTime=0)
                self._current_chat = who
                return True
            except Exception:
                pass

        return False

    def SendMsg(self, msg):
        """发送消息到当前已激活的聊天窗口"""
        try:
            win32gui.SetForegroundWindow(self.HWND)
        except Exception:
            pass

        if not hasattr(self, 'input_field') or not self.input_field:
            self.input_field = self._find_input_field(timeout=0.05)
            
        if not self.input_field:
            raise Exception("未找到聊天输入框，请确认群聊窗口已正确打开")

        try:
            self.input_field.SetFocus()
        except Exception:
            self.input_field = self._find_input_field(timeout=0.05)
            if not self.input_field:
                raise Exception("未找到聊天输入框，请确认群聊窗口已正确打开")
            self.input_field.SetFocus()

        set_clipboard_text(msg)

        # 原生 Win32 keybd_event 零延迟模拟键盘，消除 uiautomation SendKeys 内置的 120ms+ 延时
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord('A'), 0, 0, 0)
        win32api.keybd_event(ord('A'), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

        win32api.keybd_event(win32con.VK_DELETE, 0, 0, 0)
        win32api.keybd_event(win32con.VK_DELETE, 0, win32con.KEYEVENTF_KEYUP, 0)

        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord('V'), 0, 0, 0)
        win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

        paste_delay = max(0.002, min(0.03, len(msg) * 0.0001))
        time.sleep(paste_delay)

        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

    def GetCurrentActiveChatName(self):
        """读取当前打开的聊天窗口名称（多候选标题栏查找）"""
        if not self.chat_title_bar:
            self.chat_title_bar = self._find_control_multi(
                [("group", {"ClassName": "mmui::ChatTitleBarMasterView"}),
                 ("group", {"ClassName": "TitleBarView"}),
                 ("group", {"AutomationId": "chat_title_bar"})],
                timeout=0
            )
        if not self.chat_title_bar:
            return None

        # 多候选读取标题文字
        for kwargs in [{"ClassName": "mmui::XTextView"}, {"ClassName": "XTextView"}, {}]:
            try:
                label = self.chat_title_bar.TextControl(**kwargs)
                if label.Exists(0):
                    return label.Name
            except Exception:
                continue
        return None

    def GetLastMessage(self, who):
        """从会话列表读取指定群的最后一条消息（发送者, 内容）"""
        session = None
        try:
            s = self.session_list.ListItemControl(AutomationId=f'session_item_{who}')
            if s.Exists(0):
                session = s
        except Exception:
            pass

        if not session:
            try:
                who_clean = re.sub(r'\s+', '', who).lower()
                items = self.session_list.GetChildren()
                for item in items:
                    try:
                        name_clean = re.sub(r'\s+', '', item.Name).lower()
                        if who_clean in name_clean:
                            session = item
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if not session:
            return None, None

        try:
            name = session.Name
        except Exception:
            return None, None

        lines = [l.strip() for l in name.split('\n') if l.strip()]
        if not lines:
            return None, None

        # 寻找时间行作为锚点，获取时间行前的一行作为消息内容行
        msg_line = None
        for idx, line in enumerate(lines):
            if is_time_string(line):
                if idx > 0:
                    msg_line = lines[idx - 1]
                break
        
        # 备选回退方案：如果无法识别时间行，则通过排除已知后缀进行回退
        if msg_line is None:
            temp_lines = [l for l in lines if l not in ['消息免打扰', '已置顶', 'Mute']]
            if len(temp_lines) >= 2:
                msg_line = temp_lines[-2]
            else:
                msg_line = lines[-1]

        if not msg_line:
            return None, None

        if ':' in msg_line:
            parts = msg_line.split(':', 1)
            sender = parts[0].strip()
            content = parts[1].strip() if len(parts) > 1 else ""
            return sender, content
        elif '：' in msg_line:
            parts = msg_line.split('：', 1)
            sender = parts[0].strip()
            content = parts[1].strip() if len(parts) > 1 else ""
            return sender, content
        else:
            return "", msg_line


class WeChatBotWxAutoGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("微信消息极速秒回助手 - UIA驱动版 (支持最新微信)")
        self.root.geometry("1150x700")
        self.root.minsize(1000, 550)
        
        # 内部状态变量
        self.wx = None
        self.is_connected = False
        self.is_monitoring = False
        
        self.rules = []           # 规则库配置列表，格式如：{"room":x, "sender":y, "mode":z, "keywords":[], "reply":w}
        self.rules_lock = threading.Lock() # 线程锁，保证规则读写安全
        self.load_rules()         # 从本地加载规则库
        self.target_rooms = []    # 提取 of unique monitored group list
        self.safe_mode = tk.BooleanVar(value=True)
        self.current_active_room = None
        
        # 快捷短语与记录板数据初始化
        self.snippets = []
        self.snippets_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wechat_snippets.json")
        self.load_snippets()
        
        # 消息同步队列与后台线程
        self.gui_queue = queue.Queue()
        self.reply_queue = queue.Queue()  # 串行发送任务队列（彻底消除并发冲突）
        self.listener_thread = None
        self.sender_thread = None
        self.is_listening = False
        self.last_msg_sigs = {}   # 各群最新消息签名映射表
        
        # 界面主题与布局
        self.setup_styles()
        self.build_ui()
        
        # 开启队列检查定时器
        self.root.after(100, self.process_queue)
        
        # 窗口关闭安全释放
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        self.bg_color = "#f5f6fa"
        self.primary_color = "#3498db"
        self.success_color = "#2ecc71"
        self.danger_color = "#e74c3c"
        
        style.configure(".", background=self.bg_color, font=("微软雅黑", 10))
        style.configure("TLabel", background=self.bg_color)
        style.configure("Header.TLabel", font=("微软雅黑", 12, "bold"))
        style.configure("Status.TLabel", font=("微软雅黑", 10, "italic"))
        
        style.configure("TButton", font=("微软雅黑", 10), padding=5)
        style.configure("Primary.TButton", background=self.primary_color, foreground="white")
        style.map("Primary.TButton", background=[("active", "#2980b9")])
        style.configure("Success.TButton", background=self.success_color, foreground="white")
        style.map("Success.TButton", background=[("active", "#27ae60")])
        style.configure("Danger.TButton", background=self.danger_color, foreground="white")
        style.map("Danger.TButton", background=[("active", "#c0392b")])

    def build_ui(self):
        # 顶部：连接微信区块
        top_frame = ttk.LabelFrame(self.root, text=" 微信连接状态 ", padding=10)
        top_frame.pack(fill="x", padx=15, pady=10)
        
        self.btn_connect = ttk.Button(top_frame, text=" 第一步：连接并绑定当前微信 ", style="Primary.TButton", command=self.connect_wechat)
        self.btn_connect.pack(side="left", padx=5)
        
        self.lbl_status = ttk.Label(top_frame, text="未连接 (支持任意版本PC端微信)", style="Status.TLabel", foreground="gray")
        self.lbl_status.pack(side="left", padx=15)

        # 中部：主要控制和数据区域 (两栏布局)
        main_pane = ttk.PanedWindow(self.root, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=15, pady=5)
        
        # 左侧面板：设置参数与自动回复
        left_frame = ttk.LabelFrame(main_pane, text=" 秒回配置中心 & 规则库 ", padding=10)
        main_pane.add(left_frame, weight=1)
        left_frame.columnconfigure(0, weight=1)
        left_frame.columnconfigure(1, weight=1)
        
        # 目标群聊名称 (支持中文昵称)
        ttk.Label(left_frame, text="目标群聊名称 (单群):").grid(row=0, column=0, sticky="w", pady=2)
        self.ent_room = ttk.Entry(left_frame, width=30)
        self.ent_room.grid(row=1, column=0, columnspan=2, sticky="we", pady=2)
        
        # 目标人昵称 (支持中文昵称)
        ttk.Label(left_frame, text="目标发言人昵称 (单人，*表所有人):").grid(row=2, column=0, sticky="w", pady=2)
        self.ent_sender = ttk.Entry(left_frame, width=30)
        self.ent_sender.grid(row=3, column=0, columnspan=2, sticky="we", pady=2)
        
        # 匹配规则选择 与 触发关键词 并列
        ttk.Label(left_frame, text="匹配规则模式:").grid(row=4, column=0, sticky="w", pady=2)
        self.lbl_keywords = ttk.Label(left_frame, text="触发关键词 (英文逗号分隔):")
        self.lbl_keywords.grid(row=4, column=1, sticky="w", pady=2)
        
        self.cmb_mode = ttk.Combobox(left_frame, values=["无条件秒回 (任意内容)", "包含任意关键词", "精确匹配关键词"], state="readonly")
        self.cmb_mode.current(0)
        self.cmb_mode.grid(row=5, column=0, sticky="we", padx=(0, 5), pady=2)
        self.cmb_mode.bind("<<ComboboxSelected>>", self.on_match_mode_change)
        
        self.ent_keywords = ttk.Entry(left_frame, width=15)
        self.ent_keywords.grid(row=5, column=1, sticky="we", padx=(5, 0), pady=2)
        self.ent_keywords.config(state="disabled")
        
        # 回复内容
        ttk.Label(left_frame, text="专属秒回回复内容:").grid(row=6, column=0, sticky="w", pady=2)
        self.txt_reply = scrolledtext.ScrolledText(left_frame, height=2, font=("微软雅黑", 9))
        self.txt_reply.grid(row=7, column=0, columnspan=2, sticky="we", pady=2)
        self.txt_reply.insert("1.0", "收到！这是自动秒回测试。")
        
        # 规则控制操作按钮
        self.btn_add_rule = ttk.Button(left_frame, text=" 添加 / 更新规则 ", style="Success.TButton", command=self.add_or_update_rule)
        self.btn_add_rule.grid(row=8, column=0, sticky="we", padx=(0, 5), pady=5)
        
        self.btn_del_rule = ttk.Button(left_frame, text=" 删除选中规则 ", style="Danger.TButton", command=self.delete_rule)
        self.btn_del_rule.grid(row=8, column=1, sticky="we", padx=(5, 0), pady=5)
        
        # 规则展示表格
        ttk.Label(left_frame, text="当前秒回规则库 (双击规则行可编辑):").grid(row=9, column=0, sticky="w", pady=(5, 2))
        
        rule_cols = ("room", "sender", "mode", "keywords", "reply")
        self.rules_tree = ttk.Treeview(left_frame, columns=rule_cols, show="headings", height=5)
        self.rules_tree.heading("room", text="群聊名称")
        self.rules_tree.heading("sender", text="发言人")
        self.rules_tree.heading("mode", text="匹配模式")
        self.rules_tree.heading("keywords", text="关键词")
        self.rules_tree.heading("reply", text="回复内容")
        
        self.rules_tree.column("room", width=70, anchor="w")
        self.rules_tree.column("sender", width=60, anchor="w")
        self.rules_tree.column("mode", width=80, anchor="center")
        self.rules_tree.column("keywords", width=80, anchor="w")
        self.rules_tree.column("reply", width=120, anchor="w")
        
        self.rules_tree.grid(row=10, column=0, columnspan=2, sticky="we", pady=2)
        self.rules_tree.bind("<Double-1>", self.load_rule_to_form)
        
        # 安全模式选项
        chk_safe = ttk.Checkbutton(left_frame, text="安全模拟（加入100~300ms随机延迟以防封号）", variable=self.safe_mode)
        chk_safe.grid(row=11, column=0, columnspan=2, sticky="w", pady=5)
        
        # 启动/停止按钮
        self.btn_action = ttk.Button(left_frame, text=" 第二步：启动秒回监控 ", style="Success.TButton", state="disabled", command=self.toggle_monitoring)
        self.btn_action.grid(row=12, column=0, columnspan=2, sticky="we", pady=5)

        # 中间面板：快捷文本记录板
        middle_frame = ttk.LabelFrame(main_pane, text=" 快捷文本记录板 ", padding=10)
        main_pane.add(middle_frame, weight=1)
        middle_frame.columnconfigure(0, weight=1)
        middle_frame.columnconfigure(1, weight=1)
        middle_frame.rowconfigure(6, weight=1)
        
        # 1. 便签草稿箱
        ttk.Label(middle_frame, text="便签草稿箱 (临时文本编辑与交换):").grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        self.txt_scratchpad = scrolledtext.ScrolledText(middle_frame, height=6, font=("微软雅黑", 9), wrap="none")
        self.txt_scratchpad.grid(row=1, column=0, columnspan=2, sticky="we", pady=2)
        
        # 草稿箱操作按钮
        btn_copy_scratch = ttk.Button(middle_frame, text=" 复制全部草稿 ", command=self.copy_scratchpad)
        btn_copy_scratch.grid(row=2, column=0, sticky="we", padx=(0, 2), pady=2)
        
        btn_save_snippet = ttk.Button(middle_frame, text=" 存为快捷短语 ", command=self.save_scratchpad_to_snippet)
        btn_save_snippet.grid(row=2, column=1, sticky="we", padx=(2, 0), pady=2)
        
        btn_clear_scratch = ttk.Button(middle_frame, text=" 清空草稿 ", command=self.clear_scratchpad)
        btn_clear_scratch.grid(row=3, column=0, columnspan=2, sticky="we", pady=2)
        
        # 分割线
        ttk.Separator(middle_frame, orient="horizontal").grid(row=4, column=0, columnspan=2, sticky="we", pady=8)
        
        # 2. 快捷短语列表
        ttk.Label(middle_frame, text="快捷短语库 (双击可直接复制):").grid(row=5, column=0, columnspan=2, sticky="w", pady=2)
        
        self.snippets_tree = ttk.Treeview(middle_frame, columns=("content",), show="headings", height=8)
        self.snippets_tree.heading("content", text="短语内容")
        self.snippets_tree.column("content", width=150, anchor="w")
        self.snippets_tree.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=2)
        
        # 短语列表滚动条
        snippets_ysb = ttk.Scrollbar(middle_frame, orient="vertical", command=self.snippets_tree.yview)
        self.snippets_tree.configure(yscroll=snippets_ysb.set)
        snippets_ysb.grid(row=6, column=2, sticky="ns", pady=2)
        
        self.snippets_tree.bind("<Double-1>", self.on_snippet_double_click)
        
        # 快捷短语操作按钮
        btn_copy_snippet = ttk.Button(middle_frame, text=" 复制选中短语 ", command=self.copy_selected_snippet)
        btn_copy_snippet.grid(row=7, column=0, sticky="we", padx=(0, 2), pady=2)
        
        btn_del_snippet = ttk.Button(middle_frame, text=" 删除选中短语 ", command=self.delete_selected_snippet)
        btn_del_snippet.grid(row=7, column=1, sticky="we", padx=(2, 0), pady=2)
        
        btn_to_reply = ttk.Button(middle_frame, text=" 导入至规则回复内容 ", command=self.import_snippet_to_reply)
        btn_to_reply.grid(row=8, column=0, columnspan=2, sticky="we", pady=2)
        
        # 初始化刷新一次短语列表
        self.refresh_snippets_tree()

        # 右侧面板：实时群消息监听与日志 (用于抓取昵称)
        right_frame = ttk.LabelFrame(main_pane, text=" 锁定群聊消息面板（双击下方任意行可自动填入配置） ", padding=10)
        main_pane.add(right_frame, weight=2)
        
        # 表格展示群消息
        cols = ("time", "sender", "roomid", "content")
        self.tree = ttk.Treeview(right_frame, columns=cols, show="headings")
        self.tree.heading("time", text="时间")
        self.tree.heading("sender", text="发言人昵称")
        self.tree.heading("roomid", text="群聊名称")
        self.tree.heading("content", text="消息内容")
        
        self.tree.column("time", width=80, anchor="center")
        self.tree.column("sender", width=120, anchor="w")
        self.tree.column("roomid", width=120, anchor="w")
        self.tree.column("content", width=180, anchor="w")
        
        # 垂直滚动条
        ysb = ttk.Scrollbar(right_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=ysb.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")
        
        # 绑定双击事件
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # 底部：日志控制台
        log_frame = ttk.LabelFrame(self.root, text=" 系统日志控制台 ", padding=10)
        log_frame.pack(fill="x", padx=15, pady=10)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
        self.log_area.pack(fill="x", expand=True)
        
        self.log("系统就绪，请先点击【第一步：连接并绑定当前微信】按钮。")
        self.refresh_rules_tree() # 启动时刷新展示加载好的规则库

    def log(self, text):
        t_str = time.strftime('%H:%M:%S')
        self.log_area.insert("end", f"[{t_str}] {text}\n")
        self.log_area.see("end")

    def on_match_mode_change(self, event=None):
        mode = self.cmb_mode.get()
        if mode == "无条件秒回 (任意内容)":
            self.ent_keywords.delete(0, "end")
            self.ent_keywords.config(state="disabled")
        else:
            self.ent_keywords.config(state="normal")

    def refresh_rules_tree(self):
        # 清空表格
        for item in self.rules_tree.get_children():
            self.rules_tree.delete(item)
        # 重新插入所有规则
        with self.rules_lock:
            rules_copy = list(self.rules)
        for r in rules_copy:
            kws = ", ".join(r['keywords']) if r['keywords'] else "-"
            # 替换换行符，防止 Treeview 表格中多行文本重叠显示
            reply_preview = r['reply'].replace('\n', ' ↵ ')
            self.rules_tree.insert("", "end", values=(r['room'], r['sender'], r['mode'], kws, reply_preview))

    def add_or_update_rule(self):
        room = self.ent_room.get().strip()
        sender = self.ent_sender.get().strip()
        reply = self.txt_reply.get("1.0", "end-1c").strip()
        mode = self.cmb_mode.get()
        keywords_raw = self.ent_keywords.get().strip()
        
        if not room or not sender or not reply:
            messagebox.showwarning("参数缺失", "请先填入完整的群聊名称、发言者昵称和回复内容！")
            return
            
        if mode != "无条件秒回 (任意内容)" and not keywords_raw:
            messagebox.showwarning("参数缺失", "在此匹配模式下，请先输入触发关键词！")
            return
            
        keywords = [k.strip() for k in keywords_raw.replace("，", ",").split(",") if k.strip()]
        
        rule_data = {
            "room": room,
            "sender": sender,
            "mode": mode,
            "keywords": keywords,
            "reply": reply
        }
        
        with self.rules_lock:
            # 检查是否已存在该群聊+发言人的规则 (如果存在则更新，否则新增)
            existing_idx = -1
            for idx, r in enumerate(self.rules):
                if r['room'] == room and r['sender'] == sender:
                    existing_idx = idx
                    break
                    
            if existing_idx >= 0:
                self.rules[existing_idx] = rule_data
                self.log(f"已更新规则 -> 群聊: {room} | 发言人: {sender}")
            else:
                self.rules.append(rule_data)
                self.log(f"已添加规则 -> 群聊: {room} | 发言人: {sender}")
            
        self.save_rules()
        self.refresh_rules_tree()
        
        # 如果正在监控，动态更新监控的房间
        if self.is_monitoring:
            self.update_monitoring_rooms_dynamically()
        
        # 清空表单，方便输入下一条规则
        self.ent_room.delete(0, "end")
        self.ent_sender.delete(0, "end")
        self.ent_keywords.delete(0, "end")
        self.txt_reply.delete("1.0", "end")
        self.cmb_mode.current(0)
        self.on_match_mode_change()

    def delete_rule(self):
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning("未选中", "请在规则列表中选中一行进行删除！")
            return
            
        item = self.rules_tree.item(selected[0])
        values = item['values']
        room = values[0]
        sender = values[1]
        
        # 从 rules 中删除
        with self.rules_lock:
            self.rules = [r for r in self.rules if not (r['room'] == room and r['sender'] == sender)]
        self.log(f"已删除规则 -> 群聊: {room} | 发言人: {sender}")
        self.save_rules()
        self.refresh_rules_tree()

        # 如果正在监控，动态更新监控的房间
        if self.is_monitoring:
            self.update_monitoring_rooms_dynamically()

    def update_monitoring_rooms_dynamically(self):
        if not self.wx:
            return
            
        with self.rules_lock:
            new_target_rooms = list(set(r['room'] for r in self.rules))
        
        # 找出新增加的群聊和已被移除的群聊
        added_rooms = [r for r in new_target_rooms if r not in self.target_rooms]
        removed_rooms = [r for r in self.target_rooms if r not in new_target_rooms]
        
        for r in added_rooms:
            self.log(f"检测到新群聊【{r}】，正在将其加入监控列表并初始化...")
            sender_init, content_init = self.wx.GetLastMessage(r)
            if sender_init is None and content_init is None:
                self.last_msg_sigs[r] = "OFFLINE_PLACEHOLDER"
            else:
                self.last_msg_sigs[r] = f"{sender_init or ''}:{content_init or ''}"
            self.log(f"新群聊【{r}】初始化完成。")
            
        for r in removed_rooms:
            self.log(f"已移出监控群聊：【{r}】")
            if r in self.last_msg_sigs:
                del self.last_msg_sigs[r]
                
        self.target_rooms = new_target_rooms
        self.log(f"监控列表已动态更新，当前共监控 {len(self.target_rooms)} 个群聊。")

    def load_rule_to_form(self, event=None):
        selected = self.rules_tree.selection()
        if not selected:
            return
            
        values = self.rules_tree.item(selected[0], "values")
        if values:
            room = values[0]
            sender = values[1]
            mode = values[2]
            kws = values[3]
            
            # 从 rules 列表中匹配获取最原始的带换行符的回复内容
            original_reply = ""
            with self.rules_lock:
                for r in self.rules:
                    if r['room'] == room and r['sender'] == sender:
                        original_reply = r['reply']
                        break
            if not original_reply:
                # 兜底：如果没找到，使用表格里的值，但需要把 ↵ 换回换行符
                original_reply = values[4].replace(' ↵ ', '\n')
            
            self.ent_room.delete(0, "end")
            self.ent_room.insert(0, room)
            
            self.ent_sender.delete(0, "end")
            self.ent_sender.insert(0, sender)
            
            self.cmb_mode.set(mode)
            self.on_match_mode_change()
            
            self.ent_keywords.delete(0, "end")
            if kws != "-":
                self.ent_keywords.insert(0, kws)
                
            self.txt_reply.delete("1.0", "end")
            self.txt_reply.insert("1.0", original_reply)
            
            self.log(f"已加载规则至编辑器 -> 群聊: {room} | 发言人: {sender}")

    def connect_wechat(self):
        self.log("正在尝试绑定微信桌面客户端...")
        try:
            # 初始化自定义的 WeChatNT 实例
            self.wx = WeChatNT()
            self.is_connected = True
            
            self.lbl_status.config(text="连接成功 (已绑定微信窗口)", foreground=self.success_color)
            self.btn_connect.config(state="disabled")
            self.btn_action.config(state="normal")
            self.log("微信绑定成功！请在左侧配置目标群聊并点击【启动秒回监控】。")
            
            # 开启后台监听线程
            self.is_listening = True
            self.listener_thread = threading.Thread(target=self.background_listener, daemon=True)
            self.listener_thread.start()
            # 开启串行发送 Worker 线程（唯一操作剪贴板/键盘的线程，消除并发冲突）
            self.sender_thread = threading.Thread(target=self.sender_worker, daemon=True)
            self.sender_thread.start()
            
        except Exception as e:
            self.is_connected = False
            self.log(f"绑定微信失败！错误: {e}")
            messagebox.showerror("连接错误", f"无法绑定微信客户端！\n\n请确保PC微信已启动、已登录且未完全关闭。\n\n错误信息: {e}")

    def background_listener(self):
        """后台线程：定期获取目标群聊的最新消息并推送到队列"""
        self.log("后台监听线程已启动...")
        
        while self.is_listening:
            if not self.is_connected:
                time.sleep(1)
                continue
            
            with self.rules_lock:
                current_rules = list(self.rules)
                
            if not self.is_monitoring or not current_rules:
                time.sleep(0.5)
                continue
                
            # 自动维护与微信的连接稳定性，断线后自动重连
            try:
                self.wx.check_connection()
            except Exception as e:
                self.gui_queue.put(("", "系统提示", f"微信连接已断开，正在尝试重连... 错误: {e}", 'friend'))
                time.sleep(2)
                continue
                
            current_target_rooms = list(self.target_rooms)
            for room in current_target_rooms:
                if not self.is_monitoring:
                    break
                    
                try:
                    # 获取该群最后一条消息的发送者和内容
                    sender, content = self.wx.GetLastMessage(room)
                    if sender is not None or content is not None:
                        sender = sender or ""
                        content = content or ""
                        msg_sig = f"{sender}:{content}"
                        
                        # 过滤自己发送的消息、发送中、草稿等中间状态，防止自循环或双重回复
                        is_valid_msg = (
                            sender != "" and 
                            sender not in ["我", "me", "Me"] and 
                            not sender.startswith("[草稿]") and 
                            "正在发送" not in content and 
                            "发送中" not in content
                        )
                        
                        if not is_valid_msg:
                            self.last_msg_sigs[room] = msg_sig
                            continue
                            
                        # 获取旧的消息签名
                        old_sig = self.last_msg_sigs.get(room, "")
                        
                        # 如果是离线状态恢复（收到第一条消息跳至顶部），或者签名与上次不一致，才触发秒回
                        if old_sig == "OFFLINE_PLACEHOLDER" or msg_sig != old_sig:
                            self.last_msg_sigs[room] = msg_sig
                            # 推送到主线程队列（仅供展示使用）
                            self.gui_queue.put((room, sender, content, 'friend'))
                            
                            # 遍历规则库寻找匹配规则
                            for rule in current_rules:
                                if rule['room'] == room:
                                    # 1. 校验发言人是否符合规则
                                    if rule['sender'] == '*' or rule['sender'] == sender:
                                        # 2. 校验内容匹配模式
                                        content_matched = False
                                        mode = rule['mode']
                                        keywords = rule['keywords']
                                        
                                        if mode == "无条件秒回 (任意内容)":
                                            content_matched = True
                                        elif mode == "包含任意关键词":
                                            if any(kw in content for kw in keywords):
                                                content_matched = True
                                        elif mode == "精确匹配关键词":
                                            if any(kw == content for kw in keywords):
                                                content_matched = True
                                                
                                        if content_matched:
                                            # 将回复任务投入串行发送队列，由 sender_worker 串行处理
                                            self.reply_queue.put((room, content, rule['reply']))
                except Exception as e:
                    print(f"[监控异常] 处理群聊【{room}】时发生错误: {e}")
                
            time.sleep(0.01) # 扫描完所有群后等待 10ms

    def process_queue(self):
        # 保证 GUI 线程安全地读取后台传来的消息
        while not self.gui_queue.empty():
            chat, sender, content, m_type = self.gui_queue.get_nowait()
            self.handle_incoming_message(chat, sender, content, m_type)
        self.root.after(50, self.process_queue)

    def handle_incoming_message(self, chat, sender, content, m_type):
        t_str = time.strftime('%H:%M:%S')
        
        if m_type == 'friend':
            # 替换换行符，防止多行文本在表格行中重叠
            content_preview = content.replace('\n', ' ↵ ')
            # 仅在表格中展示日志
            self.tree.insert("", 0, values=(t_str, sender, chat, content_preview))
            if len(self.tree.get_children()) > 100:
                self.tree.delete(self.tree.get_children()[-1])

    def sender_worker(self):
        """串行发送 Worker：唯一操作剪贴板和键盘的线程，彻底消除并发冲突"""
        _last_sent_chat = None  # 本地缓存当前已在哪个群窗口，避免 UIA 标题栏查询
        while self.is_listening:
            try:
                # 阻塞等待发送任务，超时 0.5s 循环检查 is_listening 状态
                try:
                    item = self.reply_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                # None 是退出哨兵信号（on_closing 发送）
                if item is None:
                    self.reply_queue.task_done()
                    break

                chat, incoming_content, reply_text = item

                if not self.wx or not self.is_monitoring:
                    self.reply_queue.task_done()
                    continue

                start_time = time.time()
                try:
                    # 只有当目标群和当前窗口不同时才切换，减少不必要的窗口切换
                    # 采用标题栏 live 实时校验代替单纯的本地变量缓存，防止用户手动切换窗口导致的状态不同步
                    current_active = self.wx.GetCurrentActiveChatName() or ""
                    
                    def clean_str(s):
                        return re.sub(r'[\s\(\)（）\d]+', '', s).lower()
                        
                    if clean_str(chat) not in clean_str(current_active):
                        self.wx.ChatWith(chat)

                    if self.safe_mode.get():
                        time.sleep(0.1 + random.random() * 0.2)

                    self.wx.SendMsg(msg=reply_text)

                    elapsed = (time.time() - start_time) * 1000
                    # 通过线程安全的 after 回调更新 GUI 日志
                    _chat, _content, _elapsed = chat, incoming_content, elapsed
                    self.root.after(0, lambda c=_chat, m=_content, e=_elapsed:
                        self.log(f"【成功秒回】群聊: '{c}' | 发言: '{m}' | 关联总耗时: {e:.2f}毫秒"))
                except Exception as e:
                    _last_sent_chat = None  # 发送失败时重置缓存，下次强制重新切换
                    _e = e
                    self.root.after(0, lambda err=_e: self.log(f"秒回发送失败，错误: {err}"))
                finally:
                    self.reply_queue.task_done()
            except Exception:
                pass

    def on_tree_double_click(self, event):
        # 双击表格中的行，自动载入表单
        selected_item = self.tree.selection()
        if not selected_item:
            return
        
        values = self.tree.item(selected_item, "values")
        if values:
            sender_name = values[1]
            room_name = values[2]
            
            self.ent_room.delete(0, "end")
            self.ent_room.insert(0, room_name)
            
            self.ent_sender.delete(0, "end")
            self.ent_sender.insert(0, sender_name)
            
            self.log(f"已将该行信息载入配置区 -> 群聊: {room_name} | 发言人: {sender_name}")

    def toggle_monitoring(self):
        if not self.is_monitoring:
            with self.rules_lock:
                rules_empty = len(self.rules) == 0
            if rules_empty:
                messagebox.showwarning("规则库为空", "请先在规则库中添加至少一条秒回规则！")
                return
                
            # 提取所有唯一的监控群聊
            with self.rules_lock:
                self.target_rooms = list(set(r['room'] for r in self.rules))
            self.last_msg_sigs = {}
            self.current_active_room = None
            
            # 初始化所有目标群聊的消息签名（如不可见则标志为离线，待其发新消息跳转到顶端时秒回）
            for room in self.target_rooms:
                try:
                    sender_init, content_init = self.wx.GetLastMessage(room)
                    if sender_init is not None or content_init is not None:
                        self.last_msg_sigs[room] = f"{sender_init or ''}:{content_init or ''}"
                    else:
                        self.last_msg_sigs[room] = "OFFLINE_PLACEHOLDER"
                except Exception:
                    self.last_msg_sigs[room] = "OFFLINE_PLACEHOLDER"
            
            self.log(f"已锁定监控群聊列表，共 {len(self.target_rooms)} 个。开始监控消息...")
            self.is_monitoring = True
            self.btn_action.config(text=" 停止秒回监控 ", style="Danger.TButton")
            
            with self.rules_lock:
                rules_count = len(self.rules)
            self.log(f"▶ 秒回监控已开启！当前共运行 {rules_count} 条秒回规则。")
        else:
            self.is_monitoring = False
            self.btn_action.config(text=" 第二步：启动秒回监控 ", style="Success.TButton")
            self.log("⏸ 秒回监控已暂停。")

    def load_snippets(self):
        import json
        self.snippets = []
        if os.path.exists(self.snippets_file):
            try:
                with open(self.snippets_file, "r", encoding="utf-8") as f:
                    self.snippets = json.load(f)
            except Exception as e:
                print(f"加载快捷短语失败: {e}")
        else:
            # 默认快捷短语
            self.snippets = [
                "你好，请问有什么可以帮您？",
                "好的，稍等一下，我马上为您处理。",
                "请把具体错误截图或要求发给我看下。",
                "测试自动秒回中，请发送消息测试。"
            ]
            self.save_snippets()

    def save_snippets(self):
        import json
        try:
            with open(self.snippets_file, "w", encoding="utf-8") as f:
                json.dump(self.snippets, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存快捷短语失败: {e}")

    def load_rules(self):
        import json
        self.rules = []
        rules_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wechat_rules.json")
        if os.path.exists(rules_file):
            try:
                with open(rules_file, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)
            except Exception as e:
                print(f"加载规则库失败: {e}")

    def save_rules(self):
        import json
        rules_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wechat_rules.json")
        try:
            with open(rules_file, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存规则库失败: {e}")

    def copy_scratchpad(self):
        text = self.txt_scratchpad.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("内容为空", "便签草稿箱中没有内容！")
            return
        set_clipboard_text(text)
        self.log("【已复制】已将便签草稿内容复制到系统剪贴板。")

    def save_scratchpad_to_snippet(self):
        text = self.txt_scratchpad.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("内容为空", "不能将空文本存为快捷短语！")
            return
        if text in self.snippets:
            messagebox.showinfo("提示", "该短语已存在于短语库中。")
            return
        self.snippets.append(text)
        self.save_snippets()
        self.refresh_snippets_tree()
        self.log(f"【添加短语】成功保存短语：'{text[:15]}...'")

    def clear_scratchpad(self):
        self.txt_scratchpad.delete("1.0", "end")
        self.log("便签草稿箱已清空。")

    def refresh_snippets_tree(self):
        # 清空树形控件
        for item in self.snippets_tree.get_children():
            self.snippets_tree.delete(item)
        # 重新插入，values中存储替换了换行符的单行预览，iid存储其在self.snippets中的索引位置
        for idx, s in enumerate(self.snippets):
            preview = s.replace('\n', ' ↵ ')
            self.snippets_tree.insert("", "end", iid=str(idx), values=(preview,))

    def on_snippet_double_click(self, event):
        selected = self.snippets_tree.selection()
        if not selected:
            return
        try:
            idx = int(selected[0])
            snippet_text = self.snippets[idx]
            set_clipboard_text(snippet_text)
            self.log(f"【双击复制】已将短语复制到剪贴板: '{snippet_text[:15]}...'")
        except Exception as e:
            pass

    def copy_selected_snippet(self):
        selected = self.snippets_tree.selection()
        if not selected:
            messagebox.showwarning("未选中", "请先在短语库中选中一行！")
            return
        try:
            idx = int(selected[0])
            snippet_text = self.snippets[idx]
            set_clipboard_text(snippet_text)
            self.log(f"【复制短语】已将短语复制到剪贴板: '{snippet_text[:15]}...'")
        except Exception as e:
            messagebox.showerror("错误", f"无法复制短语: {e}")

    def delete_selected_snippet(self):
        selected = self.snippets_tree.selection()
        if not selected:
            messagebox.showwarning("未选中", "请先在短语库中选中要删除的行！")
            return
        try:
            idx = int(selected[0])
            snippet_text = self.snippets[idx]
            self.snippets.remove(snippet_text)
            self.save_snippets()
            self.refresh_snippets_tree()
            self.log(f"【删除短语】已从短语库删除：'{snippet_text[:15]}...'")
        except Exception as e:
            messagebox.showerror("错误", f"无法删除短语: {e}")

    def import_snippet_to_reply(self):
        selected = self.snippets_tree.selection()
        if not selected:
            messagebox.showwarning("未选中", "请先在短语库中选中一行短语！")
            return
        try:
            idx = int(selected[0])
            snippet_text = self.snippets[idx]
            self.txt_reply.delete("1.0", "end")
            self.txt_reply.insert("1.0", snippet_text)
            self.log(f"【导入成功】已将短语导入到左侧“专属秒回回复内容”编辑器。")
        except Exception as e:
            messagebox.showerror("错误", f"无法导入短语: {e}")

    def on_closing(self):
        self.is_listening = False
        self.is_monitoring = False
        # 发送 None 哨兵让 sender_worker 快速退出阻塞等待
        self.reply_queue.put(None)
        self.root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = WeChatBotWxAutoGUI(root)
    root.mainloop()
