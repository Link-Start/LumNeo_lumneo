# runtime/context/collaboration.py
# 模型协作调度策略（原 backend/utils/collaboration_strategy.py）。
#
# 根据消息特征 / 配置条件选择主/副模型。纯逻辑，不依赖数据库或 I/O。
import re
import random
from typing import Dict, List, Optional

from lumneo.kernel.common.util import get_typeName


def estimate_complexity(message: str) -> float:
    """估算消息复杂度 0.0-1.0"""
    score = 0.0
    length = len(message)

    if length > 2000:
        score += 0.4
    elif length > 1000:
        score += 0.25
    elif length > 500:
        score += 0.1

    code_patterns = [
        r'```[\w\s\S]*?```',
        r'def\s+\w+\s*\(',
        r'class\s+\w+',
        r'function\s+\w+',
        r'import\s+\w+',
        r'#include',
        r'<[^>]+>.*?</[^>]+>',
    ]
    for pattern in code_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            score += 0.15
            break

    complex_keywords = ['分析', '对比', '评估', '优化', '架构', '设计', '推理', '证明', '推导']
    for kw in complex_keywords:
        if kw in message:
            score += 0.08
            break

    step_patterns = [r'第[一二三四五六七八九十\d]+步', r'首先.*然后.*最后', r'步骤[\d一二三四五六七八九十]']
    for pattern in step_patterns:
        if re.search(pattern, message):
            score += 0.1
            break

    return min(score, 1.0)


def check_keyword_triggers(message: str, triggers: List[Dict[str, str]]) -> Optional[str]:
    message_lower = message.lower()
    for rule in triggers:
        keyword = rule.get("keyword", "")
        target = rule.get("target", "")
        if keyword and keyword.lower() in message_lower:
            return target
    return None


tool_indicators = ['查询', '查一下', '搜索', '读取', '写入', '文件', '天气', '执行']
negation_words = [
    '不要', '别', '不需要', '不用', '无需', '不必', '禁止', '拒绝',
    '没必要', '用不着', '别帮我', '不用查', '不用读', '不用写',
    '不想', '不愿', '不会', '不能', '无法', '没让', '没要求',
    '取消', '撤销', '停止', '终止', '关闭', '禁用', '关掉',
]


def needs_tool(message: str, window: int = 8) -> bool:
    """判断消息是否需要调用工具（含否定词过滤）。"""
    msg = message.lower()
    for indicator in tool_indicators:
        indicator_lower = indicator.lower()
        idx = msg.find(indicator_lower)
        if idx == -1:
            continue
        start = max(0, idx - window)
        prefix = msg[start:idx]
        has_negation = any(neg in prefix for neg in negation_words)
        if not has_negation:
            return True
    return False


def estimate_tool_need(message: str) -> bool:
    """判断消息是否真正需要工具（含否定词过滤）。"""
    return needs_tool(message, window=8)


async def select_model_by_strategy(
    collab_config,
    message: str,
    enable_tools: bool,
    model_map: Dict[str, Dict]
) -> tuple:
    """根据协作策略选择模型，返回 (selected_model_id, reason)。"""
    strategy = collab_config.strategy
    primary_id = collab_config.primary_model_id
    secondary_id = collab_config.secondary_model_id
    conditions = collab_config.conditions or {}

    primary_model = model_map.get(primary_id, {})
    secondary_model = model_map.get(secondary_id, {}) if secondary_id else {}
    primary_type = primary_model.get("type", "primary")
    secondary_type = secondary_model.get("type", "secondary") if secondary_model else "secondary"

    if strategy == "primary":
        return primary_id, f"策略[固定主模型]: 始终使用 「 {primary_model.get('name', '主模型')} · {get_typeName(primary_model.get('type', 'local'))} 」"

    if strategy == "secondary":
        if secondary_id and secondary_model:
            return secondary_id, f"策略[固定副模型]: 始终使用 {secondary_model.get('name', '副模型')} · {get_typeName(secondary_model.get('type', 'local'))} 」"
        return primary_id, "副模型未配置，回退到主模型"

    if strategy == "hybrid":
        roll = random.randint(1, 100)
        ratio = getattr(collab_config, 'primary_ratio', 70)
        if roll <= ratio:
            return primary_id, f"策略[混合模式]: 随机占比 {roll}/100 ≤ {ratio}%，选择主模型 「 {primary_model.get('name', '主模型')} · {get_typeName(primary_model.get('type', 'local'))} 」"
        else:
            selected = secondary_id if secondary_id else primary_id
            return selected, f"策略[混合模式]: 随机占比 {roll}/100 > {ratio}%，选择副模型 「 {secondary_model.get('name', '副模型')} · {get_typeName(secondary_model.get('type', 'local'))} 」"

    # 自动模式
    reasons = []

    if conditions.get("enable_keyword_detect", True):
        triggers = conditions.get("keyword_triggers", [])
        keyword_target = check_keyword_triggers(message, triggers)
        if keyword_target == "primary":
            return primary_id, f"策略[自动-关键词触发]: 命中主模型规则，选择 「 {primary_model.get('name', '主模型')} · {get_typeName(primary_model.get('type', 'local'))} 」"
        elif keyword_target == "secondary" and secondary_id:
            return secondary_id, f"策略[自动-关键词触发]: 命中副模型规则，选择 「 {secondary_model.get('name', '副模型')} · {get_typeName(secondary_model.get('type', 'local'))} 」"

    if conditions.get("enable_complexity_detect", True):
        complexity = estimate_complexity(message)
        threshold = conditions.get("complexity_threshold", 0.6)
        if complexity >= threshold:
            secondary_id = secondary_id if secondary_type == "secondary" else (primary_id if primary_type == "secondary" else None)
            if secondary_id:
                secondary_model = model_map.get(secondary_id, {})
                reasons.append(f"复杂度{complexity:.2f}≥阈值{threshold}，倾向副模型 「 {secondary_model.get('name', '')} · {get_typeName(secondary_model.get('type', 'local'))} 」")
                return secondary_id, f"策略[自动-复杂度检测]: {'; '.join(reasons)}"
        else:
            reasons.append(f"复杂度{complexity:.2f}<阈值{threshold}")

    if conditions.get("enable_length_detect", True):
        length_threshold = conditions.get("message_length_threshold", 500)
        if len(message) > length_threshold:
            secondary_id = secondary_id if secondary_type == "secondary" else (primary_id if primary_type == "secondary" else None)
            if secondary_id:
                secondary_model = model_map.get(secondary_id, {})
                return secondary_id, f"策略[自动-长度检测]: 消息长度{len(message)}>{length_threshold}，使用副模型 「 {secondary_model.get('name', '')} · {get_typeName(secondary_model.get('type', 'local'))} 」"

    if enable_tools and estimate_tool_need(message) and conditions.get("tool_heavy_priority", "secondary") == "secondary":
        secondary_id = secondary_id if secondary_type == "secondary" else (primary_id if primary_type == "secondary" else None)
        if secondary_id:
            secondary_model = model_map.get(secondary_id, {})
            return secondary_id, f"策略[自动-工具优先]: 消息涉及工具操作，优先使用副模型 {secondary_model.get('name', '')} · {get_typeName(secondary_model.get('type', 'local'))}"

    return primary_id, f"策略[自动-默认回退]: {'; '.join(reasons) if reasons else '无特殊触发条件'}，使用主模型 「 {primary_model.get('name', '')} · {get_typeName(primary_model.get('type', 'local'))} 」"
