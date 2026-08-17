# src/lumneo/conversation/ports/provider_repository.py
# Repository Port（领域拥有）。对应原 models 表（LLM Provider 配置）。
from abc import ABC, abstractmethod
from typing import List, Optional

from lumneo.persistence.models.provider import ProviderModel


class ProviderRepository(ABC):
    """LLM Provider 配置（models 表）持久化端口。"""

    @abstractmethod
    async def list(self) -> List[ProviderModel]: ...

    @abstractmethod
    async def create(self, **fields) -> ProviderModel: ...

    @abstractmethod
    async def update(self, model_id: str, **fields) -> Optional[ProviderModel]: ...

    @abstractmethod
    async def delete(self, model_id: str) -> bool: ...
