# -*- coding: utf-8 -*-
"""
tests/test_v23_features.py
【立体空间智能体系统 · v2.2.4 核心新特性自动化测试】
测试范围：
1. Ollama 检测探针与连通性测试接口
2. SSE 流式打字机分块输出 (stream_chat)
3. 产物输出目录管理与接口探针
"""

import sys
import json
import time
import urllib.request
import threading
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm import LLMClient
from core.registry import Registry
from core.config import ConfigManager
from apps.server.api_server import start_server


def test_llm_ollama_detection_graceful():
    """测试 Ollama 探针在本地未运行时能优雅返回 False 而不崩溃"""
    available, models = LLMClient.detect_ollama(host="http://127.0.0.1:59999", timeout=1)
    assert available is False
    assert isinstance(models, list)


def test_llm_connection_test():
    """测试连通性测试探针接口"""
    # 1. cloud 模式测试
    success, latency, msg = LLMClient.test_connection(mode="cloud")
    assert isinstance(success, bool)
    assert latency >= 0
    assert isinstance(msg, str)

    # 2. 无效端口测试（优雅失败）
    success2, latency2, msg2 = LLMClient.test_connection(mode="custom", base_url="http://127.0.0.1:59999/v1", timeout=1)
    assert success2 is False
    assert "连接失败" in msg2 or "HTTP" in msg2


def test_agent_stream_chat_fast_path():
    """测试智能体 stream_chat 针对 0-Token Fast-Path 的流式吐出"""
    reg = Registry.get_instance()
    reg.auto_discover()
    sentinel = reg.get_agent("omni_sentinel")
    assert sentinel is not None

    messages = [{"role": "user", "content": "[EXEC] ping"}]
    chunks = list(sentinel.stream_chat(messages))
    assert len(chunks) > 0
    full_text = "".join(chunks)
    assert "0-Token PONG" in full_text


class TestV23HttpApi:
    """HTTP 接口级集成测试"""

    @classmethod
    def setup_class(cls):
        cls.port = 18799
        cls.server = start_server(host="127.0.0.1", port=cls.port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()

    def test_open_outputs_api(self):
        url = f"http://127.0.0.1:{self.port}/api/system/open-outputs"
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert "outputs" in data["path"]
            assert "opened" in data

    def test_detect_ollama_api(self):
        url = f"http://127.0.0.1:{self.port}/api/llm/detect-ollama"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert "available" in data
            assert isinstance(data["models"], list)

    def test_chat_stream_api(self):
        url = f"http://127.0.0.1:{self.port}/api/chat/stream"
        payload = {
            "agent_name": "omni_sentinel",
            "messages": [{"role": "user", "content": "[EXEC] ping"}]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            lines = []
            while True:
                line = resp.readline().decode("utf-8").strip()
                if not line:
                    continue
                lines.append(line)
                if line == "data: [DONE]":
                    break
            assert any("0-Token PONG" in l for l in lines)
            assert lines[-1] == "data: [DONE]"

    def test_agent_config_http_api(self):
        # 1. 测试 GET /api/agent/:name/config
        get_url = f"http://127.0.0.1:{self.port}/api/agent/omni_sentinel/config"
        with urllib.request.urlopen(get_url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert "schema" in data
            assert "config" in data
            assert data["agent_name"] == "omni_sentinel"

        # 2. 测试 POST /api/agent/:name/config
        post_url = f"http://127.0.0.1:{self.port}/api/agent/omni_sentinel/config"
        payload = {
            "updates": {
                "patrol_interval": 1800,
                "report_format": "json"
            }
        }
        req = urllib.request.Request(
            post_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            post_data = json.loads(resp.read().decode("utf-8"))
            assert post_data["success"] is True
            assert post_data["config"]["patrol_interval"] == 1800
            assert post_data["config"]["report_format"] == "json"

    def test_watcher_events_http_api(self):
        # 1. 制造一条测试事件
        from core.watcher import WatcherEventQueue
        eq = WatcherEventQueue.get_instance()
        test_evt = eq.push("file_detected", {
            "file_name": "test_api_event.mp4",
            "message": "测试事件消息"
        })

        # 2. 测试 GET /api/watcher/events?auto_consume=0
        get_url = f"http://127.0.0.1:{self.port}/api/watcher/events?auto_consume=0"
        with urllib.request.urlopen(get_url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["count"] >= 1
            assert any(e["id"] == test_evt["id"] for e in data["events"])

        # 3. 测试 POST /api/watcher/events/consume
        post_url = f"http://127.0.0.1:{self.port}/api/watcher/events/consume"
        consume_body = {"event_ids": [test_evt["id"]]}
        req = urllib.request.Request(
            post_url,
            data=json.dumps(consume_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            c_data = json.loads(resp.read().decode("utf-8"))
            assert c_data["success"] is True
            assert test_evt["id"] in c_data["consumed_ids"]
