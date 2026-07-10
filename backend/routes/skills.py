import os
import shutil
import uuid
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Optional
from config_loader import config
from backend.db.skills import create_skill, link_skill_to_profile, list_all_skills, get_available_skills_for_profile, batch_set_selected_skills
from backend.utils.skill_parser import parse_skill_markdown
from backend.utils.skill_cache import skill_cache


router = APIRouter(prefix="/api/skills", tags=["skills"])

class BatchSelectRequest(BaseModel):
    profile_id: int
    selected_skill_ids: list[str]

# 1. 获取技能列表接口
@router.get("/list")
async def list_skills(profile_id: Optional[int] = None):
    """
    返回技能列表。
    若提供 profile_id，则返回该角色可见的技能（全局+已关联）；
    否则返回全部技能（兼容旧管理场景）。
    """
    if profile_id is not None:
        records = await get_available_skills_for_profile(profile_id)
    else:
        records = await list_all_skills()

    result_list = []
    for record in records:
        result_list.append({
            "id": record.id,
            "name": record.name,
            "description": record.metadata.get("description", ""),
            "is_global": record.is_global
        })
    return result_list

# 2. 上传技能
@router.post("/upload")
async def upload_skill_folder(
    files: List[UploadFile] = File(...), 
    skillName: str = Form(None),
    is_global: bool = Form(False),  
    profile_id: Optional[int] = Form(None) 
):
    if not files:
        raise HTTPException(status_code=400, detail="没有接收到文件")

    # 1. 获取物理路径 (文件夹名仅用于文件管理)
    first_file_path = files[0].filename
    if not first_file_path:
        raise HTTPException(status_code=400, detail="无法解析文件路径")
    
    first_file_path = first_file_path.replace("\\", "/")
    path_parts = first_file_path.split("/")
    folder_name = path_parts[0] 

    skills_root = config.skill_dir
    skill_path = os.path.join(skills_root, folder_name)
    
    # 安全检查
    abs_skill_dir = os.path.abspath(skill_path)
    abs_skills_root = os.path.abspath(skills_root)
    if not abs_skill_dir.startswith(abs_skills_root):
        raise HTTPException(status_code=400, detail="非法的技能名称")

    os.makedirs(abs_skill_dir, exist_ok=True)

    # 2. 保存文件
    for file in files:
        try:
            relative_path = file.filename.replace("\\", "/")
            if relative_path.startswith(folder_name + "/"):
                internal_path = relative_path[len(folder_name) + 1:]
            else:
                internal_path = relative_path
            
            if not internal_path: continue

            target_file_path = os.path.join(abs_skill_dir, internal_path)
            os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
            with open(target_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            print(f"保存文件失败: {e}")
        finally:
            await file.close()

    # 3. 确定 ID 和显示名称
    skill_id = str(uuid.uuid4())
    
    # 默认名称为文件夹名
    display_name = folder_name
    
    # 优先使用用户输入的名称
    if skillName and skillName.strip():
        display_name = skillName.strip()

    description = ""
    metadata = {}

    skill_md_path = os.path.join(skill_path, "SKILL.md")
    
    # 读取 SKILL.md 补充信息
    if os.path.exists(skill_md_path):
        try:
            with open(skill_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            fm, _ = parse_skill_markdown(content)
            
            if fm:
                # 如果用户没输入，用 SKILL.md 里的 name
                if not (skillName and skillName.strip()):
                    display_name = fm.get("name", display_name)
                
                description = fm.get("description", "")
                # 合并 YAML 头部信息到 metadata
                metadata.update(fm)
        except Exception as e:
            print(f"解析 SKILL.md 失败: {e}")

    # 4. 存入数据库
    try:
        await create_skill(
            skill_id=skill_id,
            name=display_name, 
            file_path=skill_path,
            metadata=metadata,
            is_global=is_global
        )

        if profile_id is not None:
            await link_skill_to_profile(profile_id, skill_id)

        skill_cache.invalidate(skill_id)
            
        return {
            "success": True,
            "id": skill_id,
            "name": display_name,
            "description": description,
            "is_global": is_global
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch-select")
async def batch_select_skills(req: BatchSelectRequest):
    """
    一次性设置某个角色下所有选中技能。
    请求体示例：{ "profile_id": 1, "selected_skill_ids": ["id1", "id2"] }
    """
    await batch_set_selected_skills(req.profile_id, req.selected_skill_ids)
    return {"success": True, "message": "批量更新成功"}