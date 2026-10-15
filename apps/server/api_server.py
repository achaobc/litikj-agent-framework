# -*- coding: utf-8 -*-
"""
apps/server/api_server.py
【立体空间智能体系统 · 核心微内核 HTTP/SSE API 网关】
职责：
1. 纯原生标准库实现 (基于 http.server.ThreadingHTTPServer)，零三方依赖；
2. 为桌面客户端 (Tauri / Vue 3) 提供全套 REST API 与 SSE 流式事件：
   - /api/system, /api/settings, /api/models
   - /api/market/agents, /api/market/workflows, /api/market/capsules
   - /api/chat, /api/chat/stream, /api/tasks, /api/logs
3. 专职无头纯服务，不依赖任何旧版静态网页文件。
"""

import os
import re
import sys
import json
import subprocess
import mimetypes
from typing import Dict, Any, List, Optional
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import urllib.request
import urllib.error
import logging

logger = logging.getLogger("KernelApi")

from core.config import ConfigManager
from core.registry import Registry
from core.engine import Engine
from core.llm import LLMClient, LLMError, QuotaExhaustedError, RateLimitError, DailyLimitExceededError
from core.quota import QuotaManager
import secrets
from core.contract import TaskContext
from core.scheduler import SchedulerEngine
from core.market import OfficialMarketService

_SERVER_TOKEN: Optional[str] = None


def get_server_token() -> str:
    """
    获取当前系统的 API 核心认证 Token (单例会话级强随机凭证)
    优先顺序：
    1. 内存中已初始化的 _SERVER_TOKEN
    2. 环境变量 LITIKJ_API_TOKEN
    3. workspace/data/.session_token 物理凭据
    4. 动态生成 secrets.token_hex(32) 并原子安全持久化 (SEC-01)
    """
    global _SERVER_TOKEN
    if _SERVER_TOKEN:
        return _SERVER_TOKEN

    env_tok = os.environ.get("LITIKJ_API_TOKEN", "").strip()
    if env_tok:
        _SERVER_TOKEN = env_tok
        return _SERVER_TOKEN

    cm = ConfigManager.get_instance()
    token_file = cm.workspace_dir / "data" / ".session_token"
    if token_file.exists():
        try:
            t = token_file.read_text(encoding="utf-8").strip()
            if t:
                _SERVER_TOKEN = t
                return _SERVER_TOKEN
        except Exception:
            pass

    new_token = secrets.token_hex(32)
    _SERVER_TOKEN = new_token
    try:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(new_token, encoding="utf-8")
        try:
            os.chmod(token_file, 0o600)
        except Exception:
            pass
    except Exception:
        pass

    return _SERVER_TOKEN


def set_server_token(token: str):
    """显式配置服务端 Token (由启动参数 --token 或主控进程注入)"""
    global _SERVER_TOKEN
    _SERVER_TOKEN = (token or "").strip()


def open_in_file_manager(target_path: Path) -> bool:
    """跨平台且在 Windows 宿主下高可靠置顶唤起文件资源管理器的工具函数"""
    target = Path(target_path).resolve()
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)

    norm_path = os.path.normpath(str(target))

    if sys.platform.startswith("win"):
        # 1. 解除 Windows 前台抢占锁定 (AllowSetForegroundWindow)，
        # 允许随后被唤起的资源管理器窗口直接穿透 pywebview/浏览器置顶展示，避免静默后台闪烁
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
        except Exception:
            pass

        # 2. 检查目录下是否有实体文件可以进行高亮选中
        # /select 参数能强制 Windows 资源管理器创建独立视窗并将其提至前台，避免多标签静默合并
        target_file = None
        if target.is_file():
            target_file = target
        elif target.is_dir():
            files = [f for f in target.iterdir() if f.is_file() and not f.name.startswith(".")]
            if not files:
                files = [f for f in target.iterdir() if f.is_file()]
            if files:
                files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                target_file = files[0]

        opened = False

        # 2.1 首选：如果存在实体文件，通过 explorer.exe /select 强制聚焦高亮最新产物
        if target_file and target_file.exists():
            try:
                subprocess.Popen(['explorer.exe', f'/select,{os.path.normpath(str(target_file))}'])
                opened = True
            except Exception:
                pass

        # 2.2 次选：独立 explorer.exe 进程打开目录 (杜绝 shell=True 与命令注入风险 SEC-07)
        if not opened:
            try:
                subprocess.Popen(['explorer.exe', norm_path])
                opened = True
            except Exception:
                pass

        # 2.3 兜底：os.startfile
        if not opened:
            try:
                os.startfile(norm_path)
                opened = True
            except Exception:
                pass

        return opened
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, norm_path])
        return True


class KernelApiRequestHandler(SimpleHTTPRequestHandler):
    """立体空间智能体系统微内核 API 路由处理器"""
    _temp_capsules: Dict[str, bytes] = {}

    # 🛡️ 严格允许的受信任 Origin 白名单（本地回环与桌面沙箱环境）
    ALLOWED_ORIGIN_PATTERNS = [
        re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$"),
        re.compile(r"^tauri://localhost$"),
        re.compile(r"^https?://tauri\.localhost(:\d+)?$"),
        re.compile(r"^tauri://.*$"),
    ]
    # 🛡️ 严格允许的 Host 域名白名单（防御 DNS Rebinding 攻击）
    ALLOWED_HOST_PATTERNS = [
        re.compile(r"^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$"),
    ]
    # 🛡️ open-outputs 允许通过系统关联程序安全打开的文件后缀白名单 (SEC-VULN-11)
    SAFE_OPEN_EXTENSIONS = {
        # 图像
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".ico",
        # 音视频
        ".mp4", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".webm", ".m4a",
        # 文档与表格
        ".txt", ".md", ".json", ".csv", ".tsv", ".yaml", ".yml", ".xml",
        ".html", ".htm", ".pdf", ".docx", ".xlsx", ".pptx",
        # 归档与日志
        ".log", ".zip", ".tar", ".gz"
    }
    # 兼容历史测试用例引用
    DANGEROUS_OPEN_EXTENSIONS = {
        ".exe", ".bat", ".cmd", ".vbs", ".vbe", ".js", ".jse",
        ".wsf", ".wsh", ".msc", ".scr", ".com", ".pif", ".ps1",
        ".psm1", ".dll", ".reg", ".jar", ".hta", ".cpl", ".sys",
        ".lnk", ".url", ".appref-ms"
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def _is_origin_allowed(cls, origin: str) -> bool:
        """审查请求 Origin 是否在本地或 Tauri 桌面受信任白名单内"""
        if not origin:
            return True  # 允许无 Origin 头的本地原生应用、CLI 及 cURL
        clean = origin.strip().rstrip('/')
        return any(p.match(clean) for p in cls.ALLOWED_ORIGIN_PATTERNS)

    @classmethod
    def _is_host_allowed(cls, host: str) -> bool:
        """审查请求 Host 头，彻底杜绝 DNS Rebinding 越权"""
        if not host:
            return True
        clean = host.strip()
        return any(p.match(clean) for p in cls.ALLOWED_HOST_PATTERNS)

    def _validate_origin_and_host(self) -> bool:
        """全局核心安全校验门禁：拒绝任何非法 Host、Sec-Fetch-Site 跨站探测或未授权跨站访问 (SEC-01, SEC-08)"""
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin", "")
        sec_fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        sec_fetch_mode = self.headers.get("Sec-Fetch-Mode", "").lower()
        referer = self.headers.get("Referer", "")

        # 1. 严格 Host 校验 (防御 DNS Rebinding 攻击)
        if not self._is_host_allowed(host):
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"success": false, "error": "安全拦截：非法 Host 域名，拒绝处理 (DNS Rebinding 防护)"}'.encode("utf-8"))
            return False

        # 2. 严格阻断来自外部网站的跨站探测 (SEC-08)
        # 🛡️ 允许受信任的本地回环与 Tauri 桌面沙箱 (如 http://tauri.localhost) 发起的合法跨端口/跨协议调用
        if sec_fetch_site == "cross-site":
            if not origin or not self._is_origin_allowed(origin):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write('{"success": false, "error": "安全拦截：禁止外部跨站探测请求 (Cross-Site Request Blocked, SEC-08)"}'.encode("utf-8"))
                return False

        # 3. 严格阻断跨站 no-cors 嗅探
        parsed = urlparse(self.path)
        path = parsed.path
        if sec_fetch_mode == "no-cors" and path.startswith("/api/"):
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"success": false, "error": "安全拦截：禁止 no-cors 跨站资源探测"}'.encode("utf-8"))
            return False

        # 4. 审查 Referer 来源 (防御无 Origin 的跨站 GET 探测 SEC-08)
        if referer:
            p_ref = urlparse(referer)
            if p_ref.netloc:
                ref_host = p_ref.netloc.split(":")[0].lower()
                if ref_host not in ("127.0.0.1", "localhost", "tauri.localhost") and not ref_host.endswith(".tauri.localhost"):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write('{"success": false, "error": "安全拦截：非受信跨站 Referer 来源 (SEC-08)"}'.encode("utf-8"))
                    return False

        # 5. 审查 Origin (CORS 白名单)
        if origin and not self._is_origin_allowed(origin):
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"success": false, "error": "安全拦截：未授权的跨域请求来源 (Untrusted Origin)"}'.encode("utf-8"))
            return False

        # OPTIONS 预检请求在 Origin 验证通过后直接放行，由 do_OPTIONS 返回 CORS 头
        if self.command == "OPTIONS":
            return True

        # 6. 会话 Token 认证 (SEC-01 & SEC-08)
        # 公开免密通道：健康体检
        if path in ("/health", "/api/health"):
            return True

        # 提取请求携带的 Token
        req_token = self.headers.get("X-Agent-OS-Token", "").strip()
        if not req_token:
            auth_header = self.headers.get("Authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                req_token = auth_header[7:].strip()

        server_token = get_server_token()

        # 凡访问敏感 API 路由 (/api/ 开头)，无论是否携带 Origin，强制要求有效 Token (SEC-01 & 时序侧信道防御)
        if path.startswith("/api/"):
            from core.security import constant_time_compare
            if not req_token or not constant_time_compare(req_token, server_token):
                self.send_response(401)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                if origin and self._is_origin_allowed(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.end_headers()
                self.wfile.write('{"success": false, "error": "认证失败：缺少或无效的 X-Agent-OS-Token 认证令牌 (SEC-01)"}'.encode("utf-8"))
                return False

        return True

    def end_headers(self):
        # 强制禁用本地强缓存，彻底杜绝客户端读取陈旧的 HTML/CSS/JS 缓存文件
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        if not self._validate_origin_and_host():
            return

        self.send_response(200)
        origin = self.headers.get("Origin", "")
        if origin and self._is_origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-Agent-OS-Token")
            self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        if not self._validate_origin_and_host():
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/health", "/api/health"):
            cm = ConfigManager.get_instance()
            self._send_json({"status": "ok", "version": cm.version, "engine": "liti-agent-os"})
            return

        if path == "/api/system":
            self._handle_get_system()
        elif path == "/api/agents":
            self._handle_get_agents()
        elif path == "/api/skills":
            self._handle_get_skills()
        elif path == "/api/market/skills":
            self._handle_get_market_skills()
        elif path == "/api/market/agents":
            self._handle_get_market_agents()
        elif path == "/api/market/workflows":
            self._handle_get_market_workflows()
        elif path == "/api/workflows":
            self._handle_get_workflows()
        elif path == "/api/workflow/suspended":
            self._handle_get_suspended_workflows()
        elif path == "/api/watcher/status":
            self._handle_get_watcher_status()
        elif path == "/api/watcher/events":
            self._handle_get_watcher_events(parsed.query)
        elif path == "/api/bili/packages":
            self._handle_get_bili_packages()
        elif path == "/api/schedules":
            self._handle_get_schedules(parsed.query)
        elif path == "/api/autostart":
            self._handle_get_autostart()
        elif path == "/api/llm/detect-ollama":
            self._handle_get_detect_ollama()
        elif path == "/api/quota":
            self._handle_get_quota()
        elif path in ("/api/system/update/check", "/api/system/update"):
            self._handle_get_update_check(parsed.query)
        elif path == "/api/system/update/backups":
            self._handle_get_update_backups()
        elif path.startswith("/api/agent/") and path.endswith("/readiness"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "agent" and parts[3] == "readiness":
                self._handle_get_agent_readiness(parts[2])
                return
        elif path.startswith("/api/agent/") and path.endswith("/config"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "agent" and parts[3] == "config":
                self._handle_get_agent_config(parts[2])
                return
        elif path.startswith("/outputs/"):
            # 托管本地输出产物 (例如生成的图片、图表、报表)，安全校验防跨目录穿越
            from urllib.parse import unquote
            clean_sub = unquote(path[len("/outputs/"):].lstrip("/"))
            cm = ConfigManager.get_instance()
            outputs_root = (cm.workspace_dir / "outputs").resolve()
            target_file = (outputs_root / clean_sub).resolve()
            if not str(target_file).startswith(str(outputs_root)) or not target_file.is_file():
                self.send_error(404, "Output File Not Found")
                return

            mime_type = "application/octet-stream"
            suffix = target_file.suffix.lower()
            if suffix in (".png", ".webp", ".gif", ".svg", ".bmp"):
                mime_type = f"image/{suffix.lstrip('.')}"
            elif suffix in (".jpg", ".jpeg"):
                mime_type = "image/jpeg"
            elif suffix == ".txt":
                mime_type = "text/plain; charset=utf-8"
            elif suffix == ".json":
                mime_type = "application/json; charset=utf-8"
            elif suffix == ".html":
                mime_type = "text/html; charset=utf-8"
            elif suffix == ".pdf":
                mime_type = "application/pdf"

            try:
                with open(target_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(content)))
                origin = self.headers.get("Origin", "")
                if origin and self._is_origin_allowed(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, f"Error reading file: {str(e)}")
            return
        else:
            # 根路径与默认路径：返回微内核纯净运行状态 JSON
            resp = json.dumps({
                "service": "Litikj Agent OS Microkernel",
                "status": "running",
                "version": ConfigManager.get_instance().version,
                "engine": "Tauri-Ready"
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            origin = self.headers.get("Origin", "")
            if origin and self._is_origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()
            self.wfile.write(resp)
            return

    def do_POST(self):
        if not self._validate_origin_and_host():
            return

        parsed = urlparse(self.path)
        path = parsed.path

        # 🛡️ 拒绝服务攻击防护 (R3-VULN-05): 限制 HTTP 请求体最大 32MB
        MAX_BODY_SIZE = 32 * 1024 * 1024
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length < 0 or content_length > MAX_BODY_SIZE:
            self.send_response(413)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"success": false, "error": "Payload Too Large: \xe8\xaf\xb7\xe6\xb1\x82\xe4\xbd\x93\xe5\xa4\xa7\xe5\xb0\x8f\xe8\xb6\x85\xe8\xbf\x87 32MB \xe5\xae\x89\xe5\x85\xa8\xe4\xb8\x8a\xe9\x99\x90"}')
            return

        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        if path == "/api/chat":
            self._handle_post_chat(body)
        elif path == "/api/chat/stream":
            self._handle_post_chat_stream(body)
        elif path in ("/api/llm/test-connection", "/api/llm/test"):
            self._handle_post_llm_test_connection(body)
        elif path in ("/api/system/open-outputs", "/api/system/open-path"):
            self._handle_post_open_outputs(body)
        elif path == "/api/system/clear-workspace-outputs":
            self._handle_post_clear_workspace_outputs()
        elif path == "/api/system/diagnose":
            self._handle_post_diagnose()
        elif path == "/api/system/env/install-whisper":
            self._handle_post_install_whisper()
        elif path in ("/api/system/update/apply", "/api/system/update"):
            self._handle_post_update_apply(body)
        elif path == "/api/system/update/rollback":
            self._handle_post_update_rollback(body)
        elif path == "/api/run":
            self._handle_post_run(body)
        elif path == "/api/workflow/run":
            self._handle_post_workflow_run(body)
        elif path == "/api/workflow/resume":
            self._handle_post_workflow_resume(body)
        elif path == "/api/agents/reload":
            self._handle_post_reload()
        elif path in ("/api/system/license", "/api/system/settings"):
            self._handle_post_license(body)
        elif path == "/api/schedules":
            self._handle_post_schedule(body)
        elif path == "/api/schedules/toggle":
            self._handle_post_schedule_toggle(body)
        elif path == "/api/schedules/run_now":
            self._handle_post_schedule_run_now(body)
        elif path == "/api/schedules/delete":
            self._handle_post_schedule_delete(body)
        elif path == "/api/autostart":
            self._handle_post_autostart(body)
        elif path == "/api/bili/upload-draft":
            self._handle_post_bili_upload_draft(body)
        elif path == "/api/bili/open-package":
            self._handle_post_bili_open_package(body)
        elif path == "/api/watcher/events/consume":
            self._handle_post_watcher_events_consume(body)
        elif path == "/api/watcher/reset":
            self._handle_post_watcher_reset(body)
        elif path == "/api/watcher/archive":
            self._handle_post_watcher_archive(body)
        elif path == "/api/market/install":
            self._handle_post_market_install(body)
        elif path == "/api/market/uninstall":
            self._handle_post_market_uninstall(body)
        elif path == "/api/market/agents/recruit":
            self._handle_post_market_agent_recruit(body)
        elif path == "/api/market/agents/dismiss":
            self._handle_post_market_agent_dismiss(body)
        elif path == "/api/market/workflows/install":
            self._handle_post_market_workflow_install(body)
        elif path == "/api/market/workflows/install-deps":
            self._handle_post_market_workflow_install_deps(body)
        elif path == "/api/market/workflows/uninstall":
            self._handle_post_market_workflow_uninstall(body)
        elif path == "/api/capsule/inspect":
            self._handle_post_capsule_inspect(body)
        elif path == "/api/capsule/install":
            self._handle_post_capsule_install(body)
        elif path == "/api/skills/custom/create":
            self._handle_post_skill_custom_create(body)
        elif path == "/api/skills/export":
            self._handle_post_skill_export(body)
        elif path == "/api/skills/run":
            self._handle_post_skill_run(body)
        elif path in ("/api/agents/create", "/api/agents/recruit"):
            self._handle_post_agent_create(body)
        elif path == "/api/agents/delete":
            self._handle_post_agent_delete(body)
        elif path == "/api/quota/refresh":
            self._handle_post_quota_refresh()
        elif path == "/api/quota/recharge":
            self._handle_post_quota_recharge(body)
        elif path.startswith("/api/agent/") and path.endswith("/heal"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "agent" and parts[3] == "heal":
                self._handle_post_agent_heal(parts[2], body)
                return
        elif path.startswith("/api/agent/") and path.endswith("/config"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "agent" and parts[3] == "config":
                self._handle_post_agent_config(parts[2], body)
                return
        else:
            self._send_json({"error": "Endpoint not found"}, status=404)

    # ================= 业务接口实现 =================

    def _handle_get_system(self):
        cm = ConfigManager.get_instance()
        gw = cm.gateway
        valid, msg = LLMClient.verify_license()
        from core.hardware import get_device_fingerprint, get_device_name
        qm = QuotaManager.get_instance()
        quota_data = qm.get_status().to_dict()
        if gw.mode == "custom":
            quota_data["status"] = "unlimited"
            quota_data["tier"] = "极客自备 Key / 本地私有 (无限制)"
            quota_data["is_unlimited"] = True
        else:
            quota_data["is_unlimited"] = False

        data = {
            "system_name": cm.system_name,
            "version": cm.version,
            "workspace_dir": str(cm.workspace_dir),
            "device": {
                "fingerprint": get_device_fingerprint(),
                "name": get_device_name()
            },
            "quota": quota_data,
            "gateway": {
                "mode": gw.mode,
                "is_active": gw.is_active(),
                "license_masked": gw.get_masked_license(),
                "status_msg": msg,
                "custom_provider": getattr(gw, "custom_provider", "custom"),
                "custom_base_url": getattr(gw, "custom_base_url", "https://api.deepseek.com/v1"),
                "custom_model": getattr(gw, "custom_model", "deepseek-chat"),
                "custom_has_key": bool(getattr(gw, "custom_api_key", "").strip()),
                "quota": quota_data
            },
            "watcher": {
                "enabled": cm.watcher.enabled,
                "poll_interval": cm.watcher.poll_interval,
                "settle_seconds": cm.watcher.settle_seconds,
                "rules_count": len(cm.watcher.rules)
            },
            "autostart": self._check_autostart_safe()
        }
        self._send_json(data)

    def _handle_post_diagnose(self):
        from core.hardware import get_device_fingerprint, get_device_name
        reg = Registry.get_instance()
        cm = ConfigManager.get_instance()
        self._send_json({
            "success": True,
            "device_name": get_device_name(),
            "device_fingerprint": get_device_fingerprint(),
            "agent_count": len(reg.list_agents()),
            "skills_count": len(reg.list_skills()),
            "licensed": cm.gateway.is_active(),
            "autostart": self._check_autostart_safe()
        })

    def _handle_post_install_whisper(self):
        """一键调起后台安装 Whisper 语音引擎"""
        cm = ConfigManager.get_instance()
        script_path = cm.root_dir / "scripts" / "setup_whisper_env.py"
        py_exe = cm.root_dir / "runtime" / "python.exe"
        if not py_exe.exists() or not script_path.exists():
            self._send_json({"success": False, "error": "未找到便携式安装程序"}, 400)
            return

        import subprocess
        try:
            res = subprocess.run(
                [str(py_exe), str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300
            )
            self._send_json({
                "success": (res.returncode == 0),
                "returncode": res.returncode,
                "output": res.stdout[-1500:] if res.stdout else ""
            })
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_get_update_check(self, query_str: str = ""):
        from core.updater import UpdateManager
        simulate = "simulate=true" in (query_str or "").lower()
        res = UpdateManager.check_for_updates(simulate=simulate)
        self._send_json(res)

    def _handle_post_update_apply(self, body: dict):
        from core.updater import UpdateManager
        patch_url = (body.get("patch_url") or "").strip()
        sha256 = (body.get("sha256") or "").strip()
        if not patch_url:
            self._send_json({"success": False, "status": "error", "error": "缺少补丁包地址 (patch_url)"}, status=400)
            return
        if not sha256:
            self._send_json({"success": False, "status": "error", "error": "安全拦截：必须提供补丁包 SHA-256 完整性散列校验值 (sha256)"}, status=400)
            return
        try:
            res = UpdateManager.apply_patch_archive(patch_url=patch_url, expected_sha256=sha256)
            self._send_json(res)
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=500)

    def _handle_get_update_backups(self):
        from core.updater import UpdateManager
        res = UpdateManager.list_backups()
        self._send_json({"success": True, "backups": res})

    def _handle_post_update_rollback(self, body: dict):
        from core.updater import UpdateManager
        backup_name = body.get("backup_name", "")
        try:
            res = UpdateManager.rollback_to_backup(backup_filename=backup_name)
            self._send_json(res)
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=500)

    def _handle_get_agents(self):
        reg = Registry.get_instance()
        agents_data = []
        for ag in reg.list_agents():
            try:
                readiness_data = ag.get_readiness_status() if hasattr(ag, "get_readiness_status") else {
                    "state": "READY", "progress": 100.0, "current_item": "已就绪"
                }
            except Exception as e:
                readiness_data = {
                    "state": "ACTION_REQUIRED", "progress": 0.0, "current_item": "自检异常", "message": str(e)
                }
            try:
                agents_data.append({
                    "name": ag.name,
                    "display_name": getattr(ag, "display_name", ag.name),
                    "icon": getattr(ag, "icon", "🤖"),
                    "description": getattr(ag, "description", ""),
                    "category": getattr(ag, "category", "通用"),
                    "quick_chips": getattr(ag, "quick_chips", []),
                    "actions": getattr(ag, "actions", []),
                    "version": getattr(ag, "version", "1.0.0"),
                    "source": getattr(ag, "source", "builtin"),
                    "source_path": getattr(ag, "source_path", ""),
                    "skills": getattr(ag, "skills_list", []),
                    "system_prompt": getattr(ag, "system_prompt", ""),
                    "temperature": getattr(ag, "temperature", 0.7),
                    "is_custom": (getattr(ag, "source", "builtin") == "external"),
                    "pre_guards": [{"name": getattr(g, "name", "guard"), "description": getattr(g, "description", "")} for g in getattr(ag, "pre_guards", [])],
                    "post_guards": [{"name": getattr(g, "name", "guard"), "description": getattr(g, "description", "")} for g in getattr(ag, "post_guards", [])],
                    "readiness": readiness_data
                })
            except Exception as err:
                print(f"[ApiServer Warning] 序列化智能体 {getattr(ag, 'name', 'unknown')} 异常: {err}")
        self._send_json({"agents": agents_data})

    def _handle_get_agent_readiness(self, agent_name: str):
        reg = Registry.get_instance()
        agent = reg.get_agent(agent_name)
        if not agent:
            self._send_json({"success": False, "error": f"Agent '{agent_name}' not found"}, 404)
            return

        status = agent.get_readiness_status() if hasattr(agent, "get_readiness_status") else {
            "agent_name": agent_name,
            "display_name": getattr(agent, "display_name", agent.name),
            "state": "READY",
            "progress": 100.0,
            "current_item": "已就绪",
            "items": [],
            "action_guide": None,
            "message": "100% 完备，处于在岗待命状态"
        }
        self._send_json({"success": True, "agent_name": agent_name, "readiness": status})

    def _handle_post_agent_heal(self, agent_name: str, body: Dict[str, Any]):
        reg = Registry.get_instance()
        agent = reg.get_agent(agent_name)
        if not agent:
            self._send_json({"success": False, "error": f"Agent '{agent_name}' not found"}, 404)
            return

        if hasattr(agent, "heal_environment"):
            res = agent.heal_environment()
        else:
            from core.preflight import AutoHealer
            res = AutoHealer.heal_agent(agent)

        self._send_json({"success": True, "agent_name": agent_name, "readiness": res})

    def _handle_get_agent_config(self, agent_name: str):
        reg = Registry.get_instance()
        agent = reg.get_agent(agent_name)
        if not agent:
            self._send_json({"success": False, "error": f"Agent '{agent_name}' not found"}, 404)
            return

        schema = {}
        config = {}
        if hasattr(agent, "get_config_schema"):
            try:
                schema = agent.get_config_schema()
            except Exception as e:
                print(f"[ApiServer Warning] get_config_schema failed: {e}")
        if hasattr(agent, "get_config"):
            try:
                config = agent.get_config()
            except Exception as e:
                print(f"[ApiServer Warning] get_config failed: {e}")

        self._send_json({
            "success": True,
            "agent_name": agent_name,
            "display_name": getattr(agent, "display_name", agent.name),
            "schema": schema,
            "config": config
        })

    def _handle_post_agent_config(self, agent_name: str, body: Dict[str, Any]):
        reg = Registry.get_instance()
        agent = reg.get_agent(agent_name)
        if not agent:
            self._send_json({"success": False, "error": f"Agent '{agent_name}' not found"}, 404)
            return

        if not hasattr(agent, "update_config"):
            self._send_json({"success": False, "error": f"Agent '{agent_name}' does not support update_config"}, 400)
            return

        try:
            updates = body.get("updates", body)
            new_config = agent.update_config(updates)
            self._send_json({
                "success": True,
                "agent_name": agent_name,
                "config": new_config,
                "message": "配置更新并持久化成功"
            })
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_post_reload(self):
        reg = Registry.get_instance()
        reg.auto_discover()
        self._send_json({
            "success": True,
            "message": "已重新扫描并加载智能体与三级技能插槽",
            "count": len(reg.list_agents()),
            "skills_count": len(reg.list_skills())
        })

    def _handle_get_skills(self):
        reg = Registry.get_instance()
        skills_data = [s.to_dict() for s in reg.list_skills()]
        self._send_json({"success": True, "status": "success", "skills": skills_data})

    def _handle_get_market_skills(self):
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()
        market_items = OfficialMarketService.list_market(cm.skills_dir, reg.list_skills())
        self._send_json({"success": True, "status": "success", "market": market_items, "market_skills": market_items})

    def _handle_post_market_install(self, body: dict):
        skill_id = body.get("skill_id", "").strip()
        if not skill_id:
            self._send_json({"success": False, "status": "error", "error": "必须指定目标技能 ID"}, status=400)
            return
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()
        try:
            res = OfficialMarketService.install_official_skill(skill_id, cm.skills_dir)
            reg.auto_discover()
            self._send_json({"success": True, "status": "success", "skill": res, "message": f"官方技能 [{res.get('name')}] 已安装并就绪"})
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_post_market_uninstall(self, body: dict):
        skill_id = body.get("skill_id", "").strip()
        origin = body.get("origin", "").strip() or None
        if not skill_id:
            self._send_json({"success": False, "status": "error", "error": "必须指定待卸载技能 ID"}, status=400)
            return
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()
        try:
            res = OfficialMarketService.uninstall_skill(skill_id, origin, cm.skills_dir)
            reg.unregister_skill(skill_id)
            reg.auto_discover()
            self._send_json({"success": True, "status": "success", "result": res, "message": "技能已成功从本地卸载"})
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_get_market_agents(self):
        from core.agent_market import AgentMarketService
        items = AgentMarketService.list_agent_market()
        self._send_json({"success": True, "status": "success", "agents": items})

    def _handle_post_market_agent_recruit(self, body: dict):
        from core.agent_market import AgentMarketService
        agent_id = (body.get("agent_id") or body.get("id") or "").strip()
        if not agent_id:
            self._send_json({"success": False, "status": "error", "error": "必须指定目标智能体 ID"}, status=400)
            return
        try:
            res = AgentMarketService.recruit_agent(agent_id)
            # 招募完成后后台自动启动静默自愈与环境装备
            reg = Registry.get_instance()
            ag = reg.get_agent(agent_id)
            if ag and hasattr(ag, "heal_environment"):
                try:
                    readiness = ag.heal_environment()
                    res["readiness"] = readiness
                except Exception as ex:
                    print(f"[Recruit AutoHeal Warning] 智能体入职自动自愈提示: {ex}")
            elif ag and hasattr(ag, "get_readiness_status"):
                res["readiness"] = ag.get_readiness_status()
            self._send_json(res)
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_post_market_agent_dismiss(self, body: dict):
        from core.agent_market import AgentMarketService
        agent_id = (body.get("agent_id") or body.get("id") or "").strip()
        if not agent_id:
            self._send_json({"success": False, "status": "error", "error": "必须指定待解雇智能体 ID"}, status=400)
            return
        try:
            res = AgentMarketService.dismiss_agent(agent_id)
            self._send_json(res)
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_get_market_workflows(self):
        from core.workflow_market import WorkflowMarketService
        items = WorkflowMarketService.list_workflow_market()
        self._send_json({"success": True, "status": "success", "workflows": items})

    def _handle_post_market_workflow_install(self, body: dict):
        from core.workflow_market import WorkflowMarketService
        workflow_id = (body.get("workflow_id") or body.get("id") or "").strip()
        if not workflow_id:
            self._send_json({"success": False, "status": "error", "error": "必须指定目标工作流 ID"}, status=400)
            return
        try:
            res = WorkflowMarketService.install_workflow(workflow_id)
            self._send_json(res)
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_post_market_workflow_install_deps(self, body: dict):
        from core.workflow_market import WorkflowMarketService
        workflow_id = (body.get("workflow_id") or body.get("id") or "").strip()
        if not workflow_id:
            self._send_json({"success": False, "status": "error", "error": "必须指定目标工作流 ID"}, status=400)
            return
        try:
            res = WorkflowMarketService.install_workflow_dependencies(workflow_id)
            self._send_json(res)
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_post_market_workflow_uninstall(self, body: dict):
        from core.workflow_market import WorkflowMarketService
        workflow_id = (body.get("workflow_id") or body.get("id") or "").strip()
        if not workflow_id:
            self._send_json({"success": False, "status": "error", "error": "必须指定待卸载工作流 ID"}, status=400)
            return
        try:
            res = WorkflowMarketService.uninstall_workflow(workflow_id)
            self._send_json(res)
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_post_capsule_inspect(self, body: dict):
        import base64
        file_base64 = (body.get("file_base64") or body.get("file_content_b64") or "").strip()
        if not file_base64:
            self._send_json({"success": False, "status": "error", "error": "未提供卡带文件数据"}, status=400)
            return
        try:
            raw_bytes = base64.b64decode(file_base64)
            inspection = OfficialMarketService.inspect_capsule_archive(raw_bytes)
            if not inspection.get("valid"):
                self._send_json({"success": False, "status": "error", "error": inspection.get("error", "无效的技能卡带")}, status=400)
                return
            # 🛡️ 内存防爆 (R3-VULN-05): 限制临时卡带缓存池最大容量 (最多保留 10 份，淘汰最旧的条目)
            while len(self._temp_capsules) >= 10:
                oldest_k = next(iter(self._temp_capsules))
                self._temp_capsules.pop(oldest_k, None)

            token = os.urandom(8).hex()
            self._temp_capsules[token] = raw_bytes
            inspection["temp_token"] = token
            self._send_json({
                "success": True,
                "status": "success",
                "inspection": inspection,
                "report": inspection,
                "inspect_token": token
            })
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": f"解析卡带失败: {str(e)}"}, status=500)

    def _handle_post_capsule_install(self, body: dict):
        import base64
        token = (body.get("temp_token") or body.get("token") or "").strip()
        file_base64 = (body.get("file_base64") or body.get("file_content_b64") or "").strip()
        raw_bytes = self._temp_capsules.pop(token, None) if token else None
        if not raw_bytes and file_base64:
            try:
                raw_bytes = base64.b64decode(file_base64)
            except Exception:
                pass
        if not raw_bytes:
            self._send_json({"success": False, "status": "error", "error": "卡带数据已过期或不存在，请重新拖入"}, status=400)
            return
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()
        try:
            res = OfficialMarketService.install_capsule_archive(raw_bytes, cm.skills_dir, target_origin="community")
            reg.auto_discover()
            self._send_json({"success": True, "status": "success", "installed": res, "message": f"第三方技能 [{res.get('display_name')}] 已安全装载"})
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": f"安装卡带失败: {str(e)}"}, status=500)

    def _handle_post_skill_custom_create(self, body: dict):
        skill_id = (body.get("id") or body.get("skill_id") or "").strip()
        name = (body.get("name") or body.get("display_name") or "").strip()
        desc = body.get("description", "").strip()
        cat = body.get("category", "自定义").strip()
        author = body.get("author", "本地开发者").strip()
        icon = body.get("icon", "🛠️").strip()
        if not skill_id:
            self._send_json({"success": False, "status": "error", "error": "技能唯一标识(id)不能为空"}, status=400)
            return
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()
        try:
            res_path = OfficialMarketService.create_custom_scaffold(
                skill_id=skill_id,
                name=name,
                description=desc,
                category=cat,
                author=author,
                skills_dir=cm.skills_dir,
                display_name=name,
                icon=icon
            )
            reg.auto_discover()
            scaffold_info = {
                "skill_id": skill_id,
                "name": name or skill_id,
                "path": str(res_path.resolve()) if hasattr(res_path, "resolve") else str(res_path)
            }
            self._send_json({"success": True, "status": "success", "scaffold": scaffold_info, "message": f"自定义技能 [{name or skill_id}] 脚手架已就绪"})
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_post_skill_export(self, body: dict):
        skill_id = body.get("skill_id", "").strip()
        if not skill_id:
            self._send_json({"success": False, "status": "error", "error": "必须指定目标技能 ID"}, status=400)
            return
        cm = ConfigManager.get_instance()
        out_dir = cm.workspace_dir / "outputs" / "capsules"
        try:
            export_path = OfficialMarketService.export_skill_capsule(skill_id, cm.skills_dir, out_dir)
            norm_path = os.path.normpath(str(export_path))
            self._send_json({
                "success": True,
                "status": "success",
                "file_name": export_path.name,
                "package_path": norm_path,
                "path": norm_path,
                "message": f"卡带已成功脱敏打包为: {export_path.name}"
            })
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)

    def _handle_post_skill_run(self, body: dict):
        """独立表单直接运行原子技能"""
        skill_id = (body.get("skill_id") or body.get("skill") or "").strip()
        params = body.get("params") if body.get("params") is not None else body.get("inputs", {})
        if not skill_id:
            self._send_json({"success": False, "status": "error", "error": "缺少技能标识 (skill_id)"}, status=400)
            return

        reg = Registry.get_instance()
        skill = reg.get_skill(skill_id)
        if not skill:
            self._send_json({"success": False, "status": "error", "error": f"未找到已装载的技能 [{skill_id}]"}, status=404)
            return

        try:
            result = skill.execute(params)
            self._send_json({
                "success": True,
                "status": "success",
                "skill_id": skill_id,
                "display_name": getattr(skill, "display_name", skill.name),
                "result": result,
                "message": f"技能 [{getattr(skill, 'display_name', skill.name)}] 独立运行完成"
            })
        except Exception as e:
            self._send_json({"success": False, "status": "error", "error": f"执行技能异常: {str(e)}"}, status=500)

    def _handle_post_agent_create(self, body: dict):
        """招聘/创建自定义智能体新员工，保存在 workspace/custom_agents/<id>/"""
        import yaml
        agent_id = (body.get("id") or body.get("agent_id") or "").strip().lower()
        name = (body.get("name") or "").strip()
        icon = (body.get("icon") or "🤖").strip()
        category = (body.get("category") or "自定义岗位").strip()
        description = (body.get("description") or "").strip()
        system_prompt = (body.get("system_prompt") or "").strip()
        temperature = float(body.get("temperature", 0.7))
        skills = body.get("skills", [])
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]
        quick_chips = body.get("quick_chips", [])
        if isinstance(quick_chips, str):
            quick_chips = [c.strip() for c in quick_chips.split(",") if c.strip()]

        clean_id = "".join(c for c in agent_id if c.isalnum() or c in ("_", "-")).strip()
        if not clean_id or not name:
            self._send_json({"success": False, "status": "error", "error": "员工唯一标识与岗位名称不能为空"}, status=400)
            return

        cm = ConfigManager.get_instance()
        custom_agents_dir = cm.workspace_dir / "custom_agents"
        target_dir = custom_agents_dir / clean_id

        if target_dir.exists():
            self._send_json({"success": False, "status": "error", "error": f"岗位标识 [{clean_id}] 已存在，请使用其他名称"}, status=400)
            return

        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. 写入 config.yaml
        config_dict = {
            "id": clean_id,
            "name": name,
            "display_name": name,
            "icon": icon,
            "category": category,
            "description": description or f"为一人公司打造的【{name}】专属数字化员工",
            "version": "1.0.0",
            "temperature": temperature,
            "system_prompt": system_prompt or f"你是一名专业的【{name}】。请全力协助用户完成工作任务。",
            "skills": skills,
            "quick_chips": quick_chips or [f"✨ 启动 {name}"]
        }
        with open(target_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, allow_unicode=True, sort_keys=False)

        # 2. 写入 agent.py (严格使用 repr() 转义字面量，杜绝 Python 代码注入与引号逃逸)
        raw_parts = [p.capitalize() for p in re.sub(r'[^a-zA-Z0-9_]', '_', clean_id).split("_") if p]
        class_name = ("".join(raw_parts) or "Custom") + "Agent"
        if not class_name.isidentifier():
            class_name = "CustomAgent"

        safe_clean_id = repr(str(clean_id))
        default_desc = f"{name}数字化员工"
        safe_desc = repr(str(description or default_desc))
        safe_run_msg = repr(f"【{name}】任务执行完成")
        safe_doc_name = str(name).replace("\r", " ").replace("\n", " ").replace('"', '\\"')

        agent_code = f'''# -*- coding: utf-8 -*-
"""
workspace/custom_agents/{clean_id}/agent.py
【{safe_doc_name} · 一人公司专属岗位员工】
"""
from core.contract import BaseAgent, TaskContext, TaskResult

class {class_name}(BaseAgent):
    def __init__(self):
        super().__init__(
            name={safe_clean_id},
            description={safe_desc}
        )

    def run(self, context: TaskContext) -> TaskResult:
        return TaskResult(
            success=True,
            message={safe_run_msg},
            data={{"agent": {safe_clean_id}}}
        )

def setup(registry):
    registry.register_agent({class_name}())
'''
        with open(target_dir / "entry.py", "w", encoding="utf-8") as f:
            f.write(agent_code)

        # 3. 动态重载注册表
        reg = Registry.get_instance()
        reg.auto_discover()

        self._send_json({
            "success": True,
            "status": "success",
            "agent_id": clean_id,
            "name": name,
            "icon": icon,
            "message": f"🎉 新员工【{name}】已成功办理入职并就绪！"
        })

    def _handle_post_agent_delete(self, body: dict):
        """解雇/删除自定义智能体员工 (SEC-11)"""
        agent_id = (body.get("agent_id") or body.get("id") or "").strip()
        if not agent_id:
            self._send_json({"success": False, "status": "error", "error": "缺少目标智能体标识 (agent_id)"}, status=400)
            return

        from core.security import validate_safe_id_and_resolve_dir
        cm = ConfigManager.get_instance()
        custom_agents_dir = cm.workspace_dir / "custom_agents"
        try:
            target_dir = validate_safe_id_and_resolve_dir(agent_id, custom_agents_dir, "智能体", must_exist=False)
        except (ValueError, PermissionError) as e:
            self._send_json({"success": False, "status": "error", "error": str(e)}, status=400)
            return

        if not target_dir.exists():
            self._send_json({
                "success": False,
                "status": "error",
                "error": "只能解雇外部自定义员工，系统原生预置智能体受内核保护不可删除！"
            }, status=400)
            return

        import shutil
        shutil.rmtree(target_dir, ignore_errors=True)

        reg = Registry.get_instance()
        reg.unregister_agent(agent_id)
        reg.auto_discover()

        self._send_json({
            "success": True,
            "status": "success",
            "agent_id": agent_id,
            "message": f"员工 [{agent_id}] 已成功解雇并清理工作区数据"
        })

    def _handle_post_license(self, body: dict):
        license_key = body.get("license_key", "").strip() if "license_key" in body else None
        mode = body.get("mode", "").strip() if "mode" in body else None
        custom_provider = body.get("custom_provider", "").strip() if "custom_provider" in body else None
        custom_api_key = body.get("custom_api_key", "").strip() if "custom_api_key" in body else None
        custom_base_url = body.get("custom_base_url", "").strip() if "custom_base_url" in body else None
        custom_model = body.get("custom_model", "").strip() if "custom_model" in body else None

        # 智能模式联动：如果显式绑定了非空卡密，且未显式指定模式，默认自动切换为官方云端中枢 cloud 模式
        if license_key and not mode:
            mode = "cloud"

        cm = ConfigManager.get_instance()
        config_path = cm.config_path

        try:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    content = f.read()

                import re
                def _escape_yaml_val(val: str) -> str:
                    return val.replace('\\', '\\\\').replace('"', '\\"')

                # 🛡️ 敏感凭据隔离存储 (R2-VULN-05 / SEC-VULN-10)：
                # 优先将卡密与自定义 API Key 写入受 .gitignore 保护的 configs/.secrets.yaml
                secrets_written = False
                secrets_path = cm.root_dir / "configs" / ".secrets.yaml"
                if yaml:
                    try:
                        secrets_path.parent.mkdir(parents=True, exist_ok=True)
                        sec_data = {}
                        if secrets_path.exists():
                            with open(secrets_path, "r", encoding="utf-8") as sf:
                                sec_data = yaml.safe_load(sf) or {}
                        if not isinstance(sec_data, dict):
                            sec_data = {}
                        gw_sec = sec_data.setdefault("gateway", {})
                        if license_key:
                            gw_sec["license_key"] = license_key
                        if custom_api_key:
                            gw_sec.setdefault("custom", {})["api_key"] = custom_api_key
                        with open(secrets_path, "w", encoding="utf-8") as sf:
                            yaml.dump(sec_data, sf, allow_unicode=True)
                        secrets_written = True
                    except Exception as se:
                        logger.warning(f"写入 .secrets.yaml 失败: {se}")

                # 更新 configs/framework.yaml (非敏感参数常驻，敏感参数脱敏)
                if mode and re.search(r'^\s*mode:\s*.*$', content, flags=re.MULTILINE):
                    safe_val = _escape_yaml_val(mode)
                    content = re.sub(r'^\s*mode:\s*.*$', lambda m: f'  mode: "{safe_val}"', content, flags=re.MULTILINE)
                if custom_provider and re.search(r'^\s*provider:\s*.*$', content, flags=re.MULTILINE):
                    safe_val = _escape_yaml_val(custom_provider)
                    content = re.sub(r'^\s*provider:\s*.*$', lambda m: f'    provider: "{safe_val}"', content, flags=re.MULTILINE)
                elif custom_provider and "custom:" in content and "provider:" not in content:
                    safe_val = _escape_yaml_val(custom_provider)
                    content = content.replace("custom:", f"custom:\n    provider: \"{safe_val}\"")
                if custom_base_url and re.search(r'^\s*base_url:\s*.*$', content, flags=re.MULTILINE):
                    safe_val = _escape_yaml_val(custom_base_url)
                    content = re.sub(r'^\s*base_url:\s*.*$', lambda m: f'    base_url: "{safe_val}"', content, flags=re.MULTILINE)
                if custom_model and re.search(r'^\s*model:\s*.*$', content, flags=re.MULTILINE):
                    safe_val = _escape_yaml_val(custom_model)
                    content = re.sub(r'^\s*model:\s*.*$', lambda m: f'    model: "{safe_val}"', content, flags=re.MULTILINE)

                # 若已成功写入 .secrets.yaml，则清空 framework.yaml 中的明文秘钥，严防 Git 跟踪泄露
                if secrets_written:
                    if re.search(r'^\s*license_key:\s*.*$', content, flags=re.MULTILINE):
                        content = re.sub(r'^\s*license_key:\s*.*$', '  license_key: ""', content, flags=re.MULTILINE)
                    if re.search(r'^\s*api_key:\s*.*$', content, flags=re.MULTILINE):
                        content = re.sub(r'^\s*api_key:\s*.*$', '    api_key: ""', content, flags=re.MULTILINE)
                else:
                    # 降级兜底方案 (未装载 PyYAML 或写入失败时)
                    if license_key and re.search(r'^\s*license_key:\s*.*$', content, flags=re.MULTILINE):
                        safe_val = _escape_yaml_val(license_key)
                        content = re.sub(r'^\s*license_key:\s*.*$', lambda m: f'  license_key: "{safe_val}"', content, flags=re.MULTILINE)
                    if custom_api_key and re.search(r'^\s*api_key:\s*.*$', content, flags=re.MULTILINE):
                        safe_val = _escape_yaml_val(custom_api_key)
                        content = re.sub(r'^\s*api_key:\s*.*$', lambda m: f'    api_key: "{safe_val}"', content, flags=re.MULTILINE)

                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # 热重载配置
            cm.reload()

            # 校验激活状态（按当前热重载后的模式强制联网校验一次并刷新缓存）
            valid, msg = LLMClient.verify_license(target_mode=cm.gateway.mode, force_network=True)

            self._send_json({
                "success": True,
                "valid": valid,
                "message": msg,
                "gateway": {
                    "mode": cm.gateway.mode,
                    "is_active": cm.gateway.is_active(),
                    "license_masked": cm.gateway.get_masked_license(),
                    "status_msg": msg,
                    "custom_provider": getattr(cm.gateway, "custom_provider", "custom"),
                    "custom_base_url": getattr(cm.gateway, "custom_base_url", ""),
                    "custom_model": getattr(cm.gateway, "custom_model", ""),
                    "custom_has_key": bool(getattr(cm.gateway, "custom_api_key", "").strip())
                }
            })
        except Exception as e:
            self._send_json({"success": False, "error": f"保存配置失败: {str(e)}"}, status=500)

    def _handle_post_chat(self, body: dict):
        agent_name = (body.get("agent_name") or body.get("agent") or "").strip()
        messages = body.get("messages", [])
        if not messages and body.get("prompt"):
            history = body.get("history", [])
            messages = list(history) + [{"role": "user", "content": body.get("prompt")}]

        if not agent_name:
            self._send_json({"success": False, "error": "必须指定目标智能体 (agent_name)"}, status=400)
            return

        reg = Registry.get_instance()
        agent = reg.get_agent(agent_name)
        if not agent:
            self._send_json({"success": False, "error": f"未找到智能体 [{agent_name}]"}, status=404)
            return

        # 执行前置安全门禁审查 (如 LicenseGuard)
        probe_ctx = TaskContext(task_id="web_chat", agent_name=agent.name, payload={"mode": "chat"})
        for guard in agent.pre_guards:
            res = guard.check(probe_ctx)
            if not res.passed:
                self._send_json({
                    "success": False,
                    "blocked": True,
                    "guard_name": guard.name,
                    "error": res.errors[0] if res.errors else "门禁未通过"
                })
                return

        # 检查是否包含定时计划/调度自然语言意图 (双轨协同直达)
        last_user_msg = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                last_user_msg = m.get("content", "").strip()
                break

        if last_user_msg:
            sched_intent = SchedulerEngine.parse_natural_language_schedule(last_user_msg, current_agent=agent_name)
            if sched_intent:
                # 自动落库并注册定时计划
                task = SchedulerEngine.get_instance().add_or_update_task(sched_intent)
                reply = (
                    f"{sched_intent['reply']}\n\n"
                    f"📋 **计划中枢任务卡片已就绪**：\n"
                    f"- **任务 ID**: `{task['id']}`\n"
                    f"- **任务名称**: **{task['name']}**\n"
                    f"- **调度机制**: `{task['schedule_type']}` (规则: `{task['time_value']}`)\n"
                    f"- **执行载荷**: `{task['command']}`\n"
                    f"- **守护状态**: 🟢 已启动后台常驻监控\n\n"
                    f"💡 *您可随时在顶部或右上角「⏰ 计划任务」控制面板中查看倒计时、手动试跑或暂停此规则。*"
                )
                self._send_json({"success": True, "reply": reply, "schedule_created": task})
                return

        try:
            reply = agent.chat(messages)
            self._send_json({"success": True, "reply": reply})
        except QuotaExhaustedError as qe:
            self._send_json({
                "success": False,
                "quota_exhausted": True,
                "error": str(qe)
            }, status=200)
        except DailyLimitExceededError as de:
            self._send_json({
                "success": False,
                "daily_limit_exceeded": True,
                "error": str(de)
            }, status=200)
        except RateLimitError as re:
            self._send_json({
                "success": False,
                "rate_limited": True,
                "error": str(re)
            }, status=200)
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, status=500)

    def _handle_post_chat_stream(self, body: dict):
        agent_name = (body.get("agent_name") or body.get("agent") or "").strip()
        messages = body.get("messages", [])
        if not messages and body.get("prompt"):
            history = body.get("history", [])
            messages = list(history) + [{"role": "user", "content": body.get("prompt")}]

        if not agent_name:
            self._send_json({"success": False, "error": "必须指定目标智能体 (agent_name)"}, status=400)
            return

        reg = Registry.get_instance()
        agent = reg.get_agent(agent_name)
        if not agent:
            self._send_json({"success": False, "error": f"未找到智能体 [{agent_name}]"}, status=404)
            return

        # 执行前置安全门禁审查
        probe_ctx = TaskContext(task_id="web_chat_stream", agent_name=agent.name, payload={"mode": "chat"})
        for guard in agent.pre_guards:
            res = guard.check(probe_ctx)
            if not res.passed:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store')
                self.end_headers()
                block_info = {
                    "blocked": True,
                    "guard_name": guard.name,
                    "error": res.errors[0] if res.errors else "门禁未通过"
                }
                self.wfile.write(f"data: {json.dumps(block_info, ensure_ascii=False)}\n\n".encode('utf-8'))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                return

        # 检查是否包含定时计划/调度自然语言意图
        last_user_msg = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                last_user_msg = m.get("content", "").strip()
                break

        if last_user_msg:
            sched_intent = SchedulerEngine.parse_natural_language_schedule(last_user_msg, current_agent=agent_name)
            if sched_intent:
                task = SchedulerEngine.get_instance().add_or_update_task(sched_intent)
                reply = (
                    f"{sched_intent['reply']}\n\n"
                    f"📋 **计划中枢任务卡片已就绪**：\n"
                    f"- **任务 ID**: `{task['id']}`\n"
                    f"- **任务名称**: **{task['name']}**\n"
                    f"- **调度机制**: `{task['schedule_type']}` (规则: `{task['time_value']}`)\n"
                    f"- **执行载荷**: `{task['command']}`\n"
                    f"- **守护状态**: 🟢 已启动后台常驻监控\n\n"
                    f"💡 *您可随时在顶部或右上角「⏰ 计划任务」控制面板中查看倒计时、手动试跑或暂停此规则。*"
                )
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store')
                self.end_headers()
                self.wfile.write(f"data: {json.dumps({'delta': reply, 'schedule_created': task}, ensure_ascii=False)}\n\n".encode('utf-8'))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                return

        # 启动 SSE 流式推送
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store')
        self.send_header('Connection', 'close')
        self.close_connection = True
        self.end_headers()

        try:
            if hasattr(agent, "stream_chat"):
                for chunk in agent.stream_chat(messages):
                    if chunk:
                        payload = json.dumps({"delta": chunk}, ensure_ascii=False)
                        self.wfile.write(f"data: {payload}\n\n".encode('utf-8'))
                        self.wfile.flush()
            else:
                reply = agent.chat(messages)
                payload = json.dumps({"delta": reply}, ensure_ascii=False)
                self.wfile.write(f"data: {payload}\n\n".encode('utf-8'))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except QuotaExhaustedError as qe:
            err_payload = json.dumps({"error": str(qe), "quota_exhausted": True}, ensure_ascii=False)
            try:
                self.wfile.write(f"data: {err_payload}\n\n".encode('utf-8'))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
        except DailyLimitExceededError as de:
            err_payload = json.dumps({"error": str(de), "daily_limit_exceeded": True}, ensure_ascii=False)
            try:
                self.wfile.write(f"data: {err_payload}\n\n".encode('utf-8'))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
        except RateLimitError as re:
            err_payload = json.dumps({"error": str(re), "rate_limited": True}, ensure_ascii=False)
            try:
                self.wfile.write(f"data: {err_payload}\n\n".encode('utf-8'))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
        except Exception as e:
            err_payload = json.dumps({"error": str(e)}, ensure_ascii=False)
            try:
                self.wfile.write(f"data: {err_payload}\n\n".encode('utf-8'))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass

    def _handle_get_detect_ollama(self):
        available, models = LLMClient.detect_ollama()
        self._send_json({"available": available, "models": models})

    def _handle_get_quota(self):
        qm = QuotaManager.get_instance()
        self._send_json({
            "success": True,
            "quota": qm.get_status().to_dict()
        })

    def _handle_post_quota_refresh(self):
        valid, msg = LLMClient.verify_license()
        qm = QuotaManager.get_instance()
        self._send_json({
            "success": True,
            "quota": qm.get_status().to_dict(),
            "valid": valid,
            "message": msg
        })

    def _handle_post_quota_recharge(self, body: dict):
        raw_pts = body.get("points", 500000)
        try:
            points = int(raw_pts)
        except (ValueError, TypeError):
            self._send_json({"success": False, "error": "算力点数必须为有效整数"}, status=400)
            return

        cm = ConfigManager.get_instance()
        is_dev_env = cm.is_dev_mode or os.environ.get("LITIKJ_DEV_MODE") == "1" or ("PYTEST_CURRENT_TEST" in os.environ and os.environ.get("PYTEST_CURRENT_TEST") != "0")
        voucher_code = (body.get("voucher") or body.get("card_key") or body.get("code") or "").strip()
        # 生产环境防御：严禁无有效凭据直接注入算力 (SEC-05)
        if not is_dev_env:
            if not voucher_code or not (voucher_code.startswith("LITIKJ-RECHARGE-") or voucher_code.startswith("LITIKJ-VIP-")):
                self._send_json({"success": False, "error": "安全拦截：生产环境增加算力点数必须提供合法的官方充值卡密凭证 (SEC-05)"}, status=403)
                return

        if points <= 0 or points > 10_000_000:
            self._send_json({"success": False, "error": "安全拦截：单次充值算力点数超出合法安全范围 (1 ~ 10,000,000)"}, status=400)
            return

        # 如果提供了充值卡密且处于生产环境，向统一鉴权中心核销真实点数 (HUB-03)
        if voucher_code and not is_dev_env:
            try:
                from core.hardware import get_device_fingerprint
                from core.llm import LLMClient
                dev_id = get_device_fingerprint()
                auth_url = "https://www.litikj.com/api/quota/redeem-client"
                if hasattr(cm, 'gateway') and getattr(cm.gateway, 'endpoint', None):
                    ep = cm.gateway.endpoint.rstrip('/')
                    if "api.litikj.com" in ep:
                        ep = ep.replace("api.litikj.com", "www.litikj.com")
                    if ep.endswith("/v1"):
                        auth_url = ep[:-3].rstrip('/') + "/api/quota/redeem-client"
                    elif ep.endswith("/api"):
                        auth_url = ep + "/quota/redeem-client"
                    else:
                        auth_url = ep + "/api/quota/redeem-client"

                req_data = json.dumps({"card_key": voucher_code, "device_id": dev_id}).encode('utf-8')
                req = urllib.request.Request(
                    auth_url,
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                ctx = LLMClient._create_ssl_context()
                with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                    cloud_res = json.loads(resp.read().decode('utf-8'))
                    if cloud_res.get("success"):
                        points = cloud_res.get("points", points)
                    else:
                        self._send_json({"success": False, "error": cloud_res.get("message", "卡密核销失败")}, status=400)
                        return
            except urllib.error.HTTPError as he:
                try:
                    err_body = json.loads(he.read().decode('utf-8'))
                    msg = err_body.get("message") or f"服务端校验失败 ({he.code})"
                except Exception:
                    msg = f"服务端校验失败 ({he.code})"
                self._send_json({"success": False, "error": msg}, status=he.code)
                return
            except Exception as e:
                logger.warning(f"鉴权中心卡密直连核销异常: {e}")
                self._send_json({"success": False, "error": f"无法连接鉴权服务器进行核销，请检查网络连接: {str(e)}"}, status=503)
                return

        qm = QuotaManager.get_instance()
        status = qm.recharge_quota(points)
        self._send_json({
            "success": True,
            "recharged_points": points,
            "quota": status.to_dict(),
            "message": f"🎉 成功注入 {points:,} 算力点数！"
        })

    def _handle_post_llm_test_connection(self, body: dict):
        cm = ConfigManager.get_instance()
        mode = body.get("mode") or cm.gateway.mode or "cloud"
        base_url = body.get("base_url", "")
        api_key = body.get("api_key", "")
        model = body.get("model", "")
        success, latency_ms, message = LLMClient.test_connection(mode=mode, base_url=base_url, api_key=api_key, model=model)
        self._send_json({"success": success, "latency_ms": latency_ms, "message": message})

    def _handle_post_open_outputs(self, body: dict = None):
        if body is None:
            body = {}
        cm = ConfigManager.get_instance()
        target_path_str = (body.get("path") or "").strip()
        action = body.get("action") or "open_dir"

        if target_path_str:
            p = Path(target_path_str).resolve()
            if not p.exists():
                self._send_json({"success": False, "error": f"目标路径不存在: {target_path_str}"}, status=404)
                return

            ws_root = cm.workspace_dir.resolve()
            try:
                is_within_ws = p.is_relative_to(ws_root)
            except AttributeError:
                is_within_ws = str(p).startswith(str(ws_root))

            # 🛡️ 严格沙盒边界：仅允许访问 workspace 物理目录内的产物，严禁任何子串绕过
            if not is_within_ws:
                self._send_json({"success": False, "error": "安全限制：仅允许打开工作区 (workspace) 内的成果产物"}, status=403)
                return

            # 🛡️ 扩展名安全门禁：严格白名单准入，严禁通过 API 直接调用 os.startfile 唤起危险或非受信文件 (SEC-VULN-11)
            if action == "open_file":
                if not p.is_file():
                    self._send_json({"success": False, "error": f"指定目标不是有效文件: {target_path_str}"}, status=400)
                    return
                if p.suffix.lower() not in self.SAFE_OPEN_EXTENSIONS:
                    self._send_json({"success": False, "error": f"安全拦截：严禁通过系统接口直接唤起可执行程序或非受信文件类型 ({p.suffix})"}, status=400)
                    return

            try:
                norm_path = os.path.normpath(str(p))
                if action == "open_file":
                    if sys.platform.startswith("win"):
                        os.startfile(norm_path)
                    else:
                        opener = "open" if sys.platform == "darwin" else "xdg-open"
                        subprocess.Popen([opener, norm_path])
                    self._send_json({"success": True, "path": norm_path, "opened": True, "mode": "file"})
                    return
                else:
                    opened = open_in_file_manager(p)
                    self._send_json({"success": True, "path": norm_path, "opened": opened, "mode": "dir"})
                    return
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
                return

        out_dir = (cm.workspace_dir / "outputs").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            opened = open_in_file_manager(out_dir)
            norm_path = os.path.normpath(str(out_dir))
            self._send_json({"success": True, "path": norm_path, "opened": opened, "mode": "root_dir"})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, status=500)

    def _handle_post_clear_workspace_outputs(self):
        """清空本地测试产生的所有绘画与输出产物，恢复出厂纯净初始态"""
        cm = ConfigManager.get_instance()
        out_dir = (cm.workspace_dir / "outputs").resolve()
        cleared_count = 0
        if out_dir.exists():
            for item in list(out_dir.iterdir()):
                try:
                    if item.is_file():
                        item.unlink()
                        cleared_count += 1
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                        cleared_count += 1
                except Exception:
                    pass
        out_dir.mkdir(parents=True, exist_ok=True)
        self._send_json({
            "success": True,
            "status": "success",
            "message": f"工作区产物已彻底清空 (清理了 {cleared_count} 个历史项目)",
            "cleared_count": cleared_count
        })

    def _handle_post_run(self, body: dict):
        agent_name = body.get("agent_name", "")
        payload = body.get("payload", {})

        if not agent_name:
            self._send_json({"success": False, "error": "必须指定目标智能体 (agent_name)"}, status=400)
            return

        engine = Engine(Registry.get_instance())
        ctx = TaskContext(
            task_id="gui_" + os.urandom(3).hex(),
            agent_name=agent_name,
            payload=payload
        )
        result = engine.dispatch(ctx)

        guards_summary = []
        for gr in result.guard_reports:
            guards_summary.append({
                "name": gr.name,
                "passed": gr.passed,
                "errors": gr.errors,
                "warnings": gr.warnings,
                "metrics": gr.metrics
            })

        self._send_json({
            "success": result.success,
            "message": result.message,
            "data": result.data,
            "guard_reports": guards_summary
        })

    def _handle_get_workflows(self):
        reg = Registry.get_instance()
        wf_data = []
        for wf in reg.list_workflows():
            steps_info = []
            for s in wf.steps:
                node_type = s.__class__.__name__
                steps_info.append({
                    "step_name": getattr(s, "step_name", getattr(s, "title", "未命名步骤")),
                    "agent_name": getattr(s, "agent_name", ""),
                    "node_type": node_type,
                    "gate_id": getattr(s, "gate_id", None),
                    "title": getattr(s, "title", None)
                })
            wf_data.append({
                "name": wf.name,
                "description": wf.description,
                "steps": steps_info
            })
        self._send_json({"workflows": wf_data})

    def _handle_get_suspended_workflows(self):
        """获取当前等待人工审批决策的工作流清单"""
        from core.workflow import Workflow
        suspended_list = Workflow.list_suspended_workflows()
        self._send_json({"suspended_workflows": suspended_list})

    def _handle_get_watcher_status(self):
        """获取通用投递箱与事件监听状态"""
        cm = ConfigManager.get_instance()
        w_cfg = cm.watcher
        from core.watcher import WatcherEngine
        engine = WatcherEngine.get_instance()
        is_running = bool(engine._running) if hasattr(engine, "_running") else w_cfg.enabled
        rules_data = []
        for r in w_cfg.rules:
            rules_data.append({
                "name": r.name,
                "rule_id": r.name,
                "watch_dir": str(r.directory),
                "directory": str(r.directory),
                "file_patterns": r.file_patterns,
                "match_pattern": ", ".join(r.file_patterns),
                "trigger_type": r.trigger_type,
                "target": r.target,
                "enabled": r.enabled,
                "exists": r.directory.exists()
            })
        self._send_json({
            "is_running": is_running,
            "enabled": w_cfg.enabled,
            "poll_interval": w_cfg.poll_interval,
            "settle_seconds": w_cfg.settle_seconds,
            "rules": rules_data
        })

    def _handle_get_watcher_events(self, query_str: str):
        """获取投递箱感知事件 (用于前端对话框实时推送与卡片渲染)"""
        from urllib.parse import parse_qs
        params = parse_qs(query_str)
        since_val = 0.0
        try:
            if "since" in params and params["since"]:
                since_val = float(params["since"][0])
        except Exception:
            since_val = 0.0

        auto_consume = False
        if "auto_consume" in params and params["auto_consume"]:
            auto_consume = params["auto_consume"][0] in ("1", "true", "True")

        from core.watcher import WatcherEventQueue
        eq = WatcherEventQueue.get_instance()
        events = eq.get_unconsumed(since=since_val)

        if auto_consume and events:
            eq.mark_consumed([e["id"] for e in events])

        self._send_json({
            "success": True,
            "events": events,
            "count": len(events)
        })

    def _handle_post_watcher_events_consume(self, body: dict):
        """标记投递箱事件为已消费"""
        event_ids = body.get("event_ids", [])
        if isinstance(event_ids, str):
            event_ids = [event_ids]
        from core.watcher import WatcherEventQueue
        eq = WatcherEventQueue.get_instance()
        eq.mark_consumed(event_ids)
        self._send_json({"success": True, "consumed_ids": event_ids})

    def _handle_post_watcher_reset(self, body: dict):
        """重置投递箱已处理指纹库，允许重新测试已有视频"""
        from core.watcher import WatcherEngine
        target_path = body.get("path")
        WatcherEngine.get_instance().reset_history(Path(target_path) if target_path else None)
        self._send_json({"success": True, "message": "投递箱指纹已重置，现有文件可重新识别触发"})

    def _handle_post_watcher_archive(self, body: dict):
        """一键归档投递箱中已完成的文件至 .archive/ 目录"""
        from core.watcher import WatcherEngine
        target_path = body.get("path", "").strip()
        if not target_path:
            self._send_json({"success": False, "error": "缺少 path 参数"}, status=400)
            return
        res = WatcherEngine.get_instance().archive_file(target_path)
        status_code = 200 if res.get("success") else 400
        self._send_json(res, status=status_code)

    def _handle_get_bili_packages(self):
        """获取本地生成的待审核/已交付 B 站物料包"""
        cm = ConfigManager.get_instance()
        data_file = cm.workspace_dir / "data" / "bili_pending_packages.json"
        packages = []
        if data_file.exists():
            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    packages = json.load(f)
            except Exception:
                packages = []
        self._send_json({"success": True, "packages": packages})

    def _handle_post_bili_upload_draft(self, body: dict):
        """人工一键确认将物料包推送到 B 站草稿箱"""
        package_id = body.get("package_id", "")
        chosen_title = body.get("chosen_title")
        cm = ConfigManager.get_instance()
        data_file = cm.workspace_dir / "data" / "bili_pending_packages.json"
        packages = []
        target_pkg = None
        if data_file.exists():
            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    packages = json.load(f)
            except Exception:
                packages = []

        for p in packages:
            if p.get("package_id") == package_id or p.get("video_stem") == package_id:
                target_pkg = p
                break

        if not target_pkg:
            self._send_json({"success": False, "error": f"未找到物料包 [{package_id}]"}, status=404)
            return

        self._send_json({
            "success": False,
            "error": "当前为开源框架版本，未装载商业 B 站扩展模块"
        }, status=400)
        return

        if up_res.get("success"):
            target_pkg["status"] = "uploaded_to_draft"
            target_pkg["bili_url"] = up_res.get("target", "")
            try:
                with open(data_file, "w", encoding="utf-8") as f:
                    json.dump(packages, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            self._send_json({"success": True, "message": f"🎉 成功推入 B 站草稿箱！{up_res.get('target', '')}"})
        else:
            self._send_json({
                "success": False,
                "error": up_res.get("message", "上传失败"),
                "detail": up_res.get("error", "")
            }, status=500)

    def _handle_post_bili_open_package(self, body: dict):
        bundle_dir = (body.get("bundle_dir") or "").strip()
        if not bundle_dir:
            self._send_json({"success": False, "error": "物料路径不能为空"}, status=400)
            return

        target_path = Path(bundle_dir).resolve()
        cm = ConfigManager.get_instance()
        ws_root = cm.workspace_dir.resolve()
        proj_root = cm.root_dir.resolve()

        # 🛡️ 严格沙箱校验：严禁唤起系统核心目录或跨目录逃逸 (SEC-07)
        is_safe = False
        try:
            if target_path.is_relative_to(ws_root) or target_path.is_relative_to(proj_root):
                is_safe = True
        except (ValueError, AttributeError):
            is_safe = str(target_path).startswith(str(ws_root)) or str(target_path).startswith(str(proj_root))

        if not is_safe:
            self._send_json({"success": False, "error": "安全拦截：严禁打开工作区沙箱以外的敏感目录 (SEC-07)"}, status=403)
            return

        if target_path.exists():
            open_in_file_manager(target_path)
            self._send_json({"success": True, "message": "已打开物料文件夹"})
        else:
            self._send_json({"success": False, "error": "目录不存在"}, status=404)

    def _handle_post_workflow_run(self, body: dict):
        wf_name = body.get("workflow_name", "")
        payload = body.get("payload", {})

        reg = Registry.get_instance()
        wf = reg.get_workflow(wf_name)
        if not wf:
            self._send_json({"success": False, "error": f"未找到多智能体流水线 [{wf_name}]"}, status=404)
            return

        engine = Engine(reg)
        wf_result = wf.execute(payload, engine)

        self._send_json({
            "success": wf_result.success,
            "suspended": wf_result.suspended,
            "status": wf_result.status,
            "message": wf_result.message,
            "workflow_id": wf_result.workflow_id,
            "workflow_name": wf_result.workflow_name,
            "steps_completed": wf_result.steps_completed,
            "total_steps": wf_result.total_steps,
            "gate_info": wf_result.gate_info,
            "circuit_breaker_agent": wf_result.circuit_breaker_agent,
            "elapsed_time": wf_result.elapsed_time,
            "final_data": wf_result.final_data,
            "step_records": wf_result.step_records
        })

    def _handle_post_workflow_resume(self, body: dict):
        """恢复挂起等待人工决策的工作流"""
        workflow_id = body.get("workflow_id", "")
        decision = body.get("decision", {})

        if not workflow_id:
            self._send_json({"success": False, "error": "缺少 workflow_id"}, status=400)
            return

        from core.workflow import Workflow
        engine = Engine(Registry.get_instance())
        wf_result = Workflow.resume_by_id(workflow_id, decision, engine)

        self._send_json({
            "success": wf_result.success,
            "suspended": wf_result.suspended,
            "status": wf_result.status,
            "message": wf_result.message,
            "workflow_id": wf_result.workflow_id,
            "workflow_name": wf_result.workflow_name,
            "steps_completed": wf_result.steps_completed,
            "total_steps": wf_result.total_steps,
            "gate_info": wf_result.gate_info,
            "circuit_breaker_agent": wf_result.circuit_breaker_agent,
            "elapsed_time": wf_result.elapsed_time,
            "final_data": wf_result.final_data,
            "step_records": wf_result.step_records
        })

    # ================= 定时调度接口实现 =================

    def _handle_get_schedules(self, query_str: str = ""):
        from urllib.parse import parse_qs
        agent_name = None
        if query_str:
            params = parse_qs(query_str)
            agent_name = params.get("agent_name", [None])[0]
        engine = SchedulerEngine.get_instance()
        tasks = engine.list_tasks(agent_name=agent_name)
        self._send_json({"success": True, "tasks": tasks, "total": len(tasks)})

    def _handle_post_schedule(self, body: dict):
        engine = SchedulerEngine.get_instance()
        task = engine.add_or_update_task(body)
        self._send_json({"success": True, "task": task})

    def _handle_post_schedule_toggle(self, body: dict):
        task_id = body.get("id") or body.get("task_id", "")
        enabled = body.get("enabled", None)
        if not task_id:
            self._send_json({"success": False, "error": "缺少 task_id"}, status=400)
            return
        engine = SchedulerEngine.get_instance()
        new_state = engine.toggle_task(task_id, enabled)
        self._send_json({"success": True, "id": task_id, "enabled": new_state})

    def _handle_post_schedule_run_now(self, body: dict):
        task_id = body.get("id") or body.get("task_id", "")
        if not task_id:
            self._send_json({"success": False, "error": "缺少 task_id"}, status=400)
            return
        engine = SchedulerEngine.get_instance()
        result = engine.execute_task_now(task_id)
        self._send_json(result)

    def _handle_post_schedule_delete(self, body: dict):
        task_id = body.get("id") or body.get("task_id", "")
        if not task_id:
            self._send_json({"success": False, "error": "缺少 task_id"}, status=400)
            return
        engine = SchedulerEngine.get_instance()
        ok = engine.delete_task(task_id)
        self._send_json({"success": ok, "id": task_id})

    # ================= Windows 开机自启动管理 =================

    def _check_autostart_safe(self) -> bool:
        try:
            from scripts.setup_autostart import is_enabled
            return is_enabled()
        except Exception:
            return False

    def _handle_get_autostart(self):
        self._send_json({"enabled": self._check_autostart_safe()})

    def _handle_post_autostart(self, body: dict):
        try:
            from scripts.setup_autostart import is_enabled, enable, disable
            target_state = body.get("enabled")
            if target_state is None:
                target_state = not is_enabled()

            if target_state:
                ok = enable()
                msg = "已成功开启 Windows 开机静默自启动"
            else:
                ok = disable()
                msg = "已成功关闭开机自启动"

            self._send_json({
                "success": ok,
                "enabled": is_enabled(),
                "message": msg
            })
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, status=500)

    def _send_json(self, data: dict, status: int = 200):
        resp_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(resp_bytes)))

        # 🛡️ CORS 安全响应：仅对受信任白名单 Origin 响应 Access-Control-Allow-Origin，绝不反射外部任意恶意来源
        origin = self.headers.get("Origin", "")
        if origin and self._is_origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-Agent-OS-Token")

        self.end_headers()
        self.wfile.write(resp_bytes)


# 向后兼容别名
ChatboxRequestHandler = KernelApiRequestHandler


def start_server(host: str = "127.0.0.1", port: int = 8765, token: Optional[str] = None):
    """启动本地轻量 HTTP/SSE 微内核 API 服务"""
    if token:
        set_server_token(token)
    else:
        get_server_token()
    Registry.get_instance().auto_discover()
    SchedulerEngine.get_instance().start_daemon()
    cm = ConfigManager.get_instance()
    if cm.watcher.enabled:
        from core.watcher import WatcherEngine
        WatcherEngine.get_instance().start_in_thread()
    server = ThreadingHTTPServer((host, port), KernelApiRequestHandler)
    server.token = get_server_token()
    print(f"🚀 [微内核引擎] API 核心服务已就绪: http://{host}:{port}")
    return server
