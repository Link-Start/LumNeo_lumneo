# src/lumneo/bootstrap/app.py
# FastAPI 应用工厂（应用装配的唯一入口）。
#
# 职责：
#   1. 创建 FastAPI 应用并挂载全部路由；
#   2. 挂载静态资源（前端构建 / 上传文件）；
#   3. 通过 lifespan 完成“后台异步初始化”（DB、MCP、容器），并暴露
#      app.state.facade / mcp_manager / container 供路由访问；
#   4. 提供 /api/wait-ready（前端探测就绪）与 /files/generate（流式代理）。
#
# 组合根产出的组件优先通过 create_app(container=...) 传入（测试 / 显式装配）；
# 若未传入，则由 lifespan 内部调用 build_container() 懒加载（生产默认路径），
# 与原始 main.py 的后台初始化语义保持一致。
import os
import asyncio
import mimetypes
from contextlib import asynccontextmanager
from typing import Optional

import httpx
import aiofiles
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles

from lumneo.api.routes.chat import router as chat_router
from lumneo.api.routes.chats import router as chats_router
from lumneo.api.routes.profiles import router as profiles_router
from lumneo.api.routes.models import router as models_router
from lumneo.api.routes.skills import router as skills_router
from lumneo.api.routes.toolcalls import router as toolcalls_router
from lumneo.api.routes.plans import router as plans_router
from lumneo.api.routes.files import router as files_router
from lumneo.api.routes.workspace import router as workspace_router
from lumneo.api.routes.collaboration import router as collaboration_router
from lumneo.bootstrap.container import Container, build_container
from lumneo.kernel.config.app_config import config
from lumneo.kernel.common.logger import logger


class PrecompressedStaticFiles(StaticFiles):
    """支持预压缩 .br 文件的静态文件服务（原 main.py 逻辑迁移）。"""

    async def get_response(self, path: str, scope) -> Response:
        is_html = path.endswith(".html") or path == "" or path == "/"
        no_cache_headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        # 检查 .br 文件
        br_path = path + ".br"
        full_br = os.path.join(self.directory, br_path) if self.directory else br_path
        if os.path.isfile(full_br):
            file_handle = await aiofiles.open(full_br, mode="rb")

            async def file_iterator():
                try:
                    while chunk := await file_handle.read(64 * 1024):
                        yield chunk
                finally:
                    await file_handle.close()

            content_type, _ = mimetypes.guess_type(path)
            headers = {
                "Content-Encoding": "br",
                "Content-Type": content_type or "application/octet-stream",
                "Vary": "Accept-Encoding",
            }
            if is_html:
                headers.update(no_cache_headers)
            return StreamingResponse(
                file_iterator(),
                status_code=200,
                headers=headers,
            )
        # 无 .br 文件时回退到默认处理
        response = await super().get_response(path, scope)
        if is_html:
            response.headers.update(no_cache_headers)
        return response


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用生命周期：启动时后台初始化，关闭时清理资源。"""
    ready_event = asyncio.Event()
    app.state.ready_event = ready_event
    app.state.mcp_manager = getattr(app.state, "mcp_manager", None)
    app.state.init_success = False
    app.state.init_error = None

    async def bg_init_services():
        logger.info("🚀 后台开始异步初始化基础设施 (DB, MCP)...")
        try:
            # 若 create_app 已传入预构建容器（测试 / 显式装配），直接复用；
            # 否则由组合根懒加载构建。
            container = getattr(app.state, "container", None)
            if container is None:
                container = await build_container()
                app.state.container = container
                app.state.facade = container.facade
                app.state.resource_facade = container.resource_facade
                app.state.mcp_manager = container.mcp_manager
            app.state.init_success = True
            ready_event.set()
            logger.info("✅ 后台基础设施全部初始化完毕！")
        except Exception as e:
            logger.error(f"❌ 后台初始化失败: {e}", exc_info=True)
            app.state.init_error = str(e)
            ready_event.set()

    init_task = asyncio.create_task(bg_init_services())

    # 复用 HTTP 客户端连接池（供 /files/generate 代理使用）
    app.state.http_client = httpx.AsyncClient(
        base_url="http://localhost", follow_redirects=True, timeout=30
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


def create_app(container: Optional[Container] = None) -> FastAPI:
    """基于（可选）已初始化容器创建 FastAPI 应用并完成全部装配。"""
    app = FastAPI(title="LumNeo V2", version="2.0.0", lifespan=_lifespan)

    # 1. 挂载 API 路由（薄层，业务逻辑经 conversation.facade / application.facade 完成）
    app.include_router(chat_router)
    app.include_router(chats_router)
    app.include_router(profiles_router)
    app.include_router(models_router)
    app.include_router(skills_router)
    app.include_router(toolcalls_router)
    app.include_router(plans_router)
    app.include_router(files_router)
    app.include_router(workspace_router)
    app.include_router(collaboration_router)

    # 2. 前端就绪探测（原 main.py 路由迁移）
    @app.get("/api/wait-ready")
    async def wait_ready(request: Request):
        """检测后台基础设施初始化是否完毕（或失败）。"""
        await request.app.state.ready_event.wait()
        if request.app.state.init_success:
            return {"ready": True, "status": "ok"}
        return {
            "ready": False,
            "status": "error",
            "error": getattr(request.app.state, "init_error", "初始化失败"),
        }

    # 3. 流式代理 /files/generate（复用连接池，支持大文件；原 main.py 迁移）
    @app.api_route(
        "/files/generate/{file_path:path}",
        methods=["GET", "POST", "PUT", "DELETE"],
    )
    async def proxy_generate(request: Request, file_path: str):
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

        excluded_headers = {
            "content-encoding",
            "transfer-encoding",
            "connection",
            "content-length",
        }
        response_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in excluded_headers
        }
        return StreamingResponse(
            resp.aiter_bytes(),
            status_code=resp.status_code,
            headers=response_headers,
            background=resp.aclose,
        )

    # 4. 静态文件挂载
    app.mount(
        "/files/uploads",
        StaticFiles(directory=str(config.uploads_dir)),
        name="uploaded_files",
    )
    if os.path.exists(str(config.static_dir)):
        app.mount(
            "/app",
            PrecompressedStaticFiles(directory=str(config.static_dir), html=True),
            name="static",
        )

    # 5. 注入组合根产出的组件（供路由通过 request.app.state 访问）
    if container is not None:
        app.state.container = container
        app.state.facade = container.facade
        app.state.resource_facade = container.resource_facade
        app.state.mcp_manager = container.mcp_manager

    return app
