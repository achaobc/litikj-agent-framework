# -*- coding: utf-8 -*-
"""
workflows/system_health_audit.py
【微内核基准协同工作流 · Benchmark Workflow】
全维哨兵状态巡检 ➔ 人机审批断点 (Human Gate) ➔ 输出审计简报
"""

from typing import Dict, Any
from core.workflow import Workflow, WorkflowStep
from core.registry import Registry


def create_system_health_audit_workflow() -> Workflow:
    """构建标杆基准协同工作流"""
    flow = Workflow(
        name="system_health_audit",
        description="【基准协同流水线】全维哨兵硬件巡检 ➔ 人机审批确认 ➔ 持久化审计归档"
    )
    flow.icon = "🛡️"
    flow.category = "系统基准"
    flow.version = "1.0.0"
    flow.required_role = "guest"
    flow.role_name = "系统官方内置"
    flow.dependencies = {
        "agents": ["omni_sentinel"],
        "skills": []
    }

    # 步骤 1: 全维哨兵巡检
    flow.add_step(
        agent_name="omni_sentinel",
        step_name="底座环境与硬件指标巡检",
        transformer=lambda s, p: {"mode": "status"}
    )

    # 步骤 2: 人机协同审批断点 (Human Gate)
    flow.add_human_gate(
        gate_id="confirm_audit",
        title="系统健康指标审定",
        description="底座硬件与智能体插槽巡检已就绪，请审定指标并决定后续处置策略：",
        static_options=[
            {
                "id": "approved",
                "label": "✅ 指标优良，准予归档",
                "topic": "系统健康指标优良，准予归档",
                "value": "APPROVED",
                "reason": "内存与磁盘余量充裕，环境安全",
                "target_completion": "100%"
            },
            {
                "id": "warning",
                "label": "⚠️ 存在负载隐患，记录观察",
                "topic": "底座存在高负载风险，记录观察",
                "value": "WARNING",
                "reason": "建议留意后台守护任务资源消耗",
                "target_completion": "80%"
            }
        ]
    )

    # 步骤 3: 归档报告
    flow.add_step(
        agent_name="omni_sentinel",
        step_name="持久化生成巡检报告",
        transformer=lambda s, p: {"mode": "report"}
    )

    return flow


def setup(registry: Registry):
    """注册基准工作流"""
    registry.register_workflow(create_system_health_audit_workflow())
