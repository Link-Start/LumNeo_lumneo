# src/lumneo/persistence/repositories/_base.py
# Repository 基础设施：Session / Transaction 边界助手（§32 / §34）。
#
# 设计要点：
# - Repository 接收 Database（基础设施），通过 `_session()` 获取连接。
# - 当调用方显式传入 `conn`（事务/Unit of Work 边界）时，Repository 不提交、不关闭，
#   把事务所有权交还上层（§33 / §34：Commit 由明确的 Transaction Boundary 控制）。
# - 当 Repository 自行打开连接（独立简单 CRUD）时，由它负责提交与关闭。
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from lumneo.persistence.database import Database


class BaseRepository:
    """Repository 基类：封装 Database 依赖与连接/事务边界。"""

    def __init__(self, database: Database):
        self.database = database
        self._active_conn: Optional[object] = None

    def bind(self, conn: object) -> None:
        """绑定一个外部连接（如 Unit of Work 共享连接）。

        绑定后，所有不显式传入 conn 的仓储操作都会复用该连接，
        且不提交、不关闭（提交/关闭由绑定方控制）。解除绑定用 unbind()。
        """
        self._active_conn = conn

    def unbind(self) -> None:
        """解除 bind() 建立的连接绑定。"""
        self._active_conn = None

    @asynccontextmanager
    async def _session(self, conn: Optional[object] = None) -> AsyncIterator[object]:
        """获取一个连接（Connection/Session 原语）。

        - conn 不为 None：复用显式传入的连接。
        - conn 为 None 但有 bind() 连接：复用绑定连接（Unit of Work 路径）。
        - 否则：自行打开、提交、关闭（默认简单 CRUD 路径）。
        只要复用了外部连接，就不提交、不关闭（事务由调用方控制）。
        """
        effective = conn if conn is not None else self._active_conn
        own = effective is None
        if own:
            connection = await self.database.connect()
        else:
            connection = effective
        try:
            yield connection
            if own:
                await connection.commit()
        finally:
            if own:
                await connection.close()
