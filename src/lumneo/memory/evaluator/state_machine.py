# src/lumneo/memory/evaluator/state_machine.py
"""
状态流转引擎（Contract §5.1, §6）
整合 Layer-Type 判定、证据去重、置信度计算、冲突检测，
输出最终的 MemoryObject 状态。
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple
from collections import defaultdict

from lumneo.memory.model.memory_candidate import MemoryCandidate
from lumneo.memory.model.memory_object import MemoryObject
from lumneo.memory.model.enums import MemoryOrigin
from lumneo.memory.model.auxiliary import Source

from .layer_type import classify_layer_type
from .dedup import deduplicate_evidence
from .confidence import calculate_confidence

# 活跃阈值（Contract §5.1）
ACTIVE_CONFIDENCE_THRESHOLD = 0.55


def _string_similarity(s1: Optional[str], s2: Optional[str]) -> float:
    """基于字符集合的 Jaccard 相似度，用于 object 比较"""
    s1 = s1 or ""
    s2 = s2 or ""
    if s1 == s2:
        return 1.0
    set1 = set(s1)
    set2 = set(s2)
    if not set1 and not set2:
        return 1.0
    inter = len(set1 & set2)
    union = len(set1 | set2)
    return inter / union if union > 0 else 0.0


class Evaluator:
    def __init__(self, confidence_cap: float = 1.0):
        self.confidence_cap = confidence_cap

    def _build_base_object(self, candidate: MemoryCandidate) -> MemoryObject:
        """
        构建基础 MemoryObject（不处理冲突），仅根据 layer-type 和 confidence 决定状态。
        返回的对象状态可能为 active 或 needs_review。
        """
        # 1. 证据去重
        deduped = deduplicate_evidence(candidate.evidence)

        # 2. 计算置信度
        conf = calculate_confidence(deduped, cap=self.confidence_cap)

        # 3. Layer-Type 判定
        layer = candidate.suggested_layer
        mem_type = candidate.suggested_type
        if layer is None or mem_type is None:
            layer_verdict = "suspicious"
        else:
            layer_verdict = classify_layer_type(layer, mem_type)

        # 4. 状态初步决策
        if layer_verdict == "suspicious":
            status = "needs_review"
            reason = "layer_type_mismatch"
        elif conf >= ACTIVE_CONFIDENCE_THRESHOLD:
            status = "active"
            reason = "confidence_ok"
        else:
            status = "needs_review"
            reason = "low_confidence"

        # 5. 生成唯一 ID
        timestamp_ns = int(datetime.now(timezone.utc).timestamp() * 1e9)
        rand_hex = uuid.uuid4().hex[:12]
        obj_id = f"mem_{timestamp_ns}_{rand_hex}"
        now = datetime.now(timezone.utc)

        # origin 映射
        origin_map = {
            "user": "explicit_user",
            "assistant": "assistant_inferred",
            "system": "system_generated",
            "external": "external_import",
        }
        origin = origin_map.get(candidate.origin_actor, "assistant_inferred")

        # 构建对象
        return MemoryObject(
            id=obj_id,
            schema_version="2.1.2",
            layer=layer if layer else "semantic",
            type=mem_type if mem_type else "fact",
            subject=candidate.subject,
            predicate=candidate.predicate,
            object=candidate.object,
            condition=None,          # Phase 1 暂不处理 condition
            content=candidate.raw_content,
            confidence=conf,
            confidence_detail=None,
            importance=3,            # 默认中等，后续可由 Importance 规则调整
            status=status,
            evidence=deduped,
            source=candidate.source,
            origin=origin,
            supersedes=None,
            superseded_by=None,
            last_accessed=None,
            access_count=0,
            tags=[],
            privacy=None,
            created_at=now,
            updated_at=now,
            metadata={
                "standardization_issue": False,
                "user_forgotten": False,
                "evaluation_reason": reason,
                "layer_type_verdict": layer_verdict,
            }
        )

    def evaluate(self, candidate: MemoryCandidate) -> MemoryObject:
        """单候选评估（无冲突检测）"""
        return self._build_base_object(candidate)

    def evaluate_batch(self, candidates: List[MemoryCandidate]) -> List[MemoryObject]:
        """
        批量评估，包含同 capture_id 内的冲突检测。
        冲突规则（Contract §5.3）：
          - 相同 subject+predicate 且 object 高度相似 → 新记忆 supersede 旧记忆
          - 明显不同 → 独立写入
          - 无法判断 → 新记忆进入 needs_review
        """
        if not candidates:
            return []

        # 第一步：为每个候选生成基础对象（此时状态为 active 或 needs_review，不含冲突处理）
        base_items = [(cand, self._build_base_object(cand)) for cand in candidates]

        # 按 capture_id 分组（通常所有候选来自同一 capture，但防御性处理）
        groups: Dict[str, List[Tuple[MemoryCandidate, MemoryObject]]] = defaultdict(list)
        for cand, obj in base_items:
            groups[cand.capture_id].append((cand, obj))

        # 最终结果容器：id -> MemoryObject，以及保持顺序的 id 列表
        final_map: Dict[str, MemoryObject] = {}
        ordered_ids: List[str] = []

        # 对每个分组进行冲突检测
        for cap_id, items in groups.items():
            # seen: (subject, predicate) -> (candidate, memory_object)
            # 用于检测同一键下的重复
            seen: Dict[Tuple[str, str], Tuple[MemoryCandidate, MemoryObject]] = {}

            for cand, obj in items:
                key = (cand.subject, cand.predicate)

                # 若 subject 或 predicate 缺失，则无法进行冲突检测，直接保留
                if cand.subject is None or cand.predicate is None:
                    final_map[obj.id] = obj
                    ordered_ids.append(obj.id)
                    continue

                if key not in seen:
                    # 首次出现，记录并放入结果
                    seen[key] = (cand, obj)
                    final_map[obj.id] = obj
                    ordered_ids.append(obj.id)
                else:
                    # 检测到冲突
                    prev_cand, prev_obj = seen[key]
                    sim = _string_similarity(prev_cand.object, cand.object)

                    # 检查新记忆是否因 layer-type 问题而无法 active
                    if obj.metadata.get("layer_type_verdict") == "suspicious":
                        # 新记忆本身有问题，不能覆盖旧记忆，保留其原状态（needs_review）
                        final_map[obj.id] = obj
                        ordered_ids.append(obj.id)
                        # 不更新 seen，旧记忆仍作为该键的代表
                    else:
                        if sim >= 0.75:
                            # 高度相似：新记忆取代旧记忆
                            # 旧记忆 -> superseded
                            updated_prev = prev_obj.model_copy(update={
                                "status": "superseded",
                                "superseded_by": obj.id,
                                "updated_at": datetime.now(timezone.utc)
                            })
                            # 新记忆 -> active，并关联旧记忆
                            updated_new = obj.model_copy(update={
                                "status": "active",
                                "supersedes": prev_obj.id,
                                "updated_at": datetime.now(timezone.utc),
                                "metadata": {
                                    **obj.metadata,
                                    "superseded_old_id": prev_obj.id,
                                }
                            })
                            # 更新 final_map
                            final_map[prev_obj.id] = updated_prev
                            final_map[obj.id] = updated_new
                            # 更新 seen 中的对象为新记忆（因为新记忆已成为该键的最新代表）
                            seen[key] = (cand, updated_new)
                            # 追加新 id（旧 id 已经在列表中）
                            ordered_ids.append(obj.id)

                        elif sim <= 0.40:
                            # 明显不同：独立写入，不覆盖
                            final_map[obj.id] = obj
                            ordered_ids.append(obj.id)
                            # 不更新 seen，旧记忆仍为键代表
                        else:
                            # 无法安全判断：新记忆进入 needs_review
                            updated_new = obj.model_copy(update={
                                "status": "needs_review",
                                "updated_at": datetime.now(timezone.utc),
                                "metadata": {
                                    **obj.metadata,
                                    "conflict_unclear": True,
                                    "conflict_with": prev_obj.id,
                                }
                            })
                            final_map[obj.id] = updated_new
                            ordered_ids.append(obj.id)
                            # 不更新 seen

        # 按原始顺序返回
        return [final_map[oid] for oid in ordered_ids if oid in final_map]


# 模块级便捷函数
def evaluate(candidate: MemoryCandidate, confidence_cap: float = 1.0) -> MemoryObject:
    return Evaluator(confidence_cap).evaluate(candidate)


def evaluate_batch(candidates: List[MemoryCandidate], confidence_cap: float = 1.0) -> List[MemoryObject]:
    return Evaluator(confidence_cap).evaluate_batch(candidates)