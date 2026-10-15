# -*- coding: utf-8 -*-
"""
scripts/setup_whisper_env.py
【立体空间智能体系统 · 便携式 AI 语音引擎自动装配工具】
职责：
1. 为当前便携式 Python (runtime/python.exe) 自动配置 pip 与 faster-whisper 引擎；
2. 自动配置国内镜像加速通道 (清华源/阿里源)，确保极速下载；
3. 验证 faster_whisper 导入有效性；
4. 提供给 CLI、bat 脚本与智能体前端 [EXEC] setup whisper 调起。
"""

import os
import sys
import time
import shutil
import urllib.request
import subprocess
from pathlib import Path

# 保证标准输出采用 utf-8
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PYTHON = PROJECT_ROOT / "runtime" / "python.exe"
SITE_PACKAGES = PROJECT_ROOT / "runtime" / "site-packages"
CACHE_DIR = PROJECT_ROOT / "workspace" / "cache"


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def check_whisper_installed() -> bool:
    """检查是否已经可以正常导入 faster_whisper"""
    cmd = [str(RUNTIME_PYTHON), "-c", "import faster_whisper; print('OK')"]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return "OK" in res.stdout
    except Exception:
        return False


def ensure_pip() -> bool:
    """为便携式 Python 自动配置 pip"""
    log("🔍 [检查 1/3] 正在检测便携式运行环境 pip 模块...")
    check_cmd = [str(RUNTIME_PYTHON), "-m", "pip", "--version"]
    res = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        log(f"🟢 便携式 pip 已就绪: {res.stdout.strip()}")
        return True

    log("⚠️ 便携版未发现 pip，正在通过官方/镜像源引导安装 pip...")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    get_pip_path = CACHE_DIR / "get-pip.py"

    # 国内高速镜像或者官方源
    urls = [
        "https://mirrors.aliyun.com/pypi/get-pip.py",
        "https://bootstrap.pypa.io/get-pip.py"
    ]

    downloaded = False
    for url in urls:
        try:
            log(f"⬇️ 正在从镜像节点下载安装脚本: {url} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(get_pip_path, "wb") as f:
                    f.write(resp.read())
            if get_pip_path.exists() and get_pip_path.stat().st_size > 100000:
                downloaded = True
                log(f"✅ 下载完成 ({round(get_pip_path.stat().st_size / 1024, 1)} KB)")
                break
        except Exception as e:
            log(f"节点下载受阻: {e}，尝试备用源...")

    if not downloaded:
        log("❌ 无法下载 get-pip.py，请检查您的网络连接。")
        return False

    log("⚙️ 正在执行便携环境 pip 注入...")
    install_cmd = [
        str(RUNTIME_PYTHON),
        str(get_pip_path),
        "--no-warn-script-location",
        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"
    ]
    sub = subprocess.run(install_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if "Successfully installed pip" in sub.stdout or (RUNTIME_PYTHON.parent / "Scripts" / "pip.exe").exists():
        log("🎉 便携式 pip 注入成功！")
        return True
    else:
        log(f"pip 注入输出:\n{sub.stdout[-500:]}")
        # 二次验证
        check_after = subprocess.run([str(RUNTIME_PYTHON), "-m", "pip", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return check_after.returncode == 0


def install_faster_whisper() -> bool:
    """通过清华源极速安装 faster-whisper"""
    log("📦 [检查 2/3] 正在通过高速镜像源装配 faster-whisper 引擎...")
    pip_cmd = [
        str(RUNTIME_PYTHON), "-m", "pip", "install",
        "faster-whisper",
        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
        "--trusted-host", "pypi.tuna.tsinghua.edu.cn",
        "--no-warn-script-location"
    ]
    log("🚀 启动 pip 安装进程（可能需要 1~2 分钟，视网络速度而定）...")
    process = subprocess.Popen(
        pip_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    for line in iter(process.stdout.readline, ''):
        line_clean = line.strip()
        if line_clean:
            # 过滤高价值日志展示给用户
            if any(k in line_clean for k in ["Downloading", "Installing", "Successfully installed", "Requirement already satisfied"]):
                log(f"  » {line_clean[:90]}")

    process.stdout.close()
    return_code = process.wait()

    if return_code == 0:
        log("✅ faster-whisper 依赖库拉取成功！")
        return True
    else:
        log(f"❌ 安装退出异常，代码: {return_code}")
        return False


def main():
    log("=" * 60)
    log("👑 【立体空间智能体系统 · 离线语音引擎装配向导】")
    log("=" * 60)

    if not RUNTIME_PYTHON.exists():
        log(f"❌ 未找到便携式 Python: {RUNTIME_PYTHON}")
        sys.exit(1)

    # 1. 检查是否已经装好
    if check_whisper_installed():
        log("🎉 离线语音引擎 (faster-whisper) 已就绪！无需重复安装。")
        log("=" * 60)
        return 0

    # 2. 确保 pip 就绪
    if not ensure_pip():
        log("❌ pip 注入失败，请检查网络或使用离线绿色包。")
        return 1

    # 3. 安装 faster-whisper
    if not install_faster_whisper():
        log("❌ faster-whisper 安装未完成，请重试或检查控制台。")
        return 1

    # 4. 最终验证
    log("🔍 [检查 3/3] 正在运行最终环境加载验证...")
    if check_whisper_installed():
        log("✨ 恭喜！离线语音引擎 (faster-whisper) 已成功就绪！")
        log("👉 现在您可以重新将视频拖入投递箱，系统将自动抽取音频并生成逐字稿字幕！")
        log("=" * 60)
        return 0
    else:
        log("⚠️ 安装完成后未能成功导入，请重启工作台后重试。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
