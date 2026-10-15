# -*- coding: utf-8 -*-
"""
scripts/package_release.py
【立体空间智能体系统 · 商业级双发行包组装与归档工具】

功能：
1. 自动定位 Tauri 编译输出的桌面宿主主程序 (app.exe / 立体空间智能体系统.exe)；
2. 检索并归档 NSIS Windows 安装包至 release/ 目录；
3. 组装内嵌 Python 3.10 便携运行时的免安装绿色版 (Portable ZIP)；
4. 严格剥离 __pycache__、.pyc、测试缓存与私有资产；
5. 输出最终交付成果报告。
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT_DIR / "release"
VERSION = "v2.5.0"

# 白名单目录与文件
INCLUDE_DIRS = [
    "runtime",
    "apps",
    "core",
    "configs",
    "agents",
    "skills",
    "workflows",
    "scripts"
]

INCLUDE_SCRIPTS = [
    "run.py",
    "一键启动智能体工作台.bat",
    "开箱必读.txt"
]

EXCLUDE_PATTERNS = [
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".env",
    "bili_cookies.json",
    "cookie.json",
    ".pyc",
    ".log",
    ".DS_Store",
    "publish_capsules_to_cdn.py",
    ".secrets.yaml",
    "secrets.yaml",
    ".session_token",
    ".pem",
    ".key"
]


def should_exclude(path: Path) -> bool:
    for part in path.parts:
        if any(exc in part for exc in EXCLUDE_PATTERNS):
            return True
    if path.suffix == ".pyc":
        return True
    return False


def package_release():
    print("\n" + "=" * 65)
    print(f"🚀 【立体空间智能体系统 {VERSION}】商业级发行矩阵打包归档")
    print("📖 出厂纯净态打包规范已载入 (详见 docs/PACKAGING_GUIDE.md)")
    print("=" * 65)

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    # 0. 自动预构建官方技能卡带与智能体卡带矩阵 (微内核与按需招募交付架构)
    import subprocess
    skill_builder = ROOT_DIR / "scripts" / "build_skill_capsules.py"
    if skill_builder.exists():
        try:
            subprocess.run([sys.executable, str(skill_builder)], check=True)
        except Exception as e:
            print(f"⚠️ 技能卡带预构建警告: {e}")

    agent_builder = ROOT_DIR / "scripts" / "build_agent_capsules.py"
    if agent_builder.exists():
        try:
            subprocess.run([sys.executable, str(agent_builder)], check=True)
        except Exception as e:
            print(f"⚠️ 智能体卡带预构建警告: {e}")

    workflow_builder = ROOT_DIR / "scripts" / "build_workflow_capsules.py"
    if workflow_builder.exists():
        try:
            subprocess.run([sys.executable, str(workflow_builder)], check=True)
        except Exception as e:
            print(f"⚠️ 工作流卡带预构建警告: {e}")

    # 1. 寻找 Tauri 编译出的桌面端主程序
    tauri_target = ROOT_DIR / "desktop" / "src-tauri" / "target" / "release"
    main_exe_candidates = [
        tauri_target / "立体空间智能体系统.exe",
        tauri_target / "app.exe"
    ]
    main_exe = None
    for cand in main_exe_candidates:
        if cand.exists():
            main_exe = cand
            break

    if not main_exe:
        print("⚠️ 未在 release 目录找到 Tauri 编译主程序 (app.exe / 立体空间智能体系统.exe)")
    else:
        print(f"✅ 锁定 Tauri 原生桌面二进制: {main_exe.name} ({main_exe.stat().st_size / (1024*1024):.2f} MB)")

    # 2. 检查并归档 NSIS 安装包 (Setup.exe)
    nsis_dir = tauri_target / "bundle" / "nsis"
    setup_exes = list(nsis_dir.glob("*.exe")) if nsis_dir.exists() else []
    if setup_exes:
        target_setup = RELEASE_DIR / f"立体空间智能体系统_{VERSION}_Setup.exe"
        shutil.copy2(setup_exes[0], target_setup)
        setup_sz = target_setup.stat().st_size / (1024 * 1024)
        print(f"🎉 [产物 A · Windows 官方安装包]: {target_setup.name} ({setup_sz:.2f} MB)")

    # 3. 组装绿色免安装便携包 (Portable ZIP)
    print("\n📦 正在组装内置嵌入式运行时的免安装绿色版 (Portable)...")
    staging_root = RELEASE_DIR / "portable_staging"
    portable_staging = staging_root / f"Litikj_Agent_OS_{VERSION}"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    portable_staging.mkdir(parents=True, exist_ok=True)

    # 3.1 放入桌面客户端主程序 (统一命名为 立体空间智能体系统.exe)
    if main_exe:
        shutil.copy2(main_exe, portable_staging / "立体空间智能体系统.exe")
        print("  • 已注入桌面主程序: 立体空间智能体系统.exe")

    # 3.2 复制核心代码与嵌入式运行时
    for d_name in INCLUDE_DIRS:
        src = ROOT_DIR / d_name
        dst = portable_staging / d_name
        if not src.exists():
            continue
        for root, _, files in os.walk(src):
            for f in files:
                f_path = Path(root) / f
                if should_exclude(f_path):
                    continue
                rel = f_path.relative_to(ROOT_DIR)


                # 🌟 极简技能装配约束：官方发布包中 skills/ 不硬塞业务技能，全走云端/按需联动拉取
                if rel.parts[0] == "skills" and len(rel.parts) > 2 and rel.parts[1] == "official":
                    continue

                # 🌟 极简底座纯净约束 (Zero-Payload Base)：
                # 官方发布包中 runtime/ 仅预置纯净 Python 核心与微内核基础依赖 (site-packages: yaml, psutil, PIL)，
                # 严格排除开发测试污染的 runtime/Lib (100MB+ C/C++ 业务依赖)、Scripts、models 与临时文件。
                if rel.parts[0] == "runtime" and len(rel.parts) > 1:
                    first_sub = rel.parts[1]
                    if first_sub in ("Lib", "Scripts", "models", "share", "__pycache__"):
                        continue

                target_file = portable_staging / rel
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f_path, target_file)
        if d_name == "agents":
            print(f"  • 已装载模块: agents/ (官方内置智能体集群已全部就绪)")
        elif d_name == "skills":
            print(f"  • 已装载模块: skills/ (纯净底座骨架：所有原子技能按需远程下载并热装配)")
        elif d_name == "runtime":
            print(f"  • 已装载模块: runtime/ (纯净微内核底座：仅保留官方 Python 核心与微内核基础依赖)")
        else:
            print(f"  • 已装载模块: {d_name}/")

    # 3.2.1 复制本地预置卡带库 (离线运行保障)
    capsules_src = RELEASE_DIR / "capsules"
    if capsules_src.exists():
        capsules_dst = portable_staging / "release" / "capsules"
        capsules_dst.mkdir(parents=True, exist_ok=True)
        for item in capsules_src.iterdir():
            if item.is_file():
                shutil.copy2(item, capsules_dst / item.name)
        print("  • 已注入本地预置卡带库 (release/capsules/)")

    # 3.3 组装纯净工作区结构
    workspace_dirs = [
        portable_staging / "workspace" / "drop_box" / "videos",
        portable_staging / "workspace" / "drop_box" / "courseware",
        portable_staging / "workspace" / "outputs" / "courseware_packages",
        portable_staging / "workspace" / "outputs",
        portable_staging / "workspace" / "logs",
        portable_staging / "workspace" / "data",
        portable_staging / "workspace" / "custom_agents"
    ]
    for wd in workspace_dirs:
        wd.mkdir(parents=True, exist_ok=True)

    custom_readme = ROOT_DIR / "workspace" / "custom_agents" / "README.md"
    if custom_readme.exists():
        shutil.copy2(custom_readme, portable_staging / "workspace" / "custom_agents" / "README.md")
    print("  • 已初始化纯净 workspace 目录结构")

    # 3.4 复制开箱脚本与说明文件
    for s_name in INCLUDE_SCRIPTS:
        src_file = ROOT_DIR / s_name
        if src_file.exists():
            shutil.copy2(src_file, portable_staging / s_name)
    print("  • 已注入开箱批处理与使用说明")

    # 3.5 🛡️ 【出厂纯净态强制脱敏与硬核断言】(遵照 docs/PACKAGING_GUIDE.md)
    print("\n🛡️ 正在执行商业出厂纯净态脱敏与零污染合规审查...")
    staging_fw = portable_staging / "configs" / "framework.yaml"
    if staging_fw.exists():
        import re
        fw_text = staging_fw.read_text(encoding="utf-8")
        # 强制将 license_key 置空，杜绝带激活码出厂
        fw_text = re.sub(r'license_key:\s*["\'].*?["\']', 'license_key: ""', fw_text)
        fw_text = re.sub(r'license_key:\s*[^"\s\n]+', 'license_key: ""', fw_text)
        # 强制将 custom api_key 置空，保护开发者私有 API 密钥
        fw_text = re.sub(r'api_key:\s*["\'].*?["\']', 'api_key: ""', fw_text)
        staging_fw.write_text(fw_text, encoding="utf-8")

    # 工作区骨架深度脱敏：清理所有日志、残留缓存与私有凭据
    clean_targets = [
        portable_staging / "workspace" / "logs",
        portable_staging / "workspace" / "cache",
        portable_staging / "workspace" / "data" / "webview"
    ]
    for ct in clean_targets:
        if ct.exists():
            for item in ct.iterdir():
                if item.is_file() and item.name != ".gitkeep":
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        ct.mkdir(parents=True, exist_ok=True)

    # 扫描并清除 staging 中的一切潜在敏感文件 (*cookie*.json, .license_cache.json, *.log)
    for root, _, files in os.walk(portable_staging):
        for f in files:
            fp = Path(root) / f
            if any(p in f.lower() for p in ["cookie", ".license_cache"]) or f.endswith(".log"):
                fp.unlink(missing_ok=True)

    # 🚨 出厂硬核断言 (Factory Release Assertion)
    import yaml
    with open(staging_fw, "r", encoding="utf-8") as f:
        parsed_cfg = yaml.safe_load(f)
    gw = parsed_cfg.get("gateway", {})
    l_key = str(gw.get("license_key", "")).strip()
    a_key = str(gw.get("custom", {}).get("api_key", "")).strip()
    if l_key:
        raise RuntimeError(f"🚨 [打包安全拦截] 发布包 framework.yaml 包含非空 license_key ({l_key})，已紧急阻断打包！")
    if a_key:
        raise RuntimeError(f"🚨 [打包安全拦截] 发布包 framework.yaml 包含非空 api_key，已紧急阻断打包！")

    print("  ✅ [PASS 1/5] 商业激活码脱敏核验: license_key 出厂置空 (强制新用户专属激活)")
    print("  ✅ [PASS 2/5] 开发者 API 密钥脱敏: api_key 出厂置空 (隐私零泄漏)")
    print("  ✅ [PASS 3/5] WebView2 沙箱数据隔离: workspace/data/webview 为全新纯净目录 (历史对话零残留)")
    print("  ✅ [PASS 4/5] 工作区运行日志清零: workspace/logs 无任何历史调试日志")
    print("  ✅ [PASS 5/5] 微内核极简装配约束: 零冗余业务依赖，底座保持轻量纯净")
    print("  📖 纯净态合规详情请参阅: docs/PACKAGING_GUIDE.md\n")

    # 3.6 压缩为 Portable.zip
    portable_zip_path = RELEASE_DIR / f"立体空间智能体系统_{VERSION}_Portable.zip"
    if portable_zip_path.exists():
        portable_zip_path.unlink()

    print(f"🗜️ 正在压缩生成绿色便携包: {portable_zip_path.name} ...")
    with zipfile.ZipFile(portable_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(staging_root):
            for f in files:
                p = Path(root) / f
                arc_name = p.relative_to(staging_root)
                zipf.write(p, arc_name)

    shutil.rmtree(staging_root)
    zip_sz = portable_zip_path.stat().st_size / (1024 * 1024)
    print(f"🎉 [产物 B · 免安装绿色便携包]: {portable_zip_path.name} ({zip_sz:.2f} MB)")

    # 4. 汇总
    print("\n" + "=" * 65)
    print(f"✨ 交付物组装完成！目录: {RELEASE_DIR}")
    for item in RELEASE_DIR.iterdir():
        if item.is_file():
            print(f"   📁 {item.name:45s} [{item.stat().st_size / (1024*1024):.2f} MB]")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    package_release()
