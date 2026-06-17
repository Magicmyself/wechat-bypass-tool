import wxauto4

def test_init():
    try:
        print("Initializing wxauto4.WeChat()...")
        wx = wxauto4.WeChat()
        print("Initialization successful!")
        print(f"WeChat nickname: {wx.nickname}")
        print(f"Current chat: {wx.CurrentChat()}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_init()
