# -*- coding: utf-8 -*-
"""
core/standard_agent.py
【立体空间智能体系统 · 工业级标准智能体基类与可复用 Mixin 矩阵】

工业级实战经验沉淀：
1. StandardConfigMixin: 纯净的标准三位一体动态设置面板与数据持久化；
2. StandardFastPathMixin: 0-Token <10ms 快速直达指令分发器 (ping/config/set/check/help)；
3. StandardAgent: 统一继承 BaseAgent + ConfigMixin + FastPathMixin 的工业级通用基类。
"""

import copy
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from .contract import BaseAgent, TaskContext, TaskResult
from .config import ConfigManager


class StandardConfigMixin:
    """
    通用标准设置面板 Mixin
    对齐 SOP 与前端 AgentSettingsModal.vue 契约：
    - get_config_schema()
    - get_config()
    - update_config(updates)
    数据默认自动持久化存储于 workspace/data/{agent_name}_config.json。
    """
    CONFIG_SCHEMA: Dict[str, Any] = {}
    DEFAULT_CONFIG: Dict[str, Any] = {}
    CONFIG_FILE_NAME: Optional[str] = None

    def _get_config_file_path(self) -> Path:
        cm = ConfigManager.get_instance()
        data_dir = cm.workspace_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        fname = self.CONFIG_FILE_NAME or f"{getattr(self, 'name', 'agent')}_config.json"
        return data_dir / fname

    def get_config_schema(self) -> Dict[str, Any]:
        """返回供前端动态表单渲染的 JSON Schema 契约"""
        if hasattr(self, "CONFIG_SCHEMA") and self.CONFIG_SCHEMA:
            return copy.deepcopy(self.CONFIG_SCHEMA)
        return {
            "title": f"{getattr(self, 'name', '智能体')} 配置",
            "type": "object",
            "properties": {}
        }

    def get_config(self) -> Dict[str, Any]:
        """读取已持久化的配置；若不存在或字段缺失，以 DEFAULT_CONFIG 补齐并保持纯净"""
        cfg_path = self._get_config_file_path()
        current = copy.deepcopy(getattr(self, "DEFAULT_CONFIG", {}))

        if cfg_path.exists():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        current.update(saved)
            except Exception:
                pass
        return current

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新配置并实时落盘持久化"""
        cfg_path = self._get_config_file_path()
        current = self.get_config()

        # 仅接收 Schema 或默认配置已声明的合法键，过滤注入风险
        schema_props = self.get_config_schema().get("properties", {})
        valid_keys = set(schema_props.keys()) | set(getattr(self, "DEFAULT_CONFIG", {}).keys())

        for k, v in updates.items():
            if not valid_keys or k in valid_keys:
                current[k] = v

        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[{getattr(self, 'name', 'Agent')} Warning] 保存配置文件失败: {e}")

        return current

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """快速提取单个配置项"""
        cfg = self.get_config()
        return cfg.get(key, default)

    def set_config_value(self, key: str, value: Any) -> Any:
        """快速修改并持久化单个配置项"""
        return self.update_config({key: value})


class StandardSelfHealingMixin:
    """
    通用标准环境自检与静默自愈 Mixin
    自动根据类属性检查与修复：
    - DROP_BOX_DIRS: 工作区所需目录，支持静默自愈；
    - REQUIRED_PACKAGES: 所需 Python 包，支持静默装入便携环境；
    - REQUIRED_BINARIES: 所需可执行二进制探测；
    - get_preflight_items: 子类可自由扩展覆盖。
    """
    DROP_BOX_DIRS: List[str] = []
    REQUIRED_PACKAGES: List[str] = []
    REQUIRED_BINARIES: List[str] = []

    def get_preflight_items(self) -> List[Any]:
        from .preflight import PreflightItem, PreflightChecker, AutoHealer
        items: List[PreflightItem] = []
        cm = ConfigManager.get_instance()

        # 1. 工作区投放箱与数据目录
        drop_dirs = getattr(self, "DROP_BOX_DIRS", [])
        if drop_dirs:
            target_dirs = [cm.workspace_dir / d for d in drop_dirs]
            missing_dirs = [d for d in target_dirs if not d.exists()]
            items.append(PreflightItem(
                name="工作区投递箱目录",
                status="ok" if not missing_dirs else "pending_heal",
                message="全部投递箱子目录已就绪" if not missing_dirs else f"缺少 {len(missing_dirs)} 个投递箱子目录",
                auto_healable=True,
                heal_func=lambda cb: AutoHealer.ensure_directories(target_dirs)
            ))

        # 2. 便携运行依赖
        req_pkgs = getattr(self, "REQUIRED_PACKAGES", [])
        if req_pkgs:
            missing_pkgs = [p for p in req_pkgs if not PreflightChecker.check_python_module(p)]
            if missing_pkgs:
                items.append(PreflightItem(
                    name="便携式 Python 运行依赖",
                    status="pending_heal",
                    message=f"缺失依赖包: {', '.join(missing_pkgs)}",
                    auto_healable=True,
                    heal_func=lambda cb: AutoHealer.ensure_python_packages(missing_pkgs, progress_callback=cb)
                ))
            else:
                items.append(PreflightItem(
                    name="便携式 Python 运行依赖",
                    status="ok",
                    message="所需依赖包均已安装完备"
                ))

        # 3. 系统级二进制工具
        req_bins = getattr(self, "REQUIRED_BINARIES", [])
        if req_bins:
            for b in req_bins:
                has_b = PreflightChecker.check_binary(b)
                items.append(PreflightItem(
                    name=f"底层工具组件 ({b})",
                    status="ok" if has_b else "failed",
                    message="运行正常" if has_b else f"未在 PATH 或内置 bin/ 中找到 {b}",
                    auto_healable=False
                ))

        return items

    def get_readiness_status(self) -> Dict[str, Any]:
        from .preflight import AutoHealer
        return AutoHealer.check_agent_readiness(self)

    def heal_environment(self, progress_callback=None) -> Dict[str, Any]:
        from .preflight import AutoHealer
        return AutoHealer.heal_agent(self, progress_callback=progress_callback)


class StandardFastPathMixin:
    """
    0-Token 快速直达通道 Mixin
    内置基础指令：ping, config, set, help, check, heal
    """

    def handle_standard_fast_path(self, command: str) -> Optional[str]:
        cmd = command.strip()
        cmd_lower = cmd.lower()
        parts = cmd.split(maxsplit=2)
        root_cmd = parts[0].lower() if parts else ""

        # 1. ping 毫秒级心跳探活
        if root_cmd in ("ping", "pong"):
            agent_name = getattr(self, "name", "Agent")
            return (
                f"### ⚡ [0-Token PONG] {agent_name} 回路运行正常\n\n"
                f"- ⏱️ **当前时间**：`{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"- 🚀 **响应延时**：`< 1ms`\n"
                f"- 🏷️ **消耗 Token**：`0 Token (纯代码原生驱动)`"
            )

        # 2. config 查看配置看板
        if root_cmd in ("config", "settings"):
            agent_name = getattr(self, "name", "Agent")
            cfg = getattr(self, "get_config", lambda: {})()
            schema = getattr(self, "get_config_schema", lambda: {})()
            props = schema.get("properties", {})

            lines = [
                f"### ⚙️ 【{agent_name}】当前生效配置看板 (0-Token)",
                "---",
                "| 配置项 (Key) | 当前值 | 描述 |",
                "| :--- | :--- | :--- |"
            ]
            for k, v in cfg.items():
                desc = props.get(k, {}).get("description", props.get(k, {}).get("title", ""))
                lines.append(f"| `{k}` | `{v}` | {desc} |")
            lines.extend([
                "",
                "💡 **修改配置提示**：输入 `[EXEC] set <配置项> <新值>`，例如 `[EXEC] set auto_clean true`"
            ])
            return "\n".join(lines)

        # 3. set <key> <val> 快捷修改配置
        if root_cmd == "set":
            if len(parts) < 3:
                return "⚠️ **[配置修改]** 请输入正确格式：`[EXEC] set <配置项> <新值>`"
            k = parts[1].strip()
            raw_v = parts[2].strip()

            # 智能推断类型 (bool, int, float, str)
            if raw_v.lower() == "true":
                v: Any = True
            elif raw_v.lower() == "false":
                v = False
            elif raw_v.isdigit():
                v = int(raw_v)
            else:
                try:
                    v = float(raw_v)
                except ValueError:
                    v = raw_v

            updater = getattr(self, "update_config", None)
            if callable(updater):
                updated = updater({k: v})
                return f"✅ **[配置更新成功]** `{k}` 已变更为 `{updated.get(k, v)}` 并持久化。"
            return "❌ 该智能体未实现配置更新契约。"

        # 4. check 环境前置体检与就绪度诊断
        if root_cmd in ("check", "doctor", "preflight"):
            agent_name = getattr(self, "name", "Agent")
            getter = getattr(self, "get_readiness_status", None)
            if callable(getter):
                status = getter()
                st = status.get("state", "READY")
                prog = status.get("progress", 100.0)
                badge = "🟢 在岗待命 (100%)" if st == "READY" else (
                    f"⏳ 正在装备运行环境 ({prog}%)" if st == "INSTALLING_DEPENDENCIES" else "⚠️ 需要操作授权"
                )
                lines = [
                    f"### 🩺 【{agent_name}】运行就绪度全景巡检看板",
                    f"- **生命周期状态**：{badge}",
                    f"- **当前就绪进度**：`{prog}%`",
                    "",
                    "| 巡检组件 | 状态 | 详细信息 | 支持静默自愈 |",
                    "| :--- | :--- | :--- | :--- |"
                ]
                for it in status.get("items", []):
                    icon = "🟢" if it["status"] == "ok" else ("⏳" if it["status"] in ("pending_heal", "healing") else ("⚠️" if it["action_required"] else "🔴"))
                    lines.append(f"| {it['name']} | {icon} `{it['status']}` | {it['message']} | {'✅ 支持' if it.get('auto_healable') else '—'} |")
                
                if st != "READY":
                    lines.append("\n👉 发送 `[EXEC] heal` 可立即启动后台全自动静默自愈！")
                return "\n".join(lines)
            return "✅ 环境检查完成。"

        # 5. heal / setup 全自动静默环境自愈
        if root_cmd in ("heal", "setup", "repair"):
            agent_name = getattr(self, "name", "Agent")
            healer = getattr(self, "heal_environment", None)
            if callable(healer):
                res = healer()
                st = res.get("state", "READY")
                prog = res.get("progress", 100.0)
                if st == "READY":
                    return f"### 🎉 【{agent_name}】全自动环境自愈已 100% 完成！\n\n所有依赖组件与目录均已完备，现已正式交付就绪，随时为您服务。"
                elif st == "ACTION_REQUIRED":
                    guide = res.get("action_guide", {})
                    return f"### ⚠️ 【{agent_name}】环境自愈已完成大部分步骤，仅需您完成一步授权：\n\n- {guide.get('message', '请在界面提示下完成账号绑定')}\n- 指令提示：`{guide.get('cmd', '[EXEC] login')}`"
                else:
                    return f"### ⏳ 【{agent_name}】环境自愈正在推进中（当前进度 {prog}%）\n\n正在自动拉取并装配缺失组件，请稍候片刻。"
            return "✅ 该智能体无需自愈。"

        # 6. help 指令清单
        if root_cmd in ("help", "?", "man"):
            agent_name = getattr(self, "name", "Agent")
            return (
                f"### 💡 【{agent_name}】0-Token 快速指令清单\n\n"
                f"- `[EXEC] ping`：毫秒级连通性探活测试\n"
                f"- `[EXEC] check`：环境依赖与运行底座门禁体检\n"
                f"- `[EXEC] heal`：全自动静默自愈与运行环境装配\n"
                f"- `[EXEC] config`：查看当前智能体生效配置\n"
                f"- `[EXEC] set <配置项> <新值>`：快速修改指定配置项\n"
                f"- `[EXEC] help`：查看本快捷指令帮助"
            )

        return None


class StandardAgent(StandardConfigMixin, StandardFastPathMixin, StandardSelfHealingMixin, BaseAgent):
    """
    立体空间工业化标准 Agent 基类
    开箱即用支持：
    1. Schema 配置面板驱动与读写落盘 (StandardConfigMixin)
    2. 0-Token Fast-Path 指令分发 (StandardFastPathMixin)
    3. 全自动环境自检与静默自愈 (StandardSelfHealingMixin)
    4. 标准 TaskReporter 工序报告
    """

    def __init__(self, name: str, description: str = ""):
        super().__init__(name=name, description=description)

    def handle_custom_fast_path(self, command: str) -> Optional[str]:
        """子类扩展的自定义 0-Token 指令处理通道 (子类按需重写)"""
        return None

    def handle_fast_path(self, command: str) -> Optional[str]:
        """优先由子类自定义 Fast-Path 消费，未命中时平滑降级至标准通道"""
        custom_reply = self.handle_custom_fast_path(command)
        if custom_reply is not None:
            return custom_reply
        return self.handle_standard_fast_path(command)
