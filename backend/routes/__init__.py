# backend/routes/__init__.py
# 需要手动导入所有模块，解决打包路由失效的问题
from fastapi import FastAPI

from . import chat, chats, files, model, models, profiles, workspace, toolcalls, skills

def register_all_routers(app: FastAPI):
    modules = [chat, chats, files, model, models, profiles, workspace, toolcalls, skills]  # 列出所有模块
    for mod in modules:
        router = getattr(mod, "router", None)
        if router is not None:
            app.include_router(router)