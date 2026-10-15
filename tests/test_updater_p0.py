# -*- coding: utf-8 -*-
"""
tests/test_updater_p0.py
验证 P0 阶段的核心功能：
1. SHA256 完整性散列比对与拦截；
2. 增量热补丁的事务级原子快照备份；
3. 白名单安全解包与模块热重载；
4. 损坏补丁注入触发秒级自愈回滚 (Auto-Rollback)；
5. 快照清单查询与历史版本手动还原能力。
"""

import io
import sys
import json
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from core.updater import UpdateManager, compute_sha256
from core.config import ConfigManager

def run_tests():
    print("=" * 60)
    print("🧪 开始执行 P0 阶段 OTA 热补丁与微内核防御测试套件")
    print("=" * 60)

    # 1. 验证 SHA-256 完整性比对与劫持拦截
    print("\n[测试 1/5] 验证 SHA-256 完整性散列比对与劫持拦截...")
    sample_data = b"Litikj Agent OS Patch Payload v2.5.1"
    
    try:
        UpdateManager.apply_patch_archive(
            archive_bytes=sample_data,
            expected_sha256="0000000000000000000000000000000000000000000000000000000000000000"
        )
        assert False, "未能成功拦截篡改的 SHA256！"
    except ValueError as e:
        print(f"  ✅ 成功拦截被篡改的补丁散列: {e.args[0].splitlines()[0]}")

    # 2. 构造一个合法的测试热补丁包 (使用专有测试文件 configs/test_dummy_patch.json)
    print("\n[测试 2/5] 测试原子快照备份与正常补丁安全写入...")
    test_dummy_file = ROOT_DIR / "configs" / "test_dummy_patch.json"
    initial_content = '{"state": "initial_v1"}'
    test_dummy_file.write_text(initial_content, encoding="utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("configs/test_dummy_patch.json", '{"state": "patched_v2"}')
    
    archive_bytes = buf.getvalue()
    valid_patch_sha = compute_sha256(archive_bytes)

    # 应用补丁，测试是否正常生成快照与写入
    res = UpdateManager.apply_patch_archive(
        archive_bytes=archive_bytes,
        expected_sha256=valid_patch_sha,
        enable_backup=True
    )
    print(f"  ✅ 补丁应用结果: {res['message']}")
    print(f"  ✅ 成功创建快照还原点: {res['backup_point']}")
    assert res["success"] is True
    assert res["backup_point"] != ""
    assert test_dummy_file.read_text(encoding="utf-8") == '{"state": "patched_v2"}'

    # 3. 验证备份快照清单查询
    print("\n[测试 3/5] 验证本地快照还原点检索与元数据解析...")
    backups = UpdateManager.list_backups()
    print(f"  ✅ 当前检测到本地快照数量: {len(backups)}")
    assert len(backups) >= 1
    latest_backup = backups[0]
    print(f"  • 最近快照点: {latest_backup['filename']} ({latest_backup['size_kb']} KB, 创建于: {latest_backup['created_at']})")

    # 4. 模拟恶意损坏的 Python 文件，验证自愈回滚机制 (Auto-Rollback)
    print("\n[测试 4/5] 注入含严重语法错误的毒丸补丁，验证【秒级自愈回滚】机制...")
    content_before = test_dummy_file.read_text(encoding="utf-8")

    bad_buf = io.BytesIO()
    with zipfile.ZipFile(bad_buf, "w") as zf:
        zf.writestr("configs/test_dummy_patch.json", '{"state": "poisoned_bad"}')
        # 故意注入一个 Python 语法错误（破坏性代码）
        zf.writestr("core/poison_test.py", "def broken_syntax( -invalid-syntax--- :::")

    bad_bytes = bad_buf.getvalue()
    bad_sha = compute_sha256(bad_bytes)

    try:
        UpdateManager.apply_patch_archive(
            archive_bytes=bad_bytes,
            expected_sha256=bad_sha,
            enable_backup=True
        )
        assert False, "毒丸补丁未能触发异常！"
    except RuntimeError as e:
        print(f"  🛡️ 成功捕获异常并激活自愈回滚:\n     {e}")

    # 验证回滚效果：
    content_after = test_dummy_file.read_text(encoding="utf-8")
    assert content_after == content_before, "回滚后文件未能还原！"
    print("  ✅ 物理文件还原验证通过：原配置内容 100% 保持一致！")

    poison_file = ROOT_DIR / "core" / "poison_test.py"
    assert not poison_file.exists(), "回滚后未抹除新增的废弃物理文件！"
    print("  ✅ 脏数据擦除验证通过：毒丸临时文件已被彻底物理清除！")

    # 5. 验证手动回滚能力
    print("\n[测试 5/5] 验证手动回滚 API (rollback_to_backup)...")
    rollback_res = UpdateManager.rollback_to_backup(backup_filename=res["backup_point"])
    print(f"  ✅ 手动回滚测试通过: {rollback_res['message']}")
    assert test_dummy_file.read_text(encoding="utf-8") == initial_content

    # 清理测试专用临时文件与测试产生的临时快照
    if test_dummy_file.exists():
        test_dummy_file.unlink()
    cm = ConfigManager.get_instance()
    backup_dir = cm.workspace_dir / ".backup"
    if backup_dir.exists():
        for p in backup_dir.glob("*.zip"):
            try:
                p.unlink()
            except Exception:
                pass

    print("\n" + "=" * 60)
    print("🎉 P0 阶段所有安全、校验、快照与自愈回滚测试 100% 全部通过！")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
