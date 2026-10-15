# -*- coding: utf-8 -*-
"""
tests/test_zero_friction_self_healing.py
【智能体开箱即用与环境全自动自愈 (Zero-Friction Self-Healing) 专项测试套件】
覆盖场景：
1. PreflightItem 自动自愈契约、单步超时保护与防死循环重试机制；
2. AutoHealer 三态就绪生命周期 (INSTALLING_DEPENDENCIES / READY / ACTION_REQUIRED)；
3. 模拟 Whisper 本地模型缺失与专属 DropBox 目录缺失的全自动拉取与状态自愈；
4. 未登录/凭据缺失时的优雅引导卡片与扫码完成后的自动状态流转；
5. StandardAgent 的 0-Token [EXEC] check 与 [EXEC] heal 快速自愈卡片；
6. 微内核 HTTP API: /api/agent/<name>/readiness 与 /api/agent/<name>/heal 联调。
"""

import os
import sys
import time
import json
import shutil
import threading
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Optional

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from core.contract import BaseAgent, TaskContext, TaskResult
from core.config import ConfigManager
from core.registry import Registry
from core.preflight import PreflightItem, PreflightChecker, AutoHealer, ReadinessState
from core.standard_agent import StandardAgent
from apps.server.api_server import start_server


def test_preflight_item_contract_and_healing():
    """验证 PreflightItem 契约、静默自愈执行与百分比进度回调"""
    progress_records = []

    def _mock_heal(cb):
        if cb:
            cb(30.0, "正在准备物料...")
            cb(80.0, "正在解压资产...")
        return True

    item = PreflightItem(
        name="测试环境组件",
        status="pending_heal",
        message="组件待修复",
        auto_healable=True,
        heal_func=_mock_heal
    )

    assert item.status == "pending_heal"
    assert item.auto_healable is True

    def _progress_cb(pct, msg):
        progress_records.append((pct, msg))

    success = item.heal(progress_callback=_progress_cb)
    assert success is True
    assert item.status == "ok"
    assert "成功自动修复" in item.message
    assert len(progress_records) >= 2
    assert progress_records[-1][0] == 100.0

    d = item.to_dict()
    assert d["name"] == "测试环境组件"
    assert d["status"] == "ok"


def test_preflight_item_timeout_and_max_retries():
    """验证杜绝死循环：单步超时自动安全回退，且达到最大重试次数后输出人话提示"""
    call_count = 0

    def _failing_heal(cb):
        nonlocal call_count
        call_count += 1
        time.sleep(0.15)
        raise ConnectionError("模拟远端镜像网络波动超时")

    item = PreflightItem(
        name="离线语音模型拉取",
        status="pending_heal",
        message="模型缺失",
        auto_healable=True,
        heal_func=_failing_heal,
        timeout=1,  # 1 秒超时
        max_retries=2
    )

    ok = item.heal()
    assert ok is False
    assert item.status == "failed"
    assert item.current_retry == 2
    assert "自动修复失败" in item.message
    assert "网络波动" in str(item.last_error)


class MockHealingAgent(StandardAgent):
    """测试用具备自愈声明的标准智能体"""
    DROP_BOX_DIRS = ["drop_box/mock_agent_box", "drop_box/mock_agent_cache"]
    REQUIRED_PACKAGES = ["os", "sys"]  # 必定存在的包

    def __init__(self, name="mock_healing_agent"):
        super().__init__(name=name, description="自愈测试智能体")
        self.mock_model_ready = False
        self.mock_credentials_ready = False

    def get_preflight_items(self) -> List[PreflightItem]:
        cm = ConfigManager.get_instance()
        target_dirs = [cm.workspace_dir / d for d in self.DROP_BOX_DIRS]
        missing_dirs = [d for d in target_dirs if not d.exists()]

        items = [
            PreflightItem(
                name="工作区专属投递箱",
                status="ok" if not missing_dirs else "pending_heal",
                message="投递箱已就绪" if not missing_dirs else "投放箱目录待创建",
                auto_healable=True,
                heal_func=lambda cb: AutoHealer.ensure_directories(target_dirs)
            ),
            PreflightItem(
                name="Whisper 离线语音模型",
                status="ok" if self.mock_model_ready else "pending_heal",
                message="本地模型完备" if self.mock_model_ready else "缺失离线模型文件",
                auto_healable=True,
                heal_func=self._heal_mock_model
            ),
            PreflightItem(
                name="第三方平台授权会话凭据",
                status="ok" if self.mock_credentials_ready else "action_required",
                message="已绑定授权" if self.mock_credentials_ready else "未绑定授权，需扫码登录",
                auto_healable=False,
                action_required=not self.mock_credentials_ready,
                action_type="qrcode",
                action_guide={
                    "type": "mock_login",
                    "title": "请使用移动端扫码登录",
                    "cmd": "[EXEC] login",
                    "message": "点击按钮弹出登录二维码"
                }
            )
        ]
        return items

    def _heal_mock_model(self, cb=None):
        if cb:
            cb(50.0, "正在拉取 mock 离线模型...")
        cm = ConfigManager.get_instance()
        m_dir = cm.root_dir / "runtime" / "models" / "whisper-base"
        m_dir.mkdir(parents=True, exist_ok=True)
        (m_dir / "model.bin").write_bytes(b"MOCK_MODEL_DATA")
        self.mock_model_ready = True
        return True

    def run(self, context: TaskContext) -> TaskResult:
        return TaskResult(success=True, message="mock run ok")


def test_auto_healer_three_state_lifecycle_and_whisper_heal(tmp_path):
    """测试完整三态生命周期：INSTALLING_DEPENDENCIES -> ACTION_REQUIRED -> READY"""
    agent = MockHealingAgent()

    # 1. 初始状态：目录与模型均缺失，且无凭据 -> 优先呈现 ACTION_REQUIRED 或 INSTALLING_DEPENDENCIES
    agent.mock_model_ready = False
    agent.mock_credentials_ready = False

    status_1 = AutoHealer.check_agent_readiness(agent)
    assert status_1["state"] == ReadinessState.ACTION_REQUIRED
    assert status_1["progress"] < 100.0
    assert status_1["action_guide"]["type"] == "mock_login"

    # 2. 模拟假设凭据无需操作时，检测到模型和目录缺失 -> 纯净呈现 INSTALLING_DEPENDENCIES
    agent.mock_credentials_ready = True
    status_2 = AutoHealer.check_agent_readiness(agent)
    assert status_2["state"] == ReadinessState.INSTALLING_DEPENDENCIES
    assert "正在为您准备专属数字员工" in status_2["message"]

    # 3. 触发全自动静默自愈 (AutoHeal)
    progress_stream = []

    def _on_progress(pct, msg):
        progress_stream.append((pct, msg))

    heal_res = AutoHealer.heal_agent(agent, progress_callback=_on_progress)
    assert heal_res["state"] == ReadinessState.READY
    assert heal_res["progress"] == 100.0
    assert "100% 完备" in heal_res["message"]
    assert len(progress_stream) > 0

    # 验证目录被静默自动创建
    cm = ConfigManager.get_instance()
    for d in agent.DROP_BOX_DIRS:
        assert (cm.workspace_dir / d).exists()

    # 验证模型文件被静默写入
    m_file = cm.root_dir / "runtime" / "models" / "whisper-base" / "model.bin"
    assert m_file.exists()


def test_auto_healer_whisper_local_first_and_mirror_fallback(tmp_path):
    """测试 Whisper 模型 Local-First 0 秒就绪与国内镜像兜底自愈"""
    # 1. 验证 Local-First：如果本地已有权重，0 秒完成判定
    is_ready = AutoHealer.is_whisper_model_ready("base")
    assert is_ready is True

    t0 = time.time()
    ok = AutoHealer.ensure_whisper_model("base")
    duration = time.time() - t0
    assert ok is True
    assert duration < 0.2  # 0 秒级判定，绝无网络阻塞

    # 2. 模拟新模型 (如 whisper-tiny-test) 缺失时的镜像与安全骨架自愈
    cm = ConfigManager.get_instance()
    test_model_dir = cm.root_dir / "runtime" / "models" / "whisper-tiny-test"
    if test_model_dir.exists():
        shutil.rmtree(test_model_dir)

    assert AutoHealer.is_whisper_model_ready("tiny-test") is False

    cb_calls = []
    def _cb(pct, msg):
        cb_calls.append((pct, msg))

    heal_ok = AutoHealer.ensure_whisper_model("tiny-test", progress_callback=_cb)
    assert heal_ok is True
    assert AutoHealer.is_whisper_model_ready("tiny-test") is True
    assert (test_model_dir / "model.bin").exists()
    assert (test_model_dir / "config.json").exists()
    assert len(cb_calls) > 0
    assert cb_calls[-1][0] == 100.0

    # 清理临时测试模型目录
    shutil.rmtree(test_model_dir)


def test_standard_agent_fast_path_check_and_heal():
    """验证标准智能体 0-Token 指令 [EXEC] check 与 [EXEC] heal"""
    agent = MockHealingAgent("fast_path_agent")
    agent.mock_model_ready = True
    agent.mock_credentials_ready = True

    # 确保目录存在
    cm = ConfigManager.get_instance()
    for d in agent.DROP_BOX_DIRS:
        (cm.workspace_dir / d).mkdir(parents=True, exist_ok=True)

    # 1. 测试 check
    check_reply = agent.handle_fast_path("check")
    assert check_reply is not None
    assert "运行就绪度全景巡检看板" in check_reply
    assert "在岗待命 (100%)" in check_reply

    # 2. 测试 heal
    heal_reply = agent.handle_fast_path("heal")
    assert heal_reply is not None
    assert "全自动环境自愈已 100% 完成" in heal_reply


class TestZeroFrictionHttpApi:
    """微内核 HTTP API 级接口联调：验证 /api/agent/<name>/readiness 与 /api/agent/<name>/heal"""

    @classmethod
    def setup_class(cls):
        cls.port = 18790
        cls.server = start_server(host="127.0.0.1", port=cls.port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()
            cls.server.server_close()

    def test_get_agents_includes_readiness(self):
        url = f"http://127.0.0.1:{self.port}/api/agents"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert "agents" in data
            assert len(data["agents"]) > 0
            for ag in data["agents"]:
                assert "readiness" in ag
                assert "state" in ag["readiness"]
                assert ag["readiness"]["state"] in (
                    ReadinessState.READY,
                    ReadinessState.INSTALLING_DEPENDENCIES,
                    ReadinessState.ACTION_REQUIRED
                )

    def test_get_agent_readiness_api(self):
        url = f"http://127.0.0.1:{self.port}/api/agent/omni_sentinel/readiness"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["agent_name"] == "omni_sentinel"
            assert "readiness" in data
            assert data["readiness"]["state"] == ReadinessState.READY

    def test_post_agent_heal_api(self):
        url = f"http://127.0.0.1:{self.port}/api/agent/omni_sentinel/heal"
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert "readiness" in data
            assert data["readiness"]["progress"] >= 0.0
