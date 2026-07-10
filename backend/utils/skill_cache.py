import os
from typing import Optional

class SkillCache:
    def __init__(self):
        # {skill_id: (prompt_content, mtime)}
        self._cache: dict[str, tuple[str, float]] = {}

    def get(self, skill_id: str, file_path: str) -> Optional[str]:
        """
        从缓存获取 prompt_content，
        若文件不存在或修改时间已变更则返回 None（缓存失效）
        """
        entry = self._cache.get(skill_id)
        if entry:
            content, cached_mtime = entry
            skill_md = os.path.join(file_path, "SKILL.md")
            try:
                current_mtime = os.path.getmtime(skill_md)
                if current_mtime == cached_mtime:
                    return content
            except OSError:
                pass
            # 文件发生变化或不存在 → 删除过期缓存
            del self._cache[skill_id]
        return None

    def set(self, skill_id: str, file_path: str, content: str):
        """将解析后的技能内容存入缓存，并记录当前文件 mtime"""
        try:
            mtime = os.path.getmtime(os.path.join(file_path, "SKILL.md"))
        except OSError:
            mtime = 0.0
        self._cache[skill_id] = (content, mtime)

    def invalidate(self, skill_id: str):
        """手动清除指定技能的缓存（用于上传/更新技能后）"""
        self._cache.pop(skill_id, None)

# 全局单例，可在其他模块直接 import
skill_cache = SkillCache()