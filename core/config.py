# -*- coding: utf-8 -*-
"""
core/config.py
【立体空间智能体系统 · 框架配置管理中枢】
职责：
1. 向上智能探测项目根目录（寻找 configs/framework.yaml）；
2. 读取框架级配置（含系统参数、Fast-Path 协议与 Gateway 网关授权）；
3. 提供强类型单例访问，彻底杜绝死路径硬编码。
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import yaml
except ImportError:
    yaml = None


def find_project_root() -> Path:
    """自适应向上寻找包含 configs/framework.yaml 的根目录"""
    env_root = os.getenv("LITIKJ_PROJECT_ROOT")
    if env_root and Path(env_root).exists():
        return Path(env_root).resolve()

    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "configs" / "framework.yaml").exists():
            return parent.resolve()

    try:
        return current.parents[1].resolve()
    except IndexError:
        return Path.cwd().resolve()


class GatewayConfig:
    """大模型网关与商业授权配置容器"""
    def __init__(self, raw: dict):
        self.endpoint: str = os.environ.get("LITIKJ_GATEWAY_ENDPOINT", "").strip() or raw.get("endpoint", "https://api.litikj.com/v1")
        
        # 🛡️ 凭证保护：优先从环境变量读取官方卡密与模型私有 Key，杜绝明文硬编码泄露风险
        env_license = os.environ.get("LITIKJ_LICENSE_KEY", "").strip()
        self.license_key: str = env_license if env_license else raw.get("license_key", "")
        self.mode: str = raw.get("mode", "cloud")  # "cloud" 或 "custom"
        
        self.max_input_chars: int = int(raw.get("max_input_chars", 25000))
        self.rate_limit_interval: float = float(raw.get("rate_limit_interval", 0.5))

        custom = raw.get("custom", {})
        self.custom_provider: str = custom.get("provider", "custom")
        
        env_api_key = (
            os.environ.get("DEEPSEEK_API_KEY", "").strip() or
            os.environ.get("OPENAI_API_KEY", "").strip() or
            os.environ.get("LITIKJ_CUSTOM_API_KEY", "").strip()
        )
        self.custom_api_key: str = env_api_key if env_api_key else custom.get("api_key", "")
        self.custom_base_url: str = os.environ.get("LITIKJ_CUSTOM_BASE_URL", "").strip() or custom.get("base_url", "https://api.deepseek.com/v1")
        self.custom_model: str = os.environ.get("LITIKJ_CUSTOM_MODEL", "").strip() or custom.get("model", "deepseek-chat")
        self.custom_temperature: float = float(custom.get("temperature", 0.7))

    def is_active(self) -> bool:
        """检查授权或配置是否就绪"""
        if self.mode == "custom":
            is_local = "127.0.0.1" in self.custom_base_url or "localhost" in self.custom_base_url
            if is_local:
                return bool(self.custom_base_url.strip())
            return bool(self.custom_api_key.strip())
        return bool(self.license_key.strip())

    def get_masked_license(self) -> str:
        """返回脱敏的激活码展示"""
        key = self.license_key.strip()
        if not key:
            return "未配置"
        if len(key) <= 8:
            return "****"
        return f"{key[:4]}****{key[-4:]}"


class WatcherRule:
    """通用投递箱监听规则"""
    def __init__(self, raw: dict, root_dir: Path):
        self.name: str = raw.get("name", "unnamed_rule")
        dir_val = raw.get("directory", "workspace/drop_box")
        p = Path(dir_val)
        self.directory: Path = p if p.is_absolute() else (root_dir / p).resolve()
        self.file_patterns: List[str] = raw.get("file_patterns", ["*.*"])
        self.trigger_type: str = raw.get("trigger_type", "workflow")  # "workflow" | "agent"
        self.target: str = raw.get("target", "")
        self.enabled: bool = bool(raw.get("enabled", True))
        self.min_file_size_mb: float = float(raw.get("min_file_size_mb", 0.0))


class WatcherConfig:
    """通用投递箱与外设监听引擎配置容器"""
    def __init__(self, raw: dict, root_dir: Path):
        self.enabled: bool = bool(raw.get("enabled", False))
        self.poll_interval: float = float(raw.get("poll_interval", 2.0))
        self.settle_seconds: float = float(raw.get("settle_seconds", 2.0))
        self.rules: List[WatcherRule] = [
            WatcherRule(r, root_dir) for r in raw.get("rules", []) if isinstance(r, dict)
        ]


class ConfigManager:
    """系统框架配置管理器 (单例模式)"""
    _instance: Optional['ConfigManager'] = None

    def __init__(self):
        self.root_dir: Path = find_project_root()
        self.config_path: Path = self.root_dir / "configs" / "framework.yaml"
        self.raw_config: Dict[str, Any] = self._load_yaml()

        # 🛡️ 敏感机密隔离：若存在 configs/.secrets.yaml，自动合并其中的敏感凭据 (卡密与 API Key)
        secrets_path = self.root_dir / "configs" / ".secrets.yaml"
        if yaml and secrets_path.exists():
            try:
                with open(secrets_path, "r", encoding="utf-8") as sf:
                    sec_data = yaml.safe_load(sf) or {}
                if isinstance(sec_data, dict) and "gateway" in sec_data:
                    gw_raw = self.raw_config.setdefault("gateway", {})
                    sec_gw = sec_data["gateway"]
                    if isinstance(sec_gw, dict):
                        if sec_gw.get("license_key"):
                            gw_raw["license_key"] = sec_gw["license_key"]
                        if "custom" in sec_gw and isinstance(sec_gw["custom"], dict):
                            custom_raw = gw_raw.setdefault("custom", {})
                            if sec_gw["custom"].get("api_key"):
                                custom_raw["api_key"] = sec_gw["custom"]["api_key"]
            except Exception:
                pass

        sys_info = self.raw_config.get("system", {})
        self.system_name: str = sys_info.get("name", "立体空间智能体系统")
        self.version: str = sys_info.get("version", "2.2.5")
        self.log_level: str = sys_info.get("log_level", "INFO")

        self.workspace_dir: Path = (self.root_dir / sys_info.get("workspace_dir", "workspace")).resolve()
        self.agents_dir: Path = (self.root_dir / sys_info.get("agents_dir", "agents")).resolve()
        self.skills_dir: Path = (self.root_dir / sys_info.get("skills_dir", "skills")).resolve()
        self.workflows_dir: Path = (self.root_dir / sys_info.get("workflows_dir", "workflows")).resolve()
        self.extra_agent_dirs: List[Path] = self._resolve_extra_dirs(sys_info.get("extra_agent_dirs", []))

        self.fast_path: Dict[str, Any] = self.raw_config.get("fast_path", {})
        self.gateway: GatewayConfig = GatewayConfig(self.raw_config.get("gateway", {}))
        self.watcher: WatcherConfig = WatcherConfig(self.raw_config.get("watcher", {}), self.root_dir)

    @property
    def is_dev_mode(self) -> bool:
        """检查系统是否处于本地开发者/集成单测模式"""
        return (
            os.environ.get("LITIKJ_DEV_MODE") == "1" or
            "PYTEST_CURRENT_TEST" in os.environ or
            "unittest" in sys.modules or
            bool(self.raw_config.get("system", {}).get("dev_mode", False))
        )

    def _resolve_extra_dirs(self, raw_dirs: list) -> List[Path]:
        """将相对路径转换为基于 project_root 的绝对路径"""
        resolved = []
        for d in raw_dirs:
            if not d:
                continue
            p = Path(d)
            if not p.is_absolute():
                p = (self.root_dir / p).resolve()
            resolved.append(p)
        return resolved

    @property
    def project_root(self) -> Path:
        return self.root_dir

    def _load_yaml(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        if yaml is None:
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[ConfigManager Error] 读取 {self.config_path.name} 失败: {e}")
            return {}

    def reload(self):
        """重新加载配置文件"""
        self.raw_config = self._load_yaml()
        sys_info = self.raw_config.get("system", {})
        self.system_name = sys_info.get("name", "立体空间智能体系统")
        self.version = sys_info.get("version", "2.2.5")
        self.log_level = sys_info.get("log_level", "INFO")
        self.workspace_dir = (self.root_dir / sys_info.get("workspace_dir", "workspace")).resolve()
        self.agents_dir = (self.root_dir / sys_info.get("agents_dir", "agents")).resolve()
        self.skills_dir = (self.root_dir / sys_info.get("skills_dir", "skills")).resolve()
        self.workflows_dir = (self.root_dir / sys_info.get("workflows_dir", "workflows")).resolve()
        self.extra_agent_dirs = self._resolve_extra_dirs(sys_info.get("extra_agent_dirs", []))
        self.fast_path = self.raw_config.get("fast_path", {})
        self.gateway = GatewayConfig(self.raw_config.get("gateway", {}))
        self.watcher = WatcherConfig(self.raw_config.get("watcher", {}), self.root_dir)
        return self

    @classmethod
    def get_instance(cls, force_reload: bool = False) -> 'ConfigManager':
        if cls._instance is None or force_reload:
            cls._instance = ConfigManager()
        return cls._instance
