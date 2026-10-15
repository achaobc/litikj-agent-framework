# -*- coding: utf-8 -*-
"""
core/quota.py
【立体空间智能体系统 · 商业级算力配额与防刷计量中枢 (QuotaManager)】
职责：
1. 客户端单次输入长度限制与智能上下文裁剪 (防巨型文件意外消耗百万 Token)；
2. 客户端防抖与高频硬拦截 (Rate Limiter / Debounce，防手抖及死循环死锁)；
3. 云端配额协议模型 (X-Litikj-Quota-Remaining / X-Litikj-Daily-Used 等) 解析与本地缓存；
4. 429 / 402 熔断预警与配额耗尽异常分流体系 (QuotaExhaustedError / RateLimitError)；
5. 加油包充值核算与自备 Key / 本地 Ollama 零配额消耗分流。
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .config import ConfigManager


class LLMError(Exception):
    """大模型网关与微内核通信异常基类"""
    pass


class LLMQuotaError(LLMError):
    """配额与防刷相关异常基类"""
    pass


class QuotaExhaustedError(LLMQuotaError):
    """官方体验算力额度已耗尽异常"""
    pass


class RateLimitError(LLMQuotaError):
    """请求频次超限或触发防抖拦截异常"""
    pass


class DailyLimitExceededError(RateLimitError):
    """单日硬顶防刷限额超限异常 (方案 A 严格风控，次日 0:00 自动恢复)"""
    pass


class QuotaStatus:
    """算力配额与消耗状态数据模型"""

    def __init__(
        self,
        total: int = 1_000_000,
        remaining: int = 1_000_000,
        daily_limit: int = 100_000,
        daily_used: int = 0,
        rpm_limit: int = 30,
        tier: str = "Standard",
        last_updated: float = 0.0
    ):
        self.total = int(total)
        self.remaining = int(remaining)
        self.daily_limit = int(daily_limit)
        self.daily_used = int(daily_used)
        self.rpm_limit = int(rpm_limit)
        self.tier = str(tier)
        self.last_updated = float(last_updated) or time.time()

    @property
    def used(self) -> int:
        return max(0, self.total - self.remaining)

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(max(0.0, min(100.0, (self.remaining / self.total) * 100.0)), 1)

    @property
    def health_status(self) -> str:
        if self.remaining <= 0:
            return "exhausted"
        if self.percent < 20.0:
            return "warning"
        return "healthy"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "remaining": self.remaining,
            "used": self.used,
            "percent": self.percent,
            "daily_limit": self.daily_limit,
            "daily_used": self.daily_used,
            "rpm_limit": self.rpm_limit,
            "tier": self.tier,
            "status": self.health_status,
            "last_updated": self.last_updated
        }


class QuotaManager:
    """
    单例模式配额与防刷守护管理器
    纯原生标准库实现，零第三方依赖
    """
    _instance: Optional['QuotaManager'] = None

    def __init__(self):
        cm = ConfigManager.get_instance()
        self.cache_dir = cm.workspace_dir / "data"
        self.cache_file = self.cache_dir / ".quota_cache.json"
        self._last_request_ts: float = 0.0
        self._status = self._load_cache()

    @classmethod
    def get_instance(cls, force_reload: bool = False) -> 'QuotaManager':
        if cls._instance is None or force_reload:
            cls._instance = QuotaManager()
        return cls._instance

    def _load_cache(self) -> QuotaStatus:
        """从持久化缓存中加载配额状态"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return QuotaStatus(
                    total=data.get("total", 1_000_000),
                    remaining=data.get("remaining", 1_000_000),
                    daily_limit=data.get("daily_limit", 100_000),
                    daily_used=data.get("daily_used", 0),
                    rpm_limit=data.get("rpm_limit", 30),
                    tier=data.get("tier", "Standard"),
                    last_updated=data.get("last_updated", time.time())
                )
            except Exception:
                pass
        return QuotaStatus()

    def _save_cache(self):
        """持久化保存配额状态至 workspace/data/.quota_cache.json"""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._status.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_status(self) -> QuotaStatus:
        return self._status

    def check_rate_limit(self, min_interval: float = 0.5) -> None:
        """
        客户端本地高频防刷与防抖
        若短时间内连续重复发送，触发硬拦截
        """
        now = time.time()
        elapsed = now - self._last_request_ts
        if self._last_request_ts > 0 and elapsed < min_interval:
            wait_need = round(min_interval - elapsed, 2)
            raise RateLimitError(f"⚠️ [操作防抖拦截] 请求过于频繁，请等待 {wait_need}s 冷却后再试！")
        self._last_request_ts = now

    def truncate_messages(
        self,
        messages: List[Dict[str, str]],
        max_chars: int = 25000
    ) -> Tuple[List[Dict[str, str]], bool, int]:
        """
        客户端单次大输入截断保护 (Max Input Protection)
        规则：
        1. 累计计算所有消息文本字符量；
        2. 若超出 max_chars，智能保留 system 引导及最近多轮关键消息；
        3. 对单条超长消息截取首尾关键段并插入安全裁剪提示；
        4. 返回 (裁剪后的消息列表, 是否发生裁剪, 裁剪后总字符数)。
        """
        if not messages:
            return messages, False, 0

        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        if total_chars <= max_chars:
            return messages, False, total_chars

        # 超出限制，执行智能上下文安全保护
        system_msg: Optional[Dict[str, str]] = None
        other_msgs: List[Dict[str, str]] = []

        for m in messages:
            if m.get("role") == "system" and system_msg is None:
                system_msg = dict(m)
            else:
                other_msgs.append(dict(m))

        budget = max_chars
        if system_msg:
            sys_len = len(system_msg.get("content", ""))
            if sys_len > 5000:
                system_msg["content"] = system_msg["content"][:4900] + "\n...[系统引导长文本已安全截断]..."
            budget -= len(system_msg.get("content", ""))

        budget = max(2000, budget)

        # 从最新消息往回装入
        selected_others: List[Dict[str, str]] = []
        current_used = 0

        for m in reversed(other_msgs):
            content = m.get("content", "") or ""
            c_len = len(content)

            if current_used + c_len <= budget:
                selected_others.insert(0, m)
                current_used += c_len
            else:
                remaining_budget = budget - current_used
                if remaining_budget >= 300 and not selected_others:
                    half = (remaining_budget - 120) // 2
                    truncated_content = (
                        content[:half]
                        + "\n\n... [⚠️ 文本量过大，为防止单次刷爆 Token 算力已为您自动安全精简上下文] ...\n\n"
                        + content[-half:]
                    )
                    m_copy = dict(m)
                    m_copy["content"] = truncated_content
                    selected_others.insert(0, m_copy)
                    current_used += len(truncated_content)
                break

        truncated_result: List[Dict[str, str]] = []
        if system_msg:
            truncated_result.append(system_msg)
        truncated_result.extend(selected_others)

        new_total = sum(len(m.get("content", "") or "") for m in truncated_result)
        return truncated_result, True, new_total

    def update_from_headers(self, headers: Any) -> QuotaStatus:
        """
        从官方云端中枢响应 Headers 中动态解析并同步配额
        兼容 urllib.response.info() 与普通字典
        """
        if not headers:
            return self._status

        header_map: Dict[str, str] = {}
        if hasattr(headers, "items"):
            for k, v in headers.items():
                header_map[k.lower()] = str(v).strip()
        elif hasattr(headers, "get"):
            for k in [
                "x-litikj-quota-total",
                "x-litikj-quota-remaining",
                "x-litikj-daily-limit",
                "x-litikj-daily-used",
                "x-litikj-rpm-limit",
                "x-litikj-tier"
            ]:
                val = headers.get(k)
                if val is not None:
                    header_map[k] = str(val).strip()

        updated = False
        if "x-litikj-quota-total" in header_map:
            try:
                self._status.total = int(header_map["x-litikj-quota-total"])
                updated = True
            except ValueError:
                pass

        if "x-litikj-quota-remaining" in header_map:
            try:
                self._status.remaining = int(header_map["x-litikj-quota-remaining"])
                updated = True
            except ValueError:
                pass

        if "x-litikj-daily-limit" in header_map:
            try:
                self._status.daily_limit = int(header_map["x-litikj-daily-limit"])
                updated = True
            except ValueError:
                pass

        if "x-litikj-daily-used" in header_map:
            try:
                self._status.daily_used = int(header_map["x-litikj-daily-used"])
                updated = True
            except ValueError:
                pass

        if "x-litikj-rpm-limit" in header_map:
            try:
                self._status.rpm_limit = int(header_map["x-litikj-rpm-limit"])
                updated = True
            except ValueError:
                pass

        if "x-litikj-tier" in header_map:
            self._status.tier = header_map["x-litikj-tier"]
            updated = True

        if updated:
            self._status.last_updated = time.time()
            self._save_cache()

        return self._status

    def consume_local_estimate(self, prompt_chars: int, completion_chars: int = 0) -> int:
        """
        在离线/无 Headers 返回时，基于字符数进行本地额度预扣与统计 (约 1 char ≈ 0.5~1 点数)
        """
        est_tokens = max(1, (prompt_chars + completion_chars) // 2)
        self._status.remaining = max(0, self._status.remaining - est_tokens)
        self._status.daily_used += est_tokens
        self._status.last_updated = time.time()
        self._save_cache()
        return est_tokens

    def recharge_quota(self, points: int) -> QuotaStatus:
        """增购算力加油包，增加配额点数"""
        points = max(0, int(points))
        self._status.total += points
        self._status.remaining += points
        self._status.last_updated = time.time()
        self._save_cache()
        return self._status

    def reset_quota(self, total: int = 1_000_000, remaining: Optional[int] = None) -> QuotaStatus:
        """重置测试配额"""
        self._status.total = total
        self._status.remaining = total if remaining is None else remaining
        self._status.daily_used = 0
        self._status.last_updated = time.time()
        self._save_cache()
        return self._status
