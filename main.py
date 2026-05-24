# main.py
import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')
if sys.stdin is None:
    sys.stdin = open(os.devnull, 'r', encoding='utf-8')

import uvicorn
import argparse
import mimetypes
import httpx
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routes.chat import router as chat_router
from backend.routes.chats import router as chats_router
from backend.routes.files import router as files_router
from backend.routes.model import router as model_router
from backend.routes.models import router as models_router
from backend.routes.profiles import router as profiles_router
from backend.routes.workspace import router as workspace_router

from backend.database import init_db
from backend.mcp_client import MCPClientManager
from config_loader import config


APP_READY = False
async def bg_init_services(app: FastAPI):
    """后台异步初始化任务，不会阻塞 FastAPI 服务的启动"""
    global APP_READY
    print("🚀 后台开始异步初始化基础设施 (DB, MCP)...")
    try:
        # 1. 初始化数据库
        await init_db()
        
        # 2. 初始化 MCP 管理器
        mcp_manager = MCPClientManager()
        await mcp_manager.connect_from_config(config.mcp_config_path)
        app.state.mcp_manager = mcp_manager
        
        # 3. 标记初始化成功
        APP_READY = True
        print("✅ 后台基础设施全部初始化完毕！")
    except Exception as e:
        print(f"❌ 后台初始化失败: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    asyncio.create_task(bg_init_services(app))
    yield  # 此时 FastAPI 会立刻对外开放端口，允许前端请求
    # 退出时清理
    print("🛑 应用有关闭信号，正在清理资源...")
    try:
        if hasattr(app.state, 'mcp_manager') and app.state.mcp_manager:
            await app.state.mcp_manager.close_all()
    except Exception as e:
        print(f"清理资源时出错: {e}")

app = FastAPI(lifespan=lifespan)

app.include_router(chat_router)
app.include_router(chats_router)
app.include_router(files_router)
app.include_router(model_router)
app.include_router(models_router)
app.include_router(profiles_router)
app.include_router(workspace_router)

from fastapi import Request, Response
TARGET_BASE_URL = "http://localhost"
@app.api_route("/files/generate/{file_path:path}", methods=["GET"])
async def proxy(request: Request, file_path: str):
    # 构建目标完整URL
    target_url = f"{TARGET_BASE_URL}/files/generate/{file_path}"
    # 获取原始请求体（二进制）
    body = await request.body()
    
    # 复制请求头，并修正 Host 头为目标服务
    headers = dict(request.headers)
    headers["host"] = "localhost"  # 覆盖 Host 头
    
    # 发起代理请求（异步）
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=request.query_params,
            follow_redirects=True   # 可选，跟随重定向
        )
    
    # 返回代理响应（保留状态码、内容和响应头）
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers)
    )

# 先挂载具体目录
app.mount("/files/uploads", StaticFiles(directory=config.uploads_dir), name="uploaded_files")

# 再挂载前端静态文件
if os.path.exists(config.static_dir):
    app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="static")
    app.mount("/assets", StaticFiles(directory=f"{config.static_dir}/assets"), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(f"{config.static_dir}/index.html")


if getattr(sys, 'frozen', False):  # 检测是否为 frozen exe
    # 关键：为 .js 文件注册正确的 MIME 类型
    mimetypes.add_type("application/javascript", ".js")
    port = 52025
    FRONTEND_PATH = f"http://127.0.0.1:{port}"
    debug_mode = False
    
else:
    port = 8080
    FRONTEND_PATH = "http://localhost:5173"  # 开发环境
    debug_mode = True

def start_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

def start_gui():
    import webview, threading, tkinter
    class Api:
        def select_folder(self):
            from tkinter import filedialog
            root = tkinter.Tk()
            root.withdraw()
            folder = filedialog.askdirectory()
            root.destroy()
            return folder

    t = threading.Thread(target=start_fastapi, daemon=True)
    t.start()

    webview.create_window(
        title="LumNeo",
        url=FRONTEND_PATH,
        width=1200,
        height=800,
        resizable=True,
        fullscreen=False,
        min_size=(800, 600),
        text_select=True,
        js_api=Api()
    )
    webview.start(debug=debug_mode, http_server=True, private_mode=False, icon='favicon.ico')

if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="启动LumNeo")
    parser.add_argument("--no-gui", action="store_true", help="不启动 GUI 界面，仅启动后端服务")
    args = parser.parse_args()

    if args.no_gui:
        # 无 GUI 模式：直接在主线程启动 FastAPI（阻塞）
        start_fastapi()
    else:
        # 有 GUI 模式：后台启动 FastAPI，主线程运行 webview
        start_gui()
        