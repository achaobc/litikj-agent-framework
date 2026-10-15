# -*- coding: utf-8 -*-
"""
tests/test_agent_recruit_and_runner.py
【立体空间智能体系统 · 岗位招聘工坊与技能独立运行器自动化测试】
测试范围：
1. 技能独立运行控制台接口 (/api/skills/run)
2. 数字化员工一键招聘工坊接口 (/api/agents/create)
3. 员工解雇与工作区安全清理接口 (/api/agents/delete)
4. 内核级内置原生员工安全保护机制
"""

import sys
import json
import time
import shutil
import threading
import urllib.request
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.registry import Registry
from core.config import ConfigManager
from apps.server.api_server import start_server


class TestRecruitAndRunnerHttpApi:
    """HTTP 接口级集成测试"""

    @classmethod
    def setup_class(cls):
        cls.port = 18797
        cls.server = start_server(host="127.0.0.1", port=cls.port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.4)

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()

    def _get(self, path: str):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "TestClient"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, data: dict):
        url = f"http://127.0.0.1:{self.port}{path}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "TestClient"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_skill_direct_run_api(self):
        """测试 /api/skills/run 独立运行技能并产出结果"""
        status, res = self._post("/api/skills/run", {
            "skill_id": "hello_skill",
            "params": {
                "name": "开发者",
                "topic": "自动化测试实战"
            }
        })
        assert status == 200
        assert res.get("success") is True
        assert res.get("status") == "success"
        result_data = res.get("result", {})
        assert result_data.get("success") is True
        assert "file_path" in result_data

    def test_skill_run_not_found(self):
        """测试运行不存在的技能时返回 404"""
        status, res = self._post("/api/skills/run", {
            "skill_id": "non_existent_skill_xyz",
            "params": {}
        })
        assert status == 404
        assert res.get("success") is False

    def test_agent_recruit_and_fire_lifecycle(self):
        """测试新员工招聘、技能挂载、热重载入职与解雇离职完整生命周期"""
        test_agent_id = "test_unit_writer"
        cm = ConfigManager.get_instance()
        target_dir = cm.workspace_dir / "custom_agents" / test_agent_id

        try:
            # 1. 招聘入职新员工
            status, res = self._post("/api/agents/create", {
                "id": test_agent_id,
                "name": "测试文案特攻专员",
                "icon": "📕",
                "category": "自媒体内容",
                "description": "自动化测试招聘的新员工",
                "system_prompt": "你是一名测试文案专员...",
                "temperature": 0.6,
                "skills": ["hello_skill"],
                "quick_chips": ["✨ 测试快捷指令"]
            })
            assert status == 200
            assert res.get("success") is True
            assert target_dir.exists()
            assert (target_dir / "config.yaml").exists()
            assert (target_dir / "entry.py").exists()

            # 2. 检查注册表和 GET /api/agents
            reg = Registry.get_instance()
            ag = reg.get_agent(test_agent_id)
            assert ag is not None
            assert "hello_skill" in getattr(ag, "skills_list", [])

            g_status, g_data = self._get("/api/agents")
            assert g_status == 200
            agent_names = [a["name"] for a in g_data.get("agents", [])]
            assert test_agent_id in agent_names
            custom_agents = [a for a in g_data.get("agents", []) if a["name"] == test_agent_id]
            assert len(custom_agents) == 1
            assert custom_agents[0].get("is_custom") is True

            # 3. 测试安全保护：解雇系统内置原生员工时应被拒绝
            p_status, p_res = self._post("/api/agents/delete", {"agent_id": "omni_sentinel"})
            assert p_status == 400
            assert p_res.get("success") is False
            assert "保护" in p_res.get("error", "")

            # 4. 正式解雇自定义新员工
            f_status, f_res = self._post("/api/agents/delete", {"agent_id": test_agent_id})
            assert f_status == 200
            assert f_res.get("success") is True
            assert not target_dir.exists()
            assert reg.get_agent(test_agent_id) is None

        finally:
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
