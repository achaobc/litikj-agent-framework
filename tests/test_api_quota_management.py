# -*- coding: utf-8 -*-
"""
tests/test_api_quota_management.py
【立体空间智能体系统 · 商业级算力配额与防刷计量中枢自动化测试】
测试范围：
1. 客户端单次输入长度限制与大文本上下文智能保护 (Max Input Protection)
2. 客户端请求频控与防抖硬拦截 (Rate Limiter / Debounce)
3. 云端配额协议模型 (X-Litikj-Quota-Remaining 等) 解析与本地缓存持久化
4. 429 / 402 熔断与配额耗尽异常 (QuotaExhaustedError) 拦截
5. 加油包充值核算与自备 Key / 本地私有模式免额度分流
6. HTTP API 接口 (/api/system, /api/quota, /api/quota/recharge) 闭环验证
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

from core.quota import (
    QuotaManager,
    QuotaStatus,
    QuotaExhaustedError,
    RateLimitError,
    DailyLimitExceededError,
    LLMError
)
from core.llm import LLMClient
from core.config import ConfigManager
from apps.server.api_server import start_server


@pytest.fixture(autouse=True)
def reset_quota_state():
    """每个测试前后保证配额处于标准健康状态"""
    qm = QuotaManager.get_instance(force_reload=True)
    qm.reset_quota(total=1_000_000, remaining=1_000_000)
    yield
    qm.reset_quota(total=1_000_000, remaining=1_000_000)


def test_quota_manager_defaults_and_status():
    """验证配额管理器默认指标与数据模型"""
    qm = QuotaManager.get_instance()
    status = qm.get_status()

    assert status.total == 1_000_000
    assert status.remaining == 1_000_000
    assert status.percent == 100.0
    assert status.health_status == "healthy"
    assert status.used == 0

    d = status.to_dict()
    assert d["total"] == 1_000_000
    assert d["remaining"] == 1_000_000
    assert d["status"] == "healthy"


def test_truncate_messages_normal():
    """验证正常长度文本无需裁剪"""
    qm = QuotaManager.get_instance()
    msgs = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你好，请帮我分析这份简短的报表。"}
    ]
    res, truncated, total_chars = qm.truncate_messages(msgs, max_chars=20000)
    assert truncated is False
    assert len(res) == 2
    assert total_chars == len(msgs[0]["content"]) + len(msgs[1]["content"])


def test_truncate_messages_large_protection():
    """验证学员意外丢入超大巨型文本时，自动触发单次上下文安全裁剪防刷爆"""
    qm = QuotaManager.get_instance()
    sys_prompt = "你是立体空间专业数据架构师。"
    huge_text = "这是一段非常冗长的财务流水记录。" * 2000  # 约 36,000 字符

    msgs = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": "前置背景数据"},
        {"role": "assistant", "content": "收到前置背景"},
        {"role": "user", "content": huge_text}
    ]

    max_chars = 5000
    res, truncated, new_total = qm.truncate_messages(msgs, max_chars=max_chars)

    assert truncated is True
    assert new_total <= max_chars
    assert res[0]["role"] == "system"
    assert res[0]["content"] == sys_prompt
    # 验证末尾保留了带有裁剪提示的安全上下文
    last_msg = res[-1]
    assert "安全精简上下文" in last_msg["content"] or "安全截断" in last_msg["content"]


def test_client_rate_limiter():
    """验证客户端本地防抖频控拦截"""
    qm = QuotaManager.get_instance()
    qm._last_request_ts = 0.0

    # 首次放行
    qm.check_rate_limit(min_interval=0.15)

    # 紧接着立即发起的第二次请求应触发频控拦截
    with pytest.raises(RateLimitError) as exc_info:
        qm.check_rate_limit(min_interval=0.15)
    assert "操作防抖拦截" in str(exc_info.value)

    # 等待冷却时间后应能再次正常放行
    time.sleep(0.2)
    qm.check_rate_limit(min_interval=0.15)


def test_quota_update_from_headers():
    """验证从云端网关响应头解析配额状态并持久化"""
    qm = QuotaManager.get_instance()
    mock_headers = {
        "X-Litikj-Quota-Total": "2000000",
        "X-Litikj-Quota-Remaining": "1500000",
        "X-Litikj-Daily-Limit": "200000",
        "X-Litikj-Daily-Used": "50000",
        "X-Litikj-RPM-Limit": "60",
        "X-Litikj-Tier": "Pro"
    }

    status = qm.update_from_headers(mock_headers)
    assert status.total == 2_000_000
    assert status.remaining == 1_500_000
    assert status.percent == 75.0
    assert status.daily_used == 50_000
    assert status.rpm_limit == 60
    assert status.tier == "Pro"
    assert status.health_status == "healthy"

    # 验证预警状态 (剩余 < 20%)
    warning_headers = {
        "X-Litikj-Quota-Total": "1000000",
        "X-Litikj-Quota-Remaining": "150000"
    }
    status = qm.update_from_headers(warning_headers)
    assert status.percent == 15.0
    assert status.health_status == "warning"

    # 验证耗尽状态 (剩余 <= 0)
    exhausted_headers = {
        "X-Litikj-Quota-Remaining": "0"
    }
    status = qm.update_from_headers(exhausted_headers)
    assert status.remaining == 0
    assert status.health_status == "exhausted"


def test_quota_recharge_and_consumption():
    """验证算力加油包注入与本地额度预扣记账"""
    qm = QuotaManager.get_instance()
    qm.reset_quota(total=1_000_000, remaining=500_000)

    # 1. 消耗 10,000 字符估算消耗
    used = qm.consume_local_estimate(prompt_chars=10000, completion_chars=2000)
    assert used == 6000
    assert qm.get_status().remaining == 494_000
    assert qm.get_status().daily_used == 6000

    # 2. 增购 500,000 点算力加油包
    status = qm.recharge_quota(500_000)
    assert status.total == 1_500_000
    assert status.remaining == 994_000


def test_llm_client_quota_exhausted_interception():
    """验证官方云端模式下，当配额耗尽时立即熔断拦截，不向云端无效发包"""
    qm = QuotaManager.get_instance()
    qm.get_status().remaining = 0

    cfg = ConfigManager.get_instance().gateway
    orig_mode = cfg.mode
    cfg.mode = "cloud"

    try:
        with pytest.raises(QuotaExhaustedError) as exc_info:
            LLMClient.chat([{"role": "user", "content": "你好"}])
        assert "官方算力额度已耗尽" in str(exc_info.value)
    finally:
        cfg.mode = orig_mode
        qm.reset_quota(total=1_000_000, remaining=1_000_000)


def test_api_server_system_quota_and_recharge():
    """启动本地 API Server 在专属测试端口 18795，验证 HTTP API 对配额指标与充值的支持"""
    port = 18795
    server = start_server(host="127.0.0.1", port=port)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.4)

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. 测试 GET /api/system 包含完整的配额看板信息
        req = urllib.request.Request(f"{base_url}/api/system")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "quota" in data
            q = data["quota"]
            assert "total" in q
            assert "remaining" in q
            assert "percent" in q
            assert "status" in q
            assert "daily_used" in q

        # 2. 测试 GET /api/quota 独立探针
        req_quota = urllib.request.Request(f"{base_url}/api/quota")
        with urllib.request.urlopen(req_quota, timeout=3) as resp:
            assert resp.status == 200
            q_data = json.loads(resp.read().decode("utf-8"))
            assert q_data["success"] is True
            assert q_data["quota"]["total"] >= 1_000_000

        # 3. 测试 POST /api/quota/recharge 增购加油包
        recharge_payload = json.dumps({"points": 200000}).encode("utf-8")
        req_recharge = urllib.request.Request(
            f"{base_url}/api/quota/recharge",
            data=recharge_payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_recharge, timeout=3) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["success"] is True
            assert res["recharged_points"] == 200_000
            assert res["quota"]["total"] >= 1_200_000

        # 4. 测试 POST /api/quota/refresh 刷新接口
        req_refresh = urllib.request.Request(
            f"{base_url}/api/quota/refresh",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_refresh, timeout=3) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["success"] is True
            assert "quota" in res
    finally:
        server.shutdown()


def test_parse_and_raise_gateway_error_daily_limit():
    """验证客户端精准识别 429 DAILY_LIMIT_EXCEEDED 单日硬顶并输出人性化提示"""
    import io
    qm = QuotaManager.get_instance()
    body = json.dumps({
        "error": {
            "code": "DAILY_LIMIT_EXCEEDED",
            "message": "今日 AI 算力限额已达上限 (100,000 Token/日)，将于明日 0:00 自动恢复。如需加急使用请联系助教/管理员提额。"
        }
    }).encode("utf-8")
    fp = io.BytesIO(body)
    http_err = urllib.error.HTTPError("http://test/chat", 429, "Daily Limit Exceeded", {}, fp)

    with pytest.raises(DailyLimitExceededError) as exc_info:
        LLMClient._parse_and_raise_gateway_error(http_err, qm)
    assert "单日防刷保护" in str(exc_info.value)
    assert "100,000 Token/日" in str(exc_info.value)


def test_parse_and_raise_gateway_error_quota_exhausted():
    """验证客户端精准识别 429/402 QUOTA_EXHAUSTED 总额耗尽并更新本地状态为 0"""
    import io
    qm = QuotaManager.get_instance()
    qm.reset_quota(total=1_000_000, remaining=500_000)

    body = json.dumps({
        "error": {
            "code": "QUOTA_EXHAUSTED",
            "message": "您的 AI 算力总配额已耗尽，请前往官网学员中心购买算力加油包增购额度！"
        }
    }).encode("utf-8")
    fp = io.BytesIO(body)
    http_err = urllib.error.HTTPError("http://test/chat", 429, "Quota Exhausted", {}, fp)

    with pytest.raises(QuotaExhaustedError) as exc_info:
        LLMClient._parse_and_raise_gateway_error(http_err, qm)
    assert "官方算力额度已耗尽" in str(exc_info.value)
    assert qm.get_status().remaining == 0


def test_parse_and_raise_gateway_error_rate_limit():
    """验证客户端识别 429 RATE_LIMIT_EXCEEDED 短时 RPM 限频"""
    import io
    qm = QuotaManager.get_instance()
    body = json.dumps({
        "error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "请求过于频繁（已达 30 次/分钟限流），请稍后重试。"
        }
    }).encode("utf-8")
    fp = io.BytesIO(body)
    http_err = urllib.error.HTTPError("http://test/chat", 429, "Too Many Requests", {}, fp)

    with pytest.raises(RateLimitError) as exc_info:
        LLMClient._parse_and_raise_gateway_error(http_err, qm)
    assert "频控保护" in str(exc_info.value)

