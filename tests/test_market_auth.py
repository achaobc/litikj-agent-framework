# -*- coding: utf-8 -*-
"""
tests/test_market_auth.py
测试技能市场与商业鉴权机制（纯净双态模型：未激活访客 / 年度会员）：
1. 检索开源示范技能目录 (hello_skill)；
2. 商业技能前置权限拦截 (guest 拦截)；
3. 年度会员 (annual) 鉴权通过装载技能卡带。
"""

import sys
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from core.market import OfficialMarketService, parse_jwt_role, has_permission
from core.config import ConfigManager


def test_market():
    print("=" * 60)
    print("🧪 测试技能市场与商业鉴权体系 (开源基准)")
    print("=" * 60)

    cm = ConfigManager.get_instance()
    user_role, user_role_name = parse_jwt_role(cm.gateway.license_key)
    print(f"当前客户端身份: {user_role} ({user_role_name})")

    # 1. 检查市场列表
    market = OfficialMarketService.list_market()
    print(f"云端技能库数量: {len(market)}")
    assert len(market) >= 1, "市场项目少于 1 个"

    for item in market:
        print(f"  • [{item['id']}] {item['name']}")
        print(f"    - 要求权限: {item.get('required_role_name')} ({item.get('required_role')})")
        print(f"    - 当前权限: 是否已授权={item.get('is_authorized')}, 是否已装载={item.get('is_installed')}")

    # 2. 模拟商业专享技能进行权限流转测试
    print("\n[测试 1/2] 模拟未激活访客 (guest) 拦截技能下载...")
    assert not has_permission("guest", "annual"), "访客不应具备年度会员权限！"

    original_key = cm.gateway.license_key
    real_load = OfficialMarketService.load_catalog_data
    mock_market = [
        item for item in market
    ] + [
        {
            "id": "mock_annual_skill",
            "name": "专属商业测试技能",
            "version": "1.0.0",
            "required_role": "annual",
            "role_name": "年度会员专享",
            "origin": "custom",
            "capsule_filename": "hello_skill_v1.0.0.skill"
        }
    ]
    OfficialMarketService.load_catalog_data = classmethod(lambda cls, sync_remote=False: mock_market)

    try:
        cm.gateway.license_key = ""
        try:
            OfficialMarketService.install_official_skill("mock_annual_skill")
            assert False, "访客未被权限拦截！"
        except PermissionError as pe:
            print(f"  ✅ 成功拦截访客并提示年度会员专享:\n     {pe.args[0].splitlines()[0]}")

        # 3. 模拟年度会员 (annual) 正常安装装载
        print("\n[测试 2/2] 模拟年度会员 (annual) 鉴权通过并解包装载所有技能...")
        annual_mock_jwt = "header.eyJyb2xlIjogImFubnVhbCIsICJpZCI6IDU2LCAiZXhwIjogOTk5OTk5OTk5OX0.signature"
        cm.gateway.license_key = annual_mock_jwt
        role, rname = parse_jwt_role(cm.gateway.license_key)
        assert role == "annual"
        assert rname == "年度会员"
        assert has_permission(role, "annual") is True

        install_res = OfficialMarketService.install_official_skill("mock_annual_skill")
        print(f"  ✅ 年度会员安装成功: {install_res['message']}")
        assert install_res["success"] is True

    finally:
        OfficialMarketService.load_catalog_data = real_load
        cm.gateway.license_key = original_key
        target_dir = cm.skills_dir / "custom" / "mock_annual_skill"
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

    print("\n" + "=" * 60)
    print("🎉 未激活访客 / 年度会员商业鉴权测试 100% 通过！")
    print("=" * 60)


if __name__ == "__main__":
    test_market()
