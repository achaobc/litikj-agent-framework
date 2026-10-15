# -*- coding: utf-8 -*-
"""
tests/test_scheduler.py
【立体空间智能体系统 · 计划任务调度中枢微内核与 API 自动化测试】
覆盖范围：
1. 纯标准库 5 字段 Cron 语法匹配引擎 (is_cron_match)
2. SchedulerEngine 核心增删改查、状态持久化与状态切换
3. 智能体快速通道执行 (execute_task_now / 0-Token Fast-path)
4. 自然语言语义调度解析器 (parse_natural_language_schedule)
5. Chatbox API 端点集成测试 (/api/schedules, /api/schedules/toggle, /api/schedules/run_now, /api/schedules/delete, /api/chat 定时意图)
"""

import sys
import json
import time
import pytest
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scheduler import is_cron_match, _match_cron_field, SchedulerEngine
from core.registry import Registry


class TestCronMatcher:
    """测试无依赖 Cron 语法匹配引擎"""

    def test_wildcard_and_exact(self):
        dt = datetime(2026, 10, 6, 9, 30)  # 2026-10-06 周二 (Python weekday=1 -> Cron dow=2)
        assert is_cron_match(dt, "30 9 * * *") is True
        assert is_cron_match(dt, "31 9 * * *") is False
        assert is_cron_match(dt, "30 10 * * *") is False
        assert is_cron_match(dt, "* * * * *") is True

    def test_step_syntax(self):
        dt1 = datetime(2026, 10, 6, 9, 30)
        dt2 = datetime(2026, 10, 6, 9, 33)
        assert is_cron_match(dt1, "*/15 * * * *") is True
        assert is_cron_match(dt2, "*/15 * * * *") is False
        assert is_cron_match(dt2, "*/3 * * * *") is True

    def test_range_and_comma(self):
        dt = datetime(2026, 10, 6, 9, 30)
        assert is_cron_match(dt, "30 8-10 * * *") is True
        assert is_cron_match(dt, "30 11-12 * * *") is False
        assert is_cron_match(dt, "15,30,45 9 * * *") is True
        assert is_cron_match(dt, "0,15,45 9 * * *") is False

    def test_invalid_cron_graceful(self):
        dt = datetime(2026, 10, 6, 9, 30)
        assert is_cron_match(dt, "invalid cron") is False
        assert is_cron_match(dt, "* * *") is False


class TestSchedulerEngine:
    """测试调度引擎任务增删改查与执行"""

    @pytest.fixture(autouse=True)
    def setup_engine(self):
        Registry.get_instance().auto_discover()
        self.engine = SchedulerEngine.get_instance()
        yield

    def test_singleton_and_list_tasks(self):
        assert self.engine is SchedulerEngine.get_instance()
        tasks = self.engine.list_tasks()
        assert isinstance(tasks, list)
        assert len(tasks) >= 1

    def test_add_toggle_and_delete_task(self):
        task_id = f"test_sched_{int(time.time() * 1000)}"
        new_task = {
            "id": task_id,
            "name": "自动化测试定时任务",
            "agent_name": "omni_sentinel",
            "schedule_type": "interval",
            "time_value": "15",
            "command": "[EXEC] ping",
            "description": "自动化测试用例"
        }
        added = self.engine.add_or_update_task(new_task)
        assert added["id"] == task_id
        assert added["enabled"] is True

        # 查询
        found = self.engine.get_task(task_id)
        assert found is not None
        assert found["name"] == "自动化测试定时任务"

        # 切换开关
        toggled = self.engine.toggle_task(task_id, enabled=False)
        assert toggled is False
        assert self.engine.get_task(task_id)["enabled"] is False

        # 手动试跑执行
        run_res = self.engine.execute_task_now(task_id)
        assert run_res["success"] is True
        assert "pong" in run_res.get("output", "").lower() or "omni_sentinel" in run_res.get("output", "").lower()

        # 删除
        deleted = self.engine.delete_task(task_id)
        assert deleted is True
        assert self.engine.get_task(task_id) is None

    def test_next_run_hints(self):
        now = datetime.now()
        task_daily = {"enabled": True, "schedule_type": "daily", "time_value": "23:59"}
        hint_daily = self.engine._compute_next_run_hint(task_daily, now)
        assert "今天" in hint_daily or "明天" in hint_daily

        task_disabled = {"enabled": False, "schedule_type": "daily", "time_value": "12:00"}
        assert self.engine._compute_next_run_hint(task_disabled, now) == "已暂停"

        task_interval = {"enabled": True, "schedule_type": "interval", "time_value": "30", "last_run": None}
        assert "30 分钟" in self.engine._compute_next_run_hint(task_interval, now)


class TestNaturalLanguageScheduler:
    """测试自然语言定时意图识别解析"""

    def test_daily_morning(self):
        query = "每天早上9点巡检"
        res = SchedulerEngine.parse_natural_language_schedule(query, "omni_sentinel")
        assert res is not None
        assert res["matched"] is True
        assert res["schedule_type"] == "daily"
        assert res["time_value"] == "09:00"
        assert res["command"] == "[EXEC] report"

    def test_daily_afternoon(self):
        query = "每天下午3点执行状态诊断"
        res = SchedulerEngine.parse_natural_language_schedule(query, "omni_sentinel")
        assert res is not None
        assert res["schedule_type"] == "daily"
        assert res["time_value"] == "15:00"
        assert res["command"] == "[EXEC] report"

    def test_interval_hours(self):
        query = "每隔2小时自动巡检"
        res = SchedulerEngine.parse_natural_language_schedule(query, "omni_sentinel")
        assert res is not None
        assert res["schedule_type"] == "interval"
        assert res["time_value"] == "120"  # 2 * 60

    def test_once_delay(self):
        query = "30分钟后提醒我巡检"
        res = SchedulerEngine.parse_natural_language_schedule(query, "omni_sentinel")
        assert res is not None
        assert res["schedule_type"] == "once"
        assert res["time_value"] == "30"

    def test_unrelated_chat(self):
        query = "你好，请介绍一下你自己"
        res = SchedulerEngine.parse_natural_language_schedule(query, "omni_sentinel")
        assert res is None


class TestChatboxSchedulerIntegration:
    """测试通过 Chatbox HTTP 服务的计划任务完整 API 链路"""

    @classmethod
    def setup_class(cls):
        import socket
        from apps.server.api_server import start_server

        cls.port = 8798
        cls.server = start_server(host="127.0.0.1", port=cls.port)
        import threading
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)  # 等待启动

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()

    def _api_get(self, path: str):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _api_post(self, path: str, payload: dict):
        url = f"http://127.0.0.1:{self.port}{path}"
        data_bytes = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_get_schedules_api(self):
        res = self._api_get("/api/schedules")
        assert res["success"] is True
        assert "tasks" in res
        assert isinstance(res["tasks"], list)

    def test_post_schedule_crud_api(self):
        task_id = f"api_test_{int(time.time() * 1000)}"
        # 1. 创建
        create_res = self._api_post("/api/schedules", {
            "id": task_id,
            "name": "API 创建的测试任务",
            "agent_name": "omni_sentinel",
            "schedule_type": "daily",
            "time_value": "10:30",
            "command": "[EXEC] ping"
        })
        assert create_res["success"] is True
        assert create_res["task"]["id"] == task_id

        # 2. 停用
        toggle_res = self._api_post("/api/schedules/toggle", {"id": task_id, "enabled": False})
        assert toggle_res["success"] is True
        assert toggle_res["enabled"] is False

        # 3. 立即试跑
        run_res = self._api_post("/api/schedules/run_now", {"id": task_id})
        assert run_res["success"] is True

        # 4. 删除
        del_res = self._api_post("/api/schedules/delete", {"id": task_id})
        assert del_res["success"] is True

    def test_post_chat_natural_language_schedule(self):
        # 模拟用户在对话框直接说“每天9点自动巡检”
        chat_res = self._api_post("/api/chat", {
            "agent_name": "omni_sentinel",
            "messages": [{"role": "user", "content": "每天早上9点巡检"}]
        })
        assert chat_res["success"] is True
        assert "schedule_created" in chat_res
        assert "09:00" in chat_res["reply"]
        created_id = chat_res["schedule_created"]["id"]

        # 清理测试生成的任务
        SchedulerEngine.get_instance().delete_task(created_id)
