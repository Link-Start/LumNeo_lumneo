# main.py
from backend.bootstrap import logger
import os
import sys
import argparse
import mimetypes
import asyncio
from contextlib import asynccontextmanager

import uvicorn
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.routes import register_all_routers
from backend.database import init_db
from backend.mcp_client import MCPClientManager
from config_loader import config


# ============ Lifespan 管理 ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时后台初始化，关闭时清理资源"""
    ready_event = asyncio.Event()
    app.state.ready_event = ready_event
    app.state.mcp_manager = None

    async def bg_init_services():
        logger.info("🚀 后台开始异步初始化基础设施 (DB, MCP)...")
        try:
            await init_db()
            mcp_manager = MCPClientManager()
            await mcp_manager.connect_from_config(config.mcp_config_path)
            app.state.mcp_manager = mcp_manager
            ready_event.set()
            logger.info("✅ 后台基础设施全部初始化完毕！")
        except Exception as e:
            logger.error(f"❌ 后台初始化失败: {e}", exc_info=True)
            ready_event.set()

    init_task = asyncio.create_task(bg_init_services())

    # 复用 HTTP 客户端连接池
    app.state.http_client = httpx.AsyncClient(
        base_url="http://localhost",
        follow_redirects=True,
        timeout=30
    )

    yield  # FastAPI 在此处开始接收请求

    # ---- 关闭清理 ----
    logger.info("🛑 应用收到关闭信号，正在清理资源...")
    init_task.cancel()
    try:
        await app.state.http_client.aclose()
    except Exception as e:
        logger.warning(f"关闭HTTP客户端出错: {e}")
    try:
        if app.state.mcp_manager:
            await app.state.mcp_manager.close_all()
    except Exception as e:
        logger.warning(f"关闭MCP管理器出错: {e}")


# ============ FastAPI App 构建 ============
app = FastAPI(lifespan=lifespan)

# 注册API路由（必须在mount静态文件之前）
register_all_routers(app)

@app.api_route("/files/generate/{file_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_generate(request: Request, file_path: str):
    """流式代理 /files/generate，复用连接池，支持大文件"""
    if not request.app.state.ready_event.is_set():
        return Response(content="Service initializing...", status_code=503)

    target_url = f"/files/generate/{file_path}"
    headers = dict(request.headers)
    headers["host"] = "localhost"

    client: httpx.AsyncClient = request.app.state.http_client
    req = client.build_request(
        method=request.method,
        url=target_url,
        headers=headers,
        content=await request.body(),
        params=request.query_params,
    )
    resp = await client.send(req, stream=True)

    # 过滤掉 hop-by-hop 头，避免代理异常
    excluded_headers = {"content-encoding", "transfer-encoding", "connection", "content-length"}
    response_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in excluded_headers
    }

    return StreamingResponse(
        resp.aiter_bytes(),
        status_code=resp.status_code,
        headers=response_headers,
        background=resp.aclose,  # 确保流关闭
    )


# ============ 静态文件挂载 ============
app.mount("/files/uploads", StaticFiles(directory=config.uploads_dir), name="uploaded_files")

if os.path.exists(config.static_dir):
    app.mount("/app", StaticFiles(directory=config.static_dir, html=True), name="static")


# ============ 运行模式判断 ============
IS_FROZEN = getattr(sys, 'frozen', False)

if IS_FROZEN:
    mimetypes.add_type("application/javascript", ".js")
    SERVER_PORT = 52025
    FRONTEND_URL = f"http://127.0.0.1:{SERVER_PORT}/app/"
    DEBUG_MODE = False
else:
    SERVER_PORT = 8080
    FRONTEND_URL = "http://localhost:5173"
    DEBUG_MODE = True


def start_fastapi():
    logger.info(f"🌐 FastAPI 启动于 0.0.0.0:{SERVER_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")


def start_gui():
    import webview
    import threading
    import subprocess
    from urllib.parse import unquote

    class Api:
        """暴露给前端的Python API"""
        def select_folder(self):
            # ⚠️ tkinter 必须在主线程运行，这里改用 webview 原生对话框
            result = webview.windows[0].create_file_dialog(
                dialog_type=webview.FOLDER_DIALOG,
                allow_multiple=False
            )
            return result[0] if result else None
        def open_with_default_app(self, file_path: str):
            """使用系统默认程序打开本地文件"""
            # 解码 URL 编码（例如 %5C 转为 \，%E8%BD%AC 转为中文字符）
            decoded_path = unquote(file_path)
            # 去除可能的 file:// 前缀
            if decoded_path.startswith('file://'):
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
            """下载普通 http/https 文件，弹出保存对话框"""
            try:
                # 从 URL 中提取文件名
                filename = name or url.split('/')[-1].split('?')[0]
                if not filename:
                    filename = "downloaded_file"
                print(f"准备下载: {filename}")

                # 1. 修复：使用 webview.windows[0].create_file_dialog 和 webview.SAVE_DIALOG
                # 2. 修复：pywebview 的 file_types 需要是字符串元组或列表，例如 ('所有文件 (*.*)',)
                result = webview.windows[0].create_file_dialog(
                    dialog_type=webview.SAVE_DIALOG,
                    save_filename=filename,
                    file_types=('所有文件 (*.*)',)
                )

                # result 正常返回的是一个包含路径的元组，如果用户取消则返回 None
                save_path = result[0] if result else None

                if not save_path:
                    return {"success": False, "error": "用户取消了保存"}
                
                # 使用 httpx 同步客户端下载（避免阻塞主线程，但此处 API 方法本身在后台线程）
                with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                    with client.stream("GET", url) as response:
                        response.raise_for_status()
                        with open(save_path, "wb") as f:
                            for chunk in response.iter_bytes(chunk_size=8192):
                                f.write(chunk)
                return {"success": True, "path": save_path}
            
            except Exception as e:
                # 打印出具体错误，避免下次再被 except 静默吃掉报错导致无法排查
                print(f"下载文件时发生错误: {e}") 
                return {"success": False, "error": str(e)}

    # FastAPI 放在守护线程
    server_thread = threading.Thread(target=start_fastapi, daemon=True)
    server_thread.start()

    # 允许在 WebView 中进行文件下载
    webview.settings['ALLOW_DOWNLOADS'] = True

    webview.create_window(
        title="LumNeo",
        url=FRONTEND_URL,
        width=1200, height=860,
        min_size=(800, 768),
        resizable=True,
        text_select=True,
        js_api=Api(),
    )
    webview.start(debug=DEBUG_MODE, http_server=True, private_mode=False, icon='favicon.ico')


# ============ 入口 ============
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动 LumNeo")
    if DEBUG_MODE:
        parser.add_argument("--gui", action="store_true", help="启动 GUI 界面")
    else:
        parser.add_argument("--no-gui", action="store_true", help="仅启动后端服务，不启动GUI")
    args = parser.parse_args()

    use_gui = args.gui if DEBUG_MODE else not args.no_gui

    if use_gui:
        start_gui()
    else:
        start_fastapi()