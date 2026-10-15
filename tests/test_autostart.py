# -*- coding: utf-8 -*-
"""
tests/test_autostart.py
开机自启动后端接口与底层管理单元测试
"""

import os
import json
import time
import threading
import sys
from pathlib import Path
from urllib.request import Request, urlopen
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.setup_autostart import is_enabled, enable, disable, LAUNCHER_VBS
from apps.server.api_server import start_server


def test_autostart_engine_toggle():
    """测试底层 VBScript 脚本创建与移除"""
    # 确保起始状态干净
    disable()
    assert is_enabled() is False

    # 启用
    assert enable() is True
    assert is_enabled() is True
    assert LAUNCHER_VBS.exists()

    # 禁用
    assert disable() is True
    assert is_enabled() is False
    assert not LAUNCHER_VBS.exists()


class TestAutostartHttpApi:
    @classmethod
    def setup_class(cls):
        cls.port = 8799
        cls.server = start_server(host="127.0.0.1", port=cls.port)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def teardown_class(cls):
        disable()  # 确保清理测试项
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

    def test_get_autostart_api(self):
        disable()
        res = self._api_get("/api/autostart")
        assert "enabled" in res
        assert res["enabled"] is False

    def test_post_autostart_api_enable_and_disable(self):
        # 1. POST 开启
        enable_res = self._api_post("/api/autostart", {"enabled": True})
        assert enable_res["success"] is True
        assert enable_res["enabled"] is True
        assert is_enabled() is True

        # 检查 /api/system 是否包含 autostart 字段
        sys_res = self._api_get("/api/system")
        assert "autostart" in sys_res
        assert sys_res["autostart"] is True

        # 2. POST 关闭
        disable_res = self._api_post("/api/autostart", {"enabled": False})
        assert disable_res["success"] is True
        assert disable_res["enabled"] is False
        assert is_enabled() is False
