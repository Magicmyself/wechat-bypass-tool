import urllib.request
import os
import sys

def download_file(url, filename):
    print(f"开始下载: {url}")
    print("下载需要一些时间，请耐心等待...")
    
    # 报告进度
    def progress_callback(blocks_transferred, block_size, total_size):
        if total_size > 0:
            percent = (blocks_transferred * block_size * 100) / total_size
            sys.stdout.write(f"\r进度: {percent:.1f}% ({blocks_transferred * block_size / 1024 / 1024:.1f}MB / {total_size / 1024 / 1024:.1f}MB)")
            sys.stdout.flush()
        else:
            sys.stdout.write(f"\r已下载: {blocks_transferred * block_size / 1024 / 1024:.1f}MB")
            sys.stdout.flush()

    try:
        # 自定义 User-Agent 模拟浏览器，防止被服务器拒绝
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')]
        urllib.request.install_opener(opener)
        
        urllib.request.urlretrieve(url, filename, reporthook=progress_callback)
        print("\n[成功] 下载完成！")
        return True
    except Exception as e:
        print(f"\n[错误] 下载失败: {e}")
        return False

def main():
    filename = "WeChatSetup-3.9.12.17.exe"
    
    # 尝试使用国内 Github 代理镜像加速下载，如果失败再使用官方直连
    urls = [
        f"https://ghp.ci/https://github.com/tom-snow/wechat-windows-versions/releases/download/v3.9.12.17/WeChatSetup-3.9.12.17.exe",
        f"https://github.com/tom-snow/wechat-windows-versions/releases/download/v3.9.12.17/WeChatSetup-3.9.12.17.exe"
    ]
    
    success = False
    for url in urls:
        if download_file(url, filename):
            success = True
            break
        print("尝试下一个镜像源...")
        
    if success:
        print(f"\n文件已保存至: {os.path.abspath(filename)}")
    else:
        print("\n[错误] 所有下载源均失败，请检查您的网络连接。")

if __name__ == "__main__":
    main()
