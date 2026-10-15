# -*- coding: utf-8 -*-
"""
core/contract.py
【立体空间智能体系统 · 核心契约与标准协议】
职责：
定义微内核框架的核心抽象基类与数据契约，彻底与具体业务解耦。
1. TaskContext & TaskResult: 任务上下文与执行结果契约；
2. BaseGuard: 门禁规则契约（由各智能体自行挂载特定平台的质检/安全检查）；
3. BaseSkill: 原子技能契约（由各业务自主封装工具或外部脚本）；
4. BaseAgent: 智能体基类（组合特有的技能与门禁规则，执行具体任务）。
"""

import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Iterator

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


class StepScope:
    """单个步骤执行作用域上下文管理器"""
    def __init__(self, reporter: 'TaskReporter', step_name: str, step_index: int):
        self.reporter = reporter
        self.step_name = step_name
        self.step_index = step_index
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.time()
        self.reporter.notify_step_start(self.step_name, self.step_index)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = round(time.time() - self.start_time, 2)
        if exc_type is not None:
            self.reporter.notify_step_end(self.step_name, self.step_index, "failed", elapsed, error=str(exc_val))
        else:
            self.reporter.notify_step_end(self.step_name, self.step_index, "completed", elapsed)
        return False

    def log(self, message: str, level: str = "INFO"):
        self.reporter.log(message, level)


class TaskReporter:
    """
    通用任务进度与运行日志报告器 (TaskReporter)
    职责：
    1. 为任何官方或第三方智能体提供标准的多工序流转 (step) 与控制台实时行日志 (log)；
    2. 实时向事件总线广播 task_step_update / task_log / task_finished 事件，驱动 GUI 渲染动效阶梯卡片。
    """
    def __init__(self, task_id: str, agent_name: str, title: str = ""):
        self.task_id = task_id
        self.agent_name = agent_name
        self.title = title or f"{agent_name} 自动化流水线"
        self.steps: List[Dict[str, Any]] = []
        self.logs: List[Dict[str, Any]] = []
        self._current_step_index = 0
        self.start_time = time.time()

    def step(self, step_name: str) -> StepScope:
        self._current_step_index += 1
        return StepScope(self, step_name, self._current_step_index)

    def log(self, message: str, level: str = "INFO"):
        t_str = time.strftime("%H:%M:%S")
        entry = {
            "time": t_str,
            "level": level,
            "message": str(message)
        }
        self.logs.append(entry)
        self._emit_event("task_log", {
            "log": entry,
            "title": self.title
        })

    def notify_step_start(self, step_name: str, step_index: int):
        step_data = {
            "index": step_index,
            "name": step_name,
            "status": "running",
            "start_time": time.time(),
            "elapsed": 0.0
        }
        self.steps.append(step_data)
        self._emit_event("task_step_update", {
            "title": self.title,
            "current_step": step_name,
            "step_index": step_index,
            "steps": self._serialize_steps()
        })

    def notify_step_end(self, step_name: str, step_index: int, status: str, elapsed: float, error: str = ""):
        for s in self.steps:
            if s["index"] == step_index:
                s["status"] = status
                s["elapsed"] = elapsed
                if error:
                    s["error"] = error
                break
        self._emit_event("task_step_update", {
            "title": self.title,
            "current_step": step_name,
            "step_index": step_index,
            "steps": self._serialize_steps()
        })

    def finish(self, success: bool = True, summary: str = ""):
        total_elapsed = round(time.time() - self.start_time, 2)
        self._emit_event("task_finished", {
            "title": self.title,
            "status": "success" if success else "failed",
            "total_elapsed": total_elapsed,
            "summary": summary,
            "steps": self._serialize_steps(),
            "logs": self.logs[-20:]
        })

    def _serialize_steps(self) -> List[Dict[str, Any]]:
        return [{
            "index": s["index"],
            "name": s["name"],
            "status": s["status"],
            "elapsed": s.get("elapsed", 0.0),
            "error": s.get("error", "")
        } for s in self.steps]

    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        try:
            from .watcher import WatcherEventQueue
            WatcherEventQueue.get_instance().push(event_type, {
                "task_id": self.task_id,
                "agent_name": self.agent_name,
                "target_agent": self.agent_name,
                **data
            })
        except Exception:
            pass


@dataclass
class TaskContext:
    """任务流转上下文"""
    task_id: str
    agent_name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _reporter: Optional[TaskReporter] = None

    def get_reporter(self, title: str = "") -> TaskReporter:
        if self._reporter is None:
            self._reporter = TaskReporter(self.task_id, self.agent_name, title)
        elif title and not self._reporter.title:
            self._reporter.title = title
        return self._reporter


@dataclass
class GuardResult:
    """门禁/规则审查结果"""
    passed: bool
    name: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def print_summary(self):
        icon = "🟢" if self.passed else "🔴"
        print(f"  {icon} [门禁审查: {self.name}] {'放行' if self.passed else '拦截'}")
        for err in self.errors:
            print(f"     ❌ 阻断原因: {err}")
        for warn in self.warnings:
            print(f"     ⚠️  合规警告: {warn}")


@dataclass
class TaskResult:
    """智能体最终执行结果"""
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    guard_reports: List[GuardResult] = field(default_factory=list)


class BaseGuard(ABC):
    """
    抽象门禁规则契约 (Guard)
    框架底座不预设任何平台规则。
    每个智能体可以按需挂载自身的前置校验（如参数合法性、外部凭据、平台死限）或后置质检（如敏感词、格式校验）。
    """
    def __init__(self, name: str, description: str = ""):
        self.name: str = name
        self.description: str = description

    @abstractmethod
    def check(self, context: TaskContext) -> GuardResult:
        """执行检查，返回 GuardResult。若 fatal_errors 非空则阻断后续执行。"""
        pass


class BaseSkill(ABC):
    """
    抽象技能契约 (Skill)
    代表一个可被智能体调用或独立运行的原子能力（例如：调用模型、处理音视频、生成图文、爬取网页等）。
    支持立体空间三级生态来源：official (官方) | community (第三方) | custom (自定义)。
    """
    def __init__(self, name: str, description: str = "", display_name: str = "",
                 version: str = "1.0.0", author: str = "立体空间官方", icon: str = "🧩",
                 category: str = "通用", origin: str = "official"):
        self.name: str = name
        self.description: str = description
        self.display_name: str = display_name or name
        self.version: str = version
        self.author: str = author
        self.icon: str = icon
        self.category: str = category
        self.origin: str = origin          # "official" | "community" | "custom"
        self.source_path: str = ""         # 物理文件路径
        self.enabled: bool = True
        self.manifest: Dict[str, Any] = {}
        self.inputs: List[Dict[str, Any]] = []
        self.outputs: List[Dict[str, Any]] = []

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行原子技能并返回产出数据字典"""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """序列化为前端可读的技能卡片元数据"""
        return {
            "name": self.name,
            "display_name": getattr(self, "display_name", self.name),
            "description": self.description,
            "version": getattr(self, "version", "1.0.0"),
            "author": getattr(self, "author", "立体空间官方"),
            "icon": getattr(self, "icon", "🧩"),
            "category": getattr(self, "category", "通用"),
            "origin": getattr(self, "origin", "official"),
            "source_path": getattr(self, "source_path", ""),
            "enabled": getattr(self, "enabled", True),
            "inputs": getattr(self, "inputs", []),
            "outputs": getattr(self, "outputs", [])
        }


class PromptSkill(BaseSkill):
    """纯提示词/SOP 流程型的轻量技能包装器"""
    def __init__(self, name: str, description: str = "", prompt_text: str = "", **kwargs):
        super().__init__(name=name, description=description, **kwargs)
        self.prompt_text = prompt_text

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"prompt": self.prompt_text, "params": params}


class BaseAgent(ABC):
    """
    抽象智能体基类 (BaseAgent)
    代表一个拥有特定领域专业知识的智能实体。
    由其自主声明：
    - pre_guards: 前置安全门禁列表；
    - post_guards: 后置产出质检门禁列表；
    - skills: 所拥有的技能字典。
    """
    def __init__(self, name: str, description: str = ""):
        self.name: str = name
        self.description: str = description
        self.pre_guards: List[BaseGuard] = []
        self.post_guards: List[BaseGuard] = []
        self.skills: Dict[str, BaseSkill] = {}
        self.source: str = "builtin"          # "builtin" (官方内置) | "external" (外部挂载)
        self.source_path: str = ""            # 物理路径

    def register_skill(self, skill: BaseSkill):
        """挂载一个技能"""
        self.skills[skill.name] = skill

    def add_pre_guard(self, guard: BaseGuard):
        """挂载一个前置安全门禁"""
        self.pre_guards.append(guard)

    def add_post_guard(self, guard: BaseGuard):
        """挂载一个后置质检门禁"""
        self.post_guards.append(guard)

    @abstractmethod
    def run(self, context: TaskContext) -> TaskResult:
        """智能体核心业务逻辑执行 (由具体的业务智能体去实现)"""
        pass

    def handle_fast_path(self, command: str) -> Optional[str]:
        """
        0-Token 快速直达接口 (子类可按需重写)
        若返回非 None 字符串，则代表直接命中本地 0-Token 极速通道，不产生任何大模型 Token 消耗。
        """
        return None

    def on_event(self, event_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        事件驱动启动入口 (Event-Driven Hook)
        当系统外部事件（如文件变动、MQ消息、系统告警、Webhook）触发时调用
        """
        return {"status": "ignored", "event": event_name}

    def get_config_schema(self) -> Dict[str, Any]:
        """通用的智能体设置 JSON Schema 契约，供 GUI 设置弹窗或 Web 前端动态渲染 (子类可按需实现)"""
        return {}

    def get_config(self) -> Dict[str, Any]:
        """获取当前智能体的生效配置字典 (子类可按需实现)"""
        return {}

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新当前智能体的配置字典 (子类可按需实现)"""
        return updates

    def get_preflight_items(self) -> List[Any]:
        """返回智能体前置自检与自愈项列表 (子类按需重写)"""
        return []

    def get_readiness_status(self) -> Dict[str, Any]:
        """返回智能体三态生命周期就绪度"""
        from .preflight import AutoHealer
        return AutoHealer.check_agent_readiness(self)

    def heal_environment(self, progress_callback=None) -> Dict[str, Any]:
        """执行全自动环境自愈"""
        from .preflight import AutoHealer
        return AutoHealer.heal_agent(self, progress_callback=progress_callback)

    def scheduled_run(self) -> Dict[str, Any]:
        """
        定时启动入口 (Scheduled Trigger)
        当系统定时器触发（如定时健康打卡、周期巡检汇总）时调用
        """
        import time
        return {"status": "executed", "timestamp": time.time()}

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        智能体多轮交互对话接口 (支持子类定制重写)
        1. 优先检查 Fast-Path 协议：若以 [EXEC] 等指令前缀开头，直达 0-Token 执行通道；
        2. 否则发送给大模型中枢网关进行推理。
        """
        # 1. 检查 Fast-Path 0-Token 快轨协议
        from .config import ConfigManager
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

        # 2. 检查具身技能意图 (0-Token 极速直达通道)
        from .tool_runner import ToolRunner
        if last_user_msg:
            skill_intent = ToolRunner.detect_offline_skill_intent(last_user_msg, self)
            if skill_intent:
                tool_id, params = skill_intent
                artifact = ToolRunner.execute_tool(tool_id, params, agent=self)
                card_md = ToolRunner.format_artifact_card_markdown(artifact)
                return (
                    f"🎨 收到指令！我已为您调用所装备的专属能力卡带 **【{artifact['tool_name']}】**，在本地 0-Token 为您绘制交付！\n"
                    f"{card_md}\n"
                    f"✨ 成果已为您渲染制作完成并安全保存至本地，您可以直接点击上方按钮打开或在文件管理器中查看！"
                )

        # 3. 常规大模型对话调用 (注入具身技能工具协议)
        from .llm import LLMClient, LLMError
        base_system_prompt = getattr(self, "system_prompt", f"你是【{self.name}】智能体。{self.description}")
        system_prompt = ToolRunner.build_tool_system_prompt(self, base_system_prompt)
        
        chat_msgs = list(messages)
        if not chat_msgs or chat_msgs[0].get("role") != "system":
            chat_msgs.insert(0, {"role": "system", "content": system_prompt})
            
        try:
            reply = LLMClient.chat(chat_msgs)
        except LLMError as le:
            # 容灾兜底：尝试离线意图识别
            if last_user_msg:
                offline_intent = ToolRunner.detect_offline_skill_intent(last_user_msg, self)
                if offline_intent:
                    tool_id, params = offline_intent
                    artifact = ToolRunner.execute_tool(tool_id, params, agent=self)
                    card_md = ToolRunner.format_artifact_card_markdown(artifact)
                    return (
                        f"🎨 收到指令！(云端连接受限，已自动切换本地原生执行通道)\n\n"
                        f"已为您调度能力卡带 **【{artifact['tool_name']}】**：\n"
                        f"{card_md}\n"
                        f"✨ 成果已物理保存至本地，您可以直接点击上方按钮查看！"
                    )
            raise le

        # 4. 解析大模型输出中的工具调用代码块并就地执行交付
        calls = ToolRunner.parse_tool_calls(reply)
        if calls:
            for c in calls:
                artifact = ToolRunner.execute_tool(c["tool"], c["params"], agent=self)
                card_md = ToolRunner.format_artifact_card_markdown(artifact)
                reply += f"\n\n{card_md}"

        return reply

    def stream_chat(self, messages: List[Dict[str, str]]) -> Iterator[str]:
        """
        流式分块输出接口 (SSE 增量推送)
        1. 检查 Fast-Path 0-Token 快轨协议：若命中，直接分块推送；
        2. 检查离线保底意图：若命中，直接推送本地执行结果；
        3. 否则携带具身工具协议调用 LLMClient.stream_chat() 流式生成；
        4. 捕获输出中的 tool_call，实时执行并在尾部附加交付物卡片。
        """
        from .config import ConfigManager
        from .tool_runner import ToolRunner
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
                yield fast_reply
                return

        # 检查具身技能意图 (0-Token 极速直达通道)
        if last_user_msg:
            skill_intent = ToolRunner.detect_offline_skill_intent(last_user_msg, self)
            if skill_intent:
                tool_id, params = skill_intent
                yield f"🎨 收到指令！我已为您调用所装备的专属能力卡带 **【{tool_id}】**，正在本地 0-Token 为您绘制交付...\n"
                artifact = ToolRunner.execute_tool(tool_id, params, agent=self)
                card_md = ToolRunner.format_artifact_card_markdown(artifact)
                yield card_md
                yield "\n✨ 成果已为您渲染制作完成并安全保存至本地，您可以直接点击上方按钮打开或在文件管理器中查看！"
                return

        from .llm import LLMClient, LLMError
        base_system_prompt = getattr(self, "system_prompt", f"你是【{self.name}】智能体。{self.description}")
        system_prompt = ToolRunner.build_tool_system_prompt(self, base_system_prompt)
        
        chat_msgs = list(messages)
        if not chat_msgs or chat_msgs[0].get("role") != "system":
            chat_msgs.insert(0, {"role": "system", "content": system_prompt})
            
        accumulated_text = ""
        try:
            for chunk in LLMClient.stream_chat(chat_msgs):
                accumulated_text += chunk
                yield chunk
        except LLMError as le:
            # 容灾兜底：尝试离线意图识别
            if last_user_msg:
                offline_intent = ToolRunner.detect_offline_skill_intent(last_user_msg, self)
                if offline_intent:
                    tool_id, params = offline_intent
                    yield f"\n\n🎨 (云端连接受限，已自动切换本地原生执行通道)\n已为您调度能力卡带 **【阿朝朋友圈海报极速直出】**：\n"
                    artifact = ToolRunner.execute_tool(tool_id, params, agent=self)
                    card_md = ToolRunner.format_artifact_card_markdown(artifact)
                    yield card_md
                    yield "\n✨ 成果已物理保存至本地，您可以直接点击上方按钮查看！"
                    return
            raise le

        # 流式传输完毕后，审查是否输出了工具调用代码块
        calls = ToolRunner.parse_tool_calls(accumulated_text)
        if calls:
            for c in calls:
                artifact = ToolRunner.execute_tool(c["tool"], c["params"], agent=self)
                card_md = ToolRunner.format_artifact_card_markdown(artifact)
                yield f"\n\n{card_md}"



