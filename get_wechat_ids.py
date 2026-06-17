import time
from wcferry import Wcf, WxMsg

def on_message(msg: WxMsg):
    # 只抓取群消息
    if msg.from_group():
        print("-" * 50)
        print(f"【收到群消息】时间: {time.strftime('%H:%M:%S')}")
        print(f"群聊ID (roomid): {msg.roomid}")
        print(f"发送人ID (sender): {msg.sender}")
        print(f"消息内容: {msg.content}")
        print("-" * 50)

def main():
    print("正在连接微信并启动监控...")
    try:
        wcf = Wcf()
        wcf.connect()
    except Exception as e:
        print(f"连接微信失败！请确保安装了对应版本的微信PC版且已登录。错误信息: {e}")
        return

    # 开启接收消息，并绑定回调
    wcf.enable_receiving_msg(on_message)
    print("\n[提示] 监控已成功启动！请让目标成员在目标群内发送一条任意消息。")
    print("[提示] 控制台会显示对应的群聊ID (roomid) 和发送人ID (sender)。\n")
    
    wcf.keep_running()

if __name__ == "__main__":
    main()
