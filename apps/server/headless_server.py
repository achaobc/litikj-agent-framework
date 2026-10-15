# -*- coding: utf-8 -*-
"""
apps/server/headless_server.py
【立体空间智能体系统 · 无头纯后台 AI 伴生微服务 (Tauri Sidecar)】
核心功能：
1. 接收 Tauri 启动参数 (--port, --host)；
2. 启动本地轻量 HTTP 微服务，并在标准输出打印 [ENGINE_READY]；
3. 捕获 SIGINT / SIGTERM 优雅退出，杜绝僵尸进程。
"""

import os
import sys
import time
import signal
import argparse
from pathlib import Path

# 确保 Windows 下非控制台环境不抛出编码或描述符异常
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 确保项目根目录在 sys.path 中
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from apps.server.api_server import start_server


def main():
    parser = argparse.ArgumentParser(description="Liti Space Agent OS - Headless Microkernel")
    parser.add_argument("--host", default="127.0.0.1", help="Server listen host")
    parser.add_argument("--port", type=int, default=8765, help="Server listen port")
    parser.add_argument("--token", default=None, help="API server authentication token")
    args = parser.parse_args()

    # 优雅退出信号监听
    def handle_shutdown(signum, frame):
        try:
            print("\n🛑 [微内核引擎] 收到退出信号，正在平稳释放底层资源...", flush=True)
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    print(f"🪐 [微内核引擎] 正在初始化立体空间智能体核心架构 (Host: {args.host}, Port: {args.port})...", flush=True)

    try:
        server = start_server(host=args.host, port=args.port, token=args.token)
        # 向 stdout 发送精准握手标记，Tauri Sidecar 监控器据此实现毫秒级就绪感知
        print(f"[ENGINE_READY] http://{args.host}:{args.port}", flush=True)
        try:
            server.serve_forever()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            try:
                print("✅ [微内核引擎] 已安全退出。", flush=True)
            except Exception:
                pass
    except OSError as e:
        if "10048" in str(e) or "already in use" in str(e).lower() or "address already in use" in str(e).lower():
            print(f"⚠️ [微内核引擎] 端口 {args.port} 检测到旧进程占用，正在强制释放并接管...", flush=True)
            # 在 Windows 下释放占用端口的孤儿旧进程
            if sys.platform.startswith("win"):
                try:
                    import subprocess
                    ps_script = f"Get-NetTCPConnection -LocalPort {int(args.port)} -State Listen -ErrorAction SilentlyContinue | Where-Object {{ $_.OwningProcess -gt 0 -and $_.OwningProcess -ne $PID }} | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
                    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], timeout=5)
                    time.sleep(1)
                    # 重新启动 (补全 token 参数 SEC-01)
                    server = start_server(host=args.host, port=args.port, token=args.token)
                    print(f"[ENGINE_READY] http://{args.host}:{args.port}", flush=True)
                    server.serve_forever()
                    return
                except Exception as ex:
                    print(f"⚠️ 强制释放端口异常: {ex}", flush=True)
            raise e
        else:
            raise e


if __name__ == "__main__":
    main()
