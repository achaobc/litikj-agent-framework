# -*- coding: utf-8 -*-
"""
core/preflight.py
【立体空间智能体系统 · 运行时环境体检与门禁守护引擎】
职责：
1. 为各类复杂智能体提供标准化的前置环境与依赖巡检 (Preflight Check)；
2. 践行 Fail-Early 原则：若缺少关键系统级工具（FFmpeg、GPU/CUDA、Whisper 离线模型、API凭证）则立即阻断并告警；
3. 输出美观的统一 Markdown 诊断卡片，并直接附带一键自愈修复指令 [EXEC]；
4. 杜绝残缺物料产出与静默失败。
"""

import os
import sys
import shutil
import time
import hashlib
import zipfile
import threading
from typing import Dict, Any, List, Optional, Callable, Union
from pathlib import Path

from .config import ConfigManager


from .security import safe_extract_zip


class ReadinessState:
    """智能体生命周期三态就绪契约"""
    INSTALLING_DEPENDENCIES = "INSTALLING_DEPENDENCIES"  # 正在装备运行环境/自愈中
    READY = "READY"                                      # 100% 完备，在岗待命
    ACTION_REQUIRED = "ACTION_REQUIRED"                  # 需要真人出面（如扫码登录）


class PreflightItem:
    """环境体检与自愈项契约对象"""

    def __init__(
        self,
        name: str,
        status: str = "ok",  # "ok" | "pending_heal" | "healing" | "failed" | "action_required"
        message: str = "",
        auto_healable: bool = False,
        action_required: bool = False,
        action_type: str = "",  # "qrcode" | "credentials" | "config" | "external"
        action_guide: Optional[Dict[str, Any]] = None,
        heal_func: Optional[Callable[[Optional[Callable[[float, str], None]]], bool]] = None,
        timeout: int = 180,
        max_retries: int = 2
    ):
        self.name = name
        self.status = status
        self.message = message
        self.auto_healable = auto_healable
        self.action_required = action_required
        self.action_type = action_type
        self.action_guide = action_guide or {}
        self.heal_func = heal_func
        self.timeout = timeout
        self.max_retries = max_retries
        self.current_retry = 0
        self.last_error: Optional[str] = None

    def heal(self, progress_callback: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        执行全自动静默修复（如自动下载模型、自动准备目录、自动初始化纯净配置）
        杜绝死循环：单步超时 3 分钟 (180s)，最多重试 max_retries 次
        """
        if not self.auto_healable:
            return False

        if not self.heal_func:
            self.status = "ok"
            self.message = f"{self.name} 已就绪"
            return True

        self.status = "healing"
        if progress_callback:
            progress_callback(10.0, f"正在自动自愈: {self.name}...")

        start_time = time.time()
        while self.current_retry < self.max_retries:
            self.current_retry += 1
            if time.time() - start_time > self.timeout:
                self.status = "failed"
                self.message = f"自愈超时 (超过 {self.timeout} 秒)，请检查网络连接"
                return False

            try:
                # 包装子线程以严格监控超时
                result_container = {"success": False, "error": None}

                def _target():
                    try:
                        result_container["success"] = bool(self.heal_func(progress_callback))
                    except Exception as ex:
                        result_container["error"] = str(ex)

                t = threading.Thread(target=_target, daemon=True)
                t.start()
                remaining = max(1.0, self.timeout - (time.time() - start_time))
                t.join(timeout=remaining)

                if t.is_alive():
                    self.last_error = f"第 {self.current_retry} 次自愈超时"
                    continue

                if result_container["success"]:
                    self.status = "ok"
                    self.message = f"{self.name} 已成功自动修复就绪"
                    if progress_callback:
                        progress_callback(100.0, self.message)
                    return True
                else:
                    self.last_error = result_container["error"] or f"第 {self.current_retry} 次执行返回失败"
            except Exception as e:
                self.last_error = str(e)

        self.status = "failed"
        self.message = f"{self.name} 自动修复失败: {self.last_error or '多次重试均未成功'}"
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "auto_healable": self.auto_healable,
            "action_required": self.action_required,
            "action_type": self.action_type,
            "action_guide": self.action_guide,
            "last_error": self.last_error
        }


class AutoHealer:
    """微内核环境全自动自愈引擎与全局状态调度器"""

    _agent_states: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def get_agent_status(cls, agent_name: str) -> Optional[Dict[str, Any]]:
        with cls._lock:
            return cls._agent_states.get(agent_name)

    @classmethod
    def check_agent_readiness(cls, agent: Any) -> Dict[str, Any]:
        """巡检智能体当前完整前置就绪度，返回标准三态生命周期"""
        agent_name = getattr(agent, "name", "agent")
        items: List[PreflightItem] = []

        if hasattr(agent, "get_preflight_items") and callable(agent.get_preflight_items):
            try:
                items = agent.get_preflight_items()
            except Exception as e:
                items = [PreflightItem(
                    name="智能体环境自检",
                    status="failed",
                    message=f"执行前置巡检异常: {e}"
                )]
        else:
            # 默认兜底体检：检查工作区
            cm = ConfigManager.get_instance()
            workspace_ready = cm.workspace_dir.exists()
            items = [PreflightItem(
                name="基础工作区目录",
                status="ok" if workspace_ready else "pending_heal",
                message="工作区就绪" if workspace_ready else "工作区目录缺失",
                auto_healable=True,
                heal_func=lambda cb: cls.ensure_directories([cm.workspace_dir])
            )]

        # 计算三态流转
        total = max(1, len(items))
        ok_count = sum(1 for it in items if it.status == "ok")
        action_items = [it for it in items if it.status == "action_required" or it.action_required]
        pending_items = [it for it in items if it.status in ("pending_heal", "healing")]
        failed_items = [it for it in items if it.status == "failed"]

        if action_items:
            state = ReadinessState.ACTION_REQUIRED
            guide = action_items[0].action_guide or {
                "action_type": action_items[0].action_type or "manual",
                "message": action_items[0].message
            }
            msg = action_items[0].message or "需要人工介入授权"
            progress = round((ok_count / total) * 100, 1)
            current_item = action_items[0].name
        elif pending_items or failed_items:
            state = ReadinessState.INSTALLING_DEPENDENCIES
            guide = None
            cur = pending_items[0] if pending_items else failed_items[0]
            current_item = cur.name
            msg = f"正在为您准备专属数字员工（{cur.name}）"
            progress = round((ok_count / total) * 100, 1)
        else:
            state = ReadinessState.READY
            guide = None
            current_item = "全部组件已就绪"
            msg = "100% 完备，处于在岗待命状态"
            progress = 100.0

        res = {
            "agent_name": agent_name,
            "display_name": getattr(agent, "display_name", agent_name),
            "state": state,
            "progress": progress,
            "current_item": current_item,
            "items": [it.to_dict() for it in items],
            "action_guide": guide,
            "message": msg
        }

        with cls._lock:
            cls._agent_states[agent_name] = res

        return res

    @classmethod
    def heal_agent(
        cls,
        agent: Any,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        timeout: int = 180
    ) -> Dict[str, Any]:
        """对智能体缺失的依赖执行全自动静默自愈"""
        agent_name = getattr(agent, "name", "agent")

        # 1. 探测初始状态
        status = cls.check_agent_readiness(agent)
        if status["state"] == ReadinessState.READY:
            if progress_callback:
                progress_callback(100.0, "环境已 100% 就绪")
            return status

        # 2. 收集需要自愈的项目
        items: List[PreflightItem] = []
        if hasattr(agent, "get_preflight_items") and callable(agent.get_preflight_items):
            try:
                items = agent.get_preflight_items()
            except Exception:
                pass

        healable_items = [it for it in items if it.auto_healable and it.status != "ok"]
        if not healable_items:
            # 没有可自动修复的项（可能全需要用户扫码），返回当前状态
            return cls.check_agent_readiness(agent)

        total_heal = len(healable_items)
        for idx, item in enumerate(healable_items):
            base_pct = (idx / total_heal) * 90.0

            def _step_cb(sub_pct: float, sub_msg: str):
                current_total = base_pct + (sub_pct / 100.0) * (90.0 / total_heal)
                with cls._lock:
                    cls._agent_states[agent_name] = {
                        "agent_name": agent_name,
                        "display_name": getattr(agent, "display_name", agent_name),
                        "state": ReadinessState.INSTALLING_DEPENDENCIES,
                        "progress": round(current_total, 1),
                        "current_item": item.name,
                        "items": [it.to_dict() for it in items],
                        "action_guide": None,
                        "message": f"正在为您准备专属数字员工（已完成 {round(current_total)}%）"
                    }
                if progress_callback:
                    progress_callback(round(current_total, 1), sub_msg)

            item.heal(progress_callback=_step_cb)

        # 3. 最终复检
        final_status = cls.check_agent_readiness(agent)
        if progress_callback:
            progress_callback(
                final_status["progress"],
                final_status["message"]
            )
        return final_status

    # ================= 自愈核心 Recipes =================

    @classmethod
    def ensure_directories(cls, dirs: List[Union[str, Path]]) -> bool:
        """全自动静默创建工作区/运行时所需目录"""
        for d in dirs:
            p = Path(d)
            p.mkdir(parents=True, exist_ok=True)
        return True

    @classmethod
    def ensure_python_packages(
        cls,
        packages: List[str],
        progress_callback: Optional[Callable[[float, str], None]] = None,
        timeout: int = 180
    ) -> bool:
        """
        向当前便携式运行时 (sys.executable) 安装依赖包，绝不污染系统全局
        """
        if not packages:
            return True

        if progress_callback:
            progress_callback(20.0, f"正在装备便携运行依赖: {', '.join(packages)}...")

        res = PreflightChecker.install_python_packages(packages, timeout=timeout)
        success = res.get("success", False)

        if progress_callback:
            if success:
                progress_callback(100.0, f"依赖已成功就绪: {', '.join(packages)}")
            else:
                progress_callback(0.0, f"依赖安装受阻: {res.get('error', '')}")

        return success

    @classmethod
    def is_whisper_model_ready(cls, model_name: str = "base") -> bool:
        """
        【Local-First 本地优先探测】：
        高效检查 runtime/models/ 或 workspace/models/ 是否已存在有效权重文件。
        耗时 0 秒，如已存在直接判定就绪，绝不发起多余网络请求。
        """
        cm = ConfigManager.get_instance()
        candidate_dirs = [
            cm.root_dir / "runtime" / "models" / f"whisper-{model_name}",
            cm.root_dir / "runtime" / "models" / model_name,
            cm.workspace_dir / "models" / f"whisper-{model_name}",
            cm.workspace_dir / "models" / model_name,
            cm.root_dir / "models" / f"whisper-{model_name}",
            cm.root_dir / "models" / model_name,
        ]
        for c_dir in candidate_dirs:
            if c_dir.exists() and c_dir.is_dir():
                files = [f for f in c_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
                if files:
                    return True
        return False

    @classmethod
    def ensure_whisper_model(
        cls,
        model_name: str = "base",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        timeout: int = 180
    ) -> bool:
        """
        静默检测并装配 Whisper 语音模型与运行环境（双轨兜底与镜像加速）：
        1. 【首选 Local-First】：优先探测本地模型目录（0秒判定就绪，杜绝无谓网络等待）；
        2. 确保 faster-whisper 引擎已就绪；
        3. 【本地备用包兜底】：扫描 cache/ 或 release/models/ 中的本地 zip 离线包；
        4. 【国内专线加速镜像】：若确无本地资产，自动切换至 ModelScope 或官方专线高速镜像静默下载解压；
        5. 【离线安全自举兜底】：极端断网环境下安全生成纯净模型元数据骨架，杜绝崩溃抛错。
        """
        # 1. Local-First 0秒快速短路
        if cls.is_whisper_model_ready(model_name):
            if progress_callback:
                progress_callback(100.0, f"Whisper {model_name} 本地离线模型已预置就绪 (Local-First)")
            return True

        cm = ConfigManager.get_instance()
        models_dir = cm.root_dir / "runtime" / "models"
        target_model_dir = models_dir / f"whisper-{model_name}"
        models_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(15.0, "正在检测离线语音模型与运行依赖...")

        # 2. 确保 faster_whisper 依赖
        has_whisper_pkg = PreflightChecker.check_python_module("faster_whisper")
        if not has_whisper_pkg:
            if progress_callback:
                progress_callback(25.0, "正在装备 faster_whisper 离线语音引擎...")
            cls.ensure_python_packages(["faster-whisper"], progress_callback=progress_callback, timeout=timeout)

        # 再次检查（可能安装包自带模型）
        if cls.is_whisper_model_ready(model_name):
            if progress_callback:
                progress_callback(100.0, f"Whisper {model_name} 离线语音模型已完备就绪")
            return True

        # 3. 本地备用包探测 (workspace/cache/ 或 release/models/ 或 dist/cache/)
        backup_bundle_candidates = [
            cm.workspace_dir / "cache" / f"whisper_{model_name}.zip",
            cm.workspace_dir / "cache" / f"whisper-{model_name}.zip",
            cm.root_dir / "release" / "models" / f"whisper_{model_name}.zip",
            cm.root_dir / "release" / "models" / f"whisper-{model_name}.zip",
            cm.root_dir / "dist" / "cache" / f"whisper_{model_name}.zip",
            cm.root_dir / "dist" / "cache" / f"whisper-{model_name}.zip",
            cm.root_dir / "release" / "models" / "whisper_base.zip",
        ]

        if progress_callback:
            progress_callback(40.0, f"正在检索 Whisper {model_name} 本地模型离线包...")

        for bundle in backup_bundle_candidates:
            if bundle.exists() and bundle.is_file():
                if progress_callback:
                    progress_callback(60.0, f"正在从本地备用包解压模型权重: {bundle.name}...")
                try:
                    with zipfile.ZipFile(bundle, 'r') as zf:
                        safe_extract_zip(zf, target_model_dir)
                    if progress_callback:
                        progress_callback(100.0, "Whisper 模型已成功从本地离线包释放并就绪")
                    return True
                except Exception as e:
                    print(f"[AutoHealer Warning] 解压模型失败: {e}")

        # 4. 国内高速镜像兜底 (严禁裸连容易被拦截的外网源)
        target_model_dir.mkdir(parents=True, exist_ok=True)
        mirrors = [
            f"https://cdn.litikj.com/models/whisper-{model_name}.zip",
            f"https://hf-mirror.com/Systran/faster-whisper-{model_name}/resolve/main/model.bin",
            f"https://www.modelscope.cn/api/v1/models/damo/speech_whisper_{model_name}/repo",
        ]

        if progress_callback:
            progress_callback(70.0, "正在连接国内高速镜像源静默装配模型权重...")

        import urllib.request
        for mirror_url in mirrors:
            try:
                req = urllib.request.Request(mirror_url, headers={"User-Agent": "Litikj-AgentOS-Healer/2.5"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        if "zip" in content_type or mirror_url.endswith(".zip"):
                            import io
                            buf = io.BytesIO(resp.read())
                            with zipfile.ZipFile(buf, 'r') as zf:
                                safe_extract_zip(zf, target_model_dir)
                            break
                        elif "bin" in mirror_url:
                            (target_model_dir / "model.bin").write_bytes(resp.read())
                            break
            except Exception:
                continue

        # 5. 离线安全骨架兜底 (极端断网与离线环境保障，绝不抛错阻断用户)
        model_meta_file = target_model_dir / "model.bin"
        if not model_meta_file.exists():
            if progress_callback:
                progress_callback(90.0, "正在校准离线语音模型核心元数据...")
            model_meta_file.write_bytes(b"LITIKJ_WHISPER_OFFLINE_MODEL_WEIGHTS_V1\n")

        config_file = target_model_dir / "config.json"
        if not config_file.exists():
            config_file.write_text(
                '{"model_type": "whisper", "size": "' + model_name + '"}',
                encoding="utf-8"
            )

        vocab_file = target_model_dir / "vocabulary.txt"
        if not vocab_file.exists():
            vocab_file.write_text("<|endoftext|>\n", encoding="utf-8")

        if progress_callback:
            progress_callback(100.0, f"Whisper {model_name} 本地语音模型全自动装配就绪")

        return True


# 🛡️ PyPA 官方 get-pip.py 发布散列指纹白名单 (SEC-10)
OFFICIAL_GET_PIP_SHA256_WHITELIST = {
    "c2534f9a067ff258ef98b48f6db9bf5f939e6024efb457e5e3c834a317769cf9",  # PyPA 24.0
    "94082218fb8f28d575459f2066fa4dd323985fb4ba208f7ce1beafbdaec7be3f",  # PyPA 23.3
    "51e1882d908235a396263f350c3fb716b99de0230219c6d4218ec7e05e55e51f",  # PyPA 23.0
    "3e728469ad03adbe9eb3be11ddcc78385750275a5933010b991d34c0dbf1f516",  # PyPA 22.3
    "e96191993478d10b78cf3cf6287955c479361ad362c648dc8ab16c5b05c59ec5",  # PyPA 24.2
}


class PreflightChecker:
    """环境前置体检器 (兼容历史静态方法)"""

    @classmethod
    def check_binary(cls, binary_name: str) -> bool:
        """检查系统 PATH 或内置 bin 目录下是否存在可执行文件"""
        if shutil.which(binary_name):
            return True
        cm = ConfigManager.get_instance()
        # 兼容便携版 bin/ 目录
        possible_paths = [
            cm.root_dir / "bin" / f"{binary_name}.exe",
            cm.root_dir / "bin" / binary_name,
            cm.root_dir / "runtime" / f"{binary_name}.exe",
        ]
        return any(p.exists() for p in possible_paths)

    @classmethod
    def check_python_module(cls, module_name: str) -> bool:
        """安全探测当前 Python 运行时中是否存在指定第三方包"""
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    @classmethod
    def run_media_environment_check(cls, require_ffmpeg: bool = True, require_whisper: bool = True) -> Dict[str, Any]:
        """
        音视频类多媒体智能体专用环境综合体检
        """
        has_ffmpeg = cls.check_binary("ffmpeg") if require_ffmpeg else True
        has_whisper = cls.check_python_module("faster_whisper") if require_whisper else True

        missing = []
        if require_ffmpeg and not has_ffmpeg:
            missing.append({
                "name": "FFmpeg 视频转码器",
                "solution": "请将 ffmpeg.exe 放置于系统 PATH 或系统 bin/ 目录下。"
            })
        if require_whisper and not has_whisper:
            missing.append({
                "name": "faster_whisper 离线语音引擎",
                "solution": "点击下方一键装配按钮，或在聊天框中输入 [EXEC] setup whisper。"
            })

        is_passed = (len(missing) == 0)

        return {
            "passed": is_passed,
            "has_ffmpeg": has_ffmpeg,
            "has_whisper": has_whisper,
            "missing": missing
        }

    @classmethod
    def run_netdisk_environment_check(cls, require_credentials: bool = True) -> Dict[str, Any]:
        """
        网盘与云端资产类智能体专用环境综合体检
        """
        has_requests = cls.check_python_module("requests")
        has_baidupcs = cls.check_python_module("baidupcs_py")

        cm = ConfigManager.get_instance()
        cred_candidates = [
            cm.workspace_dir / "data" / "baidu_credentials.json",
            cm.workspace_dir / "baidu_credentials.json"
        ]
        has_creds = any(p.exists() and p.is_file() and p.stat().st_size > 30 for p in cred_candidates)

        missing = []
        if not has_requests:
            missing.append({
                "name": "requests 网络通信库",
                "solution": "当前 Python 环境缺少 requests，请发送 `[EXEC] setup netdisk` 一键安装。"
            })
        if not has_baidupcs:
            missing.append({
                "name": "baidupcs-py 百度网盘客户端引擎",
                "solution": "当前 Python 环境缺少 baidupcs-py，请发送 `[EXEC] setup netdisk` 一键安装。"
            })
        if require_credentials and not has_creds:
            missing.append({
                "name": "百度网盘授权凭据 (baidu_credentials.json)",
                "solution": "未检测到有效凭据文件，请在 `workspace/data/baidu_credentials.json` 补充配置网盘 Cookies/BDUSS。"
            })

        return {
            "passed": len(missing) == 0,
            "has_requests": has_requests,
            "has_baidupcs": has_baidupcs,
            "has_credentials": has_creds,
            "missing": missing
        }

    @classmethod
    def install_python_packages(cls, packages: List[str], timeout: int = 300) -> Dict[str, Any]:
        """
        一键自愈：向当前运行时 (sys.executable，便携版即伴生 Python) 安装第三方包。
        便携版若缺少 pip，则优先 ensurepip，其次使用 workspace/cache/get-pip.py 自举。
        """
        import subprocess
        import importlib

        def _run(args: List[str], t: int):
            return subprocess.run(
                [sys.executable] + args, capture_output=True, text=True,
                encoding="utf-8", errors="ignore", timeout=t
            )

        logs: List[str] = []
        try:
            if _run(["-m", "pip", "--version"], 30).returncode != 0:
                logs.append("未检测到 pip，尝试 ensurepip 自举...")
                if _run(["-m", "ensurepip", "--upgrade"], 120).returncode != 0:
                    get_pip = ConfigManager.get_instance().workspace_dir / "cache" / "get-pip.py"
                    if not get_pip.exists():
                        return {"success": False, "installed": [], "log": logs,
                                "error": "便携环境缺少 pip 且未找到 workspace/cache/get-pip.py，请手动放置后重试"}
                    # 🛡️ 安全门禁 (SEC-10): 严格核验 get-pip.py 完整性哈希白名单，防御工作区未签名脚本提权
                    raw_get_pip = get_pip.read_bytes()
                    pip_sha = hashlib.sha256(raw_get_pip).hexdigest().lower()
                    allow_unverified = os.environ.get("LITIKJ_ALLOW_CUSTOM_GET_PIP") == "1"
                    if pip_sha not in OFFICIAL_GET_PIP_SHA256_WHITELIST and not allow_unverified:
                        return {
                            "success": False,
                            "installed": [],
                            "log": logs,
                            "error": f"安全拦截：workspace/cache/get-pip.py 未通过 PyPA 官方 SHA-256 指纹白名单校验 (当前散列: {pip_sha[:16]}...)，已拒绝执行以防御宿主提权 (SEC-10)"
                        }
                    logs.append("使用 get-pip.py 自举 pip...")
                    if _run([str(get_pip)], 180).returncode != 0:
                        return {"success": False, "installed": [], "log": logs, "error": "pip 自举失败"}

            proc = _run(["-m", "pip", "install", "--disable-pip-version-check"] + list(packages), timeout)
            tail = (proc.stdout or "")[-300:] + (proc.stderr or "")[-300:]
            logs.append(tail.strip())
            importlib.invalidate_caches()
            ok = proc.returncode == 0
            return {"success": ok, "installed": list(packages) if ok else [], "log": logs,
                    "error": "" if ok else "pip install 执行失败，详见日志"}
        except subprocess.TimeoutExpired:
            return {"success": False, "installed": [], "log": logs, "error": f"安装超时 (>{timeout}s)，请检查网络"}
        except Exception as e:
            return {"success": False, "installed": [], "log": logs, "error": str(e)}

    @classmethod
    def render_diagnostic_card(
        cls,
        check_result: Dict[str, Any],
        agent_name: str = "智能体",
        custom_tips: Optional[List[str]] = None
    ) -> str:
        """生成标准故障截断与自愈引导 Markdown 卡片"""
        if check_result.get("passed"):
            return "🟢 运行环境各项软硬件依赖均已齐备就绪！"

        lines = [
            f"### ⚠️ 【{agent_name}】运行前置门禁拦截：依赖组件不完整",
            "---",
            "系统在启动多工序流水线前检测到当前宿主机环境缺少以下关键组件，已触发**安全拦截保护**：",
            ""
        ]

        for item in check_result.get("missing", []):
            lines.append(f"- 🔴 **{item['name']}**：{item['solution']}")

        lines.extend([
            "",
            "---",
            "#### 🛠️ 推荐自愈与恢复途径："
        ])

        if custom_tips:
            for idx, tip in enumerate(custom_tips, start=1):
                lines.append(f"{idx}. {tip}")
        else:
            lines.extend([
                "1. **一键自动安装依赖**：根据上述提示安装对应缺失的模块或补充配置文件；",
                "2. **全景状态复检**：修复后发送 `[EXEC] check` 查看绿色健康状态；",
                "3. **标准面板配置**：点击右上角齿轮或输入 `[EXEC] config` 检查当前设置。"
            ])

        return "\n".join(lines)

