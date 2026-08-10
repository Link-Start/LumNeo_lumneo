# main.py
from backend.bootstrap import logger
import os
import sys
import socket
import time
import argparse
import mimetypes
import asyncio
import datetime  # Phase 4 修复：移到顶部，供 lifespan 使用
from contextlib import asynccontextmanager

import uvicorn
import httpx
import aiofiles
from starlette.responses import StreamingResponse
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.routes import register_all_routers
from backend.database import init_db
from backend.mcp_client import MCPClientManager
from backend.memory import MemoryManager, FTSIndexManager, Consolidator
from config_loader import config


class PrecompressedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        is_html = path.endswith(".html") or path == "" or path == "/"
        no_cache_headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        # 检查 .br 文件
        br_path = path + ".br"
        full_br = os.path.join(self.directory, br_path) if self.directory else br_path
        if os.path.isfile(full_br):
            # 异步打开文件
            file_handle = await aiofiles.open(full_br, mode="rb")
            
            async def file_iterator():
                try:
                    while chunk := await file_handle.read(64 * 1024):
                        yield chunk
                finally:
                    await file_handle.close()
            
            # 获取正确的 Content-Type（基于原始文件扩展名）
            content_type, _ = mimetypes.guess_type(path)
            headers = {
                "Content-Encoding": "br",
                "Content-Type": content_type or "application/octet-stream",
                "Vary": "Accept-Encoding",
            }

            if is_html:
                headers.update(no_cache_headers)

            # 注意：不设置 Content-Length，因为 StreamingResponse 会自动分块传输
            return StreamingResponse(
                file_iterator(),
                status_code=200,
                headers=headers,
            )
        
        # 无 .gz 文件时回退
        response = await super().get_response(path, scope)

        if is_html:
            response.headers.update(no_cache_headers)
        return response

# ============ Lifespan 管理 ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时后台初始化，关闭时清理资源"""
    ready_event = asyncio.Event()
    app.state.ready_event = ready_event
    app.state.mcp_manager = None
    app.state.init_success = False
    app.state.init_error = None
    app.state.memory_manager = None
    app.state.fts_manager = None
    app.state.consolidator = None

    async def bg_init_services():
        logger.info("🚀 后台开始异步初始化基础设施 (DB, MCP, Memory)...")
        try:
            await init_db()

            # 创建 MemoryManager（自动创建目录）
            memory_mgr = MemoryManager()
            app.state.memory_manager = memory_mgr
            # 初始化 FTS5
            from backend.database import get_db
            db = await get_db()
            fts_mgr = FTSIndexManager(db)
            await fts_mgr.init_schema()
            # 启动一致性校验与重建
            rebuilt, total = await fts_mgr.startup_consistency_check()
            if rebuilt > 0:
                logger.info(f"🔄 FTS5 重建 {rebuilt}/{total} 个索引")
            
            app.state.fts_manager = fts_mgr
            memory_mgr.fts_manager = fts_mgr

            # 启动 access_count 定时刷盘任务
            flush_task = asyncio.create_task(memory_mgr.start_access_flush_loop())
            memory_mgr._access_flush_task = flush_task

            # Consolidator 定时归档
            consolidator = Consolidator(memory_mgr, app)
            app.state.consolidator = consolidator

            # 启动 Consolidator 定时任务（每 2 小时检查一次）
            async def _consolidator_loop():
                while True:
                    await asyncio.sleep(7200)  # 2 小时
                    # await asyncio.sleep(120)  # 2 分钟
                    try:
                        processed, extracted = await consolidator.run()
                        if processed > 0:
                            logger.info(f"🗄️ Consolidator: 处理 {processed} 条 timeline, 提取 {extracted} 条记忆")
                    except Exception as e:
                        logger.warning(f"Consolidator 定时任务出错: {e}")
            
            app.state._consolidator_task = asyncio.create_task(_consolidator_loop())

            # 启动月度摘要定时任务（每月 1 号 03:00 执行）
            async def _monthly_summary_loop():
                while True:
                    now = datetime.datetime.now()
                    # 计算到下个月 1 号 03:00 的等待时间
                    if now.day == 1 and now.hour < 3:
                        # 本月 1 号，且还没到 3 点
                        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
                    else:
                        # 计算下个月 1 号
                        if now.month == 12:
                            next_run = now.replace(year=now.year + 1, month=1, day=1, hour=3, minute=0, second=0, microsecond=0)
                        else:
                            next_run = now.replace(month=now.month + 1, day=1, hour=3, minute=0, second=0, microsecond=0)
                    
                    wait_seconds = (next_run - now).total_seconds()
                    logger.info(f"📅 下次月度摘要生成: {next_run.isoformat()} (等待 {wait_seconds/3600:.1f} 小时)")
                    await asyncio.sleep(wait_seconds)

                    try:
                        # 重新获取当前时间，避免 sleep 跨月后使用过期 now
                        now = datetime.datetime.now()
                        # 生成上个月的摘要
                        target_month = now.month - 1 if now.month > 1 else 12
                        target_year = now.year if now.month > 1 else now.year - 1
                        summary_path = await consolidator.generate_monthly_summary(target_year, target_month)
                        if summary_path:
                            logger.info(f"📅 月度摘要已生成: {summary_path}")
                    except Exception as e:
                        logger.warning(f"月度摘要生成出错: {e}")
            
            app.state._monthly_task = asyncio.create_task(_monthly_summary_loop())

            # FTS5 每日定时全量重建（每日凌晨 4:00）
            async def _fts_rebuild_loop():
                while True:
                    now = datetime.datetime.now()
                    next_run = now.replace(hour=4, minute=0, second=0, microsecond=0)
                    if next_run <= now:
                        next_run += datetime.timedelta(days=1)
                    
                    wait_seconds = (next_run - now).total_seconds()
                    logger.info(f"🔄 下次 FTS5 全量重建: {next_run.isoformat()} (等待 {wait_seconds/3600:.1f} 小时)")
                    await asyncio.sleep(wait_seconds)
                    
                    try:
                        if app.state.fts_manager:
                            count = await app.state.fts_manager.rebuild_index()
                            logger.info(f"🔄 FTS5 全量重建完成，共重建 {count} 个索引")
                    except Exception as e:
                        logger.warning(f"FTS5 定时重建出错: {e}")
            
            app.state._fts_rebuild_task = asyncio.create_task(_fts_rebuild_loop())

            mcp_manager = MCPClientManager()
            await mcp_manager.connect_from_config(config.mcp_config_path)
            app.state.mcp_manager = mcp_manager
            app.state.init_success = True
            ready_event.set()
            logger.info("✅ 后台基础设施全部初始化完毕！")
        except Exception as e:
            logger.error(f"❌ 后台初始化失败: {e}", exc_info=True)
            app.state.init_error = str(e)
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
        await init_task
    except asyncio.CancelledError:
        pass

    # 关闭 FTS 管理器
    if app.state.fts_manager:
        try:
            await asyncio.wait_for(app.state.fts_manager.close(), timeout=2.0)
            logger.info("FTS 管理器已关闭")
        except asyncio.TimeoutError:
            logger.warning("FTS 关闭超时，强制跳过")
        except Exception as e:
            logger.warning(f"FTS 关闭异常: {e}")

    # 取消 Consolidator 定时任务
    if hasattr(app.state, '_consolidator_task'):
        app.state._consolidator_task.cancel()
        try:
            await app.state._consolidator_task
        except asyncio.CancelledError:
            pass

    # 取消月度摘要定时任务
    if hasattr(app.state, '_monthly_task'):
        app.state._monthly_task.cancel()
        try:
            await app.state._monthly_task
        except asyncio.CancelledError:
            pass

    # Phase 4 新增：取消 FTS5 定时重建任务
    if hasattr(app.state, '_fts_rebuild_task'):
        app.state._fts_rebuild_task.cancel()
        try:
            await app.state._fts_rebuild_task
        except asyncio.CancelledError:
            pass

    # 关闭 MemoryManager
    if app.state.memory_manager:
        try:
            await asyncio.wait_for(app.state.memory_manager.shutdown(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning("MemoryManager 关闭超时")
    try:
        await app.state.http_client.aclose()
    except Exception as e:
        logger.warning(f"关闭HTTP客户端出错: {e}")
    try:
        if app.state.mcp_manager:
            await app.state.mcp_manager.close_all()
    except Exception as e:
        logger.warning(f"关闭MCP管理器出错: {e}")

    logger.info("✅ 资源清理完毕")


# ============ FastAPI App 构建 ============
app = FastAPI(lifespan=lifespan)

# 注册API路由（必须在mount静态文件之前）
register_all_routers(app)

@app.get("/api/wait-ready")
async def wait_ready(request: Request):
    """检测后台基础设施初始化是否完毕（或失败）"""
    await request.app.state.ready_event.wait()
    if request.app.state.init_success:
        return {"ready": True, "status": "ok"}
    else:
        return {
            "ready": False,
            "status": "error",
            "error": getattr(request.app.state, 'init_error', '初始化失败'),
        }

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
    app.mount("/app", PrecompressedStaticFiles(directory=config.static_dir, html=True), name="static")


# ============ 运行模式判断 ============
IS_FROZEN = getattr(sys, 'frozen', False)

if IS_FROZEN:
    mimetypes.add_type("application/javascript", ".js")
    SERVER_PORT = 52025
    FRONTEND_URL = f"http://127.0.0.1:{SERVER_PORT}/app/"
    DEBUG_MODE = False
else:
    SERVER_PORT = 8686
    FRONTEND_URL = "http://localhost:8520"
    DEBUG_MODE = True

def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """检测指定端口是否已经被监听"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0

def wait_for_server_ready(host: str, port: int, timeout: int = 15) -> bool:
    """轮询等待服务启动"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_open(host, port):
            return True
        time.sleep(0.1) # 每 100ms 检测一次
    return False


def start_fastapi():
    try:
        logger.info(f"🌐 FastAPI 启动于 0.0.0.0:{SERVER_PORT}")
        uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")
    except Exception as e:
        # 捕获端口占用等异常，防止线程静默死亡
        logger.error(f"❌ FastAPI 启动失败: {e}")


def start_gui():
    import webview
    import threading
    import subprocess
    from urllib.parse import unquote

    class Api:
        """暴露给前端的Python API"""
        def select_folder(self):
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
                logger.error(f"下载文件时发生错误: {e}") 
                return {"success": False, "error": str(e)}

    # FastAPI 放在守护线程
    server_thread = threading.Thread(target=start_fastapi, daemon=True)
    server_thread.start()

    logger.info(f"⏳ 等待 FastAPI 服务就绪...")
    if not wait_for_server_ready("127.0.0.1", SERVER_PORT, timeout=15):
        # 如果 15 秒后还没启动，说明内部报错了（大概率是端口被占用）
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "启动失败", 
            f"后端服务无法启动 (端口 {SERVER_PORT} 可能被占用)。\n请检查是否有同名进程残留，然后重试。"
        )
        sys.exit(1) # 强制退出
        
    logger.info("✅ FastAPI 服务已就绪，准备打开界面...")

    # 允许在 WebView 中进行文件下载
    webview.settings['ALLOW_DOWNLOADS'] = True

    webview.create_window(
        title="LumNeo",
        url=FRONTEND_URL.rstrip('/') + '?v=' + str(int(time.time())),
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
        use_gui = args.gui if DEBUG_MODE else not args.no_gui

    if use_gui:
        start_gui()
    else:
        start_fastapi()