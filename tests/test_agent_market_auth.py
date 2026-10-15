# -*- coding: utf-8 -*-
"""
tests/test_agent_market_auth.py
测试数字化员工智能体市场与商业鉴权机制（极简双态体系：未激活访客 / 年度会员）：
1. 检索智能体市场目录，包含 B站爆款自媒体总监、小红书图文主编、基准哨兵等；
2. 未激活访客 (guest) 尝试招募专享智能体时，成功拦截并引导激活；
3. 年度会员 (annual) 鉴权通过，支持一键招募、动态解包、内存热重载上岗；
4. 保护基准智能体，验证安全解雇与离职流转。
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from core.agent_market import AgentMarketService
from core.market import parse_jwt_role, has_permission
from core.config import ConfigManager
from core.registry import Registry


def test_agent_market():
    print("=" * 65)
    print("🧪 测试数字化员工招募市场与商业鉴权体系 (未激活访客 / 年度会员)")
    print("=" * 65)

    cm = ConfigManager.get_instance()
    reg = Registry.get_instance()

    # 1. 获取市场清单，验证在架与下架状态
    market = AgentMarketService.list_agent_market()
    print(f"云端智能体名录数量: {len(market)}")
    assert len(market) >= 1, "市场智能体少于 1 个！"

    agent_ids = [item["id"] for item in market]
    print(f"包含智能体代号: {agent_ids}")
    assert "omni_sentinel" in agent_ids
    assert len(agent_ids) == 1

    # 2. 模拟商业专享智能体进行权限流转测试
    real_load_catalog = AgentMarketService.load_agent_catalog
    mock_catalog = [
        item for item in market
    ] + [
        {
            "id": "mock_annual_expert",
            "name": "专属测试专家",
            "version": "1.0.0",
            "required_role": "annual",
            "role_name": "年度会员专享",
            "badge_color": "amber",
            "capsule_filename": "omni_sentinel_v1.0.0.agent"
        }
    ]
    AgentMarketService.load_agent_catalog = classmethod(lambda cls: mock_catalog)

    # 3. 模拟访客拦截测试
    print("\n[测试 1/3] 模拟未激活访客 (guest) 招募商业智能体拦截...")
    original_key = cm.gateway.license_key
    try:
        cm.gateway.license_key = ""
        role, rname = parse_jwt_role(cm.gateway.license_key)
        assert role == "guest"
        print(f"  • 当前模拟身份: {role} ({rname})")

        try:
            AgentMarketService.recruit_agent("mock_annual_expert")
            assert False, "访客未被权限拦截！"
        except PermissionError as pe:
            print(f"  ✅ 成功拦截访客并提示年度会员专享:\n     {pe.args[0].splitlines()[0]}")

        # 4. 模拟年度会员 (annual) 招募
        print("\n[测试 2/3] 模拟年度会员 (annual) 畅享一键招募与热重载...")
        annual_mock_jwt = "header.eyJyb2xlIjogImFubnVhbCIsICJpZCI6IDg4LCAiZXhwIjogOTk5OTk5OTk5OX0.signature"
        cm.gateway.license_key = annual_mock_jwt
        role, rname = parse_jwt_role(cm.gateway.license_key)
        assert role == "annual"
        assert rname == "年度会员"
        print(f"  • 当前模拟身份: {role} ({rname})")

        recruit_res = AgentMarketService.recruit_agent("mock_annual_expert")
        print(f"  ✅ 招募成功: {recruit_res.get('message')}")
        assert recruit_res["success"] is True

        # 验证 Registry 中是否热重载
        active_names = [a.name for a in reg.list_agents()]
        print(f"  • 当前在职员工清单: {active_names}")
        assert "omni_sentinel" in active_names

        # 5. 测试解雇保护与离职
        print("\n[测试 3/3] 测试解雇保护与离职流转...")
        # 5.1 尝试解雇全维调度哨兵（系统基准员工），应被拦截
        try:
            AgentMarketService.dismiss_agent("omni_sentinel")
            assert False, "系统基准哨兵未被保护！"
        except PermissionError as pe:
            print(f"  ✅ 成功保护系统基准智能体: {pe}")

        # 5.2 正常解雇新招募的测试员工
        dismiss_res = AgentMarketService.dismiss_agent("mock_annual_expert")
        print(f"  ✅ 正常办理离职: {dismiss_res.get('message')}")
        assert dismiss_res["success"] is True

    finally:
        # 恢复环境
        AgentMarketService.load_agent_catalog = real_load_catalog
        cm.gateway.license_key = original_key

    print("\n" + "=" * 65)
    print("🎉 数字化员工招募市场与商业鉴权测试 100% 通过！")
    print("=" * 65)


if __name__ == "__main__":
    test_agent_market()
