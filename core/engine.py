# -*- coding: utf-8 -*-
"""
core/engine.py
【立体空间智能体系统 · 任务调度执行引擎 (Engine)】
职责：
1. 接收标准化任务上下文 (TaskContext)；
2. 调度对应智能体，并严格驱动三段式通用执行流：
   [前置门禁审查 Pre-Guards] ➔ [智能体核心业务 Run] ➔ [后置产出品质检 Post-Guards]；
3. 若前置门禁阻断，立即中断任务并输出诊断报告，杜绝污染下游生产环境。
"""

import sys
import time
import uuid
from typing import Dict, Any, Optional

from .contract import TaskContext, TaskResult, GuardResult
from .registry import Registry


class Engine:
    """微内核调度执行引擎"""

    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or Registry.get_instance()

    def dispatch(self, context: TaskContext) -> TaskResult:
        """
        分发并执行任务
        执行顺序：
        1. 寻址智能体；
        2. 遍历执行 agent.pre_guards；如有阻断，立即退出；
        3. 调用 agent.run(context)；
        4. 遍历执行 agent.post_guards；
        5. 封装 TaskResult 返回。
        """
        agent = self.registry.get_agent(context.agent_name)
        if not agent:
            return TaskResult(
                success=False,
                message=f"调度失败：未找到名为 [{context.agent_name}] 的已注册智能体！",
                data={}
            )

        print(f"\n🚀 [Engine] 启动智能体: 【{agent.name}】 | 任务 ID: {context.task_id}")
        guard_reports = []

        # 1. 执行前置安全门禁审查
        if agent.pre_guards:
            print(f"🛡️  [Engine] 正在执行前置安全门禁审查 ({len(agent.pre_guards)} 项)...")
            for guard in agent.pre_guards:
                res: GuardResult = guard.check(context)
                guard_reports.append(res)
                res.print_summary()
                if not res.passed or res.errors:
                    print(f"⛔ [Engine] 前置安全门禁 [{guard.name}] 触发阻断，任务已安全终止！")
                    return TaskResult(
                        success=False,
                        message=f"前置门禁 [{guard.name}] 审查未通过",
                        data={"blocked_by": guard.name},
                        guard_reports=guard_reports
                    )

        # 2. 执行智能体核心业务
        start_time = time.time()
        print(f"⚙️  [Engine] 正在运行智能体核心逻辑...")
        try:
            task_result: TaskResult = agent.run(context)
        except Exception as e:
            print(f"❌ [Engine] 智能体运行异常: {e}")
            return TaskResult(
                success=False,
                message=f"智能体运行时抛出异常: {e}",
                data={},
                guard_reports=guard_reports
            )

        elapsed = round(time.time() - start_time, 2)
        task_result.guard_reports.extend(guard_reports)

        # 3. 执行后置产出品质检
        if agent.post_guards and task_result.success:
            print(f"🔍 [Engine] 正在执行产出后置质检 ({len(agent.post_guards)} 项)...")
            for guard in agent.post_guards:
                res: GuardResult = guard.check(context)
                task_result.guard_reports.append(res)
                res.print_summary()
                if not res.passed or res.errors:
                    task_result.success = False
                    task_result.message = f"后置质检 [{guard.name}] 未通过"

        status_text = "成功" if task_result.success else "失败/被拦截"
        print(f"🏁 [Engine] 任务执行完毕 (耗时 {elapsed}s) -> 状态: {status_text}\n")
        return task_result

    def dispatch_quick(self, agent_name: str, payload: Dict[str, Any]) -> TaskResult:
        """极简快捷分发入口"""
        ctx = TaskContext(
            task_id=str(uuid.uuid4())[:8],
            agent_name=agent_name,
            payload=payload
        )
        return self.dispatch(ctx)
