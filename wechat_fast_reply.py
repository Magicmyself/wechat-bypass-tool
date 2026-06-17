import time
import random
from wcferry import Wcf, WxMsg

# ==================== 配置区 ====================
# 请在此处填入您使用 get_wechat_ids.py 获取到的ID
TARGET_ROOM = "xxxxxx@chatroom"   # 目标群聊的 roomid
TARGET_SENDER = "wxid_xxxxxxxxx"   # 目标群成员的微信ID (sender)

# 您想要秒回的固定内容
REPLY_TEXT = "收到！这是自动秒回的固定内容。"

# 是否开启防封随机微调延迟（开启后会延迟 0.1~0.3 秒，模拟真人操作，更安全）
SAFE_MODE = True
# ================================================

wcf = Wcf()
wcf.connect()

def on_message(msg: WxMsg):
    # 过滤条件：群消息 且 群ID匹配 且 发送人ID匹配 且 是文本消息
    if msg.from_group() and msg.roomid == TARGET_ROOM and msg.sender == TARGET_SENDER:
        if msg.type == 1:  # 1 代表文本消息
            start_time = time.time()
            
            # 如果开启安全模式，加入一个 0.1 到 0.3 秒之间的极短随机延迟，模拟人类打字
            if SAFE_MODE:
                time.sleep(0.1 + random.random() * 0.2)
                
            # 发送文本回复
            wcf.send_text(msg=REPLY_TEXT, receiver=msg.roomid)
            
            end_time = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] 成功响应 {msg.sender} 发送的消息: '{msg.content}'")
            print(f"回复用时: {(end_time - start_time) * 1000:.2f} 毫秒")

def main():
    # 开启接收消息，绑定回调函数
    wcf.enable_receiving_msg(on_message)
    print("=" * 60)
    print("  微信群消息极速响应（秒回）机器人已启动")
    print("=" * 60)
    print(f"当前监控目标群: {TARGET_ROOM}")
    print(f"当前监控发言人: {TARGET_SENDER}")
    print(f"秒回固定内容: {REPLY_TEXT}")
    print(f"安全模拟模式: {'已开启 (延迟 100-300ms)' if SAFE_MODE else '已关闭 (极限秒回)'}")
    print("正在监听中...")
    
    wcf.keep_running()

if __name__ == "__main__":
    main()
