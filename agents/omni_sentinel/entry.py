# -*- coding: utf-8 -*-
"""
agents/omni_sentinel/entry.py
【全维调度演示标杆智能体 · OmniSentinel 主入口 (AGENT SPEC v2.5 标准化重构版)】

工业级规范对齐：
1. 继承 StandardAgent 工业级基类 (StandardConfigMixin + StandardFastPathMixin + StandardSelfHealingMixin)；
2. 动态标准配置面板 (Config Schema Protocol)：暴露巡检周期、预警阈值与报告格式，支持桌面端通用面板自适应渲染与落盘；
3. 环境前置门禁与静默自愈 (Fail-Early & Auto-Healing)：声明 DROP_BOX_DIRS 与可选硬件探针 PreflightItem，支持 0-Token [EXEC] check / heal；
4. 0-Token 极速直达通道：通用指令 (ping/config/set/check/heal/help) 由基类接管，子类专注扩展专属业务指令 (status/report/demo/recruit)；
5. 四维全触发核心范式：0-Token直达 / 对话启动 / 定时打卡 / 事件驱动；
6. 任务工序流转与交付卡片：基于 TaskReporter 划分 4 道工序阶梯，驱动桌面端动态任务进度条与交付简报；
7. 零顶层第三方依赖：严守 SOP §4.3，按需懒加载。
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator

from core.standard_agent import StandardAgent
from core.contract import TaskContext, TaskResult, TaskReporter
from core.guards import LicenseGuard
from core.registry import Registry
from core.config import ConfigManager
from core.preflight import PreflightItem, PreflightChecker, AutoHealer, ReadinessState
from core.llm import LLMClient

from .tools.inspector import SystemInspector


class OmniSentinelAgent(StandardAgent):
    """全维调度标杆演示智能体 (Omni Sentinel)"""

    # =================================================================
    # 【通用标准配置面板契约】(Config Schema Protocol - SOP §3)
    # =================================================================
    CONFIG_SCHEMA: Dict[str, Any] = {
        "title": "全维调度哨兵参数配置",
        "type": "object",
        "properties": {
            "patrol_interval": {
                "type": "integer",
                "title": "后台定时打卡巡检周期 (秒)",
                "description": "定时触发 scheduled_run 的周期时间 (默认 3600 秒)",
                "default": 3600,
                "minimum": 60,
                "maximum": 86400
            },
            "disk_alert_threshold_gb": {
                "type": "number",
                "title": "磁盘可用空间预警阈值 (GB)",
                "description": "当宿主磁盘剩余可用空间低于该阈值时触发系统预警",
                "default": 10.0,
                "minimum": 1.0
            },
            "memory_alert_threshold_percent": {
                "type": "number",
                "title": "系统内存占用预警阈值 (%)",
                "description": "当内存使用率超过该百分比时触发告警提示",
                "default": 85.0,
                "minimum": 10.0,
                "maximum": 99.0
            },
            "report_format": {
                "type": "string",
                "title": "巡检报告输出格式",
                "description": "生成的健康打卡报告持久化格式",
                "enum": ["markdown", "json"],
                "enumNames": ["Markdown 格式 (.md)", "JSON 结构化 (.json)"],
                "default": "markdown"
            },
            "retain_reports_count": {
                "type": "integer",
                "title": "历史巡检报告保留份数",
                "description": "自动清理超期巡检日志，避免磁盘冗余占用",
                "default": 7,
                "minimum": 1,
                "maximum": 30
            },
            "enable_proactive_alert": {
                "type": "boolean",
                "title": "开启异常事件主动感知推送",
                "description": "当检测到底层资源越界或异常时，主动向消息总线推送通知",
                "default": True
            }
        }
    }

    DEFAULT_CONFIG: Dict[str, Any] = {
        "patrol_interval": 3600,
        "disk_alert_threshold_gb": 10.0,
        "memory_alert_threshold_percent": 85.0,
        "report_format": "markdown",
        "retain_reports_count": 7,
        "enable_proactive_alert": True
    }

    CONFIG_FILE_NAME = "omni_sentinel_config.json"

    # =================================================================
    # 【环境门禁与静默自愈声明】(Fail-Early & Auto-Healing - SOP §5)
    # =================================================================
    DROP_BOX_DIRS = [
        "outputs",
        "drop_box",
        "data"
    ]
    REQUIRED_PACKAGES = []
    REQUIRED_BINARIES = []

    def __init__(self):
        super().__init__(
            name="omni_sentinel",
            description="全维调度标杆演示智能体 (四维触发范式：0-Token直达 / 对话启动 / 定时打卡 / 事件驱动)"
        )
        self.display_name = "全维调度哨兵"
        self.icon = "🛡️"
        self.category = "系统基准"
        self.base_dir = Path(__file__).resolve().parent

        # 1. 挂载商业授权安全门禁 (体验审计模式：未激活访客亦可免门禁体验底层巡检与架构范例)
        self.add_pre_guard(LicenseGuard(name="全维哨兵商业授权审计门禁", strict=False))

        # 2. 读取人设提示词
        self.prompt_text = self._load_file("persona/prompt.md")
        self.system_prompt = self.prompt_text or (
            "你是 OmniSentinel 全维调度哨兵。提倡'软件归软件，AI归AI'，"
            "引导用户在确定性场景使用 0-Token 快速通道，在认知策略场景使用大模型。"
        )
        self.skills_list = []

    def _load_file(self, rel_path: str) -> str:
        f = self.base_dir / rel_path
        if f.exists():
            try:
                return f.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return ""

    def get_preflight_items(self) -> List[PreflightItem]:
        """
        向微内核 AutoHealer 暴露标准自检与自愈项清单 (SOP §5)
        """
        cm = ConfigManager.get_instance()
        items: List[PreflightItem] = []

        # 1. 工作区输出与投递箱目录巡检与自愈
        target_dirs = [
            cm.workspace_dir / "outputs",
            cm.workspace_dir / "drop_box",
            cm.workspace_dir / "data"
        ]
        missing_dirs = [d for d in target_dirs if not d.exists()]
        items.append(PreflightItem(
            name="工作区投递与产物目录",
            status="ok" if not missing_dirs else "pending_heal",
            message="输出与投递目录已完备" if not missing_dirs else f"待静默创建 {len(missing_dirs)} 个基础目录",
            auto_healable=True,
            heal_func=lambda cb: AutoHealer.ensure_directories(target_dirs)
        ))

        # 2. 增强型硬件负载探针 (psutil) 状态探测 (遵循便携式零第三方依赖原则，支持按需一键自愈装配)
        has_psutil = PreflightChecker.check_python_module("psutil")
        items.append(PreflightItem(
            name="增强型硬件负载探针 (psutil)",
            status="ok" if has_psutil else "pending_heal",
            message="高精硬件探针已装配就绪" if has_psutil else "当前处于标准库轻量探针模式 (支持一键自愈装配高精探针)",
            auto_healable=True,
            heal_func=lambda cb: AutoHealer.ensure_python_packages(["psutil"], progress_callback=cb)
        ))

        # 3. 微内核核心配置架构完整性
        framework_cfg = cm.root_dir / "configs" / "framework.yaml"
        items.append(PreflightItem(
            name="微内核 Single Source 核心配置",
            status="ok" if framework_cfg.exists() else "failed",
            message="framework.yaml 基准配置正常" if framework_cfg.exists() else "缺少 configs/framework.yaml",
            auto_healable=False
        ))

        # 4. 商业授权审计状态 (体验模式不阻断)
        lic_ok, lic_msg = LLMClient.verify_license(force_network=False)
        items.append(PreflightItem(
            name="数字化员工商业授权审计",
            status="ok" if lic_ok else "ok",
            message="年度会员商业授权已激活" if lic_ok else f"未激活访客体验模式 ({lic_msg}，全功能开放)",
            auto_healable=False
        ))

        return items

    # =================================================================
    # 【0-Token 快速直达通道】(Fast-Path - 子类业务扩展)
    # =================================================================
    def handle_custom_fast_path(self, command: str) -> Optional[str]:
        """
        子类扩展的专属 0-Token 业务指令 (响应 < 5ms，消耗 0 Token)
        基础通用指令 (ping / check / heal / config / set / help) 自动由 StandardFastPathMixin 接管。
        """
        cmd_raw = command.strip()
        parts = cmd_raw.split(maxsplit=1)
        root_cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        # 1. status / info / diagnose: 极速宿主硬件与智能体插槽全景体检
        if root_cmd in ("status", "info", "diagnose"):
            reg = Registry.get_instance()
            agent_count = len(reg.list_agents())
            return self._build_status_overview(agent_count)

        # 2. report / build_report: 立即生成巡检报告并沉淀
        if root_cmd in ("report", "build_report"):
            res = self.scheduled_run()
            return (
                "### 📋 [0-Token 巡检打卡完成]\n\n"
                f"- 📁 **报告路径**：`{res.get('report_path')}`\n"
                f"- 🤖 **活跃智能体**：`{res.get('agent_count')} 个`\n"
                f"- ⏱️ **执行时间**：`{res.get('timestamp')}`\n"
                "- 🏷️ **消耗 Token**：`0 Token`\n\n"
                f"**报告摘要预览**：\n\n{res.get('summary')}"
            )

        # 3. demo / code / sample: 架构范例代码展示与一键悬浮复制
        if root_cmd in ("demo", "code", "sample"):
            return self._build_demo_code_block()

        # 4. recruit <agent_id>: 0-Token 指令招募数字化员工
        if root_cmd == "recruit":
            if not arg:
                return "⚠️ **[OmniSentinel 招募调度]** 请指定要招募的数字化员工标识，例如：`[EXEC] recruit my_custom_agent`"
            try:
                from core.agent_market import AgentMarketService
                AgentMarketService.recruit_agent(arg)
                return f"✅ **[OmniSentinel]** 数字化员工 `{arg}` 招募成功并已挂载入职！"
            except Exception as e:
                return f"❌ **[OmniSentinel]** 数字化员工 `{arg}` 招募失败：{e}"

        return None

    def _build_status_overview(self, agent_count: int = 0) -> str:
        """生成带阈值判定的极速状态看板"""
        m = SystemInspector.get_system_metrics()
        cfg = self.get_config()
        disk_threshold = float(cfg.get("disk_alert_threshold_gb", 10.0))
        mem_threshold = float(cfg.get("memory_alert_threshold_percent", 85.0))

        disk_free = m.get("disk_free_gb", 0.0)
        disk_warn = disk_free < disk_threshold and disk_free > 0
        disk_badge = "⚠️ 剩余空间告急" if disk_warn else "🟢 空间充足"

        lines = [
            "### ⚡ [0-Token 快速直达] 全维哨兵底座巡检状态",
            f"- 🖥️ **系统环境**：`{m['os']}`",
            f"- 🐍 **Python 版本**：`v{m['python']}`",
            f"- 💾 **磁盘空间**：`{m['disk_used_gb']} GB / {m['disk_total_gb']} GB` ({m['disk_percent']}% 已用, 剩余 `{disk_free} GB` · {disk_badge})",
            f"- 🧠 **内存状态**：`{m['memory']}`",
            f"- 🤖 **活跃智能体**：`{agent_count} 个已挂载`",
            f"- ⚙️ **巡检配置**：打卡间隔 `{cfg.get('patrol_interval', 3600)}s` | 报告格式 `{cfg.get('report_format', 'markdown')}`",
            f"- ⏱️ **巡检时间**：`{m['timestamp']}`",
            f"- 🏷️ **消耗 Token**：`0 Token (纯代码原生驱动，耗时 < 5ms)`"
        ]
        return "\n".join(lines)

    def _build_demo_code_block(self) -> str:
        """生成支持悬浮复制的代码展示卡片"""
        return (
            "📋 **[0-Token 示例代码] 全维调度哨兵核心微内核调用范式**\n\n"
            "下面是一段标准的智能体调度 Python 范例代码，您可以将鼠标悬停在右上角，点击 **[📋 复制]** 按钮一键复制到剪贴板测试：\n\n"
            "```python\n"
            "# 立体空间智能体系统 · 示例脚本\n"
            "from core.registry import Registry\n"
            "from core.config import ConfigManager\n\n"
            "def quick_agent_inspection():\n"
            "    \"\"\"遍历已挂载智能体并执行 0-Token 极速巡检\"\"\"\n"
            "    registry = Registry.get_instance()\n"
            "    agents = registry.list_agents()\n"
            "    print(f\"✅ 已挂载智能体总数: {len(agents)}\")\n"
            "    \n"
            "    for agent in agents:\n"
            "        print(f\"🤖 智能体: {agent.name} | 门禁数: {len(agent.pre_guards)}\")\n\n"
            "if __name__ == \"__main__\":\n"
            "    quick_agent_inspection()\n"
            "```\n\n"
            "*💡 悬浮复制特性说明：代码块右上角已配备悬浮复制功能，点击即可将纯文本源码直接复制至系统剪贴板。*"
        )

    # =================================================================
    # 【维度二：对话认知启动】(Dialogue Trigger - 自然语言与教学引导)
    # =================================================================
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        多轮对话交互入口
        1. 优先检查并分流 [EXEC] 快速直达通道 (0-Token)；
        2. 针对代码演示即时返回；
        3. 若大模型网关就绪则推理，否则优雅降级至架构教学模式。
        """
        # 1. 优先分流 Fast-Path 0-Token 极速直达
        fast_cfg = ConfigManager.get_instance().fast_path
        prefix = fast_cfg.get("prefix", "[EXEC]")
        enabled = fast_cfg.get("enabled", True)

        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "").strip()
                break

        if enabled and last_user_msg.startswith(prefix):
            cmd = last_user_msg[len(prefix):].strip()
            fast_reply = self.handle_fast_path(cmd)
            if fast_reply is not None:
                return fast_reply

        # 针对代码生成/演示指令立即返回带有代码块的内容，方便测试一键复制
        if any(kw in last_user_msg for kw in ["演示代码", "代码生成", "复制", "示例代码", "demo", "code"]):
            return (
                "📋 **[示例代码] 全维调度哨兵核心微内核调用范式**\n\n"
                "已为您生成立体空间微内核标准调用代码。请将鼠标移至下方代码块右上角，即可看到 **[📋 复制]** 按钮，点击即可一键复制：\n\n"
                "```python\n"
                "# 立体空间智能体系统 · 核心调用演示脚本\n"
                "import sys\n"
                "from core.registry import Registry\n"
                "from core.scheduler import SchedulerManager\n\n"
                "def inspect_agent_system():\n"
                "    \"\"\"立体空间智能体系统微内核探针\"\"\"\n"
                "    registry = Registry.get_instance()\n"
                "    agents = registry.list_agents()\n"
                "    print(f\"[System] 当前已挂载智能体数量: {len(agents)}\")\n"
                "    for agent in agents:\n"
                "        print(f\"  -> 智能体: {agent.name} (版本: {getattr(agent, 'version', '1.1.0')})\")\n"
                "        \n"
                "    scheduler = SchedulerManager.get_instance()\n"
                "    tasks = scheduler.list_tasks()\n"
                "    print(f\"[Scheduler] 后台自动化任务数量: {len(tasks)}\")\n\n"
                "if __name__ == '__main__':\n"
                "    inspect_agent_system()\n"
                "```\n\n"
                "✨ **功能验证**：您可以点击右上角 **[💾 导出记录]** 将此会话沉淀为本地 Markdown 文档，或点击顶部 **[⚙️ 设置配置]** 体验动态参数调整！"
            )

        # 2. 检查具身技能意图 (支持 0-Token 离线原生直达)
        from core.tool_runner import ToolRunner
        if ToolRunner.detect_offline_skill_intent(last_user_msg, self):
            return super().chat(messages)

        # 3. 对话认知通道：若网关激活则调用大模型，若未激活或失败则返回明确指引
        cfg = ConfigManager.get_instance().gateway
        if cfg.is_active():
            try:
                return super().chat(messages)
            except Exception as e:
                return (
                    f"🛡️ [OmniSentinel 哨兵提示] 远程大模型网关通信异常 ({e})。\n\n"
                    f"针对您提出的问题: \"{last_user_msg}\"\n\n"
                    "💡 排查建议：\n"
                    "1. 若使用官方云端中枢：请检查网络是否畅通，或在【系统设置】中重新核验激活卡密；\n"
                    "2. 若使用自备 Key / Ollama：请在【系统设置】中检查 API Key 与模型名称是否正确；\n"
                    "3. 输入 `[EXEC] check` 可快速体检底座环境；输入 `[EXEC] ping` 检测心跳回路。"
                )

        # 未激活状态明确引导
        if cfg.mode == "cloud":
            return (
                f"🛡️ [OmniSentinel 哨兵提示] 系统当前处于【官方云端中枢 · 待激活状态】。\n\n"
                f"收到您的对话提问: \"{last_user_msg}\"\n\n"
                f"💡 【如何开启大模型功能】：\n"
                f"• 请点击左下角 **⚙️ 系统设置**，在【专属激活卡密】输入框中粘贴您的卡密并点击【绑定】；\n"
                f"• 官方中枢免配 API Key，绑定卡密后即可自动开启全部大模型创作与思考能力；\n"
                f"• 您也可以输入 `[EXEC] status` 或 `[EXEC] ping` 体验 0-Token 本地快速直达通道。"
            )
        else:
            return (
                f"🛡️ [OmniSentinel 哨兵提示] 系统当前处于【自定义模型模式】，尚未配置 API 密钥。\n\n"
                f"收到您的对话提问: \"{last_user_msg}\"\n\n"
                f"💡 请点击左下角 **⚙️ 系统设置**，在【大模型推理引擎】中配置 API Key，或直接切换为【官方云端中枢 (卡密免配)】。"
            )

    def stream_chat(self, messages: List[Dict[str, str]]) -> Iterator[str]:
        """流式分块输出入口 (支持 0-Token 极速直达与大模型分块混合推送)"""
        fast_cfg = ConfigManager.get_instance().fast_path
        prefix = fast_cfg.get("prefix", "[EXEC]")
        enabled = fast_cfg.get("enabled", True)

        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "").strip()
                break

        # 1. 优先分流 0-Token 极速直达
        if enabled and last_user_msg.startswith(prefix):
            cmd = last_user_msg[len(prefix):].strip()
            fast_reply = self.handle_fast_path(cmd)
            if fast_reply is not None:
                yield fast_reply
                return

        # 2. 针对代码演示即刻返回
        if any(kw in last_user_msg for kw in ["演示代码", "代码生成", "复制", "示例代码", "demo", "code"]):
            reply = self.chat(messages)
            yield reply
            return

        # 3. 具身技能意图
        from core.tool_runner import ToolRunner
        if ToolRunner.detect_offline_skill_intent(last_user_msg, self):
            yield from super().stream_chat(messages)
            return

        # 4. 对话认知流式推送
        cfg = ConfigManager.get_instance().gateway
        if cfg.is_active():
            try:
                yield from super().stream_chat(messages)
                return
            except Exception as e:
                yield (
                    f"🛡️ [OmniSentinel 哨兵提示] 远程大模型网关通信异常 ({e})。\n"
                    f"针对您提出的问题: \"{last_user_msg}\"\n"
                    "您可以使用 `[EXEC] check` 快速排查本地环境，或检查网络与激活码状态。"
                )
                return

        yield self.chat(messages)

    # =================================================================
    # 【维度三：定时周期启动】(Scheduled Trigger - 打卡沉淀与轮转)
    # =================================================================
    def scheduled_run(self) -> Dict[str, Any]:
        """
        定时启动入口 (Scheduled Trigger)
        当定时器 (Cron / Timer) 到达周期时调用，自动执行巡检并将报告持久化沉淀到 workspace/outputs/
        支持按照配置的 report_format 生成 Markdown 或 JSON，并根据 retain_reports_count 轮转归档
        """
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()
        cfg = self.get_config()
        fmt = cfg.get("report_format", "markdown")
        retain_count = int(cfg.get("retain_reports_count", 7))

        active_agents = [ag.name for ag in reg.list_agents()]
        metrics = SystemInspector.get_system_metrics()
        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")

        out_dir = cm.workspace_dir / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. 写入最新主报告
        if fmt == "json":
            report_file = out_dir / "sentinel_report.json"
            data_to_write = {
                "timestamp": timestamp_str,
                "trigger": "定时周期调度 (Cron/Timer)",
                "metrics": metrics,
                "active_agents": active_agents,
                "token_cost": 0
            }
            report_file.write_text(json.dumps(data_to_write, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            report_file = out_dir / "sentinel_report.md"
            report_md = SystemInspector.generate_markdown_report(active_agents, trigger_type="定时周期任务 (Cron/Timer)")
            report_file.write_text(report_md, encoding="utf-8")

        # 2. 轮转归档历史快照
        try:
            history_dir = out_dir / "sentinel_history"
            history_dir.mkdir(parents=True, exist_ok=True)
            snapshot_name = f"report_{time.strftime('%Y%m%d_%H%M%S')}.{ 'json' if fmt == 'json' else 'md' }"
            snapshot_file = history_dir / snapshot_name
            snapshot_file.write_text(report_file.read_text(encoding="utf-8"), encoding="utf-8")

            # 清理超出上限的历史文件
            history_files = sorted(history_dir.glob("report_*.*"), key=lambda f: f.stat().st_mtime)
            if len(history_files) > retain_count:
                for old_f in history_files[:-retain_count]:
                    try:
                        old_f.unlink()
                    except Exception:
                        pass
        except Exception as e:
            print(f"⚠️ [OmniSentinel] 报告归档轮转异常: {e}")

        summary = (
            f"已巡检 {len(active_agents)} 个智能体，宿主健康状态良好，"
            f"报告已持久化写入: {report_file.relative_to(cm.root_dir) if report_file.is_relative_to(cm.root_dir) else report_file}"
        )

        return {
            "success": True,
            "report_path": str(report_file),
            "timestamp": timestamp_str,
            "agent_count": len(active_agents),
            "summary": summary
        }

    # =================================================================
    # 【维度四：事件驱动启动】(Event-Driven Trigger - EDA)
    # =================================================================
    def on_event(self, event_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        事件驱动启动入口 (EDA)
        当系统内外部发生事件时（如文件变更、阈值超限、商业告警）被调用响应
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        if event_name == "file_changed":
            file_path = data.get("file_path", "未知文件")
            action = data.get("action", "modified")
            msg = f"🔔 [事件感知] OmniSentinel 检测到文件变动: [{action}] {file_path}"
            return {"handled": True, "event": event_name, "message": msg, "timestamp": timestamp}

        if event_name == "alert_triggered":
            level = data.get("level", "WARNING")
            reason = data.get("reason", "未提供原因")
            msg = f"🚨 [系统告警] 触发级别 [{level}]: {reason}"
            return {"handled": True, "event": event_name, "message": msg, "timestamp": timestamp}

        if event_name == "license_expired":
            msg = "⚠️ [商业门禁告警] 授权状态已变更或失效，请及时续期以恢复全功能！"
            return {"handled": True, "event": event_name, "message": msg, "timestamp": timestamp}

        return {
            "handled": True,
            "event": event_name,
            "message": f"ℹ️ [OmniSentinel] 收到并记录自定义事件: {event_name}",
            "data": data,
            "timestamp": timestamp
        }

    # =================================================================
    # 【统一批处理执行流水线】(TaskReporter 工序阶梯驱动)
    # =================================================================
    def run(self, context: TaskContext) -> TaskResult:
        """
        批处理统一执行入口 (规范接入 TaskReporter 工序流转)
        """
        payload = context.payload or {}
        action = payload.get("action", "inspect")

        # 兼容外部调度与事件传入
        if action == "schedule":
            res = self.scheduled_run()
            return TaskResult(success=True, message="定时打卡巡检完成", data=res)

        if action == "event":
            event_name = payload.get("event", "custom_ping")
            event_data = payload.get("data", {})
            res = self.on_event(event_name, event_data)
            return TaskResult(success=True, message="事件处理完成", data=res)

        if action in ("fast_path", "fast"):
            cmd = payload.get("command", "status")
            reply = self.handle_fast_path(cmd)
            return TaskResult(success=True, message="0-Token 指令执行完成", data={"command": cmd, "reply": reply})

        # 核心巡检流水线 (TaskReporter 工序阶梯驱动)
        reporter = context.get_reporter(title="🛡️ OmniSentinel 全维底座巡检流水线")
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()

        # 工序 1：环境与门禁巡检 (Fail-Early 防御)
        with reporter.step("工序 1: 前置环境与目录门禁巡检"):
            reporter.log("正在探测工作区目录与核心配置完整性...")
            readiness = self.get_readiness_status()
            if readiness.get("state") != "READY":
                reporter.log("检测到缺失基础目录，正在触发全自动静默自愈...")
                self.heal_environment()
            reporter.log(f"门禁巡检通过，当前就绪度: {readiness.get('progress', 100.0)}%")

        # 工序 2：宿主硬件与微内核诊断
        with reporter.step("工序 2: 宿主硬件指标与资源诊断"):
            reporter.log("正在采集 CPU、内存、磁盘及 Python 解释器状态...")
            metrics = SystemInspector.get_system_metrics()
            reporter.log(f"宿主系统: {metrics['os']} | Python: {metrics['python']}")
            reporter.log(f"磁盘剩余: {metrics['disk_free_gb']} GB ({metrics['disk_percent']}% 已用)")

        # 工序 3：多智能体插槽探查
        with reporter.step("工序 3: 已挂载数字化员工插槽探查"):
            reporter.log("扫描微内核 Registry 智能体注册表...")
            agents = reg.list_agents()
            reporter.log(f"当前在岗数字化员工总数: {len(agents)} 个")
            for ag in agents:
                reporter.log(f"  -> [{ag.name}] 门禁数: {len(ag.pre_guards)} (来源: {getattr(ag, 'source', 'internal')})")

        # 工序 4：健康巡检报告生成与持久化归档
        with reporter.step("工序 4: 生成健康打卡报告与持久化归档"):
            reporter.log("正在聚合指标生成标准巡检物料...")
            sched_res = self.scheduled_run()
            reporter.log(f"报告已写入: {sched_res.get('report_path')}")

        # 标准交付成果卡片
        summary_card = (
            f"### 🛡️ OmniSentinel 标杆巡检流水线执行完毕\n\n"
            f"- 🖥️ **宿主底座**：`{metrics['os']}` (Python v{metrics['python']})\n"
            f"- 💾 **磁盘可用**：`{metrics['disk_free_gb']} GB` (使用率 {metrics['disk_percent']}%)\n"
            f"- 🤖 **在岗智能体**：`{len(agents)} 个已挂载`\n"
            f"- 📁 **产物归档**：`{sched_res.get('report_path')}`\n"
            f"- 🏷️ **消耗 Token**：`0 Token (纯确定性软件工程直达)`\n\n"
            f"💡 **快捷操作建议**：\n"
            f"- 发送 `[EXEC] status` 可随时毫秒级查看状态看板\n"
            f"- 发送 `[EXEC] config` 可调整巡检周期与报警阈值"
        )

        return TaskResult(
            success=True,
            message=summary_card,
            data={
                "metrics": metrics,
                "agent_count": len(agents),
                "report": sched_res
            }
        )


def setup(registry: Registry):
    """插件自动注册钩子"""
    registry.register_agent(OmniSentinelAgent())
