# -*- coding: utf-8 -*-
"""
core/guards.py
【立体空间智能体系统 · 框架通用门禁库】
职责：
提供系统级通用的安全与合规门禁实现，供各类商业智能体一键组合使用。
"""

import sys
from typing import Optional

from .contract import BaseGuard, TaskContext, GuardResult
from .config import ConfigManager
from .llm import LLMClient


class LicenseGuard(BaseGuard):
    """
    商业智能体授权验证门禁 (防白嫖与防盗版)
    所有收费版商业智能体在初始化时挂载此门禁，可在任务调度或对话开启前进行拦截。
    支持 strict 参数：True 严格拦截阻断；False 审计记录并以体验警告模式放行。
    """
    def __init__(self, name: str = "商业授权许可门禁", strict: bool = True):
        super().__init__(name=name, description="校验商业授权激活码状态与云端凭证")
        self.strict = strict

    def check(self, context: TaskContext) -> GuardResult:
        cfg = ConfigManager.get_instance().gateway
        valid, msg = LLMClient.verify_license(force_network=False)
        from .hardware import get_device_fingerprint, get_device_name

        fingerprint = get_device_fingerprint()
        dev_name = get_device_name()

        if not valid:
            if self.strict:
                return GuardResult(
                    passed=False,
                    name=self.name,
                    errors=[f"商业授权校验未通过: {msg}。请在 configs/framework.yaml 中配置有效的 license_key！"],
                    metrics={
                        "授权状态": "未授权/拦截",
                        "原因": msg,
                        "本机指纹": fingerprint,
                        "设备名称": dev_name,
                        "授权模式": cfg.mode
                    }
                )
            else:
                return GuardResult(
                    passed=True,
                    name=self.name,
                    warnings=[f"商业授权审计: 当前环境处于未激活状态 ({msg})，体验模式放行"],
                    metrics={
                        "授权状态": "体验模式/未激活",
                        "原因": msg,
                        "本机指纹": fingerprint,
                        "设备名称": dev_name,
                        "授权模式": cfg.mode
                    }
                )

        return GuardResult(
            passed=True,
            name=self.name,
            metrics={
                "授权状态": "正常",
                "凭据信息": msg,
                "本机指纹": fingerprint,
                "设备名称": dev_name,
                "模式": cfg.mode
            }
        )
