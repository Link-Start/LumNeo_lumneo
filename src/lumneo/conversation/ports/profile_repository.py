# conversation/ports/profile_repository.py
# Repository Port（领域拥有，§25）。
from abc import ABC, abstractmethod
from typing import List, Optional

from lumneo.persistence.models.profile import ProfileModel


class ProfileRepository(ABC):
    """角色配置（profiles）持久化端口。"""

    @abstractmethod
    async def create(self, **fields) -> ProfileModel: ...

    @abstractmethod
    async def update(self, profile_id: int, **fields) -> Optional[ProfileModel]: ...

    @abstractmethod
    async def list(self) -> List[ProfileModel]: ...

    @abstractmethod
    async def delete(self, profile_id: int) -> bool: ...

    @abstractmethod
    async def get_by_id(self, profile_id: int) -> Optional[ProfileModel]: ...
