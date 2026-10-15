# -*- coding: utf-8 -*-
"""
scripts/setup_autostart.py
立体空间智能体工作台 · Windows 开机自启动管理实用工具
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LAUNCHER_VBS = STARTUP_DIR / "LitiSpaceAgentStudio.vbs"
BAT_PATH = ROOT_DIR / "一键启动智能体工作台.bat"


def is_enabled() -> bool:
    """检查是否已开启开机自启"""
    return LAUNCHER_VBS.exists()


def resolve_launcher_target():
    """
    智能检测并锁定宿主启动目标：
    优先锁定桌面原生客户端可执行程序 (.exe)，次选批处理引导脚本 (.bat)。
    兼容 NSIS 安装版目录、绿色便携版目录以及本地开发调试目录。
    """
    candidates = [
        # 1. 优先检查 NSIS 安装目录外层主程序 (当 ROOT_DIR 为 resources 时)
        ROOT_DIR.parent / "立体空间智能体系统.exe",
        ROOT_DIR.parent / "app.exe",
        # 2. 便携绿色版根目录主程序
        ROOT_DIR / "立体空间智能体系统.exe",
        ROOT_DIR / "app.exe",
        # 3. 本地编译输出目录主程序
        ROOT_DIR / "desktop" / "src-tauri" / "target" / "release" / "立体空间智能体系统.exe",
        ROOT_DIR / "desktop" / "src-tauri" / "target" / "release" / "app.exe",
        # 4. 批处理脚本兜底
        ROOT_DIR.parent / "一键启动智能体工作台.bat",
        ROOT_DIR / "一键启动智能体工作台.bat",
    ]

    for cand in candidates:
        if cand.is_file():
            return cand, cand.parent

    # 兜底回退
    return BAT_PATH, ROOT_DIR


def enable() -> bool:
    """开启开机自启 (创建静默无黑框 VBS 引导脚本，常驻系统托盘)"""
    try:
        STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        target_path, work_dir = resolve_launcher_target()

        if target_path.suffix.lower() == ".exe":
            # 优先唤醒原生桌面二进制，带 --autostart 参数静默最小化至系统托盘常驻
            run_cmd = f'"""{str(target_path)}"" --autostart"'
        else:
            # 批处理脚本通过 cmd /c 静默执行
            run_cmd = f'"cmd /c """"{str(target_path)}"""" --autostart"'

        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.CurrentDirectory = "{str(work_dir)}"\n'
            f'WshShell.Run {run_cmd}, 0, False\n'
        )
        LAUNCHER_VBS.write_text(vbs_content, encoding="gbk")
        print("========================================================")
        print("[成功] 已成功开启【立体空间智能体工作台】开机自启动！")
        print("========================================================")
        print(f"启动项路径: {LAUNCHER_VBS}")
        print(f"指向程序:   {target_path}")
        print(f"工作目录:   {work_dir}")
        print("运行特性:   已采用 VBScript 静默唤起技术，开机无黑框常驻系统托盘。")
        print("========================================================")
        return True
    except Exception as e:
        print(f"[失败] 开启开机自启失败: {e}")
        return False


def disable() -> bool:
    """取消开机自启"""
    try:
        if LAUNCHER_VBS.exists():
            LAUNCHER_VBS.unlink()
            print("========================================================")
            print("[成功] 已成功取消【立体空间智能体工作台】开机自启动！")
            print("========================================================")
            print(f"已清理启动项: {LAUNCHER_VBS}")
            print("========================================================")
        else:
            print("[提示] 当前尚未配置开机自启项，无需清理。")
        return True
    except Exception as e:
        print(f"[失败] 取消自启失败: {e}")
        return False


def status():
    """查看当前状态"""
    if is_enabled():
        print("========================================================")
        print("[状态] 开机自启动: 【已开启 (ENABLED)】")
        print(f"引导文件: {LAUNCHER_VBS}")
        print("========================================================")
    else:
        print("========================================================")
        print("[状态] 开机自启动: 【未开启 (DISABLED)】")
        print("========================================================")


if __name__ == "__main__":
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    if action in ("enable", "on", "install"):
        enable()
    elif action in ("disable", "off", "uninstall", "remove"):
        disable()
    elif action in ("status", "check"):
        status()
    else:
        print("用法: python scripts/setup_autostart.py [enable|disable|status]")
