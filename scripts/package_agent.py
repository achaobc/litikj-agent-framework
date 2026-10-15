# -*- coding: utf-8 -*-
"""
scripts/package_agent.py
【立体空间智能体系统 · 单体/全量数字化员工卡带打包与前置质量门禁工具】

职责与流程：
1. 【门禁 1 · 静态合规扫描】：调用 check_agent_sop_compliance() 核验零顶层第三方依赖 (SOP §4.3)；
2. 【门禁 2 · 自动化单测门禁】：自动执行 pytest tests/test_{agent_name}.py，未通过严禁打包；
3. 【打包流水线】：生成 .agent 卡带、计算 SHA-256、更新本地与发布端 agent_catalog.json；
4. 【可选发布】：若带 --publish 参数，直接同步至官方生产 CDN (cdn.litikj.com) 并验证 HTTP 200。
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from core.scaffold import check_agent_sop_compliance
from scripts.build_agent_capsules import (
    find_all_agents,
    package_single_agent,
    OUTPUT_CAPSULES_DIR,
    ROOT_DIR
)


def run_compliance_check(agent_dir: Path) -> bool:
    print("\n" + "=" * 65)
    print(f"🛡️  [门禁 1/3] 执行 SOP 工业级静态合规质检: {agent_dir.name}")
    print("=" * 65)

    errors = check_agent_sop_compliance(agent_dir)
    if errors:
        print(f"❌ 静态扫描未通过，发现 {len(errors)} 项阻断性问题：")
        for err in errors:
            print(f"   • {err}")
        return False

    print("✅ SOP 静态合规质检通过（无顶层非法三方依赖，接口契约齐备）")
    return True


def run_unit_tests(agent_name: str) -> bool:
    print("\n" + "=" * 65)
    print(f"🧪 [门禁 2/3] 执行自动化测试套件: tests/test_{agent_name}.py")
    print("=" * 65)

    test_file = ROOT_DIR / "tests" / f"test_{agent_name}.py"
    if not test_file.exists():
        print(f"⚠️ 未找到专属测试套件 {test_file.name}，跳过单测门禁。")
        return True

    cmd = [sys.executable, "-m", "pytest", str(test_file), "-q"]
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print(f"\n❌ 单元测试套件未全量通过，阻断卡带打包！")
        return False

    print(f"✅ 单元测试套件 100% 通过！")
    return True


def package_agent(agent_name: str, skip_test: bool = False, publish: bool = False) -> bool:
    agent_dir = ROOT_DIR / "agents" / agent_name
    if not agent_dir.exists():
        print(f"❌ 未找到智能体目录: {agent_dir}")
        return False

    # 1. 静态合规扫描
    if not run_compliance_check(agent_dir):
        return False

    # 2. 单测门禁
    if not skip_test:
        if not run_unit_tests(agent_name):
            return False

    # 3. 执行打包
    print("\n" + "=" * 65)
    print(f"📦 [步骤 3/3] 生成标准化卡带 (.agent) 与清单索引")
    print("=" * 65)

    all_agents = find_all_agents()
    target_info = next((a for a in all_agents if a["id"] == agent_name), None)
    if not target_info:
        print(f"❌ 智能体 [{agent_name}] 未能通过扫描验证（可能缺少合法 config.yaml）")
        return False

    OUTPUT_CAPSULES_DIR.mkdir(parents=True, exist_ok=True)
    meta = package_single_agent(target_info, OUTPUT_CAPSULES_DIR)

    # 同步更新 agent_catalog.json
    from scripts.build_agent_capsules import main as rebuild_all_catalog
    rebuild_all_catalog()

    print(f"\n🎉 卡带打包完成！")
    print(f"   • 卡带文件：{meta['capsule_filename']} ({meta['size']})")
    print(f"   • SHA-256 ：{meta['sha256']}")
    print(f"   • 存储路径：{OUTPUT_CAPSULES_DIR / meta['capsule_filename']}")

    # 4. 可选 CDN 发布
    if publish:
        print("\n" + "=" * 65)
        print(f"🚀 [自动上架] 同步发布至生产 CDN (cdn.litikj.com)")
        print("=" * 65)
        print("开源版本暂不提供内部生产 CDN 发布功能")

    return True


def main():
    parser = argparse.ArgumentParser(description="数字化员工智能体卡带打包与前置质量门禁工具")
    parser.add_argument("agent", nargs="?", default="", help="要打包的智能体名称 (如 omni_sentinel)")
    parser.add_argument("--all", action="store_true", help="全量扫描并打包所有智能体")
    parser.add_argument("--no-test", action="store_true", help="跳过单元测试门禁")
    parser.add_argument("--publish", action="store_true", help="打包完成后自动上传部署至官方 CDN")

    args = parser.parse_args()

    if args.all:
        agents = find_all_agents()
        print(f"🚀 开始全量打包 {len(agents)} 个数字化员工智能体...")
        for a in agents:
            ok = package_agent(a["id"], skip_test=args.no_test, publish=False)
            if not ok:
                print(f"❌ 智能体 [{a['id']}] 打包中断！")
                sys.exit(1)
        if args.publish:
            try:
                from scripts.publish_capsules_to_cdn import upload_to_server
                upload_to_server()
            except ImportError:
                print("⚠️ [框架提示] 当前环境未配置商业生产 CDN 上传模块 (scripts.publish_capsules_to_cdn)，已跳过自动上架。")
        print("\n✅ 全量智能体卡带打包完成！")
    elif args.agent:
        ok = package_agent(args.agent, skip_test=args.no_test, publish=args.publish)
        if not ok:
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
