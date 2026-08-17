# src/lumneo/conversation/ports/skill_repository.py
# Repository Port（领域拥有）。
from abc import ABC, abstractmethod
from typing import List, Optional

from lumneo.persistence.models.skill import SkillModel


class SkillRepository(ABC):
    """技能（skills）持久化端口。"""

    @abstractmethod
    async def create_or_update(self, skill_id: str, name: str, **fields) -> Optional[SkillModel]: ...

    @abstractmethod
    async def update(self, skill_id: str, **fields) -> Optional[SkillModel]: ...

    @abstractmethod
    async def delete(self, skill_id: str) -> bool: ...

    @abstractmethod
    async def get_by_id(self, skill_id: str) -> Optional[SkillModel]: ...

    @abstractmethod
    async def list_all(self) -> List[SkillModel]: ...

    @abstractmethod
    async def list_by_profile(self, profile_id: int) -> List[SkillModel]: ...

    @abstractmethod
    async def list_available_for_profile(self, profile_id: int) -> List[SkillModel]: ...

    @abstractmethod
    async def link_to_profile(self, profile_id: int, skill_id: str, config_overrides: dict = None) -> None: ...

    @abstractmethod
    async def get_profiles_using_skill(self, skill_id: str) -> list: ...

    @abstractmethod
    async def replace_profile_skills(self, profile_id: int, skill_ids: List[str]) -> None: ...

    @abstractmethod
    async def set_selected_skills(self, profile_id: int, selected_skill_ids: List[str]) -> None: ...
