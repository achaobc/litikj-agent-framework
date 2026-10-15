# -*- coding: utf-8 -*-
"""
立体空间智能体系统 (Litikj Agent OS) - 微内核底座
"""

from .config import ConfigManager, GatewayConfig
from .contract import TaskContext, TaskResult, GuardResult, BaseGuard, BaseSkill, BaseAgent
from .registry import Registry
from .engine import Engine
from .llm import LLMClient
from .guards import LicenseGuard
from .workflow import Workflow, WorkflowStep, WorkflowResult
from .standard_agent import StandardAgent, StandardConfigMixin, StandardFastPathMixin

__version__ = "2.2.0"
__all__ = [
    "ConfigManager",
    "GatewayConfig",
    "TaskContext",
    "TaskResult",
    "GuardResult",
    "BaseGuard",
    "BaseSkill",
    "BaseAgent",
    "StandardAgent",
    "StandardConfigMixin",
    "StandardFastPathMixin",
    "Registry",
    "Engine",
    "LLMClient",
    "LicenseGuard",
    "Workflow",
    "WorkflowStep",
    "WorkflowResult"
]
