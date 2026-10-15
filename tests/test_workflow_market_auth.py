# -*- coding: utf-8 -*-
"""
tests/test_workflow_market_auth.py
【开源版 · 多智能体协同工作流市场与依赖拓扑自动化测试套件】
测试范围：
1. 检索开源工作流市场名录 (system_health_audit) 与依赖拓扑感知；
2. 商业工作流前置权限拦截 (guest 拦截)；
3. 年度会员 (annual) 鉴权通过装载工作流卡带；
4. 一键自动补齐依赖测试；
5. 系统基准流水线 (system_health_audit) 卸载防御。
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from core.workflow_market import WorkflowMarketService
from core.market import parse_jwt_role, has_permission
from core.config import ConfigManager
from core.registry import Registry


def test_workflow_market():
    print("=" * 68)
    print("🧪 测试多智能体协同工作流市场与依赖拓扑体系 (开源基准)")
    print("=" * 68)

    cm = ConfigManager.get_instance()
    reg = Registry.get_instance()
    reg.auto_discover()

    # 1. 检索市场清单与依赖拓扑
    market = WorkflowMarketService.list_workflow_market()
    print(f"云端工作流库数量: {len(market)}")
    assert len(market) >= 1, "工作流市场项目少于 1 个！"

    wf_ids = [w["id"] for w in market]
    print(f"包含工作流: {wf_ids}")
    assert "system_health_audit" in wf_ids
    assert "media_matrix_pipeline" not in wf_ids
    assert "knowledge_course_pipeline" not in wf_ids

    # 验证依赖拓扑字段
    health_flow = next(w for w in market if w["id"] == "system_health_audit")
    assert "dependencies" in health_flow
    assert "missing_agents" in health_flow
    assert "missing_skills" in health_flow
    assert "is_deps_ready" in health_flow

    # 2. 模拟商业专享工作流权限流转测试
    real_load_catalog = WorkflowMarketService.load_workflow_catalog
    mock_catalog = [
        item for item in market
    ] + [
        {
            "id": "mock_annual_pipeline",
            "name": "专属商业测试流水线",
            "version": "1.0.0",
            "required_role": "annual",
            "role_name": "年度会员专享",
            "badge_color": "amber",
            "capsule_filename": "system_health_audit_v1.0.0.flow",
            "dependencies": {
                "agents": ["omni_sentinel"],
                "skills": []
            }
        }
    ]
    WorkflowMarketService.load_workflow_catalog = classmethod(lambda cls: mock_catalog)

    original_key = cm.gateway.license_key
    try:
        # 3. 模拟访客商业拦截测试
        cm.gateway.license_key = ""
        role, rname = parse_jwt_role(cm.gateway.license_key)
        assert role == "guest"

        try:
            WorkflowMarketService.install_workflow("mock_annual_pipeline")
            assert False, "访客未被商业权限拦截！"
        except PermissionError as pe:
            print(f"  ✅ 成功拦截访客并提示年度会员专享: {pe}")

        # 4. 模拟年度会员 (annual) 鉴权装载
        annual_mock_jwt = "header.eyJyb2xlIjogImFubnVhbCIsICJpZCI6IDk5LCAiZXhwIjogOTk5OTk5OTk5OX0.signature"
        cm.gateway.license_key = annual_mock_jwt
        role, rname = parse_jwt_role(cm.gateway.license_key)
        assert role == "annual"

        install_res = WorkflowMarketService.install_workflow("mock_annual_pipeline")
        assert install_res["success"] is True

        # 5. 测试一键补齐依赖
        fix_res = WorkflowMarketService.install_workflow_dependencies("mock_annual_pipeline", force=True)
        assert fix_res["success"] is True

        # 6. 测试基准流水线保护与安全卸载
        try:
            WorkflowMarketService.uninstall_workflow("system_health_audit")
            assert False, "系统官方基准流水线未受保护！"
        except PermissionError as pe:
            print(f"  ✅ 成功保护系统基准流水线: {pe}")

        un_res = WorkflowMarketService.uninstall_workflow("mock_annual_pipeline")
        assert un_res["success"] is True

    finally:
        WorkflowMarketService.load_workflow_catalog = real_load_catalog
        cm.gateway.license_key = original_key
        target_dir = cm.root_dir / "workflows" / "mock_annual_pipeline"
        if target_dir.exists():
            import shutil
            shutil.rmtree(target_dir, ignore_errors=True)

    print("\n" + "=" * 68)
    print("🎉 多智能体协同工作流市场测试 100% 通过！")
    print("=" * 68)


if __name__ == "__main__":
    test_workflow_market()
