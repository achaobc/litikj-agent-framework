# -*- coding: utf-8 -*-
"""
scripts/build_workflow_capsules.py
【立体空间智能体系统 · 多智能体协同工作流卡带 (.flow) 与市场名录生成器】

职责：
1. 扫描 workflows/ 目录下的多智能体接力协同工作流；
2. 自动剥离缓存并打包为标准化 .flow 独立卡带 (Zip 压缩)；
3. 计算 SHA-256 完整性散列并生成 release/capsules/workflow_catalog.json；
4. 同步至 configs/workflow_catalog.json 作为离线/预置官方云端市场名录。
"""

import io
import os
import sys
import json
import shutil
import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Any, List

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT_DIR / "workflows"
RELEASE_CAPSULES_DIR = ROOT_DIR / "release" / "capsules"
CONFIGS_DIR = ROOT_DIR / "configs"

EXCLUDE_PATTERNS = [
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".pyc",
    ".DS_Store"
]


def should_exclude(p: Path) -> bool:
    for part in p.parts:
        if any(exc in part for exc in EXCLUDE_PATTERNS):
            return True
    if p.suffix == ".pyc":
        return True
    return False


def build_workflow_capsule(flow_dir_or_file: Path) -> Dict[str, Any]:
    """将单个工作流目录或单文件脚本打包为 .flow 卡带"""
    meta: Dict[str, Any] = {}
    is_dir = flow_dir_or_file.is_dir()
    flow_id = flow_dir_or_file.name if is_dir else flow_dir_or_file.stem

    if is_dir:
        cfg_path = flow_dir_or_file / "config.yaml"
        if cfg_path.exists():
            try:
                import yaml
                with open(cfg_path, "r", encoding="utf-8") as f:
                    meta = yaml.safe_load(f) or {}
            except Exception:
                pass
    else:
        # 单脚本工作流，提取默认属性
        if flow_id == "system_health_audit":
            meta = {
                "id": "system_health_audit",
                "name": "系统全维健康审计流水线",
                "display_name": "系统全维健康审计流水线",
                "version": "1.0.0",
                "author": "阿朝编程 / 立体空间官方",
                "category": "系统基准",
                "icon": "🛡️",
                "description": "立体空间标杆基准协同流水线：全维哨兵硬件巡检 ➔ 人机审批把关 ➔ 持久化审计归档",
                "required_role": "guest",
                "role_name": "系统官方内置",
                "badge_color": "emerald",
                "dependencies": {
                    "agents": ["omni_sentinel"],
                    "skills": []
                }
            }

    name = meta.get("name") or meta.get("display_name") or flow_id
    version = meta.get("version", "1.0.0")
    required_role = meta.get("required_role", "annual")
    role_name = meta.get("role_name", "年度会员专享" if required_role == "annual" else "免费公开")
    badge_color = meta.get("badge_color", "amber" if required_role == "annual" else "emerald")
    icon = meta.get("icon", "🔄")
    category = meta.get("category", "多智能体协同")
    description = meta.get("description", "官方认证多智能体接力协同工作流")
    author = meta.get("author", "阿朝编程 / 立体空间官方")
    dependencies = meta.get("dependencies", {"agents": [], "skills": []})

    capsule_name = f"{flow_id}_v{version}.flow"
    capsule_path = RELEASE_CAPSULES_DIR / capsule_name

    # 打包写入内存并计算 SHA-256
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        if is_dir:
            for root, dirs, files in os.walk(flow_dir_or_file):
                dirs[:] = [d for d in dirs if not any(exc in d for exc in EXCLUDE_PATTERNS)]
                for file in files:
                    file_path = Path(root) / file
                    if should_exclude(file_path):
                        continue
                    arcname = file_path.relative_to(flow_dir_or_file)
                    zf.write(file_path, arcname)
        else:
            # 单文件打包：写入 flow_id/entry.py 和 flow_id/config.yaml
            zf.write(flow_dir_or_file, "entry.py")
            # 补全 config.yaml
            import yaml
            cfg_bytes = yaml.dump(meta, allow_unicode=True, sort_keys=False).encode("utf-8")
            zf.writestr("config.yaml", cfg_bytes)

    capsule_bytes = bio.getvalue()
    sha256_hash = hashlib.sha256(capsule_bytes).hexdigest()
    size_kb = max(1, round(len(capsule_bytes) / 1024))

    with open(capsule_path, "wb") as f:
        f.write(capsule_bytes)

    catalog_item = {
        "id": flow_id,
        "name": name,
        "display_name": name,
        "version": version,
        "author": author,
        "category": category,
        "icon": icon,
        "description": description,
        "dependencies": dependencies,
        "size": f"{size_kb} KB",
        "size_kb": size_kb,
        "sha256": sha256_hash,
        "required_role": required_role,
        "role_name": role_name,
        "badge_color": badge_color,
        "capsule_filename": capsule_name,
        "download_url": f"https://cdn.litikj.com/capsules/{capsule_name}"
    }

    print(f"  • [{flow_id}] -> {capsule_name} ({catalog_item['size']}, 权限: {role_name})")
    return catalog_item


def build_all_workflow_capsules():
    print("\n" + "=" * 65)
    print("🔄 【立体空间智能体系统】工作流卡带 (.flow) 与市场名录生成器")
    print("=" * 65)

    RELEASE_CAPSULES_DIR.mkdir(parents=True, exist_ok=True)
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)

    catalog = []

    # 1. 扫描子目录工作流
    for p in WORKFLOWS_DIR.iterdir():
        if p.name.startswith((".", "_")):
            continue
        if p.is_dir():
            if (p / "entry.py").exists() or (p / "workflow.py").exists() or (p / "config.yaml").exists():
                catalog.append(build_workflow_capsule(p))
        elif p.is_file() and p.suffix == ".py":
            catalog.append(build_workflow_capsule(p))

    # 按 id 排序
    catalog.sort(key=lambda x: x["id"])

    # 2. 保存清单
    catalog_path_release = RELEASE_CAPSULES_DIR / "workflow_catalog.json"
    catalog_path_configs = CONFIGS_DIR / "workflow_catalog.json"

    with open(catalog_path_release, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    with open(catalog_path_configs, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 65)
    print(f"🎉 成功打包 {len(catalog)} 个独立工作流卡带！")
    print(f"📁 产物目录: release/capsules/")
    print(f"📋 招募清单: {catalog_path_release.relative_to(ROOT_DIR)} & configs/workflow_catalog.json")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    build_all_workflow_capsules()
