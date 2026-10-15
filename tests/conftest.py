# -*- coding: utf-8 -*-
"""
tests/conftest.py
Pytest 全局测试套件前置钩子：
1. 配置安全测试环境环境变量
2. 为本地测试客户端自动安装受信任会话 Token 拦截注入器 (除显式测试未认证场景外)
"""

import os
import urllib.request

os.environ["PYTEST_CURRENT_TEST"] = "1"


class PytestApiAuthHandler(urllib.request.BaseHandler):
    """
    自动为单测中通过 urllib 访问 127.0.0.1 的本地 API 请求附带合法 X-Agent-OS-Token。
    如果请求头中包含 'X-Test-No-Auth' 或明确携带 'Origin'（用于测试前端跨域未认证拦截），则不自动注入。
    """
    def http_request(self, req):
        host = req.host
        if host and ("127.0.0.1" in host or "localhost" in host):
            # 显式测试未认证场景
            if req.headers.get("X-test-no-auth") or req.headers.get("X-Test-No-Auth"):
                req.headers.pop("X-test-no-auth", None)
                req.headers.pop("X-Test-No-Auth", None)
                return req

            # 携带 Origin 时由测试用例自行掌控 Token 注入逻辑
            if "Origin" in req.headers:
                return req

            # 常规单测请求：若尚未提供 Token 头，则自动补充当前微内核服务 Token
            if "X-agent-os-token" not in req.headers and "Authorization" not in req.headers:
                try:
                    from apps.server.api_server import get_server_token
                    tok = get_server_token()
                    if tok:
                        req.add_unredirected_header("X-Agent-OS-Token", tok)
                except Exception:
                    pass
        return req


opener = urllib.request.build_opener(PytestApiAuthHandler)
urllib.request.install_opener(opener)
