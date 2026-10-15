# -*- coding: utf-8 -*-
"""
scripts/build_agent_capsules.py
【立体空间智能体系统 · 数字化员工智能体卡带 (.agent) 自动化打包生成器】

功能：
1. 扫描 agents/ 目录下的各垂直领域智能体；
2. 剥离 __pycache__、.pyc、开发缓存；
3. 打包生成独立的标准化智能体卡带 (release/capsules/{agent_id}_v{version}.agent)；
4. 计算 SHA-256 完整性散列校验值；
5. 生成官方智能体招募市场清单 (release/capsules/agent_catalog.json & configs/agent_catalog.json)；
6. 供客户端按需鉴权招募入职。
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
AGENTS_DIR = ROOT_DIR / "agents"
OUTPUT_CAPSULES_DIR = ROOT_DIR / "release" / "capsules"

AGENT_PERMISSIONS = {
    "omni_sentinel": {
        "required_role": "guest",
        "role_name": "系统官方内置",
        "badge_color": "emerald"
    }
}

DELISTED_AGENTS = set()

EXCLUDE_PATTERNS = ["__pycache__", ".pyc", ".DS_Store", ".pytest_cache", ".git"]


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def find_all_agents() -> List[Dict[str, Any]]:
    """扫描 agents/ 目录中的合法智能体（跳过已下架待打磨的测试智能体）"""
    agents = []
    if not AGENTS_DIR.exists():
        return agents

    for item in AGENTS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith((".", "_")):
            if item.name in DELISTED_AGENTS:
                continue
            entry_py = item / "entry.py"
            if entry_py.exists():
                agents.append({
                    "id": item.name,
                    "dir": item
                })
    return agents


def package_single_agent(agent_info: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """将单个智能体打包为 .agent 格式的轻量独立卡带"""
    agent_id = agent_info["id"]
    agent_dir: Path = agent_info["dir"]
    perm_config = AGENT_PERMISSIONS.get(agent_id, {
        "required_role": "annual",
        "role_name": "年度会员专享",
        "badge_color": "amber"
    })

    version = "1.0.0"
    display_name = agent_id
    icon = "🤖"
    category = "通用业务"
    description = f"立体空间专属智能体: {agent_id}"
    skills = []

    config_yaml = agent_dir / "config.yaml"
    if config_yaml.exists():
        try:
            import yaml
            with open(config_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                version = data.get("version", version)
                display_name = data.get("display_name", display_name)
                icon = data.get("icon", icon)
                category = data.get("category", category)
                description = data.get("description", description)
                skills = data.get("skills", [])
        except Exception:
            pass

    capsule_name = f"{agent_id}_v{version}.agent"
    capsule_path = output_dir / capsule_name

    with zipfile.ZipFile(capsule_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(agent_dir):
            dirs[:] = [d for d in dirs if not any(exc in d for exc in EXCLUDE_PATTERNS)]
            for file in files:
                if any(exc in file for exc in EXCLUDE_PATTERNS) or file.endswith(".pyc"):
                    continue
                file_full = Path(root) / file
                rel = file_full.relative_to(agent_dir)
                zf.write(file_full, arcname=str(rel).replace("\\", "/"))

    size_bytes = capsule_path.stat().st_size
    size_kb = max(1, round(size_bytes / 1024))
    sha256_hash = compute_sha256(capsule_path)

    return {
        "id": agent_id,
        "name": display_name,
        "display_name": display_name,
        "version": version,
        "author": "阿朝编程 / 立体空间官方",
        "category": category,
        "icon": icon,
        "description": description,
        "skills": skills,
        "size": f"{size_kb} KB",
        "size_kb": size_kb,
        "sha256": sha256_hash,
        "required_role": perm_config["required_role"],
        "role_name": perm_config["role_name"],
        "badge_color": perm_config["badge_color"],
        "capsule_filename": capsule_name,
        "download_url": f"https://cdn.litikj.com/capsules/{capsule_name}"
    }


def main():
    print("=" * 65)
    print("💼 【立体空间智能体系统】智能体卡带 (.agent) 与招募市场生成器")
    print("=" * 65)

    OUTPUT_CAPSULES_DIR.mkdir(parents=True, exist_ok=True)

    # 自动清理已下架智能体的本地历史卡带缓存，确保发行物纯净
    for delisted_id in DELISTED_AGENTS:
        for old_file in OUTPUT_CAPSULES_DIR.glob(f"{delisted_id}*.agent"):
            try:
                old_file.unlink()
                print(f"  🗑️ 已清理下架智能体卡带缓存: {old_file.name}")
            except Exception as e:
                print(f"  ⚠️ 清理下架卡带失败 {old_file.name}: {e}")

    agents = find_all_agents()

    print(f"🔍 检索到本地真实智能体: {len(agents)} 个")
    catalog_items = []

    for ag in agents:
        meta = package_single_agent(ag, OUTPUT_CAPSULES_DIR)
        catalog_items.append(meta)
        print(f"  • [{meta['id']}] -> {meta['capsule_filename']} ({meta['size']}, 权限: {meta['role_name']})")

    # 导出智能体招募市场清单
    catalog_path = OUTPUT_CAPSULES_DIR / "agent_catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog_items, f, ensure_ascii=False, indent=2)

    builtin_catalog = ROOT_DIR / "configs" / "agent_catalog.json"
    with open(builtin_catalog, "w", encoding="utf-8") as f:
        json.dump(catalog_items, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 65)
    print(f"🎉 成功打包 {len(catalog_items)} 个独立智能体卡带！")
    print(f"📁 产物目录: release/capsules/")
    print(f"📋 招募清单: {catalog_path.relative_to(ROOT_DIR)} & configs/agent_catalog.json")
    print("=" * 65)


if __name__ == "__main__":
    main()
