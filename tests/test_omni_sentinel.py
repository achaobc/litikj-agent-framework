# -*- coding: utf-8 -*-
"""
tests/test_omni_sentinel.py
【OmniSentinel 全维调度标杆示范智能体 · 标准化端到端回归测试套件 (AGENT SPEC v2.5)】

验证项：
1. 智能体自动发现与基准注册
2. StandardAgent 通用配置面板契约与持久化 (get_config_schema / update_config / [EXEC] config / set)
3. 0-Token 快速直达通道 (ping / status / report / demo / help)
4. 环境前置门禁与静默自愈 (Preflight / check / heal)
5. 四维全触发模式 (0-Token / 对话认知 / 定时周期 / 事件驱动)
6. TaskReporter 工序流转与交付卡片输出
7. 外部智能体挂载与动态隔离验证
"""

import sys
import shutil
import time
from pathlib import Path
import pytest

# 添加项目根目录
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import ConfigManager
from core.registry import Registry
from core.engine import Engine
from core.contract import TaskContext


@pytest.fixture(scope="module")
def agent():
    """初始化微内核并返回 omni_sentinel 实例"""
    cm = ConfigManager.get_instance(force_reload=True)
    reg = Registry.get_instance()
    reg.auto_discover()
    ag = reg.get_agent("omni_sentinel")
    assert ag is not None, "未在 Registry 中发现 omni_sentinel 智能体！"
    return ag


def test_omni_sentinel_discovery(agent):
    """1. 验证智能体自动发现与元数据"""
    assert agent.name == "omni_sentinel"
    assert "全维调度" in agent.description
    assert hasattr(agent, "CONFIG_SCHEMA")
    assert hasattr(agent, "DEFAULT_CONFIG")


def test_omni_sentinel_config_schema_and_persistence(agent):
    """2. 验证通用标准设置面板 (JSON Schema 契约与落盘持久化)"""
    # 2.1 Schema 契约验证
    schema = agent.get_config_schema()
    assert schema.get("type") == "object"
    props = schema.get("properties", {})
    assert "patrol_interval" in props
    assert "disk_alert_threshold_gb" in props
    assert "report_format" in props

    # 2.2 读取默认配置
    cfg = agent.get_config()
    assert "patrol_interval" in cfg
    original_interval = cfg.get("patrol_interval", 3600)

    # 2.3 修改配置并验证落盘
    updated = agent.update_config({"patrol_interval": 1800})
    assert updated["patrol_interval"] == 1800
    assert agent.get_config_value("patrol_interval") == 1800

    # 2.4 测试 [EXEC] config 看板
    cfg_reply = agent.chat([{"role": "user", "content": "[EXEC] config"}])
    assert "当前生效配置看板" in cfg_reply
    assert "patrol_interval" in cfg_reply

    # 2.5 测试 [EXEC] set 快捷指令
    set_reply = agent.chat([{"role": "user", "content": "[EXEC] set patrol_interval 2400"}])
    assert "配置更新成功" in set_reply
    assert agent.get_config_value("patrol_interval") == 2400

    # 2.6 恢复原始配置
    agent.update_config({"patrol_interval": original_interval})


def test_omni_sentinel_fast_path(agent):
    """3. 验证 0-Token 快速直达通道 (Fast-Path)"""
    # 3.1 [EXEC] ping 毫秒级心跳
    t0 = time.time()
    ping_reply = agent.chat([{"role": "user", "content": "[EXEC] ping"}])
    t_ping = (time.time() - t0) * 1000
    assert "0-Token PONG" in ping_reply or "PONG" in ping_reply
    assert "omni_sentinel" in ping_reply
    assert t_ping < 50, f"ping 响应延时过长: {t_ping:.2f}ms"

    # 3.2 [EXEC] status 极速诊断看板
    status_reply = agent.chat([{"role": "user", "content": "[EXEC] status"}])
    assert "0-Token 快速直达" in status_reply
    assert "磁盘空间" in status_reply or "磁盘占用" in status_reply
    assert "活跃智能体" in status_reply

    # 3.3 [EXEC] demo 演示代码
    demo_reply = agent.chat([{"role": "user", "content": "[EXEC] demo"}])
    assert "全维调度哨兵核心微内核调用范式" in demo_reply
    assert "```python" in demo_reply

    # 3.4 [EXEC] help 帮助菜单
    help_reply = agent.chat([{"role": "user", "content": "[EXEC] help"}])
    assert "0-Token 快速指令清单" in help_reply


def test_omni_sentinel_preflight_and_heal(agent):
    """4. 验证环境前置门禁体检与静默自愈 (Fail-Early & Auto-Healing)"""
    # 4.1 检查 PreflightItems
    items = agent.get_preflight_items()
    assert len(items) >= 2
    item_names = [it.name for it in items]
    assert any("工作区" in name for name in item_names)

    # 4.2 检查全景就绪度探针
    readiness = agent.get_readiness_status()
    assert readiness["state"] in ("READY", "INSTALLING_DEPENDENCIES", "ACTION_REQUIRED")
    assert readiness["progress"] >= 0

    # 4.3 [EXEC] check 0-Token 看板
    check_reply = agent.chat([{"role": "user", "content": "[EXEC] check"}])
    assert "运行就绪度全景巡检看板" in check_reply
    assert "生命周期状态" in check_reply

    # 4.4 [EXEC] heal 自愈指令
    heal_reply = agent.chat([{"role": "user", "content": "[EXEC] heal"}])
    assert "环境自愈" in heal_reply


def test_omni_sentinel_scheduled_run(agent):
    """5. 验证定时启动与打卡报告写入与轮转 (Scheduled Trigger)"""
    sched_res = agent.scheduled_run()
    assert sched_res["success"] is True
    report_file = Path(sched_res["report_path"])
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "OmniSentinel Report" in content or "0 Token" in content or "token_cost" in content


def test_omni_sentinel_event_driven(agent):
    """6. 验证事件驱动启动 (Event-Driven Trigger)"""
    event_res = agent.on_event("file_changed", {"file_path": "test_script.py", "action": "created"})
    assert event_res["handled"] is True
    assert "test_script.py" in event_res["message"]

    event_alert = agent.on_event("alert_triggered", {"level": "CRITICAL", "reason": "磁盘空间预警"})
    assert event_alert["handled"] is True
    assert "CRITICAL" in event_alert["message"]


def test_omni_sentinel_dialogue_cognition(agent):
    """7. 验证对话认知启动 (Dialogue Trigger)"""
    reply = agent.chat([{"role": "user", "content": "请用一段话简短阐述：为何智能体系统需要混合调度？"}])
    assert len(reply) > 20


def test_omni_sentinel_batch_run_with_task_reporter(agent):
    """8. 验证 Engine 批处理流水线与 TaskReporter 工序流转"""
    reg = Registry.get_instance()
    engine = Engine(reg)
    ctx = TaskContext(task_id="test_sentinel_pipeline", agent_name="omni_sentinel", payload={"action": "inspect"})
    run_res = engine.dispatch(ctx)
    assert run_res.success is True
    assert "OmniSentinel 标杆巡检流水线执行完毕" in run_res.message
    assert ctx._reporter is not None
    assert len(ctx._reporter.steps) == 4
    assert "工序 1" in ctx._reporter.steps[0]["name"]
    assert len(ctx._reporter.logs) > 0


def test_omni_sentinel_external_agent_mounting():
    """9. 验证外部智能体挂载与动态隔离机制"""
    cm = ConfigManager.get_instance()
    reg = Registry.get_instance()

    custom_dir = cm.workspace_dir / "custom_agents" / "dummy_external_bot"
    custom_dir.mkdir(parents=True, exist_ok=True)
    custom_entry = custom_dir / "entry.py"

    code = """# -*- coding: utf-8 -*-
from core.contract import BaseAgent, TaskContext, TaskResult
from core.registry import Registry

class DummyExternalAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="dummy_external_bot", description="用于测试外部挂载的模拟智能体")
    def run(self, ctx):
        return TaskResult(success=True, message="外部智能体运行正常")
    def handle_fast_path(self, cmd):
        return f"外部智能体 0-Token 响应: {cmd}"

def setup(registry: Registry):
    registry.register_agent(DummyExternalAgent())
"""
    custom_entry.write_text(code, encoding="utf-8")

    try:
        reg.auto_discover()
        ext_agent = reg.get_agent("dummy_external_bot")
        assert ext_agent is not None, "外部智能体未被 Registry 扫描发现！"
        assert ext_agent.source == "external"

        ext_fast = ext_agent.chat([{"role": "user", "content": "[EXEC] hello"}])
        assert "外部智能体 0-Token 响应: hello" in ext_fast
    finally:
        shutil.rmtree(custom_dir, ignore_errors=True)
        reg.auto_discover()


if __name__ == "__main__":
    pytest.main(["-v", __file__])
