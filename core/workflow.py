# -*- coding: utf-8 -*-
"""
core/workflow.py
【立体空间智能体系统 · 多智能体协作流水线引擎 (Workflow 2.0)】
核心升级：
1. 【人机协同审批断点 (Human Gate)】：支持工作流运行至关键节点自动挂载/挂起 (Suspend)，等待人在前端/桌面交互确认后无缝恢复 (Resume)；
2. 【并行分支扇出 (Parallel Fan-out)】：支持将上游产出并发派发给多个独立智能体 (如同时生成B站、公众号与海报)；
3. 【全链路状态快照持久化 (State Persistence)】：支持跨进程、跨会话恢复未完成的工作流；
4. 【级联门禁与熔断机制 (Circuit Breaker)】：任意节点被门禁拦截，立即终止下游执行，保护生产环境。
"""

import os
import sys
import time
import json
import uuid
import concurrent.futures
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from pathlib import Path

from .contract import TaskContext, TaskResult, GuardResult
from .engine import Engine
from .registry import Registry
from .config import ConfigManager

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


@dataclass
class WorkflowStep:
    """流水线普通单步节点定义"""
    agent_name: str
    step_name: str = ""
    transformer: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None
    input_mapping: Optional[Dict[str, str]] = None
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None

    def __post_init__(self):
        if not self.step_name:
            self.step_name = f"调度智能体 [{self.agent_name}]"


@dataclass
class WorkflowHumanGate:
    """人机协同审批断点 (Human-in-the-Loop Node)"""
    gate_id: str
    title: str
    description: str = ""
    step_name: str = ""
    agent_name: str = "human_gate"
    options_extractor: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None
    options_field: str = ""  # 从 shared_state 中提取候选选项的字段名
    static_options: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.step_name:
            self.step_name = f"人机审批: {self.title}"

    def extract_options(self, shared_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """提取供人选择的选项清单"""
        if self.options_extractor:
            try:
                return self.options_extractor(shared_state)
            except Exception:
                pass
        if self.options_field and self.options_field in shared_state:
            val = shared_state[self.options_field]
            if isinstance(val, list):
                # 兼容字符串列表与字典列表
                return [{"id": str(i), "label": str(v), "value": v} if not isinstance(v, dict) else v for i, v in enumerate(val)]
        return self.static_options


@dataclass
class WorkflowParallelStep:
    """多智能体并发分支节点 (Parallel Fan-out)"""
    step_name: str
    sub_steps: List[WorkflowStep]
    agent_name: str = "parallel_fan_out"
    max_workers: int = 4


@dataclass
class WorkflowResult:
    """多智能体流水线协同最终执行结果"""
    workflow_id: str
    workflow_name: str
    success: bool
    message: str
    steps_completed: int
    total_steps: int
    final_data: Dict[str, Any] = field(default_factory=dict)
    step_records: List[Dict[str, Any]] = field(default_factory=list)
    circuit_breaker_agent: Optional[str] = None
    suspended: bool = False
    status: str = "COMPLETED"  # "COMPLETED" | "SUSPENDED_WAITING_HUMAN" | "FAILED"
    gate_info: Optional[Dict[str, Any]] = None
    elapsed_time: float = 0.0

    def print_summary(self):
        print("\n" + "=" * 68)
        if self.suspended:
            status_icon = "⏸️"
            status_text = "已挂起 (等待人工审批决策)"
        elif self.success:
            status_icon = "🎉"
            status_text = "成功"
        else:
            status_icon = "⛔"
            status_text = "中途熔断/失败"

        print(f"{status_icon} 【多智能体协作流水线报告: {self.workflow_name}】")
        print(f"  • 流水线 ID: {self.workflow_id}")
        print(f"  • 执行状态: {status_text} ({self.status})")
        print(f"  • 执行进度: {self.steps_completed} / {self.total_steps} 步已完成")
        print(f"  • 总耗时:   {self.elapsed_time:.2f} 秒")
        print(f"  • 摘要消息: {self.message}")
        if self.gate_info:
            print(f"  • 待审批项: [{self.gate_info.get('title')}] - ID: {self.gate_info.get('gate_id')}")
        if self.circuit_breaker_agent:
            print(f"  • 熔断节点: 智能体 【{self.circuit_breaker_agent}】")
        print("-" * 68)
        print("📋 【各节点流转记录】:")
        for r in self.step_records:
            icon = "✅" if r.get("success") else ("⏸️" if r.get("suspended") else "❌")
            print(f"  {icon} [第 {r.get('step_index')} 步] {r.get('step_name')} (类型: {r.get('node_type')}) -> 耗时 {r.get('elapsed_time', 0):.2f}s")
            if not r.get("success") and not r.get("suspended"):
                print(f"     ❌ 失败消息: {r.get('message')}")
        print("=" * 68 + "\n")


class Workflow:
    """多智能体接力流水线容器 (2.0)"""

    def __init__(self, name: str, description: str = ""):
        self.name: str = name
        self.description: str = description
        self.steps: List[Union[WorkflowStep, WorkflowHumanGate, WorkflowParallelStep]] = []

    def add_step(
        self,
        agent_name: str,
        step_name: str = "",
        transformer: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None,
        input_mapping: Optional[Dict[str, str]] = None,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> 'Workflow':
        """追加一个普通单智能体接力节点"""
        step = WorkflowStep(
            agent_name=agent_name,
            step_name=step_name,
            transformer=transformer,
            input_mapping=input_mapping,
            condition=condition
        )
        self.steps.append(step)
        return self

    def add_human_gate(
        self,
        gate_id: str,
        title: str,
        description: str = "",
        options_extractor: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None,
        options_field: str = "",
        static_options: List[Dict[str, Any]] = None
    ) -> 'Workflow':
        """追加一个人机协同审批/选择断点 (Human Gate)"""
        gate = WorkflowHumanGate(
            gate_id=gate_id,
            title=title,
            description=description,
            options_extractor=options_extractor,
            options_field=options_field,
            static_options=static_options or []
        )
        self.steps.append(gate)
        return self

    def add_parallel_steps(
        self,
        step_name: str,
        sub_steps: List[WorkflowStep],
        max_workers: int = 4
    ) -> 'Workflow':
        """追加多智能体并发扇出节点 (Parallel Fan-out)"""
        parallel = WorkflowParallelStep(
            step_name=step_name,
            sub_steps=sub_steps,
            max_workers=max_workers
        )
        self.steps.append(parallel)
        return self

    def add_parallel_step(self, step_name: str, sub_steps: List[WorkflowStep], max_workers: int = 4) -> 'Workflow':
        """add_parallel_steps 的别名"""
        return self.add_parallel_steps(step_name, sub_steps, max_workers)

    # ================= 状态快照持久化 =================
    @staticmethod
    def _get_state_dir() -> Path:
        cm = ConfigManager.get_instance()
        d = cm.workspace_dir / "data" / "workflow_states"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _save_snapshot(self, workflow_id: str, snapshot: Dict[str, Any]):
        from .security import validate_safe_id
        try:
            clean_id = validate_safe_id(workflow_id, "工作流实例ID")
            state_dir = self._get_state_dir().resolve()
            p = (state_dir / f"{clean_id}.json").resolve()
            if not p.is_relative_to(state_dir):
                raise PermissionError(f"安全拦截：非法路径遍历 [{workflow_id}]")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Workflow Warning] 保存快照失败: {e}")

    @classmethod
    def load_snapshot(cls, workflow_id: str) -> Optional[Dict[str, Any]]:
        from .security import validate_safe_id
        try:
            clean_id = validate_safe_id(workflow_id, "工作流实例ID")
            state_dir = cls._get_state_dir().resolve()
            p = (state_dir / f"{clean_id}.json").resolve()
            if not p.is_relative_to(state_dir):
                return None
            if not p.exists():
                return None
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @classmethod
    def list_suspended_workflows(cls) -> List[Dict[str, Any]]:
        """列出所有处于挂起等待人工决策的工作流实例"""
        res = []
        d = cls._get_state_dir()
        if not d.exists():
            return res
        for f in d.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if data.get("status") == "SUSPENDED_WAITING_HUMAN":
                        res.append(data)
            except Exception:
                pass
        return res

    # ================= 驱动执行与恢复 =================
    def execute(
        self,
        initial_payload: Dict[str, Any],
        engine: Optional[Engine] = None,
        resume_snapshot: Optional[Dict[str, Any]] = None
    ) -> WorkflowResult:
        """
        驱动多智能体全链路协同执行 (支持从快照断点继续恢复)
        """
        eng = engine or Engine(Registry.get_instance())
        total_steps = len(self.steps)
        start_all = time.time()

        if resume_snapshot:
            # 从挂起断点恢复
            workflow_id = resume_snapshot["workflow_id"]
            shared_state = resume_snapshot.get("shared_state", {})
            step_records = resume_snapshot.get("step_records", [])
            start_step_idx = resume_snapshot.get("next_step_index", 1)
            print("\n" + "=" * 68)
            print(f"🔄 [Workflow 恢复执行] 工作流 【{self.name}】 自断点 (第 {start_step_idx} 步) 继续恢复运行...")
            print(f"📋 流水线 ID: {workflow_id}")
            print("=" * 68)
        else:
            # 初始全新运行
            workflow_id = "wf_" + os.urandom(3).hex()
            shared_state = dict(initial_payload)
            step_records = []
            start_step_idx = 1
            print("\n" + "=" * 68)
            print(f"🚀 [Workflow 2.0] 启动多智能体协作流水线: 【{self.name}】 ({total_steps} 个接力节点)")
            print(f"📋 任务说明: {self.description or '未提供描述'}")
            print("=" * 68)

        for idx in range(start_step_idx, total_steps + 1):
            step = self.steps[idx - 1]
            step_start = time.time()

            # ---------------- Case A: 人机协同审批断点 (Human Gate) ----------------
            if isinstance(step, WorkflowHumanGate):
                print(f"\n⏸️  [Workflow 节点 {idx}/{total_steps}] 触发人机决策节点: 【{step.title}】 (ID: {step.gate_id})")
                human_decisions = shared_state.get("_human_decisions", {})

                # 检查该断点是否已经由人提交了决策
                if step.gate_id in human_decisions:
                    decision_val = human_decisions[step.gate_id]
                    print(f"👤 [Workflow] 读取到人工决策记录: {decision_val}")
                    # 合并人工选择结果到共享上下文中
                    if isinstance(decision_val, dict):
                        shared_state.update(decision_val)
                    else:
                        shared_state[step.gate_id] = decision_val

                    step_records.append({
                        "step_index": idx,
                        "step_name": step.step_name,
                        "node_type": "HumanGate",
                        "agent_name": "human",
                        "success": True,
                        "message": f"人工决策已完成: {decision_val}",
                        "elapsed_time": round(time.time() - step_start, 2)
                    })
                    continue

                # 尚未决策，提取选项并挂起工作流
                options = step.extract_options(shared_state)
                gate_payload = {
                    "gate_id": step.gate_id,
                    "title": step.title,
                    "description": step.description,
                    "options": options
                }

                total_elapsed = round(time.time() - start_all, 2)
                record = {
                    "step_index": idx,
                    "step_name": step.step_name,
                    "node_type": "HumanGate",
                    "agent_name": "human",
                    "suspended": True,
                    "success": True,
                    "message": f"工作流挂起，等待人工在工作台做出选择 ({step.title})",
                    "elapsed_time": round(time.time() - step_start, 2)
                }
                step_records.append(record)

                # 保存断点快照
                snapshot_data = {
                    "workflow_id": workflow_id,
                    "workflow_name": self.name,
                    "status": "SUSPENDED_WAITING_HUMAN",
                    "next_step_index": idx,  # 下次从该断点开始 (带入决策)
                    "current_gate": gate_payload,
                    "shared_state": shared_state,
                    "step_records": step_records,
                    "updated_at": time.time()
                }
                self._save_snapshot(workflow_id, snapshot_data)

                print(f"💡 [Workflow 挂起就绪] 状态已持久化至快照。请在桌面工作台完成审批以恢复流水线！")
                res = WorkflowResult(
                    workflow_id=workflow_id,
                    workflow_name=self.name,
                    success=True,
                    suspended=True,
                    status="SUSPENDED_WAITING_HUMAN",
                    message=f"已到达人机协同决策节点: 【{step.title}】，等待人工确认",
                    steps_completed=idx - 1,
                    total_steps=total_steps,
                    final_data=shared_state,
                    step_records=step_records,
                    gate_info=gate_payload,
                    elapsed_time=total_elapsed
                )
                res.print_summary()
                return res

            # ---------------- Case B: 多智能体并发扇出节点 (Parallel Fan-out) ----------------
            elif isinstance(step, WorkflowParallelStep):
                print(f"\n⚡ [Workflow 节点 {idx}/{total_steps}] 触发多智能体并发扇出: 【{step.step_name}】 ({len(step.sub_steps)} 个分支并发)")

                def _run_sub_step(sub: WorkflowStep):
                    sub_start = time.time()
                    p = dict(shared_state)
                    if sub.transformer:
                        p = sub.transformer(shared_state, p)
                    elif sub.input_mapping:
                        p = {}
                        for tk, sk in sub.input_mapping.items():
                            if sk in shared_state:
                                p[tk] = shared_state[sk]

                    ctx = TaskContext(task_id=f"{workflow_id}_s{idx}_{sub.agent_name}", agent_name=sub.agent_name, payload=p)
                    res = eng.dispatch(ctx)
                    return sub, res, round(time.time() - sub_start, 2)

                parallel_results = []
                parallel_failed = False
                failed_agent = None

                with concurrent.futures.ThreadPoolExecutor(max_workers=step.max_workers) as executor:
                    futures = [executor.submit(_run_sub_step, s) for s in step.sub_steps]
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            sub_step, res, sub_elapsed = f.result()
                            parallel_results.append((sub_step, res, sub_elapsed))
                            if not res.success:
                                parallel_failed = True
                                failed_agent = sub_step.agent_name
                        except Exception as e:
                            parallel_failed = True
                            failed_agent = "unknown"

                step_elapsed = round(time.time() - step_start, 2)
                sub_summaries = []
                for sub_step, res, sub_elapsed in parallel_results:
                    sub_summaries.append({
                        "agent_name": sub_step.agent_name,
                        "success": res.success,
                        "message": res.message,
                        "data": res.data
                    })
                    if res.success and res.data:
                        shared_state.update(res.data)

                record = {
                    "step_index": idx,
                    "step_name": step.step_name,
                    "node_type": "ParallelStep",
                    "agent_name": step.agent_name,
                    "sub_steps": sub_summaries,
                    "success": not parallel_failed,
                    "message": "并发分支完成" if not parallel_failed else f"并发分支 [{failed_agent}] 失败",
                    "elapsed_time": step_elapsed
                }
                step_records.append(record)

                if parallel_failed:
                    print(f"⛔ [Workflow 并发熔断] 分支智能体 [{failed_agent}] 执行异常，流水线熔断！")
                    total_elapsed = round(time.time() - start_all, 2)
                    res = WorkflowResult(
                        workflow_id=workflow_id,
                        workflow_name=self.name,
                        success=False,
                        status="FAILED",
                        message=f"并发节点 [{step.step_name}] 中分支 [{failed_agent}] 执行失败",
                        steps_completed=idx - 1,
                        total_steps=total_steps,
                        final_data=shared_state,
                        step_records=step_records,
                        circuit_breaker_agent=failed_agent,
                        elapsed_time=total_elapsed
                    )
                    res.print_summary()
                    return res

                print(f"✅ [Workflow 节点 {idx}/{total_steps}] 所有并发分支全部接力完成！")

            # ---------------- Case C: 普通单步智能体节点 (Sequential Step) ----------------
            else:
                print(f"\n🔗 [Workflow 节点 {idx}/{total_steps}] 准备接力: 【{step.step_name}】 (目标: {step.agent_name})")

                # 条件过滤
                if step.condition and not step.condition(shared_state):
                    print(f"⏭️  [Workflow] 步骤 {idx} 跳过（未满足执行条件）")
                    step_records.append({
                        "step_index": idx,
                        "step_name": step.step_name,
                        "node_type": "SequentialStep",
                        "agent_name": step.agent_name,
                        "success": True,
                        "skipped": True,
                        "message": "条件不满足，跳过执行",
                        "elapsed_time": 0.0
                    })
                    continue

                # 构造载荷
                step_payload: Dict[str, Any] = {}
                if step.transformer:
                    step_payload = step.transformer(shared_state, step_payload)
                elif step.input_mapping:
                    step_payload = dict(shared_state)
                    for target_k, src_k in step.input_mapping.items():
                        if src_k in shared_state:
                            step_payload[target_k] = shared_state[src_k]
                else:
                    step_payload = dict(shared_state)

                # 调度智能体
                task_ctx = TaskContext(
                    task_id=f"{workflow_id}_s{idx}",
                    agent_name=step.agent_name,
                    payload=step_payload,
                    metadata={"workflow_id": workflow_id, "step_index": idx}
                )
                step_result: TaskResult = eng.dispatch(task_ctx)
                step_elapsed = round(time.time() - step_start, 2)

                record = {
                    "step_index": idx,
                    "step_name": step.step_name,
                    "node_type": "SequentialStep",
                    "agent_name": step.agent_name,
                    "input_payload": step_payload,
                    "output_data": step_result.data,
                    "success": step_result.success,
                    "message": step_result.message,
                    "elapsed_time": step_elapsed
                }
                step_records.append(record)

                # 熔断判定
                if not step_result.success:
                    print(f"⛔ [Workflow 熔断保护] 节点 [{step.agent_name}] 审查未通过或运行失败！")
                    total_elapsed = round(time.time() - start_all, 2)
                    res = WorkflowResult(
                        workflow_id=workflow_id,
                        workflow_name=self.name,
                        success=False,
                        status="FAILED",
                        message=f"在步骤 {idx} [{step.step_name}] 触发熔断: {step_result.message}",
                        steps_completed=idx - 1,
                        total_steps=total_steps,
                        final_data=shared_state,
                        step_records=step_records,
                        circuit_breaker_agent=step.agent_name,
                        elapsed_time=total_elapsed
                    )
                    res.print_summary()
                    return res

                if step_result.data:
                    shared_state.update(step_result.data)

                print(f"✅ [Workflow 节点 {idx}/{total_steps}] 接力完成！输出已合流进共享上下文。")

        # 所有步骤全部完成
        total_elapsed = round(time.time() - start_all, 2)
        final_res = WorkflowResult(
            workflow_id=workflow_id,
            workflow_name=self.name,
            success=True,
            status="COMPLETED",
            message=f"多智能体协作流水线 [{self.name}] 全链路协同成功！",
            steps_completed=total_steps,
            total_steps=total_steps,
            final_data=shared_state,
            step_records=step_records,
            elapsed_time=total_elapsed
        )

        # 更新快照为已完成
        self._save_snapshot(workflow_id, {
            "workflow_id": workflow_id,
            "workflow_name": self.name,
            "status": "COMPLETED",
            "final_data": shared_state,
            "step_records": step_records,
            "completed_at": time.time()
        })

        final_res.print_summary()
        return final_res

    @classmethod
    def resume_by_id(cls, workflow_id: str, decision: Dict[str, Any], engine: Optional[Engine] = None) -> WorkflowResult:
        """
        根据 workflow_id 和人工审批决策恢复执行工作流
        """
        snapshot = cls.load_snapshot(workflow_id)
        if not snapshot:
            return WorkflowResult(
                workflow_id=workflow_id,
                workflow_name="unknown",
                success=False,
                status="FAILED",
                message=f"未找到 workflow_id 为 [{workflow_id}] 的快照记录！",
                steps_completed=0,
                total_steps=0
            )

        wf_name = snapshot.get("workflow_name", "")
        reg = Registry.get_instance()
        wf = reg.get_workflow(wf_name)
        if not wf:
            return WorkflowResult(
                workflow_id=workflow_id,
                workflow_name=wf_name,
                success=False,
                status="FAILED",
                message=f"未找到名称为 [{wf_name}] 的注册工作流！",
                steps_completed=0,
                total_steps=0
            )

        # 将人工决策写入 shared_state
        gate_id = snapshot.get("current_gate", {}).get("gate_id", "default_gate")
        if "_human_decisions" not in snapshot["shared_state"]:
            snapshot["shared_state"]["_human_decisions"] = {}
        snapshot["shared_state"]["_human_decisions"][gate_id] = decision

        # 触发恢复执行
        return wf.execute(
            initial_payload={},
            engine=engine,
            resume_snapshot=snapshot
        )
