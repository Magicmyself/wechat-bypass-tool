import os
import sys
import time
import random
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from wcferry import Wcf, WxMsg

# 线程安全的队列，用于在后台线程接收消息并同步到GUI
gui_queue = queue.Queue()

class WeChatBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("微信消息极速秒回助手 - WCF")
        self.root.geometry("900x650")
        self.root.minsize(800, 550)
        
        # 内部状态变量
        self.wcf = None
        self.is_connected = False
        self.is_monitoring = False
        self.target_room = ""
        self.target_sender = ""
        self.reply_text = ""
        self.safe_mode = tk.BooleanVar(value=True)
        
        # 自定义界面主题颜色 (深灰/科技蓝风格)
        self.setup_styles()
        
        # 布局构建
        self.build_ui()
        
        # 启动队列监听器
        self.root.after(100, self.process_queue)
        
        # 窗口关闭协议
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        # 配色定义
        self.bg_color = "#f5f6fa"
        self.primary_color = "#3498db"
        self.success_color = "#2ecc71"
        self.danger_color = "#e74c3c"
        
        style.configure(".", background=self.bg_color, font=("微软雅黑", 10))
        style.configure("TLabel", background=self.bg_color)
        style.configure("Header.TLabel", font=("微软雅黑", 12, "bold"))
        style.configure("Status.TLabel", font=("微软雅黑", 10, "italic"))
        
        # 按钮风格
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
        
        self.btn_connect = ttk.Button(top_frame, text=" 第一步：连接并初始化微信 ", style="Primary.TButton", command=self.connect_wechat)
        self.btn_connect.pack(side="left", padx=5)
        
        self.lbl_status = ttk.Label(top_frame, text="未连接 (请确保PC端微信已登录)", style="Status.TLabel", foreground="gray")
        self.lbl_status.pack(side="left", padx=15)

        # 中部：主要控制和数据区域 (两栏布局)
        main_pane = ttk.PanedWindow(self.root, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=15, pady=5)
        
        # 左侧面板：设置参数与自动回复
        left_frame = ttk.LabelFrame(main_pane, text=" 秒回配置中心 ", padding=10)
        main_pane.add(left_frame, weight=1)
        
        # 目标群ID
        ttk.Label(left_frame, text="目标群聊 ID (roomid):").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_room = ttk.Entry(left_frame, width=30)
        self.ent_room.grid(row=1, column=0, columnspan=2, sticky="we", pady=5)
        
        # 目标人ID
        ttk.Label(left_frame, text="目标发言人 ID (sender):").grid(row=2, column=0, sticky="w", pady=5)
        self.ent_sender = ttk.Entry(left_frame, width=30)
        self.ent_sender.grid(row=3, column=0, columnspan=2, sticky="we", pady=5)
        
        # 回复内容
        ttk.Label(left_frame, text="秒回固定内容:").grid(row=4, column=0, sticky="w", pady=5)
        self.txt_reply = scrolledtext.ScrolledText(left_frame, height=4, width=30, font=("微软雅黑", 9))
        self.txt_reply.grid(row=5, column=0, columnspan=2, sticky="we", pady=5)
        self.txt_reply.insert("1.0", "收到！这是极速秒回测试。")
        
        # 安全模式选项
        chk_safe = ttk.Checkbutton(left_frame, text="安全模拟（加入100~300ms随机延迟以防封号）", variable=self.safe_mode)
        chk_safe.grid(row=6, column=0, columnspan=2, sticky="w", pady=10)
        
        # 启动/停止按钮
        self.btn_action = ttk.Button(left_frame, text=" 第二步：启动秒回监控 ", style="Success.TButton", state="disabled", command=self.toggle_monitoring)
        self.btn_action.grid(row=7, column=0, columnspan=2, sticky="we", pady=10)

        # 右侧面板：实时群消息监听与日志 (用于抓取ID)
        right_frame = ttk.LabelFrame(main_pane, text=" 实时消息监听板（双击下方任意行可自动填入配置） ", padding=10)
        main_pane.add(right_frame, weight=2)
        
        # 表格展示群消息
        cols = ("time", "sender", "roomid", "content")
        self.tree = ttk.Treeview(right_frame, columns=cols, show="headings")
        self.tree.heading("time", text="时间")
        self.tree.heading("sender", text="发言人ID")
        self.tree.heading("roomid", text="群聊ID")
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
        
        self.log("系统就绪，请先点击【第一步：连接并初始化微信】按钮。")

    def log(self, text):
        t_str = time.strftime('%H:%M:%S')
        self.log_area.insert("end", f"[{t_str}] {text}\n")
        self.log_area.see("end")

    def connect_wechat(self):
        self.log("正在尝试连接微信客户端...")
        try:
            self.wcf = Wcf()
            self.wcf.connect()
            self.is_connected = True
            
            self.lbl_status.config(text="连接成功 (已注入微信进程)", foreground=self.success_color)
            self.btn_connect.config(state="disabled")
            self.btn_action.config(state="normal")
            self.log("微信连接成功！已激活底层消息接收模块。")
            
            # 后台开启接收消息
            self.wcf.enable_receiving_msg(self.message_callback)
            
        except Exception as e:
            self.is_connected = False
            self.log(f"连接失败！请确保PC版微信已运行并登录。错误: {e}")
            messagebox.showerror("连接错误", f"无法注入微信客户端，请检查微信是否开启！\n\n错误信息: {e}")

    def message_callback(self, msg: WxMsg):
        # 微信消息线程回调，将消息传递进队列，由主GUI线程更新UI
        gui_queue.put(msg)

    def process_queue(self):
        # 主线程定期检查队列，保证UI操作的线程安全
        while not gui_queue.empty():
            msg = gui_queue.get_nowait()
            self.handle_incoming_message(msg)
        self.root.after(50, self.process_queue)

    def handle_incoming_message(self, msg: WxMsg):
        # 1. 无论是任何群消息，都展示在右侧的 Treeview 监听板上
        if msg.from_group():
            t_str = time.strftime('%H:%M:%S')
            # 插入表格顶部
            row_id = self.tree.insert("", 0, values=(t_str, msg.sender, msg.roomid, msg.content))
            # 限制表格最大行数防止内存无限增长 (只保留最新100条)
            if len(self.tree.get_children()) > 100:
                last_item = self.tree.get_children()[-1]
                self.tree.delete(last_item)
                
            # 2. 如果开启了自动秒回监控，且当前消息完全匹配设置的目标
            if self.is_monitoring:
                if msg.roomid == self.target_room and msg.sender == self.target_sender:
                    if msg.type == 1: # 文本消息
                        threading.Thread(target=self.do_fast_reply, args=(msg.content,), daemon=True).start()

    def do_fast_reply(self, incoming_content):
        # 执行极速秒回 (在独立线程中执行，防止阻碍GUI线程)
        try:
            start_time = time.time()
            if self.safe_mode.get():
                # 安全模式随机延迟 100-300ms
                time.sleep(0.1 + random.random() * 0.2)
                
            self.wcf.send_text(msg=self.reply_text, receiver=self.target_room)
            end_time = time.time()
            
            elapsed = (end_time - start_time) * 1000
            self.root.after(0, lambda: self.log(f"【成功秒回】目标发了: '{incoming_content}' | 回复用时: {elapsed:.2f}毫秒"))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"秒回发送失败，错误: {e}"))

    def on_tree_double_click(self, event):
        # 双击监听板上的某条群消息，自动填充输入框
        selected_item = self.tree.selection()
        if not selected_item:
            return
        
        values = self.tree.item(selected_item, "values")
        if values:
            sender_id = values[1]
            room_id = values[2]
            
            self.ent_room.delete(0, "end")
            self.ent_room.insert(0, room_id)
            
            self.ent_sender.delete(0, "end")
            self.ent_sender.insert(0, sender_id)
            
            self.log(f"已自动填入群聊ID: {room_id} | 发言人ID: {sender_id}")

    def toggle_monitoring(self):
        if not self.is_monitoring:
            # 开启监控前校验输入
            room = self.ent_room.get().strip()
            sender = self.ent_sender.get().strip()
            reply = self.txt_reply.get("1.0", "end-1c").strip()
            
            if not room or not sender or not reply:
                messagebox.showwarning("参数缺失", "请先填入完整的群聊ID、发言者ID和回复内容！\n(您可以通过双击右侧消息板中的行来自动填入ID)")
                return
            
            self.target_room = room
            self.target_sender = sender
            self.reply_text = reply
            
            self.is_monitoring = True
            self.btn_action.config(text=" 停止秒回监控 ", style="Danger.TButton")
            
            # 禁用输入框防止误改
            self.ent_room.config(state="disabled")
            self.ent_sender.config(state="disabled")
            self.txt_reply.config(state="disabled")
            
            self.log(f"▶ 秒回监控已开启！锁定群聊: {self.target_room} | 目标人物: {self.target_sender}")
        else:
            self.is_monitoring = False
            self.btn_action.config(text=" 第二步：启动秒回监控 ", style="Success.TButton")
            
            # 恢复输入框
            self.ent_room.config(state="normal")
            self.ent_sender.config(state="normal")
            self.txt_reply.config(state="normal")
            
            self.log("⏸ 秒回监控已暂停。")

    def on_closing(self):
        if self.wcf:
            try:
                self.wcf.disable_receiving_msg()
            except:
                pass
        self.root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = WeChatBotGUI(root)
    root.mainloop()
