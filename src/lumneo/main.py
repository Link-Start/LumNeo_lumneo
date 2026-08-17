# src/lumneo/main.py
import os
import sys
import socket
import time
import argparse
import mimetypes

import uvicorn
import httpx

# 允许以 `python src/lumneo/main.py` 直接运行：把 src 目录加入模块搜索路径，
# 使 `import lumneo` 可解析（否则 sys.path[0] 为 src/lumneo 而非 src）。
_SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_ROOT not in sys.path:
    sys.path.insert(0, _SRC_ROOT)

from lumneo.bootstrap.app import create_app
from lumneo.kernel.common.logger import logger


# ============ 运行模式判断 ============
IS_FROZEN = getattr(sys, "frozen", False)

if IS_FROZEN:
    # 打包后 .js 可能被错误识别为 text/plain，强制修正 MIME
    mimetypes.add_type("application/javascript", ".js")
    SERVER_PORT = 52025
    FRONTEND_URL = f"http://127.0.0.1:{SERVER_PORT}/app/"
    DEBUG_MODE = False
else:
    SERVER_PORT = 8686
    FRONTEND_URL = "http://localhost:8520"
    DEBUG_MODE = True

# ============ 端口辅助 ============
def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """检测指定端口是否已经被监听。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0

def wait_for_server_ready(host: str, port: int, timeout: int = 15) -> bool:
    """轮询等待服务启动。"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_open(host, port):
            return True
        time.sleep(0.1)  # 每 100ms 检测一次
    return False


def start_fastapi(app):
    try:
        logger.info(f"🌐 FastAPI 启动于 0.0.0.0:{SERVER_PORT}")
        uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")
    except Exception as e:
        # 捕获端口占用等异常，防止线程静默死亡
        logger.error(f"❌ FastAPI 启动失败: {e}")


def start_gui(app):
    import webview
    import threading
    import subprocess
    from urllib.parse import unquote

    class Api:
        """暴露给前端的 Python API。"""

        def select_folder(self):
            result = webview.windows[0].create_file_dialog(
                dialog_type=webview.FOLDER_DIALOG,
                allow_multiple=False,
            )
            return result[0] if result else None

        def open_with_default_app(self, file_path: str):
            """使用系统默认程序打开本地文件。"""
            # 解码 URL 编码（例如 %5C 转为 \，%E8%BD%AC 转为中文字符）
            decoded_path = unquote(file_path)
            # 去除可能的 file:// 前缀
            if decoded_path.startswith("file://"):
                decoded_path = decoded_path[7:]
            # 确保路径存在
            if not os.path.exists(decoded_path):
                return {"success": False, "error": f"文件不存在: {decoded_path}"}
            try:
                if sys.platform == "win32":
                    os.startfile(decoded_path)
                elif sys.platform == "darwin":
                    subprocess.run(["open", decoded_path])
                else:
                    subprocess.run(["xdg-open", decoded_path])
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

        def download_file(self, url: str, name: str):
            """下载普通 http/https 文件，弹出保存对话框。"""
            try:
                # 从 URL 中提取文件名
                filename = name or url.split("/")[-1].split("?")[0]
                if not filename:
                    filename = "downloaded_file"

                result = webview.windows[0].create_file_dialog(
                    dialog_type=webview.SAVE_DIALOG,
                    save_filename=filename,
                    file_types=("所有文件 (*.*)",),
                )

                # result 正常返回的是一个包含路径的元组，如果用户取消则返回 None
                save_path = result[0] if result else None

                if not save_path:
                    return {"success": False, "error": "用户取消了保存"}

                # 使用 httpx 同步客户端下载
                with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                    with client.stream("GET", url) as response:
                        response.raise_for_status()
                        with open(save_path, "wb") as f:
                            for chunk in response.iter_bytes(chunk_size=8192):
                                f.write(chunk)
                return {"success": True, "path": save_path}

            except Exception as e:
                logger.error(f"下载文件时发生错误: {e}")
                return {"success": False, "error": str(e)}

    # FastAPI 放在守护线程
    server_thread = threading.Thread(target=start_fastapi, args=(app,), daemon=True)
    server_thread.start()

    logger.info("⏳ 等待 FastAPI 服务就绪...")
    if not wait_for_server_ready("127.0.0.1", SERVER_PORT, timeout=15):
        # 如果 15 秒后还没启动，说明内部报错了（大概率是端口被占用）
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "启动失败",
            f"后端服务无法启动 (端口 {SERVER_PORT} 可能被占用)。\n请检查是否有同名进程残留，然后重试。",
        )
        sys.exit(1)  # 强制退出

    logger.info("✅ FastAPI 服务已就绪，准备打开界面...")

    # 允许在 WebView 中进行文件下载
    webview.settings["ALLOW_DOWNLOADS"] = True

    webview.create_window(
        title="LumNeo",
        url=FRONTEND_URL.rstrip("/") + "?v=" + str(int(time.time())),
        width=1200,
        height=860,
        min_size=(800, 768),
        resizable=True,
        text_select=True,
        js_api=Api(),
    )
    webview.start(debug=DEBUG_MODE, http_server=True, private_mode=False, icon="favicon.ico")

# ============ 入口 ============
def main():
    global DEBUG_MODE
    parser = argparse.ArgumentParser(description="启动 LumNeo")
    parser.add_argument("--debug", action="store_true", help="启用 DEBUG 模式")

    if DEBUG_MODE:
        parser.add_argument("--gui", action="store_true", help="启动 GUI 界面")
    else:
        parser.add_argument("--no-gui", action="store_true", help="仅启动后端服务，不启动GUI")
    args = parser.parse_args()

    if args.debug:
        DEBUG_MODE = True
        use_gui = True
    else:
        use_gui = args.gui if DEBUG_MODE else (not args.no_gui)

    # 构建应用（组合根在 lifespan 内懒加载；也可显式 create_app(container)）
    app = create_app()

    if use_gui:
        start_gui(app)
    else:
        start_fastapi(app)


if __name__ == "__main__":
    main()
