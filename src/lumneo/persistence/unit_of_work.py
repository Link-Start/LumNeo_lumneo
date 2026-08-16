# persistence/unit_of_work.py
# 工作单元（Unit of Work，§35）。
#
# 用于把“多个仓储操作”纳入同一个数据库连接与事务边界，
# 避免跨仓储业务在同一个 HTTP/工具调用中各自开关连接、无法回滚。
#
# 用法：
#   async with UnitOfWork(database) as uow:
#       conv_repo = uow.get_repository(SQLConversationRepository)
#       msg_repo  = uow.get_repository(SQLMessageRepository)
#       await conv_repo.create(...)
#       await msg_repo.add(...)
#   # 正常退出自动 commit；异常退出自动 rollback 并关闭连接。
#
# 内部机制：UnitOfWork 打开一个连接并 bind() 到每个被请求的仓储，
# 仓储的 _session() 会复用该连接且不提交/关闭（§33 / §34）。
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional, Type

from lumneo.persistence.database import Database
from lumneo.persistence.repositories._base import BaseRepository


class UnitOfWork:
    """跨仓储的单一连接 + 事务边界。"""

    def __init__(self, database: Database):
        self._database = database
        self._conn: Optional[object] = None
        self._repos: Dict[Type[BaseRepository], BaseRepository] = {}

    async def __aenter__(self) -> "UnitOfWork":
        self._conn = await self._database.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type is None:
                await self._conn.commit()
            else:
                await self._conn.rollback()
        finally:
            await self._conn.close()
            self._conn = None
            for repo in self._repos.values():
                repo.unbind()
            self._repos.clear()

    @property
    def connection(self) -> object:
        """暴露当前连接，供需要 conn 参数的仓储方法直接使用。"""
        return self._conn

    def get_repository(self, repo_cls: Type[BaseRepository]) -> BaseRepository:
        """获取一个绑定到本工作单元连接的仓储实例（同一类型复用）。"""
        if repo_cls not in self._repos:
            repo = repo_cls(self._database)
            if self._conn is not None:
                repo.bind(self._conn)
            self._repos[repo_cls] = repo
        return self._repos[repo_cls]
