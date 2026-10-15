# -*- coding: utf-8 -*-
"""
scripts/build_skill_capsules.py
【立体空间智能体系统 · 技能卡带自动化打包与市场清单生成器】

功能：
1. 扫描 skills/official 与 skills/custom 下的真实技能；
2. 严格剥离 __pycache__、.pyc、测试临时文件；
3. 打包生成独立的标准化技能卡带 (release/capsules/{skill_id}_v{version}.skill)；
4. 自动计算 SHA-256 完整性校验和与文件体积；
5. 生成官方技能市场清单 (release/capsules/market_catalog.json)，包含商业权限分级配置；
6. 供云端中枢部署或本地鉴权按需分发。

使用方法：
  python scripts/build_skill_capsules.py
"""

import os
import sys
import json
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
SKILLS_DIR = ROOT_DIR / "skills"
OUTPUT_CAPSULES_DIR = ROOT_DIR / "release" / "capsules"

# 技能商业权限定义（当前体系：未激活访客 / 年度会员）
SKILL_PERMISSIONS = {
    "hello_skill": {
        "required_role": "free",
        "role_name": "开源社区免费",
        "badge_color": "emerald",
        "category": "开发示范",
        "icon": "👋",
        "description": "开源微内核标准示范技能：演示参数传递、结构化输出与产物落盘"
    }
}

EXCLUDE_PATTERNS = ["__pycache__", ".pyc", ".DS_Store", ".pytest_cache", ".git"]


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def find_all_skills() -> List[Dict[str, Any]]:
    """扫描 skills/ 目录寻找合法技能包"""
    skills = []
    scan_roots = [
        ("official", SKILLS_DIR / "official"),
        ("custom", SKILLS_DIR / "custom")
    ]

    for origin, s_root in scan_roots:
        if not s_root.exists():
            continue
        for item in s_root.iterdir():
            if item.is_dir() and not item.name.startswith((".", "_")):
                entry_py = item / "entry.py"
                manifest_file = item / "manifest.yaml"
                if entry_py.exists():
                    skills.append({
                        "id": item.name,
                        "origin": origin,
                        "dir": item,
                        "has_manifest": manifest_file.exists()
                    })
    return skills


def package_single_skill(skill_info: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """将单个技能打包为 .skill 格式的轻量标准卡带"""
    skill_id = skill_info["id"]
    skill_dir: Path = skill_info["dir"]
    perm_config = SKILL_PERMISSIONS.get(skill_id, {
        "required_role": "free",
        "role_name": "免费公开",
        "badge_color": "emerald",
        "category": "通用工具",
        "icon": "🧩",
        "description": f"立体空间通用原子技能: {skill_id}"
    })

    version = "1.0.0"
    manifest_yaml = skill_dir / "manifest.yaml"
    display_name = skill_id

    # 尝试从 manifest.yaml 解析详细信息
    if manifest_yaml.exists():
        try:
            import yaml
            with open(manifest_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                version = data.get("version", version)
                display_name = data.get("display_name", data.get("name", display_name))
        except Exception:
            pass

    capsule_name = f"{skill_id}_v{version}.skill"
    capsule_path = output_dir / capsule_name

    # 打包 zip 文件 (扩展名为 .skill)
    with zipfile.ZipFile(capsule_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(skill_dir):
            dirs[:] = [d for d in dirs if not any(exc in d for exc in EXCLUDE_PATTERNS)]
            for file in files:
                if any(exc in file for exc in EXCLUDE_PATTERNS) or file.endswith(".pyc"):
                    continue
                file_full = Path(root) / file
                rel_to_skill = file_full.relative_to(skill_dir)
                zf.write(file_full, arcname=str(rel_to_skill).replace("\\", "/"))

    size_bytes = capsule_path.stat().st_size
    size_kb = max(1, round(size_bytes / 1024))
    sha256_hash = compute_sha256(capsule_path)

    return {
        "id": skill_id,
        "name": display_name,
        "display_name": display_name,
        "version": version,
        "author": "阿朝编程 / 立体空间官方",
        "category": perm_config["category"],
        "icon": perm_config["icon"],
        "description": perm_config["description"],
        "size": f"{size_kb} KB",
        "size_kb": size_kb,
        "sha256": sha256_hash,
        "required_role": perm_config["required_role"],
        "role_name": perm_config["role_name"],
        "badge_color": perm_config["badge_color"],
        "capsule_filename": capsule_name,
        "download_url": f"https://cdn.litikj.com/capsules/{capsule_name}",
        "origin": skill_info["origin"]
    }


def main():
    print("=" * 65)
    print("📦 【立体空间智能体系统】技能卡带与官方市场目录打包生成器")
    print("=" * 65)

    OUTPUT_CAPSULES_DIR.mkdir(parents=True, exist_ok=True)
    skills = find_all_skills()

    print(f"🔍 检索到本地真实业务技能: {len(skills)} 个")
    catalog_items = []

    for s in skills:
        meta = package_single_skill(s, OUTPUT_CAPSULES_DIR)
        catalog_items.append(meta)
        print(f"  • [{meta['id']}] -> {meta['capsule_filename']} ({meta['size']}, 权限: {meta['role_name']})")

    # 导出完整的官方市场 Manifest 目录
    catalog_path = OUTPUT_CAPSULES_DIR / "market_catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog_items, f, ensure_ascii=False, indent=2)

    # 同时复制一份到 configs/ 作为本地内置离线市场源
    builtin_catalog = ROOT_DIR / "configs" / "market_catalog.json"
    with open(builtin_catalog, "w", encoding="utf-8") as f:
        json.dump(catalog_items, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 65)
    print(f"🎉 成功打包 {len(catalog_items)} 个独立技能卡带！")
    print(f"📁 产物目录: release/capsules/")
    print(f"📋 市场清单: {catalog_path.relative_to(ROOT_DIR)} & configs/market_catalog.json")
    print("=" * 65)


if __name__ == "__main__":
    main()
