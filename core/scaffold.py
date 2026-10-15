# -*- coding: utf-8 -*-
"""
core/scaffold.py
【立体空间智能体系统 · 规范化业务工程脚手架 (Scaffolding 2.0)】

职责：
1. 一键生成符合 7 大工业级标准的智能体 (Agent)；
2. 标准化内置：
   - 继承 StandardAgent (具备 JSON Schema 动态配置、落盘持久化、0-Token Fast-Path)
   - 零顶层依赖 (SOP §4.3) + tools/ 懒加载示范
   - 环境前置门禁体检 (Preflight)
   - 任务工序流转与实时日志通知 (TaskReporter)
   - 启发式 NLP 兜底架构
   - 自动配套生成 tests/test_{name}.py 契约测试用例
3. 提供静态合规质检函数 check_agent_sop_compliance()。
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import ConfigManager

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


DISALLOWED_TOP_LEVEL_MODULES = {
    "requests", "urllib3", "aiohttp", "httpx",
    "baidupcs_py", "faster_whisper", "whisper",
    "torch", "torchvision", "torchaudio",
    "cv2", "PIL", "numpy", "pandas", "scipy", "sklearn",
    "playwright", "selenium", "moviepy", "pydub"
}


def check_agent_sop_compliance(agent_dir: Path) -> List[str]:
    """
    对指定智能体工程目录进行 SOP 工业级合规静态扫描
    检查项：
    1. 关键文件物理存在 (config.yaml, persona/prompt.md, entry.py)
    2. Python 源码顶层 AST 扫描：严禁顶层导入第三方重量级包 (SOP §4.3)
    3. entry.py 规范接口契约与 setup(registry) 挂载点
    """
    errors = []
    if not agent_dir.exists():
        return [f"目录不存在: {agent_dir}"]

    # 1. 结构完整性校验
    req_files = [
        agent_dir / "config.yaml",
        agent_dir / "persona" / "prompt.md",
        agent_dir / "entry.py"
    ]
    for rf in req_files:
        if not rf.exists():
            errors.append(f"缺少必要规范文件: {rf.relative_to(agent_dir)}")

    # 2. AST 顶层依赖扫描
    for py_file in agent_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"解析 Python 语法失败 [{py_file.name}]: {e}")
            continue

        for node in tree.body:
            # 仅扫描模块顶层的 Import 节点
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0]
                    if root_pkg in DISALLOWED_TOP_LEVEL_MODULES:
                        errors.append(
                            f"[{py_file.name}:{node.lineno}] 违反 SOP §4.3: 顶层严禁导入第三方库 '{root_pkg}'，"
                            f"必须在函数内进行延迟加载 (Lazy Import)！"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg in DISALLOWED_TOP_LEVEL_MODULES:
                        errors.append(
                            f"[{py_file.name}:{node.lineno}] 违反 SOP §4.3: 顶层严禁导入第三方库 '{root_pkg}'，"
                            f"必须在函数内进行延迟加载 (Lazy Import)！"
                        )

    # 3. 挂载入口校验
    entry_path = agent_dir / "entry.py"
    if entry_path.exists():
        content = entry_path.read_text(encoding="utf-8")
        if "def setup(" not in content:
            errors.append("[entry.py] 缺少 setup(registry) 动态插件挂载函数")

        # 4. 环境自检与自愈契约校验 (Fail-Early Inspection & Self-Healing Contract)
        # 严格遵守《智能体开发三大首要铁律》: 智能体在开发时必须具备环境检测与一键安装依赖能力
        try:
            entry_tree = ast.parse(content)
            has_self_check = False
            for node in entry_tree.body:
                if isinstance(node, ast.ClassDef):
                    # 检查基类是否包含 StandardAgent 或 StandardSelfHealingMixin
                    base_names = [b.id for b in node.bases if isinstance(b, ast.Name)]
                    base_attrs = [b.attr for b in node.bases if isinstance(b, ast.Attribute)]
                    all_bases = set(base_names + base_attrs)
                    if "StandardAgent" in all_bases or "StandardSelfHealingMixin" in all_bases:
                        has_self_check = True
                        break

                    # 检查是否定义了环境自检/就绪探针/自愈方法
                    method_names = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
                    if any(m in method_names for m in (
                        "get_preflight_items", "get_readiness_status", "heal_environment",
                        "check_readiness", "run_preflight", "handle_fast_path", "run_media_environment_check"
                    )):
                        has_self_check = True
                        break
            if not has_self_check:
                errors.append(
                    "[entry.py] 违反《智能体开发三大首要铁律》: 智能体必须具备环境自检与自愈能力！"
                    "请继承 StandardAgent，或实现 get_preflight_items() / check_readiness()。"
                )
        except Exception:
            pass

    return errors


def create_agent_scaffold(name: str, description: str = "", is_custom: bool = True, agent_type: str = "media", with_tests: bool = True) -> Path:
    """
    生成标准化 Agent 插件目录工程 (Scaffold 2.0)
    :param name: 智能体标识名 (snake_case)
    :param description: 功能简介
    :param is_custom: 是否创建为外部自定义插件
    :param agent_type: 智能体类型 "media" (自媒体/内容生产类) 或 "general" (通用任务类)
    :param with_tests: 是否同步生成配套自动化测试文件
    """
    cm = ConfigManager.get_instance()
    base_dir = (cm.workspace_dir / "custom_agents") if is_custom else cm.agents_dir
    target_dir = base_dir / name

    if target_dir.exists():
        raise FileExistsError(f"目标智能体目录已存在: {target_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "persona").mkdir(exist_ok=True)
    (target_dir / "tools").mkdir(exist_ok=True)

    desc = description or f"{name} 工业化业务智能体"
    class_name = "".join(part.capitalize() for part in name.split("_")) + "Agent"

    # 1. config.yaml
    config_content = f"""name: "{name}"
display_name: "{name.title().replace('_', ' ')} 智能体"
version: "1.0.0"
icon: "{'🎬' if agent_type == 'media' else '🤖'}"
category: "{'自媒体矩阵' if agent_type == 'media' else '业务拓展'}"
description: "{desc}"
author: "Litikj Developer"

quick_chips:
  - "⚡ [EXEC] ping (0-Token 基础连通测试)"
  - "🔍 [EXEC] check (全景环境与依赖体检)"
  - "🩹 [EXEC] heal (一键环境全自动静默自愈)"
  - "⚙️ [EXEC] config (查看通用设置面板)"
  - "你好，请介绍你的核心业务能力"

actions:
  - label: "环境巡检"
    command: "[EXEC] check"
    icon: "🔍"
  - label: "一键自愈"
    command: "[EXEC] heal"
    icon: "🩹"
  - label: "设置配置"
    command: "[EXEC] config"
    icon: "⚙️"
  - label: "连通测试"
    command: "[EXEC] ping"
    icon: "⚡"
"""
    (target_dir / "config.yaml").write_text(config_content, encoding="utf-8")

    # 2. persona/prompt.md
    prompt_content = f"""# 【{name}】人设与行为准则

你是一个名为【{name}】的专业工业级智能体。
你的职责是：{desc}。

## 行为规范：
1. **拒绝死板模板**：严禁输出泛化的套话，所有推荐结论必须基于用户输入或真实内容动态提炼。
2. **Fail-Early 原则**：在执行多步骤流水线前，必须前置检查系统环境与输入文件有效性，若异常则优雅阻断并给出自愈方案。
3. **输出闭环**：任务处理完毕后，必须以结构化交付卡片形式输出物料、文件路径及一键确认操作指令。
"""
    (target_dir / "persona" / "prompt.md").write_text(prompt_content, encoding="utf-8")

    # 3. tools/__init__.py & tools/demo_tool.py
    (target_dir / "tools" / "__init__.py").write_text("# -*- coding: utf-8 -*-\n", encoding="utf-8")
    demo_tool_content = f"""# -*- coding: utf-8 -*-
\"\"\"
{name}/tools/demo_tool.py
【示范工具模块 · 严格遵循 SOP §4.3 零顶层依赖与延迟加载规范】
\"\"\"

from pathlib import Path
from typing import Dict, Any


def execute_demo_task(param: str) -> Dict[str, Any]:
    \"\"\"
    执行示范任务。
    如果需要第三方库 (例如 requests, PIL 等)，必须在函数内导入：
    \"\"\"
    # [示范] 运行时延迟加载，绝不写在文件顶层:
    # try:
    #     import requests
    # except ImportError:
    #     raise RuntimeError("缺少 requests 依赖，请在终端执行 [EXEC] setup 修复")

    return {{
        "status": "success",
        "result": f"已成功处理任务: {{param}}"
    }}
"""
    (target_dir / "tools" / "demo_tool.py").write_text(demo_tool_content, encoding="utf-8")

    # 4. entry.py (基于 StandardAgent)
    entry_content = f"""# -*- coding: utf-8 -*-
\"\"\"
{name}/entry.py
【{name} 智能体业务实现】
遵循立体空间 7 大标准规范：
1. 继承 StandardAgent，开箱即用支持通用设置面板与落盘 (get_config_schema / get_config / update_config)；
2. 具备 0-Token Fast-Path 本地极速通道 (handle_fast_path)；
3. 具备前置环境依赖体检与优雅阻断 (Preflight Check)；
4. 具备多工序流水线日志上报 (TaskReporter)；
5. 接入大模型并配齐无死板模板的启发式 NLP 动态兜底；
6. 严格零顶层第三方依赖 (SOP §4.3)。
\"\"\"

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.standard_agent import StandardAgent
from core.contract import TaskContext, TaskResult
from core.guards import LicenseGuard
from core.registry import Registry
from core.preflight import PreflightChecker
from core.nlp_extractor import HeuristicNLPExtractor
from core.llm import LLMClient


class {class_name}(StandardAgent):
    \"\"\"{desc}\"\"\"

    # 【三大首要铁律：环境自检与静默自愈声明】
    # 出厂底座保持绝对纯净，按需在此声明专属目录与依赖
    DROP_BOX_DIRS: List[str] = ["drop_box/{name}"]
    REQUIRED_PACKAGES: List[str] = []
    REQUIRED_BINARIES: List[str] = [{'["ffmpeg"]' if agent_type == 'media' else '[]'}]

    # 标准配置面板 JSON Schema 定义 (对齐 AgentSettingsModal.vue)
    CONFIG_SCHEMA = {{
        "title": "{name} 预置业务配置",
        "type": "object",
        "properties": {{
            "target_account": {{
                "type": "string",
                "title": "运营账号矩阵",
                "enum": ["default", "primary", "secondary"],
                "enumNames": ["默认测试账号 (default)", "主账号 (primary)", "备用副矩阵 (secondary)"],
                "default": "default",
                "description": "当前自动化产物所属的矩阵账号"
            }},
            "publish_mode": {{
                "type": "string",
                "title": "产物交付模式",
                "enum": ["package", "draft", "direct"],
                "enumNames": ["📦 本地物料包 (安全落盘 · 人工核查)", "📝 私密草稿箱模式 (快速过审)", "🚀 自动全量直发模式"],
                "default": "package",
                "description": "物料产出后的流转策略"
            }},
            "style_tag": {{
                "type": "string",
                "title": "视觉与文案风格",
                "default": "极简专业",
                "description": "内容提炼与封面排版的视觉基调"
            }},
            "auto_notify": {{
                "type": "boolean",
                "title": "完成后弹窗通知",
                "default": True,
                "description": "物料交付后是否触发桌面通知"
            }}
        }}
    }}

    DEFAULT_CONFIG = {{
        "target_account": "default",
        "publish_mode": "package",
        "style_tag": "极简专业",
        "auto_notify": True
    }}

    def __init__(self):
        super().__init__(
            name="{name}",
            description="{desc}"
        )
        self.base_dir = Path(__file__).resolve().parent
        
        # 挂载基础授权门禁
        self.add_pre_guard(LicenseGuard(name="{name} 授权审计门禁", strict=False))

        # 读取人设提示词
        prompt_file = self.base_dir / "persona" / "prompt.md"
        self.system_prompt = prompt_file.read_text(encoding="utf-8").strip() if prompt_file.exists() else ""

    # =================================================================
    # 【0-Token 自定义扩展通道 (Custom Fast-Path)】
    # =================================================================
    def handle_custom_fast_path(self, command: str) -> Optional[str]:
        \"\"\"扩展特有的 0-Token 快速指令 (基础指令 ping/check/heal/config/set/help 已由基类全自动处理)\"\"\"
        cmd = command.strip().lower()
        parts = cmd.split()
        root_cmd = parts[0] if parts else ""

        if root_cmd == "info":
            return f"### ℹ️ 【{name}】智能体状态简报\\n- 交付模式: `{{self.get_config_value('publish_mode')}}`\\n- 账号: `{{self.get_config_value('target_account')}}`"

        return None

    # =================================================================
    # 【任务流水线调度入口 (5-Stage TaskReporter)】
    # =================================================================
    def run(self, context: TaskContext) -> TaskResult:
        \"\"\"工业化自动化流水线交付入口\"\"\"
        reporter = context.get_reporter(title=f"{{self.name}} 自动化交付流水线")
        payload = context.payload or {{}}
        cfg = self.get_config()

        # 工序 1：环境与门禁巡检 (Fail-Early 零心智防御)
        with reporter.step("环境与输入门禁体检"):
            reporter.log("正在探测智能体运行依赖与投递箱目录...")
            readiness = self.get_readiness_status()
            if readiness.get("state") != "READY":
                reporter.log("⚠️ 检测到环境未完备，自动触发静默自愈...")
                heal_res = self.heal_environment()
                if heal_res.get("state") != "READY":
                    diag_msg = f"智能体环境自愈受阻 ({{heal_res.get('state')}}): 请先执行 [EXEC] heal 或完成界面指引。"
                    return TaskResult(success=False, message=diag_msg, data={{"error": "environment_not_ready"}})
            reporter.log("前置门禁巡检通过，环境 100% 就绪 🟢")

        # 工序 2：业务处理与内容提炼 (以启发式 NLP 结合大模型为例)
        with reporter.step("业务处理与内容提炼"):
            reporter.log("正在解析输入任务并提炼高转化物料...")
            topic = str(payload.get("topic") or "示例业务主题")
            input_text = str(payload.get("text") or "本期实操深入拆解核心系统架构与代码落地实践。")
            
            # 使用公共 NLP 核心库进行动态提炼
            keywords = HeuristicNLPExtractor.extract_keywords(input_text)
            titles = HeuristicNLPExtractor.generate_candidate_titles(topic, input_text, keywords)
            reporter.log(f"已动态生成 {{len(titles)}} 组备选标题")

        # 工序 3：整理标准交付物料简报
        report_card = [
            f"## 🎬 《{{topic}}》交付简报",
            f"> **当前模式**：`{{cfg.get('publish_mode')}}` · **账号矩阵**：`{{cfg.get('target_account')}}`",
            "---",
            f"#### 1. 推荐主标题：`{{titles[0]}}`",
            "备选标题：",
            f"  • {{titles[1]}}",
            f"  • {{titles[2]}}",
            "",
            f"#### 2. 精准标签：`{{', '.join(keywords)}}`",
            "---",
            "### 🎯 一键确认指令：",
            "- `[EXEC] config`：调整智能体配置面板",
            "- `[EXEC] ping`：连通性健康复查"
        ]

        return TaskResult(
            success=True,
            message="\\n".join(report_card),
            data={{"titles": titles, "keywords": keywords, "config": cfg}}
        )


def setup(registry: Registry):
    \"\"\"动态插件挂载入口\"\"\"
    registry.register_agent({class_name}())
"""
    (target_dir / "entry.py").write_text(entry_content, encoding="utf-8")

    # 5. README.md
    readme_content = f"""# 🤖 {name} 智能体工程说明书

- **中文名称**：{name.title().replace('_', ' ')}
- **类型**：{'自媒体矩阵类' if agent_type == 'media' else '通用业务类'}
- **简介**：{desc}

## 内置标准支持：
1. **通用标准设置面板**：继承 `StandardAgent`，自动对接前端 `AgentSettingsModal.vue` 动态渲染；
2. **0-Token 快速直达指令**：`[EXEC] ping`、`[EXEC] check`、`[EXEC] config`、`[EXEC] set`、`[EXEC] help`；
3. **Fail-Early 门禁防御**：集成 `PreflightChecker`，缺失依赖时优雅截断并引导自愈；
4. **动态 NLP 提炼与兜底**：集成 `HeuristicNLPExtractor`，杜绝死模板；
5. **零顶层第三方依赖**：遵循 SOP §4.3，在便携微内核中安全热发现。
"""
    (target_dir / "README.md").write_text(readme_content, encoding="utf-8")

    # 6. 配套单元测试生成 tests/test_{name}.py
    if with_tests:
        if not is_custom:
            import_code = f"from agents.{name}.entry import {class_name}"
        else:
            import_code = f"""import importlib.util
_entry_p = Path(__file__).resolve().parents[1] / "custom_agents" / "{name}" / "entry.py"
_spec = importlib.util.spec_from_file_location("custom_agents.{name}.entry", _entry_p)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
{class_name} = getattr(_mod, "{class_name}")"""

        if not test_file.exists():
            test_content = f"""# -*- coding: utf-8 -*-
\"\"\"
tests/test_{name}.py
【{name} 智能体工业化自动化契约测试套件】
覆盖：
1. Schema 契约与配置持久化测试；
2. 0-Token Fast-Path 指令回路测试；
3. Fail-Early 门禁与 TaskReporter 流水线测试；
4. SOP §4.3 零顶层依赖静态扫描测试。
\"\"\"

import pytest
from pathlib import Path
from core.contract import TaskContext
from core.scaffold import check_agent_sop_compliance
{import_code}


def test_{name}_sop_compliance():
    \"\"\"测试智能体是否完全符合工业级 SOP 规约 (零顶层第三方依赖)\"\"\"
    agent_dir = Path(__file__).resolve().parents[1] / "{'custom_agents' if is_custom else 'agents'}" / "{name}"
    errors = check_agent_sop_compliance(agent_dir)
    assert errors == [], f"SOP 规约校验未通过: {{errors}}"


def test_{name}_config_schema_contract():
    \"\"\"测试通用设置面板 JSON Schema 契约与配置持久化\"\"\"
    agent = {class_name}()
    schema = agent.get_config_schema()
    assert "properties" in schema
    assert "target_account" in schema["properties"]

    # 读取初始配置
    cfg = agent.get_config()
    assert isinstance(cfg, dict)
    assert "target_account" in cfg

    # 更新并持久化配置
    updated = agent.update_config({{"target_account": "primary", "auto_notify": False}})
    assert updated["target_account"] == "primary"
    assert updated["auto_notify"] is False

    # 恢复默认
    agent.update_config({{"target_account": "default", "auto_notify": True}})


def test_{name}_fast_path_routing():
    \"\"\"测试 0-Token Fast-Path 快速直达指令\"\"\"
    agent = {class_name}()

    # 1. ping
    res_ping = agent.handle_fast_path("ping")
    assert res_ping is not None
    assert "0-Token PONG" in res_ping

    # 2. config
    res_cfg = agent.handle_fast_path("config")
    assert res_cfg is not None
    assert "当前生效配置看板" in res_cfg

    # 3. set
    res_set = agent.handle_fast_path("set style_tag 赛博朋克风")
    assert "配置更新成功" in res_set
    assert agent.get_config_value("style_tag") == "赛博朋克风"

    # 4. help
    res_help = agent.handle_fast_path("help")
    assert "快速指令清单" in res_help


def test_{name}_self_healing_and_check():
    \"\"\"测试智能体环境自检与静默自愈能力 (SOP 铁律二与铁律三)\"\"\"
    agent = {class_name}()
    readiness = agent.get_readiness_status()
    assert "state" in readiness
    assert "items" in readiness

    # 验证具备 [EXEC] check 指令
    res_chk = agent.handle_fast_path("check")
    assert res_chk is not None
    assert "全景巡检看板" in res_chk

    # 验证具备 [EXEC] heal 指令
    res_heal = agent.handle_fast_path("heal")
    assert res_heal is not None


def test_{name}_run_pipeline():
    \"\"\"测试多工序流水线调度\"\"\"
    agent = {class_name}()
    ctx = TaskContext(
        task_id="test_run_01",
        agent_name="{name}",
        payload={{"topic": "工业化系统开发", "text": "本期实操深入拆解核心系统架构与代码落地实践。"}}
    )
    result = agent.run(ctx)
    assert result.success is True
    assert "交付简报" in result.message
    assert len(result.data["titles"]) > 0
"""
            test_file.write_text(test_content, encoding="utf-8")
            print(f"✨ [Scaffold] 配套单元测试已生成: {test_file}")

    print(f"✨ [Scaffold] 标准化智能体工程已就绪: {target_dir}")
    return target_dir


def create_workflow_scaffold(name: str, description: str = "") -> Path:
    """生成标准化 Workflow 协作流水线脚本"""
    cm = ConfigManager.get_instance()
    workflows_dir = cm.workflows_dir
    workflows_dir.mkdir(parents=True, exist_ok=True)
    target_file = workflows_dir / f"{name}.py"

    if target_file.exists():
        raise FileExistsError(f"目标流水线脚本已存在: {target_file}")

    desc = description or f"{name} 多智能体接力流水线"

    wf_content = f"""# -*- coding: utf-8 -*-
\"\"\"
workflows/{name}.py
【{desc}】
\"\"\"

from typing import Dict, Any
from core.workflow import Workflow
from core.registry import Registry


def create_{name}_workflow() -> Workflow:
    flow = Workflow(
        name="{name}",
        description="{desc}"
    )

    flow.add_step(
        agent_name="omni_sentinel",
        step_name="底座环境与系统巡检",
        transformer=lambda state, p: {{"action": "inspect"}}
    )

    return flow


def setup(registry: Registry):
    \"\"\"注册中心自动挂载入口\"\"\"
    workflow = create_{name}_workflow()
    registry.register_workflow(workflow)
"""
    target_file.write_text(wf_content, encoding="utf-8")
    print(f"✨ [Scaffold] 流水线工程已成功生成: {target_file}")
    return target_file


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="立体空间智能体工程脚手架与合规检查 CLI")
    subparsers = parser.add_subparsers(dest="cmd")

    # 创建智能体
    p_agent = subparsers.add_parser("agent", help="一键创建标准化 Agent 工程")
    p_agent.add_argument("name", help="智能体标识 (如: seo_article_writer)")
    p_agent.add_argument("--desc", default="", help="智能体简介")
    p_agent.add_argument("--builtin", action="store_true", help="是否创建到 agents/ 目录 (默认 custom_agents/)")
    p_agent.add_argument("--type", choices=["media", "general"], default="media", help="智能体业务类型")

    # 检查智能体合规
    p_check = subparsers.add_parser("check", help="静态扫描智能体 SOP 合规性")
    p_check.add_argument("target", help="智能体目录路径或名称")

    args = parser.parse_args()

    if args.cmd == "agent":
        create_agent_scaffold(
            name=args.name,
            description=args.desc,
            is_custom=not args.builtin,
            agent_type=args.type
        )
    elif args.cmd == "check":
        p = Path(args.target)
        if not p.exists():
            cm = ConfigManager.get_instance()
            p = cm.agents_dir / args.target
        errs = check_agent_sop_compliance(p)
        if not errs:
            print(f"✅ 智能体 [{p.name}] 完美符合工业级 SOP 规约！")
        else:
            print(f"❌ 智能体 [{p.name}] 发现 {len(errs)} 项不合规问题：")
            for e in errs:
                print(f"  • {e}")
            sys.exit(1)
    else:
        parser.print_help()
