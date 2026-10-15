# -*- coding: utf-8 -*-
"""
scripts/prepare_runtime.py
【立体空间智能体系统 · 嵌入式 Python 便携运行时准备工具】

职责：
1. 检查/下载官方纯净 Windows 64位 Python 3.10.11 嵌入式运行时 (python-3.10.11-embed-amd64.zip)；
2. 释放到 runtime/ 目录；
3. 配置 python310._pth 开启 site-packages 与根目录映射；
4. 注入必要依赖包 (PyYAML, psutil, Pillow 等)；
5. 执行健康巡检，验证嵌入式 Python 独立运行能力。
"""

import os
import sys
import shutil
import zipfile
import urllib.request
import subprocess
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT_DIR / "runtime"
CACHE_DIR = ROOT_DIR / "dist" / "cache"
EMBED_ZIP_NAME = "python-3.10.11-embed-amd64.zip"
CACHE_ZIP_PATH = CACHE_DIR / EMBED_ZIP_NAME
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/3.10.11/{EMBED_ZIP_NAME}"

REQUIRED_PACKAGES = ["yaml", "psutil", "PIL"]


def download_with_progress(url: str, dest_path: Path):
    """带进度显示的下载工具"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")

    print(f"🌐 正在从官方源下载嵌入式 Python 运行时: {url}")

    def report_progress(block_num, block_size, total_size):
        if total_size > 0:
            percent = min(100.0, block_num * block_size * 100.0 / total_size)
            downloaded_mb = (block_num * block_size) / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            sys.stdout.write(f"\r📥 下载进度: {percent:5.1f}% [{downloaded_mb:.2f} MB / {total_mb:.2f} MB]")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, temp_path, reporthook=report_progress)
        print("\n✅ 下载完成！")
        if dest_path.exists():
            dest_path.unlink()
        temp_path.rename(dest_path)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f"下载嵌入式 Python 失败: {e}")


def patch_pth_file(runtime_dir: Path):
    """修复 ._pth 文件以支持 site-packages 和动态 import"""
    pth_files = list(runtime_dir.glob("*._pth"))
    if not pth_files:
        print("⚠️ 未找到 *._pth 文件，跳过修改。")
        return

    pth_file = pth_files[0]
    print(f"🔧 正在适配嵌入式配置: {pth_file.name}")

    content = pth_file.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines()]

    # 确保开启 import site
    new_lines = []
    has_site = False
    for line in lines:
        if line.startswith("#import site") or line.startswith("import site"):
            new_lines.append("import site")
            has_site = True
        else:
            new_lines.append(line)

    if not has_site:
        new_lines.append("import site")

    # 注入 site-packages 与项目相对路径 (包括上级根目录 ..)
    extra_paths = ["site-packages", "Lib/site-packages", ".", ".."]
    for p in extra_paths:
        if p not in new_lines:
            new_lines.insert(0, p)

    pth_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print("✅ ._pth 配置修复成功 (已激活 site-packages 与 import site)")


def copy_or_install_dependencies(runtime_dir: Path):
    """为嵌入式 Python 注入依赖 (PyYAML, psutil, Pillow)"""
    site_packages = runtime_dir / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    print(f"📦 正在准备基础依赖库 ({', '.join(REQUIRED_PACKAGES)})...")

    # 优先方式：尝试从当前 Python 环境的 site-packages 直接复制（秒级完成，杜绝网络问题）
    copied_count = 0
    cur_site = None
    for p in sys.path:
        if p.endswith("site-packages") and os.path.exists(p):
            cur_site = Path(p)
            break

    if cur_site and cur_site.exists():
        print(f"🔍 检索到宿主 Python 依赖库: {cur_site}")
        pkg_map = {
            "yaml": ["yaml", "PyYAML"],
            "psutil": ["psutil"],
            "PIL": ["PIL", "Pillow"]
        }
        for mod_name, prefixes in pkg_map.items():
            found = False
            for entry in cur_site.iterdir():
                for pref in prefixes:
                    if entry.name.lower().startswith(pref.lower()):
                        dest = site_packages / entry.name
                        if not dest.exists():
                            if entry.is_dir():
                                shutil.copytree(entry, dest)
                            else:
                                shutil.copy2(entry, dest)
                        found = True
            if found:
                copied_count += 1
                print(f"  • 已装载依赖: {mod_name}")

    # 次选方式：如果未完整装载，使用当前 Python 的 pip install --target 进行兜底
    if copied_count < len(REQUIRED_PACKAGES):
        print("⚡ 正在通过 pip 补齐缺失依赖到 runtime/site-packages...")
        cmd = [
            sys.executable, "-m", "pip", "install",
            "--target", str(site_packages),
            "pyyaml", "psutil", "pillow",
            "--no-user"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"⚠️ pip 安装提示: {res.stderr}")
        else:
            print("✅ pip 补齐依赖完成！")


def verify_runtime(runtime_dir: Path) -> bool:
    """验证嵌入式 Python 解释器能否独立正常执行并导入核心库"""
    python_exe = runtime_dir / "python.exe"
    if not python_exe.exists():
        print(f"❌ 错误: 未在 {runtime_dir} 中找到 python.exe")
        return False

    test_code = "import sys, yaml, psutil; print(f'RUNTIME_VERIFIED:{sys.version.split()[0]}')"
    try:
        res = subprocess.run(
            [str(python_exe), "-c", test_code],
            capture_output=True,
            text=True,
            timeout=10
        )
        if "RUNTIME_VERIFIED" in res.stdout:
            print(f"🎉 嵌入式 Python 独立巡检通过: {res.stdout.strip()}")
            return True
        else:
            print(f"❌ 运行测试失败: stdout={res.stdout}, stderr={res.stderr}")
            return False
    except Exception as e:
        print(f"❌ 无法启动嵌入式 python.exe: {e}")
        return False


def setup_runtime(force_rebuild: bool = False):
    print("=" * 60)
    print("🪐 【立体空间智能体系统 · 嵌入式 Python 运行时准备器】")
    print("=" * 60)

    python_exe = RUNTIME_DIR / "python.exe"
    if python_exe.exists() and not force_rebuild:
        print(f"🔍 检测到现有 runtime 目录: {RUNTIME_DIR}")
        if verify_runtime(RUNTIME_DIR):
            print("✨ 现有嵌入式运行时就绪且健康，无需重复构建！\n")
            return RUNTIME_DIR

    # 1. 下载或提取 zip
    if not CACHE_ZIP_PATH.exists():
        download_with_progress(PYTHON_EMBED_URL, CACHE_ZIP_PATH)
    else:
        print(f"📦 发现本地缓存运行时包: {CACHE_ZIP_PATH.name}")

    # 2. 解压到 runtime
    if RUNTIME_DIR.exists():
        shutil.rmtree(RUNTIME_DIR)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    print(f"📂 正在释放嵌入式运行时至: {RUNTIME_DIR} ...")
    with zipfile.ZipFile(CACHE_ZIP_PATH, "r") as zipf:
        zipf.extractall(RUNTIME_DIR)

    # 3. 修复 ._pth
    patch_pth_file(RUNTIME_DIR)

    # 4. 拷贝/注入依赖 (仅微内核核心依赖)
    copy_or_install_dependencies(RUNTIME_DIR)

    # 5. 校验
    if verify_runtime(RUNTIME_DIR):
        size_mb = sum(f.stat().st_size for f in RUNTIME_DIR.rglob("*") if f.is_file()) / (1024 * 1024)
        print("=" * 60)
        print(f"✅ 嵌入式 Python 运行时准备就绪！")
        print(f"📊 体积: {size_mb:.2f} MB")
        print("=" * 60 + "\n")
        return RUNTIME_DIR
    else:
        raise RuntimeError("嵌入式运行时验证未通过，请检查配置。")


if __name__ == "__main__":
    force = "--force" in sys.argv
    setup_runtime(force_rebuild=force)
