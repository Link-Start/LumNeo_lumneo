# backend/utils/skill_parser.py
import re
import yaml
from typing import Dict, Tuple

def parse_skill_markdown(content: str) -> Tuple[Dict, str]:
    """
    解析 SKILL.md 文件内容
    返回: (frontmatter_dict, markdown_body)
    """
    # 匹配 --- 包裹的头部
    match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    
    frontmatter = {}
    body = content

    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1))
            if not isinstance(frontmatter, dict):
                frontmatter = {}
        except yaml.YAMLError:
            pass # YAML 解析失败，忽略头部
        
        # 截取正文部分
        body = match.group(2).strip()
    
    return frontmatter, body
