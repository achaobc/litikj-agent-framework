# -*- coding: utf-8 -*-
"""
tests/test_standard_agent_and_scaffold.py
【验证标准基类 StandardAgent、SOP 合规扫描器与脚手架 2.0】
"""

import pytest
from pathlib import Path
from core.standard_agent import StandardAgent, StandardConfigMixin, StandardFastPathMixin
from core.contract import TaskContext, TaskResult
from core.scaffold import check_agent_sop_compliance, create_agent_scaffold


class MockDemoAgent(StandardAgent):
    CONFIG_SCHEMA = {
        "title": "测试模拟智能体",
        "type": "object",
        "properties": {
            "channel": {"type": "string", "default": "vlog", "title": "渠道"},
            "retry_limit": {"type": "integer", "default": 3, "title": "重试上限"}
        }
    }
    DEFAULT_CONFIG = {
        "channel": "vlog",
        "retry_limit": 3
    }
    CONFIG_FILE_NAME = "mock_demo_agent_config.json"

    def __init__(self):
        super().__init__(name="mock_demo_agent", description="模拟测试智能体")

    def run(self, context: TaskContext) -> TaskResult:
        return TaskResult(success=True, message="mock run ok")


def test_standard_agent_config_and_persistence():
    agent = MockDemoAgent()

    # 1. Schema 契约
    schema = agent.get_config_schema()
    assert schema["title"] == "测试模拟智能体"
    assert "channel" in schema["properties"]

    # 2. 读取默认配置
    cfg = agent.get_config()
    assert cfg["channel"] == "vlog"
    assert cfg["retry_limit"] == 3

    # 3. 更新并持久化
    updated = agent.update_config({"channel": "tech", "retry_limit": 5})
    assert updated["channel"] == "tech"
    assert updated["retry_limit"] == 5
    assert agent.get_config_value("channel") == "tech"

    # 4. 恢复默认
    agent.update_config({"channel": "vlog", "retry_limit": 3})


def test_standard_agent_fast_path():
    agent = MockDemoAgent()

    # 1. ping
    res_ping = agent.handle_fast_path("ping")
    assert res_ping is not None
    assert "0-Token PONG" in res_ping
    assert "mock_demo_agent" in res_ping

    # 2. config
    res_cfg = agent.handle_fast_path("config")
    assert res_cfg is not None
    assert "当前生效配置看板" in res_cfg

    # 3. set
    res_set = agent.handle_fast_path("set channel gaming")
    assert "配置更新成功" in res_set
    assert agent.get_config_value("channel") == "gaming"

    # 恢复
    agent.set_config_value("channel", "vlog")

    # 4. help
    res_help = agent.handle_fast_path("help")
    assert "快速指令清单" in res_help


def test_sop_compliance_checker(tmp_path):
    # 1. 真实正向测试
    from core.config import ConfigManager
    cm = ConfigManager.get_instance()
    sentinel_dir = cm.agents_dir / "omni_sentinel"
    assert check_agent_sop_compliance(sentinel_dir) == []

    # 2. 构造违规反向用例：顶层包含 import requests
    bad_agent = tmp_path / "bad_agent"
    bad_agent.mkdir()
    (bad_agent / "config.yaml").write_text("name: bad\nversion: 1.0.0\n", encoding="utf-8")
    (bad_agent / "persona").mkdir()
    (bad_agent / "persona" / "prompt.md").write_text("prompt", encoding="utf-8")
    (bad_agent / "entry.py").write_text(
        "import requests\nfrom core.contract import BaseAgent\ndef setup(reg): pass\n",
        encoding="utf-8"
    )

    errs = check_agent_sop_compliance(bad_agent)
    assert len(errs) > 0
    assert any("SOP §4.3" in e and "requests" in e for e in errs)

    # 3. 构造违规反向用例：缺失环境自检与自愈契约 (违反三大首要铁律)
    no_check_agent = tmp_path / "no_check_agent"
    no_check_agent.mkdir()
    (no_check_agent / "config.yaml").write_text("name: no_check\nversion: 1.0.0\n", encoding="utf-8")
    (no_check_agent / "persona").mkdir()
    (no_check_agent / "persona" / "prompt.md").write_text("prompt", encoding="utf-8")
    (no_check_agent / "entry.py").write_text(
        "class NoCheckAgent:\n    def run(self): pass\ndef setup(reg): pass\n",
        encoding="utf-8"
    )
    errs_nc = check_agent_sop_compliance(no_check_agent)
    assert any("三大首要铁律" in e and "自检与自愈能力" in e for e in errs_nc)


def test_scaffold_creation(tmp_path):
    from core.config import ConfigManager
    cm = ConfigManager.get_instance()
    test_agent_name = "temp_scaffold_tester"
    target_dir = cm.workspace_dir / "custom_agents" / test_agent_name

    import shutil
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)

    try:
        created = create_agent_scaffold(
            name=test_agent_name,
            description="脚手架测试专用智能体",
            is_custom=True,
            agent_type="general",
            with_tests=False
        )
        assert created.exists()
        assert (created / "config.yaml").exists()
        assert (created / "persona" / "prompt.md").exists()
        assert (created / "tools" / "demo_tool.py").exists()
        assert (created / "entry.py").exists()

        # 验证新生成的工程本身 100% 遵守 SOP
        errs = check_agent_sop_compliance(created)
        assert errs == []
    finally:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
