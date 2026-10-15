# -*- coding: utf-8 -*-
"""
tests/test_agent_tool_calling.py
【对话内具身执行闭环 (Agent Tool-Calling in Chat) 单元与集成自动化测试套件】
覆盖验证：
1. 具身能力工具库系统提示词自动生成与规范注入；
2. 大模型工具调用代码块解析与容错处理；
3. 原子技能本地调度、产物识别与卡带元数据封装；
4. 离线/0-Token 技能意图智能提取 (主题与卖点列表提取)；
5. Web 产物托管安全路由 (/outputs/...) 及其防路径穿越安全边界；
6. 物理成果精准打开 API (POST /api/system/open-outputs)；
7. 对话接口 (同步与流式 SSE) 中具身执行全链路闭环测试。
"""

import os
import sys
import json
import time
import shutil
import urllib.request
import urllib.error
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.registry import Registry
from core.config import ConfigManager
from core.contract import BaseAgent
from core.tool_runner import ToolRunner
from apps.server.api_server import start_server


class TestToolRunnerCore:
    """ToolRunner 核心模块单元测试"""

    def setup_method(self):
        self.cm = ConfigManager.get_instance()
        self.reg = Registry.get_instance()
        self.reg.auto_discover()

    def test_build_tool_system_prompt(self):
        """测试根据智能体装备的技能列表生成具身工具协议提示词"""
        class DummyAgent(BaseAgent):
            def __init__(self):
                super().__init__("dummy_tester", "测试专用员工")
                self.skills_list = ["hello_skill"]

            def run(self, ctx):
                pass

        agent = DummyAgent()
        prompt = ToolRunner.build_tool_system_prompt(agent, "你是一名测试专员。")
        assert "你是一名测试专员。" in prompt
        assert "hello_skill" in prompt
        assert "示范问候与打卡" in prompt
        assert "```tool_call" in prompt
        assert "topic" in prompt

    def test_parse_tool_calls_markdown(self):
        """测试从 Markdown 代码块中稳健解析工具调用参数"""
        text = (
            "好的，我为您生成元数据！\n\n"
            "```tool_call\n"
            "{\n"
            '  "tool": "hello_skill",\n'
            '  "params": {\n'
            '    "name": "Python自动化运维实战"\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "请稍候片刻！"
        )
        calls = ToolRunner.parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["tool"] == "hello_skill"
        assert calls[0]["params"]["name"] == "Python自动化运维实战"

    def test_parse_tool_calls_trailing_comma_resilience(self):
        """测试 JSON 含有尾随逗号时的容错解析"""
        text = (
            "```tool_call\n"
            "{\n"
            '  "tool": "hello_skill",\n'
            '  "params": {\n'
            '    "name": "容错测试",\n'
            "  },\n"
            "}\n"
            "```"
        )
        calls = ToolRunner.parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["tool"] == "hello_skill"
        assert calls[0]["params"]["name"] == "容错测试"

    def test_execute_tool_and_artifact_packaging(self):
        """测试执行原子技能并打包结构化产物元数据"""
        artifact = ToolRunner.execute_tool("hello_skill", {
            "name": "具身执行核心测试"
        })
        assert artifact["success"] is True
        assert artifact["tool"] == "hello_skill"
        assert artifact["preview_url"].startswith("/outputs/")
        assert os.path.exists(artifact["file_path"])
        assert artifact["file_name"].endswith(".json")

        # 验证 Markdown 序列化格式
        card_md = ToolRunner.format_artifact_card_markdown(artifact)
        assert ":::skill-artifact" in card_md
        assert artifact["preview_url"] in card_md

    def test_detect_offline_skill_intent(self):
        """测试离线意图感知：从自然语言中提取元数据主题"""
        class MockWorker(BaseAgent):
            def __init__(self):
                super().__init__("meta_worker", "元数据员工")
                self.skills_list = ["hello_skill"]

            def run(self, ctx):
                pass

        worker = MockWorker()
        user_msg = "帮我向《从零手写智能体系统》打个招呼"
        intent = ToolRunner.detect_offline_skill_intent(user_msg, worker)
        assert intent is not None
        tool_id, params = intent
        assert tool_id == "hello_skill"
        assert params["name"] == "从零手写智能体系统"

    def test_execute_tool_agent_scope_isolation(self):
        """R2-VULN-04: 测试 ToolRunner.execute_tool 严格校验 Agent 装备作用域白名单"""
        class RestrictedAgent(BaseAgent):
            def __init__(self):
                super().__init__("restricted_agent", "受限智能体")
                self.skills_list = ["hello_skill"]  # 仅装备 bili_meta_generator

            def run(self, ctx):
                pass

        agent = RestrictedAgent()

        # 尝试调用其未装备的技能 bili_cover_generator -> 必须被拦截并返回安全错误
        artifact = ToolRunner.execute_tool("bili_cover_generator", {"topic": "越权探测"}, agent=agent)
        assert artifact["success"] is False
        assert "安全拦截" in artifact["error"]
        assert "未装备技能卡带" in artifact["error"]

        # 调用其已装备的技能 -> 正常执行
        allowed_res = ToolRunner.execute_tool("hello_skill", {"name": "合法调用"}, agent=agent)
        assert allowed_res["success"] is True


class TestToolCallingHttpApi:
    """HTTP 路由与对话具身执行集成测试"""

    TEST_HOST = "127.0.0.1"
    TEST_PORT = 18796

    @classmethod
    def setup_class(cls):
        import threading
        cls.cm = ConfigManager.get_instance()
        cls.orig_license = cls.cm.gateway.license_key
        cls.cm.gateway.license_key = "TEST-UNIT-TOOL-CALLING"

        cls.server = start_server(host=cls.TEST_HOST, port=cls.TEST_PORT)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.4)

        reg = Registry.get_instance()
        agent = reg.get_agent("omni_sentinel")
        if agent:
            agent.skills_list = ["hello_skill"]

    @classmethod
    def teardown_class(cls):
        reg = Registry.get_instance()
        agent = reg.get_agent("omni_sentinel")
        if agent:
            agent.skills_list = []
        if hasattr(cls, "orig_license"):
            cls.cm.gateway.license_key = cls.orig_license
        try:
            if hasattr(cls, "server"):
                cls.server.shutdown()
        except Exception:
            pass

    def _post(self, path: str, data: dict):
        url = f"http://{self.TEST_HOST}:{self.TEST_PORT}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _get(self, path: str):
        url = f"http://{self.TEST_HOST}:{self.TEST_PORT}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                content_type = resp.headers.get("Content-Type", "")
                data = resp.read()
                return resp.status, content_type, data
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), e.read()

    def test_outputs_static_file_serving(self):
        """测试 /outputs/... 静态产物资源托管及防跨目录穿越安全"""
        # 1. 确保 outputs 目录下生成测试图片
        cm = ConfigManager.get_instance()
        test_dir = cm.workspace_dir / "outputs" / "posters"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "test_api_sample.png"
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest")

        try:
            # 2. 正常获取文件
            status, c_type, data = self._get("/outputs/posters/test_api_sample.png")
            assert status == 200
            assert "image/png" in c_type
            assert len(data) > 0

            # 3. 安全防护：跨目录穿越应返回 404
            status, _, _ = self._get("/outputs/../../configs/framework.yaml")
            assert status == 404

            # 4. 不存在的文件应返回 404
            status, _, _ = self._get("/outputs/non_existent_file_123.png")
            assert status == 404
        finally:
            if test_file.exists():
                test_file.unlink(missing_ok=True)

    def test_open_outputs_targeted_file_and_dir(self):
        """测试精准唤起本地成果与文件目录 API"""
        cm = ConfigManager.get_instance()
        test_dir = cm.workspace_dir / "outputs" / "posters"
        test_dir.mkdir(parents=True, exist_ok=True)
        sample = test_dir / "probe_open.txt"
        sample.write_text("test probe content", encoding="utf-8")

        try:
            # 1. 路径合法性与目录高亮
            status, res = self._post("/api/system/open-outputs", {
                "path": str(sample.resolve()),
                "action": "open_dir"
            })
            assert status == 200
            assert res.get("success") is True
            assert res.get("mode") == "dir"

            # 2. 越界非法路径应被拒绝
            status, res = self._post("/api/system/open-outputs", {
                "path": "C:/Windows/System32/calc.exe",
                "action": "open_file"
            })
            assert status == 403
            assert res.get("success") is False
        finally:
            if sample.exists():
                sample.unlink(missing_ok=True)

    def test_api_server_dialogue_tool_calling_closed_loop(self):
        """测试端到端自然语言对话自动触发技能执行并交付产物卡片"""
        # 对已装备 bili_meta_generator 的 omni_sentinel 发起元数据生成对话
        status, res = self._post("/api/chat", {
            "agent_name": "omni_sentinel",
            "messages": [
                {
                    "role": "user",
                    "content": "帮我向《立体空间智能体操作系统实战》打个招呼"
                }
            ]
        })
        assert status == 200
        assert res.get("success") is True
        reply = res.get("reply", "")
        # 确认回复中包含了结构化交付物标记 :::skill-artifact
        assert ":::skill-artifact" in reply
        assert "hello_skill" in reply
        assert "/outputs/" in reply
        assert ".json" in reply

    def test_api_server_stream_tool_calling_closed_loop(self):
        """测试 SSE 流式输出中的技能执行与产物卡片增量推送"""
        url = f"http://{self.TEST_HOST}:{self.TEST_PORT}/api/chat/stream"
        payload = json.dumps({
            "agent_name": "omni_sentinel",
            "messages": [
                {
                    "role": "user",
                    "content": "向《一人公司智能体实操课》打个招呼"
                }
            ]
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        streamed_chunks = []
        with urllib.request.urlopen(req, timeout=5) as resp:
            while True:
                line_str = resp.readline().decode("utf-8").strip()
                if not line_str:
                    continue
                if line_str.startswith("data:"):
                    payload = line_str[5:].strip()
                    streamed_chunks.append(payload)
                    if payload == "[DONE]":
                        break

        full_stream_text = "".join(streamed_chunks)
        assert ":::skill-artifact" in full_stream_text
        assert "hello_skill" in full_stream_text
        assert "[DONE]" in streamed_chunks
