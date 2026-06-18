import os
import sys
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

def set_clipboard_text(text):
    # 使用 Win32 原生 API 极速写入剪贴板，避免 pyperclip 的库环境检查开销
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()

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
            
        # 绑定并缓存会话列表 ListControl，加速非当前窗口的 UIA 检索，防止超时
        self.session_list = self.control.ListControl(AutomationId='session_list')
        if not self.session_list.Exists(1):
            self.session_list = self.control
            
        # 绑定并缓存聊天窗口标题栏，加速当前窗口检测，消除检索延迟
        self.chat_title_bar = self.control.GroupControl(ClassName='mmui::ChatTitleBarMasterView')
        if not self.chat_title_bar.Exists(1):
            self.chat_title_bar = None
            
        # 缓存 Control 实例以避免频繁遍历 UI 树造成的性能开销
        self.session_controls = {}
        self.input_field = None

    def get_wechat_hwnd(self):
        wechat_hwnd = None
        def callback(hwnd, extra):
            nonlocal wechat_hwnd
            classname = win32gui.GetClassName(hwnd)
            if classname == 'Qt51514QWindowIcon':
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = psutil.Process(pid)
                    if proc.name().lower() == 'weixin.exe':
                        title = win32gui.GetWindowText(hwnd)
                        if '微信' in title or title == '微信':
                            wechat_hwnd = hwnd
                except Exception:
                    pass
        win32gui.EnumWindows(callback, None)
        return wechat_hwnd

    def ChatWith(self, who):
        # 1. 尝试直接点击左侧会话列表中的项目
        session = self.session_list.ListItemControl(AutomationId=f'session_item_{who}')
        if session.Exists(0.1):
            session.Click()
            # 动态等待输入框加载完成
            input_field = self.control.EditControl(AutomationId='chat_input_field')
            start = time.time()
            while time.time() - start < 0.2:
                if input_field.Exists(0.01):
                    break
                time.sleep(0.01)
            return True
            
        # 2. 如果左侧没有，使用搜索框搜索
        search_box = self.control.EditControl(ClassName='mmui::XValidatorTextEdit', Name='搜索')
        if search_box.Exists(0.2):
            search_box.Click()
            search_box.SendKeys('{Ctrl}a{Delete}')
            
            set_clipboard_text(who)
            search_box.SendKeys('{Ctrl}v')
            time.sleep(0.3) # 缩短等待搜索结果列表渲染时间
            
            # 按回车键直接进入第一个搜索结果
            search_box.SendKeys('{Enter}')
            # 动态等待输入框加载
            input_field = self.control.EditControl(AutomationId='chat_input_field')
            start = time.time()
            while time.time() - start < 0.3:
                if input_field.Exists(0.01):
                    break
                time.sleep(0.01)
            return True
        return False

    def SendMsg(self, msg):
        # 每次都执行 100ms 快速定位，避免使用长期失效的 COM 缓存，防止 Windows UIA 超时导致锁死 1~2 秒
        input_field = self.control.EditControl(AutomationId='chat_input_field')
        if not input_field.Exists(0.1):
            raise Exception("未找到聊天输入框")
            
        # 使用 SetFocus() 代替 Click()，避免移动物理鼠标或模拟鼠标点击的延迟
        input_field.SetFocus()
        
        # 使用原生 Win32 API 极速写入剪贴板
        set_clipboard_text(msg)
        
        # 使用 Win32 API 原生 keybd_event 零延迟模拟键盘操作，彻底消除 uiautomation SendKeys 内置的 120ms+ 延时
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
        
        # 根据文本长度动态计算极短的粘贴等待时间，防止长文本在微信里未完成粘贴便敲下回车发送
        paste_delay = max(0.005, min(0.05, len(msg) * 0.0001))
        time.sleep(paste_delay)
        
        # 模拟 Enter
        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

    def GetCurrentActiveChatName(self):
        # 优先使用缓存的标题栏进行极速检测，如果失效或未加载则执行延迟绑定
        if not self.chat_title_bar:
            self.chat_title_bar = self.control.GroupControl(ClassName='mmui::ChatTitleBarMasterView')
            if not self.chat_title_bar.Exists(0.1):
                self.chat_title_bar = None
                return None
        
        label = self.chat_title_bar.TextControl(ClassName='mmui::XTextView')
        if label.Exists(0.05):
            return label.Name
        return None


    def GetLastMessage(self, who):
        # 每次都执行 50ms 极短超时搜索，基于 session_list 限定查找以防超时
        session = self.session_list.ListItemControl(AutomationId=f'session_item_{who}')
        if not session.Exists(0.05):
            return None, None
            
        try:
            name = session.Name
        except Exception:
            return None, None
            
        lines = [l.strip() for l in name.split('\n') if l.strip()]
        if not lines or len(lines) < 2:
            return None, None
            
        # 微信会话单元格中，最后一条消息的内容总是位于时间线（最后一行）的上一行
        msg_line = lines[-2]
        
        if ':' in msg_line:
            parts = msg_line.split(':', 1)
            sender = parts[0].strip()
            content = parts[1].strip() if len(parts) > 1 else ""
            return sender, content
        else:
            return "", msg_line

class WeChatBotWxAutoGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("微信消息极速秒回助手 - UIA驱动版 (支持最新微信)")
        self.root.geometry("900x650")
        self.root.minsize(800, 550)
        
        # 内部状态变量
        self.wx = None
        self.is_connected = False
        self.is_monitoring = False
        
        self.rules = []           # 规则库配置列表，格式如：{"room":x, "sender":y, "mode":z, "keywords":[], "reply":w}
        self.target_rooms = []    # 提取的唯一群聊列表
        self.safe_mode = tk.BooleanVar(value=True)
        self.current_active_room = None
        
        # 消息同步队列与后台线程
        self.gui_queue = queue.Queue()
        self.listener_thread = None
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
        for r in self.rules:
            kws = ", ".join(r['keywords']) if r['keywords'] else "-"
            self.rules_tree.insert("", "end", values=(r['room'], r['sender'], r['mode'], kws, r['reply']))

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
        
        # 检查是否已存在该群聊+发言人的规则 (如果存在则更新，否则新增)
        existing_idx = -1
        for idx, r in enumerate(self.rules):
            if r['room'] == room and r['sender'] == sender:
                existing_idx = idx
                break
                
        rule_data = {
            "room": room,
            "sender": sender,
            "mode": mode,
            "keywords": keywords,
            "reply": reply
        }
        
        if existing_idx >= 0:
            self.rules[existing_idx] = rule_data
            self.log(f"已更新规则 -> 群聊: {room} | 发言人: {sender}")
        else:
            self.rules.append(rule_data)
            self.log(f"已添加规则 -> 群聊: {room} | 发言人: {sender}")
            
        self.refresh_rules_tree()
        
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
        self.rules = [r for r in self.rules if not (r['room'] == room and r['sender'] == sender)]
        self.log(f"已删除规则 -> 群聊: {room} | 发言人: {sender}")
        self.refresh_rules_tree()

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
            reply = values[4]
            
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
            self.txt_reply.insert("1.0", reply)
            
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
            
            # 开启后台循环接收线程
            self.is_listening = True
            self.listener_thread = threading.Thread(target=self.background_listener, daemon=True)
            self.listener_thread.start()
            
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
            
            if not self.is_monitoring or not self.rules:
                time.sleep(0.5)
                continue
                
            for room in self.target_rooms:
                if not self.is_monitoring:
                    break
                    
                try:
                    # 获取该群最后一条消息的发送者和内容
                    sender, content = self.wx.GetLastMessage(room)
                    if sender and content:
                        msg_sig = f"{sender}:{content}"
                        old_sig = self.last_msg_sigs.get(room, "")
                        if msg_sig != old_sig:
                            self.last_msg_sigs[room] = msg_sig
                            # 推送到主线程队列（仅供展示使用）
                            self.gui_queue.put((room, sender, content, 'friend'))
                            
                            # 遍历规则库寻找匹配规则
                            for rule in self.rules:
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
                                            # 极致优化：直接在此处（后台线程）同步触发发送专属回复内容
                                            threading.Thread(
                                                target=self.do_fast_reply, 
                                                args=(room, content, rule['reply']), 
                                                daemon=True
                                            ).start()
                except Exception as e:
                    pass
                
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
            # 仅在表格中展示日志
            self.tree.insert("", 0, values=(t_str, sender, chat, content))
            if len(self.tree.get_children()) > 100:
                self.tree.delete(self.tree.get_children()[-1])

    def do_fast_reply(self, chat, incoming_content, reply_text):
        try:
            start_time = time.time()
            
            # 动态检测当前窗口，若不同则快速切换
            current_active = self.wx.GetCurrentActiveChatName()
            if current_active != chat:
                self.wx.ChatWith(chat)
                
            if self.safe_mode.get():
                time.sleep(0.1 + random.random() * 0.2)
                
            # 发送该规则对应的专属回复
            self.wx.SendMsg(msg=reply_text)
            
            end_time = time.time()
            elapsed = (end_time - start_time) * 1000
            self.root.after(0, lambda: self.log(f"【成功秒回】群聊: '{chat}' | 发言: '{incoming_content}' | 关联总耗时: {elapsed:.2f}毫秒"))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"秒回发送失败，错误: {e}"))

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
            if not self.rules:
                messagebox.showwarning("规则库为空", "请先在规则库中添加至少一条秒回规则！")
                return
                
            # 提取所有唯一的监控群聊
            self.target_rooms = list(set(r['room'] for r in self.rules))
            self.last_msg_sigs = {}
            self.current_active_room = None
            
            first_room = self.target_rooms[0]
            try:
                self.log(f"正在初始化窗口，激活首个群聊【{first_room}】...")
                self.wx.ChatWith(first_room)
                self.current_active_room = first_room
                
                # 初始化所有目标群的消息签名
                for r in self.target_rooms:
                    sender_init, content_init = self.wx.GetLastMessage(r)
                    if sender_init and content_init:
                        self.last_msg_sigs[r] = f"{sender_init}:{content_init}"
                    else:
                        self.last_msg_sigs[r] = ""
                        
                self.log(f"已锁定并激活所有群聊，共 {len(self.target_rooms)} 个。开始监控消息...")
            except Exception as e:
                self.log(f"激活群聊失败: {e}")
                messagebox.showerror("打开错误", f"无法切换到该群聊！\n请确保微信中该群聊在聊天列表中可见，或者名称完全正确。\n\n错误: {e}")
                return
                
            self.is_monitoring = True
            self.btn_action.config(text=" 停止秒回监控 ", style="Danger.TButton")
            
            # 禁用所有编辑器控件与表单
            self.ent_room.config(state="disabled")
            self.ent_sender.config(state="disabled")
            self.cmb_mode.config(state="disabled")
            self.ent_keywords.config(state="disabled")
            self.txt_reply.config(state="disabled")
            self.btn_add_rule.config(state="disabled")
            self.btn_del_rule.config(state="disabled")
            
            self.log(f"▶ 秒回监控已开启！当前共运行 {len(self.rules)} 条秒回规则。")
        else:
            self.is_monitoring = False
            self.btn_action.config(text=" 第二步：启动秒回监控 ", style="Success.TButton")
            
            # 恢复编辑器控件与表单
            self.ent_room.config(state="normal")
            self.ent_sender.config(state="normal")
            self.cmb_mode.config(state="normal")
            if self.cmb_mode.get() != "无条件秒回 (任意内容)":
                self.ent_keywords.config(state="normal")
            self.txt_reply.config(state="normal")
            self.btn_add_rule.config(state="normal")
            self.btn_del_rule.config(state="normal")
            
            self.log("⏸ 秒回监控已暂停。")

    def on_closing(self):
        self.is_listening = False
        self.root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = WeChatBotWxAutoGUI(root)
    root.mainloop()
