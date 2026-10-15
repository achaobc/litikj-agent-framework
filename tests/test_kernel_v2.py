# -*- coding: utf-8 -*-
"""
tests/test_kernel_v2.py
【微内核 2.0 升级全套端到端验证测试】
测试范围：
1. Workflow 2.0 人机协同审批断点 (Human Gate) 挂起与恢复 (Resume)
2. Workflow 2.0 多智能体并发扇出 (Parallel Fan-out)
3. WatcherEngine 通用投递箱防抖感知与自动调度
4. CLI 脚手架 (Scaffolding) 一键初始化
"""

import sys
import time
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import ConfigManager
from core.registry import Registry
from core.workflow import Workflow, WorkflowStep
from core.watcher import WatcherEngine
from core.scaffold import create_agent_scaffold, create_workflow_scaffold


def test_workflow_2_human_gate_and_resume():
    print("\n" + "=" * 60)
    print("🧪 1. 测试 Workflow 2.0 人机协同审批断点与恢复")
    print("=" * 60)

    reg = Registry.get_instance()
    reg.auto_discover()

    # 构建一个包含人机审批节点的工作流
    flow = Workflow("test_approval_flow", description="测试审批流")
    reg.register_workflow(flow)

    # 步骤 1: 巡检前置准备
    flow.add_step("omni_sentinel", step_name="前置巡检", transformer=lambda s, p: {"action": "inspect"})

    # 步骤 2: 人机审批断点 (选择选题)
    flow.add_human_gate(
        gate_id="select_topic",
        title="今日选题决策",
        description="请选出今天要讲的核心主题",
        static_options=[
            {"id": "t1", "title": "Auto.js商业防封", "score": 98},
            {"id": "t2", "title": "Python爬虫与逆向", "score": 92}
        ]
    )

    # 步骤 3: 确定选题后的后置处理
    flow.add_step("omni_sentinel", step_name="后置确认", transformer=lambda s, p: {"action": "inspect", "chosen_topic": s.get("select_topic")})

    # 执行第一次：应该自动在步骤 2 挂起
    res1 = flow.execute({"initial_tag": "demo"})
    print(f"执行结果 1: status={res1.status}, suspended={res1.suspended}, completed={res1.steps_completed}/{res1.total_steps}")
    assert res1.suspended is True, "工作流未在 Human Gate 正常挂起！"
    assert res1.status == "SUSPENDED_WAITING_HUMAN"
    assert res1.gate_info["gate_id"] == "select_topic"
    assert len(res1.gate_info["options"]) == 2
    wf_id = res1.workflow_id
    print(f"✅ 工作流已成功在 Human Gate 挂起，获取到 workflow_id: {wf_id}")

    # 检查挂起列表
    suspended_list = Workflow.list_suspended_workflows()
    assert any(w["workflow_id"] == wf_id for w in suspended_list), "挂起清单中未找到当前工作流快照！"
    print("✅ 挂起工作流快照持久化校验通过")

    # 执行恢复 (模拟用户在工作台或命令行做出选择)
    print("\n👤 模拟用户在工作台选定选项: {'select_topic': 'Auto.js商业防封实战'}")
    res2 = Workflow.resume_by_id(wf_id, {"select_topic": "Auto.js商业防封实战"})
    print(f"恢复执行结果 2: status={res2.status}, success={res2.success}, completed={res2.steps_completed}/{res2.total_steps}")
    assert res2.success is True, "工作流恢复执行失败！"
    assert res2.status == "COMPLETED"
    assert res2.final_data.get("select_topic") == "Auto.js商业防封实战"
    print("✅ 工作流携人工决策无缝恢复执行完毕！")


def test_workflow_2_parallel_fanout():
    print("\n" + "=" * 60)
    print("🧪 2. 测试 Workflow 2.0 多智能体并发扇出 (Parallel Fan-out)")
    print("=" * 60)

    reg = Registry.get_instance()
    reg.auto_discover()

    flow = Workflow("test_parallel_flow", description="测试并发流")
    reg.register_workflow(flow)

    # 并发分支：同时并发两个分支
    sub1 = WorkflowStep(agent_name="omni_sentinel", step_name="分支1: 巡检A", transformer=lambda s, p: {"action": "inspect"})
    sub2 = WorkflowStep(agent_name="omni_sentinel", step_name="分支2: 巡检B", transformer=lambda s, p: {"action": "inspect"})

    flow.add_parallel_steps(step_name="三端同时处理", sub_steps=[sub1, sub2], max_workers=2)

    res = flow.execute({"test_key": "val"})
    print(f"并发执行结果: success={res.success}, completed={res.steps_completed}/{res.total_steps}")
    assert res.success is True, "并发节点执行失败！"
    assert res.status == "COMPLETED"
    print("✅ 多智能体并发扇出执行测试通过！")


def test_watcher_engine():
    print("\n" + "=" * 60)
    print("🧪 3. 测试 WatcherEngine 通用投递箱防抖感知与自动调度")
    print("=" * 60)

    cm = ConfigManager.get_instance()
    test_dir = cm.workspace_dir / "drop_box" / "videos"
    test_dir.mkdir(parents=True, exist_ok=True)
    dummy_video = test_dir / "test_recording_001.mp4"

    watcher = WatcherEngine.get_instance()
    # 临时将 settle_seconds 设为 0.1s 方便单元测试极速跑通
    watcher.watcher_cfg.settle_seconds = 0.1

    # 自定义拦截回调以验证触发载荷
    dispatched_events = []
    watcher.custom_callback = lambda rule, path: dispatched_events.append((rule.name, path.name))

    # 写入模拟文件
    dummy_video.write_bytes(b"dummy video data stream " * 100)

    # 首次扫描：感知新文件并加入跟踪防抖列表
    watcher.scan_once()

    # 等待稳定期后执行二次扫描：触发就绪事件
    time.sleep(0.15)
    triggered = watcher.scan_once()
    print(f"扫描触发文件列表: {[f.name for f in triggered]}")
    assert len(triggered) >= 1
    assert any(f.name == dummy_video.name for f in triggered)
    assert len(dispatched_events) >= 1
    assert any(e[1] == dummy_video.name for e in dispatched_events)
    print(f"✅ Watcher 成功捕获并分发就绪文件: {dispatched_events}")

    # 再次扫描，验证防重放 (同一个文件不再重复触发)
    triggered_again = watcher.scan_once()
    assert dummy_video not in triggered_again
    print("✅ Watcher 防重复触发机制验证通过！")

    # 清理测试文件
    dummy_video.unlink(missing_ok=True)


def test_scaffolding():
    print("\n" + "=" * 60)
    print("🧪 4. 测试工程脚手架 (Scaffolding)")
    print("=" * 60)

    cm = ConfigManager.get_instance()
    # 1. 测试生成新 Agent
    agent_dir = create_agent_scaffold("test_temp_bot", description="临时测试智能体", is_custom=True, with_tests=False)
    assert (agent_dir / "entry.py").exists()
    assert (agent_dir / "config.yaml").exists()
    print(f"✅ 新智能体脚手架生成成功: {agent_dir}")

    # 2. 测试生成新 Workflow
    wf_file = create_workflow_scaffold("test_temp_flow", description="临时测试流水线")
    assert wf_file.exists()
    print(f"✅ 新流水线脚手架生成成功: {wf_file}")

    # 清理临时文件
    shutil.rmtree(agent_dir, ignore_errors=True)
    wf_file.unlink(missing_ok=True)
    print("✅ 临时脚手架工程清理完毕！")


def run_all():
    test_workflow_2_human_gate_and_resume()
    test_workflow_2_parallel_fanout()
    test_watcher_engine()
    test_scaffolding()

    print("\n" + "=" * 60)
    print("🎉 恭喜！立体空间智能体操作系统 (Litikj Agent OS) 微内核 2.0 全部通过验证！")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_all()
