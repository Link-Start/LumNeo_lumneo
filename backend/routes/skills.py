# backend/routes/skills.py
import os
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List
from config_loader import config  # 引用全局配置
import shutil

router = APIRouter(prefix="/api/skills", tags=["skills"])

@router.post("/upload")
async def upload_skill_folder(files: List[UploadFile] = File(...)):
    """
    接收上传的技能文件夹（前端会保留目录结构）
    保存路径: {data_dir}/skills/{skill_name}/...
    """
    if not files:
        raise HTTPException(status_code=400, detail="没有接收到文件")

    # 获取技能名称（取第一个文件的根目录名）
    # 假设前端传递的 filename 包含相对路径，如 "MySkill/SKILL.md"
    first_file_path = files[0].filename
    if not first_file_path:
        raise HTTPException(status_code=400, detail="无法解析文件路径")

    # 标准化路径分隔符
    first_file_path = first_file_path.replace("\\", "/")
    
    # 提取根目录作为 Skill 名称
    path_parts = first_file_path.split("/")
    skill_name = path_parts[0]

    # 定义保存根目录
    skills_root = os.path.join(config.data_dir, "skills")
    skill_dir = os.path.join(skills_root, skill_name)
    
    # 安全检查：防止路径穿越
    # 确保最终保存的绝对路径在 skills_root 目录内
    abs_skill_dir = os.path.abspath(skill_dir)
    abs_skills_root = os.path.abspath(skills_root)
    
    if not abs_skill_dir.startswith(abs_skills_root):
        raise HTTPException(status_code=400, detail=f"非法的技能名称: {skill_name}")

    # 创建目录
    os.makedirs(abs_skill_dir, exist_ok=True)

    saved_count = 0
    for file in files:
        try:
            # 获取文件的相对路径，构建保存路径
            # file.filename 包含目录结构，如 "MySkill/scripts/run.py"
            relative_path = file.filename.replace("\\", "/")
            
            # 去掉最外层的 Skill 名称，只保留内部结构
            # "MySkill/scripts/run.py" -> "scripts/run.py"
            if relative_path.startswith(skill_name + "/"):
                internal_path = relative_path[len(skill_name) + 1:]
            else:
                # 异常情况：文件不在 Skill 根目录下
                internal_path = relative_path

            if not internal_path:
                continue # 跳过根目录本身

            target_file_path = os.path.join(abs_skill_dir, internal_path)
            target_file_dir = os.path.dirname(target_file_path)

            # 再次安全检查
            if not os.path.abspath(target_file_path).startswith(abs_skill_dir):
                continue

            # 创建子目录
            os.makedirs(target_file_dir, exist_ok=True)

            # 写入文件
            with open(target_file_path, "wb") as buffer:
                # 使用 shutil.copyfileobj 可以更高效地处理大文件
                shutil.copyfileobj(file.file, buffer)
            
            saved_count += 1
            
        except Exception as e:
            print(f"保存文件 {file.filename} 失败: {e}")
        finally:
            await file.close()

    return {
        "success": True, 
        "skill_name": skill_name, 
        "saved_files": saved_count,
        "path": skill_dir
    }

@router.get("/list")
async def list_skills():
    """获取所有已安装的技能列表"""
    skills_root = os.path.join(config.data_dir, "skills")
    if not os.path.exists(skills_root):
        return []
    
    skills = []
    for name in os.listdir(skills_root):
        skill_path = os.path.join(skills_root, name)
        if os.path.isdir(skill_path):
            # 检查是否包含 SKILL.md
            has_skill_md = os.path.exists(os.path.join(skill_path, "SKILL.md"))
            skills.append({
                "name": name,
                "has_skill_md": has_skill_md,
                "path": skill_path
            })
    return skills
