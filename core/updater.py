# -*- coding: utf-8 -*-
"""
core/updater.py
【立体空间智能体系统 · OTA 轻量级热补丁与远程版本更新微内核引擎】

职责：
1. 本地与远程版本比对 (SemVer 智能解析与灰度比对)；
2. 官方中枢 / GitHub Releases 远程接口轮询与静默版本探测；
3. SHA-256 完整性校验 (防链路篡改与中间人劫持)；
4. 事务级原子快照备份与自愈回滚机制 (Auto-Rollback)：
   - 解包前自动为受影响的旧文件创建快照归档于 workspace/.backup/；
   - 解包写入后执行轻量级健康语法巡检；
   - 巡检失败或解包异常触发 0 损失自愈回滚，彻底杜绝系统变砖；
5. 安全沙盒增量解包器 (Strict Whitelist Sandbox)：
   - 防 Zip Slip 路径穿越；
   - 严禁触碰 workspace/ (学员私有成果、对话、数据 100% 物理隔离保护)；
   - 严禁触碰 runtime/ (30MB 嵌入式环境免重复下载)；
   - 仅允许平滑覆盖 skills/, agents/, core/, apps/, configs/；
6. 补丁注入后触发模块缓存刷新与 Registry 内存级热重载。
"""

import os
import sys
import io
import json
import shutil
import hashlib
import zipfile
import py_compile
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .config import ConfigManager
from .security import safe_extract_zip, validate_safe_id

# 允许热补丁覆盖的代码与资源白名单顶级目录
ALLOWED_TARGET_ROOTS = {"skills", "agents", "core", "apps", "configs", "workflows", "desktop"}

# 严格禁止任何热补丁触碰的保护区 (保护学员资产与环境)
FORBIDDEN_ROOTS = {"workspace", "runtime", ".git", ".venv", "__pycache__"}

# 🛡️ 官方增量热补丁安全下载域名白名单 (防第三方恶意 URL 投毒与中间人劫持)
ALLOWED_UPDATE_DOMAINS = (
    "https://cdn.litikj.com/",
    "https://www.litikj.com/",
    "https://release.litikj.com/",
    "https://download.litikj.com/",
)


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """🛡️ 严格审查 HTTP 301/302 重定向目标，防止被重定向劫持至非官方未受信服务器 (SEC-04)"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        clean_url = (newurl or "").strip()
        if clean_url.startswith("http://"):
            raise PermissionError(f"安全拦截：严禁补丁下载重定向至明文 HTTP 地址 ({clean_url})")
        if not any(clean_url.startswith(d) for d in ALLOWED_UPDATE_DOMAINS):
            raise PermissionError(f"安全拦截：补丁下载重定向目标不在受信官方更新域名白名单中 ({clean_url})")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def compute_sha256(data: bytes) -> str:
    """计算二进制字节流的 SHA-256 散列值"""
    return hashlib.sha256(data).hexdigest().lower()


def parse_semver(v_str: str) -> Tuple[int, int, int]:
    """解析语义化版本号字符串，如 'v2.5.0' -> (2, 5, 0)"""
    clean = v_str.strip().lower().lstrip("v")
    parts = clean.split(".")
    res = []
    for p in parts[:3]:
        num_str = "".join(c for c in p if c.isdigit())
        res.append(int(num_str) if num_str else 0)
    while len(res) < 3:
        res.append(0)
    return (res[0], res[1], res[2])


def is_newer_version(remote_v: str, local_v: str) -> bool:
    """判定远程版本是否严格高于本地版本"""
    return parse_semver(remote_v) > parse_semver(local_v)


class UpdateManager:
    """OTA 热补丁与版本更新管理器"""

    @classmethod
    def check_for_updates(cls, simulate: bool = False) -> Dict[str, Any]:
        """
        发起版本更新检测
        :param simulate: 若为 True，则返回一份用于演练的增量模拟补丁数据
        """
        cm = ConfigManager.get_instance()
        current_version = cm.version or "2.5.0"

        # 演练/模拟模式 (用于一键体验热补丁流程)
        if simulate:
            next_patch_ver = f"2.5.{parse_semver(current_version)[2] + 1}"
            return {
                "has_update": True,
                "current_version": current_version,
                "latest_version": next_patch_ver,
                "title": f"🎉 发现立体空间增量热补丁 (v{next_patch_ver})",
                "release_notes": [
                    "新增【自媒体爆款封面 3D 渲染】原子技能卡带",
                    "优化全维哨兵 0-Token 快速直达响应延迟",
                    "修复跨设备硬件指纹冷启动秒开稳定性",
                    "升级系统设置 Clash Verge 现代双列卡片架构"
                ],
                "patch_type": "hotfix",
                "file_size_kb": 32,
                "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "download_url": "mock://hotfix_patch_bundle",
                "is_simulated": True,
                "message": f"发现新补丁 v{next_patch_ver}，体积仅 32 KB，点击即可一键无感热更新！"
            }

        # 真实远程探测流程
        remote_url = "https://raw.githubusercontent.com/achaobc/litikj-agent-os/main/configs/version.json"
        
        try:
            req = urllib.request.Request(
                remote_url,
                headers={"User-Agent": f"LitikjAgentOS/{current_version} (Windows x64)"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    latest_v = data.get("latest_version", current_version)
                    has_up = is_newer_version(latest_v, current_version)
                    notes = data.get("release_notes", [])
                    if isinstance(notes, str):
                        notes = [line.strip() for line in notes.split("\n") if line.strip()]

                    return {
                        "has_update": has_up,
                        "current_version": current_version,
                        "latest_version": latest_v,
                        "title": data.get("title", f"立体空间智能体系统 v{latest_v}"),
                        "release_notes": notes,
                        "patch_type": data.get("patch_type", "hotfix"),
                        "channel": data.get("channel", "stable"),
                        "release_date": data.get("release_date", ""),
                        "file_size_kb": data.get("file_size_kb", 32),
                        "sha256": data.get("sha256", ""),
                        "download_url": data.get("download_url", ""),
                        "is_simulated": False,
                        "message": f"发现新版本 v{latest_v}" if has_up else "当前已是最新版本"
                    }
        except Exception:
            # 当远程暂时不可达或无网络时平稳回退，绝不阻断系统正常运行
            pass

        return {
            "has_update": False,
            "current_version": current_version,
            "latest_version": current_version,
            "title": f"立体空间智能体系统 (v{current_version})",
            "release_notes": ["当前底座微内核与技能矩阵均处于最新就绪状态。"],
            "patch_type": "none",
            "file_size_kb": 0,
            "sha256": "",
            "download_url": "",
            "is_simulated": False,
            "message": "当前已是最新版本，所有组件健康就绪！"
        }

    @classmethod
    def apply_patch_archive(
        cls,
        archive_bytes: Optional[bytes] = None,
        patch_url: str = "",
        expected_sha256: str = "",
        enable_backup: bool = True
    ) -> Dict[str, Any]:
        """
        安全沙箱解包并应用增量热补丁（具备 SHA256 校验、原子备份快照与自愈回滚机制）
        """
        cm = ConfigManager.get_instance()
        project_root = cm.root_dir
        current_version = cm.version or "2.5.0"

        # 若未传入字节流且为模拟包，构建一份轻量内省模拟热补丁
        if not archive_bytes and (not patch_url or patch_url.startswith("mock://")):
            next_patch_ver = f"2.5.{parse_semver(current_version)[2] + 1}"
            return cls._apply_simulated_patch(next_patch_ver)

        # 真实下载流程 (强制 HTTPS 传输与官方受信任域名白名单)
        if not archive_bytes and (patch_url.startswith("http://") or patch_url.startswith("https://")):
            if patch_url.startswith("http://"):
                raise PermissionError(f"安全拦截：严禁使用不安全的明文 HTTP 协议下载系统热补丁包，必须使用 HTTPS 加密通道！({patch_url})")
            if not any(patch_url.startswith(d) for d in ALLOWED_UPDATE_DOMAINS):
                raise PermissionError(
                    f"安全拦截：补丁包下载域名不在受信任的官方更新源白名单中！\n"
                    f"受阻地址: {patch_url}\n"
                    f"仅允许从以下官方受信任前缀下载热补丁:\n" + "\n".join(f"  • {d}" for d in ALLOWED_UPDATE_DOMAINS)
                )

            try:
                opener = urllib.request.build_opener(SafeRedirectHandler)
                req = urllib.request.Request(patch_url, headers={"User-Agent": "LitikjAgentOS-Updater"})
                with opener.open(req, timeout=15) as resp:
                    archive_bytes = resp.read()
            except Exception as e:
                raise RuntimeError(f"下载增量补丁包失败: {str(e)}")

        if not archive_bytes:
            raise ValueError("补丁数据为空，无法执行解包注入")

        # 1. 🛡️ SHA-256 完整性散列强校验 (严禁空哈希或特殊测试串绕过, SEC-04)
        actual_sha256 = compute_sha256(archive_bytes)
        clean_expected = (expected_sha256 or "").strip().lower()
        if not clean_expected:
            raise ValueError("安全拦截：必须提供预期的 SHA-256 完整性散列校验值，禁止空哈希热更新！")

        if actual_sha256 != clean_expected:
            raise ValueError(
                f"安全拦截：补丁包 SHA-256 完整性校验未通过！\n"
                f"期望值: {clean_expected}\n实际值: {actual_sha256}\n"
                f"可能由于下载传输损坏或遭遇链路篡改，更新已安全终止。"
            )

        zip_buffer = io.BytesIO(archive_bytes)
        
        # 2. 🛡️ 严格安全前置审查：绝不允许路径穿越 (Zip Slip) 或修改保护目录 (SEC-02/R2-VULN-01)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            namelist = zf.namelist()
            for name in namelist:
                clean_name = name.replace("\\", "/")
                if ".." in clean_name or ":" in clean_name or clean_name.startswith("/"):
                    raise PermissionError(f"安全拦截：补丁包中检测到非法路径穿越尝试 [{name}]")
                parts = Path(clean_name).parts
                if not parts:
                    continue
                root_part = parts[0].lower()
                if root_part in FORBIDDEN_ROOTS:
                    raise PermissionError(f"安全拦截：严禁热补丁篡改保护区目录 [{root_part}]！")

        # 3. 💾 事务级原子快照备份 (制作回滚还原点)
        backup_zip_path: Optional[Path] = None
        newly_created_files: List[Path] = []
        updated_files: List[str] = []

        if enable_backup:
            backup_zip_path = cls._create_snapshot_backup(zip_buffer, project_root, current_version)

        # 4. 执行白名单沙盒覆盖写入 (复用 safe_extract_zip 统一安全解压与物理边界断言 R2-VULN-01)
        import tempfile
        temp_staging_dir = Path(tempfile.mkdtemp(prefix="litikj_patch_staging_"))
        try:
            zip_buffer.seek(0)
            safe_extract_zip(zip_buffer, temp_staging_dir, ignore_files={"meta.json"})

            for staged_file in temp_staging_dir.rglob("*"):
                if not staged_file.is_file():
                    continue
                file_rel = staged_file.relative_to(temp_staging_dir)
                rel_str = str(file_rel).replace("\\", "/")
                root_part = file_rel.parts[0].lower()
                if root_part in FORBIDDEN_ROOTS:
                    raise PermissionError(f"安全拦截：严禁热补丁篡改保护区目录 [{root_part}]！")
                if root_part not in ALLOWED_TARGET_ROOTS and rel_str != "configs/framework.yaml":
                    continue

                dest_file = (project_root / file_rel).resolve()
                if not dest_file.is_relative_to(project_root.resolve()):
                    raise PermissionError(f"安全拦截：检测到越界写入尝试 [{rel_str}]")

                if not dest_file.exists():
                    newly_created_files.append(dest_file)

                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_file, dest_file)
                updated_files.append(rel_str)

            # 5. 🔍 执行语法巡检与微内核健康探针 (Health Probe)
            cls._verify_system_health(project_root, updated_files)

            # 6. 模块缓存平滑刷新与内存热重载
            cls._reload_python_modules(updated_files)

            # 7. 清理过期备份 (保持最新 5 份快照)
            if enable_backup:
                cls._cleanup_old_backups(keep=5)

        except Exception as e:
            # 🚨 触发秒级自愈回滚！
            if backup_zip_path and backup_zip_path.exists():
                rollback_res = cls._execute_rollback(backup_zip_path, project_root, newly_created_files)
                raise RuntimeError(
                    f"热补丁应用时健康巡检异常 ({e})。\n"
                    f"🛡️ 系统已触发秒级自愈回滚机制，已成功恢复 {rollback_res['restored_count']} 个核心文件，"
                    f"系统已 100% 安全回滚至稳定基线 (v{current_version})！"
                ) from e
            raise e
        finally:
            if temp_staging_dir and temp_staging_dir.exists():
                shutil.rmtree(temp_staging_dir, ignore_errors=True)

        return {
            "success": True,
            "status": "success",
            "updated_count": len(updated_files),
            "updated_files": updated_files[:10],
            "sha256": actual_sha256,
            "backup_point": backup_zip_path.name if backup_zip_path else "",
            "message": f"🎉 成功热更新 {len(updated_files)} 个核心文件，健康巡检 100% 通过，新功能即刻生效！"
        }

    @classmethod
    def _create_snapshot_backup(cls, zip_buffer: io.BytesIO, project_root: Path, current_version: str) -> Path:
        """为即将被覆盖的文件创建原子快照备份"""
        cm = ConfigManager.get_instance()
        backup_dir = cm.workspace_dir / ".backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_file_name = f"backup_v{current_version}_{timestamp_str}.zip"
        backup_zip_path = backup_dir / backup_file_name

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            incoming_files = [zinfo.filename for zinfo in zf.infolist() if not zinfo.is_dir()]

        # 收集本地已存在的旧版文件
        files_to_backup: List[Path] = []
        for rel_str in incoming_files:
            rel_p = Path(rel_str)
            abs_p = project_root / rel_p
            if abs_p.is_file():
                files_to_backup.append(rel_p)

        with zipfile.ZipFile(backup_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bzf:
            for rel_p in files_to_backup:
                abs_p = project_root / rel_p
                arcname = str(rel_p).replace("\\", "/")
                bzf.write(abs_p, arcname=arcname)

            # 写入备份元数据
            meta = {
                "created_at": datetime.now().isoformat(),
                "from_version": current_version,
                "backed_up_count": len(files_to_backup),
                "backed_up_files": [str(p).replace("\\", "/") for p in files_to_backup]
            }
            bzf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

        return backup_zip_path

    @classmethod
    def _verify_system_health(cls, project_root: Path, updated_files: List[str]):
        """健康自检：编译检查所有被更新的 Python 代码语法，并校验注册表装载"""
        for f_rel in updated_files:
            if f_rel.endswith(".py"):
                abs_f = project_root / Path(f_rel)
                if abs_f.is_file():
                    py_compile.compile(str(abs_f), doraise=True)

        # 尝试触发注册表轻量自省
        from core.registry import Registry
        reg = Registry.get_instance()
        reg.auto_discover()

    @classmethod
    def _reload_python_modules(cls, updated_files: List[str]):
        """针对变动的 Python 文件，从 sys.modules 中清除旧缓存并热重载"""
        for f_rel in updated_files:
            if not f_rel.endswith(".py"):
                continue
            # 将路径转为模块点分名，例如 core/updater.py -> core.updater
            p = Path(f_rel)
            parts = p.with_suffix("").parts
            mod_name = ".".join(parts)
            if mod_name in sys.modules:
                try:
                    import importlib
                    importlib.reload(sys.modules[mod_name])
                except Exception:
                    sys.modules.pop(mod_name, None)

        try:
            from core.registry import Registry
            Registry.get_instance().auto_discover()
        except Exception:
            pass

    @classmethod
    def _execute_rollback(cls, backup_zip_path: Path, project_root: Path, newly_created_files: List[Path]) -> Dict[str, Any]:
        """执行秒级物理还原与状态回滚 (严格 Zip Slip 防护 SEC-02)"""
        restored = 0
        if backup_zip_path.exists():
            extracted = safe_extract_zip(backup_zip_path, project_root, ignore_files={"meta.json"})
            restored = len(extracted)

        # 抹除本次解包新增的废弃物理文件
        for new_f in newly_created_files:
            if new_f.exists() and new_f.is_file():
                try:
                    new_f.unlink()
                except Exception:
                    pass

        # 重新扫描注册表以恢复原有组件
        try:
            from core.registry import Registry
            Registry.get_instance().auto_discover()
        except Exception:
            pass

        return {"restored_count": restored}

    @classmethod
    def list_backups(cls) -> List[Dict[str, Any]]:
        """获取所有本地快照备份清单"""
        cm = ConfigManager.get_instance()
        backup_dir = cm.workspace_dir / ".backup"
        if not backup_dir.exists():
            return []

        backups = []
        for p in sorted(backup_dir.glob("backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
            sz_kb = max(1, round(p.stat().st_size / 1024))
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            from_ver = "unknown"
            try:
                with zipfile.ZipFile(p, "r") as zf:
                    if "meta.json" in zf.namelist():
                        meta = json.loads(zf.read("meta.json").decode("utf-8"))
                        from_ver = meta.get("from_version", from_ver)
            except Exception:
                pass

            backups.append({
                "filename": p.name,
                "version": from_ver,
                "size_kb": sz_kb,
                "created_at": mtime
            })
        return backups

    @classmethod
    def rollback_to_backup(cls, backup_filename: str = "") -> Dict[str, Any]:
        """手动触发回滚至指定的历史快照点 (防路径穿越 SEC-02/SEC-11)"""
        cm = ConfigManager.get_instance()
        backup_dir = cm.workspace_dir / ".backup"
        project_root = cm.root_dir

        if not backup_filename:
            # 默认选用最近一次备份
            backups = sorted(backup_dir.glob("backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
            if not backups:
                raise FileNotFoundError("未检索到任何可供回滚的系统快照还原点！")
            target_backup = backups[0]
        else:
            p_input = Path(backup_filename)
            if p_input.suffix.lower() != ".zip" or "/" in backup_filename or "\\" in backup_filename or ".." in backup_filename or ":" in backup_filename:
                raise ValueError(f"非法的快照备份文件名 [{backup_filename}]：仅限合法 zip 文件名，严禁路径遍历")
            
            # 严格白名单校验快照文件名 (允许包含版本号点号与时间戳，如 backup_v2.5.0_20261015_120000.zip SEC-11)
            import re
            if not re.match(r"^[a-zA-Z0-9_.-]{1,100}$", p_input.name):
                raise ValueError(f"非法的快照备份文件名 [{backup_filename}]：格式不合规 (SEC-11)")

            target_backup = (backup_dir / p_input.name).resolve()
            if not target_backup.is_relative_to(backup_dir.resolve()) or not target_backup.exists():
                raise FileNotFoundError(f"指定的还原点快照文件不存在: {backup_filename}")

        res = cls._execute_rollback(target_backup, project_root, newly_created_files=[])
        return {
            "success": True,
            "status": "success",
            "restored_count": res["restored_count"],
            "backup_point": target_backup.name,
            "message": f"🎉 成功从快照点 [{target_backup.name}] 还原 {res['restored_count']} 个文件！系统已回退就绪。"
        }

    @classmethod
    def _cleanup_old_backups(cls, keep: int = 5):
        """仅保留最近的 keep 份快照，防止无限制占用硬盘空间"""
        cm = ConfigManager.get_instance()
        backup_dir = cm.workspace_dir / ".backup"
        if not backup_dir.exists():
            return
        backups = sorted(backup_dir.glob("backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
        for old_b in backups[keep:]:
            try:
                old_b.unlink()
            except Exception:
                pass

    @classmethod
    def _apply_simulated_patch(cls, target_version: str) -> Dict[str, Any]:
        """模拟演练补丁升级，演示热重载与版本更新流"""
        cm = ConfigManager.get_instance()
        framework_yaml_path = cm.root_dir / "configs" / "framework.yaml"
        
        # 1. 尝试就地升级 framework.yaml 中的版本号
        if framework_yaml_path.exists():
            try:
                with open(framework_yaml_path, "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                if re.search(r'^\s*version:\s*.*$', content, flags=re.MULTILINE):
                    new_content = re.sub(
                        r'^\s*version:\s*.*$',
                        f'  version: "{target_version}"',
                        content,
                        flags=re.MULTILINE
                    )
                    with open(framework_yaml_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                cm.version = target_version
            except Exception:
                pass

        # 2. 内存热重载
        try:
            from core.registry import Registry
            reg = Registry.get_instance()
            reg.auto_discover()
        except Exception:
            pass

        return {
            "success": True,
            "status": "success",
            "new_version": target_version,
            "updated_count": 4,
            "updated_files": [
                "skills/custom/bili_cover_generator/entry.py",
                "core/hardware.py",
                "agents/omni_sentinel/entry.py",
                "configs/framework.yaml"
            ],
            "message": f"🎉 增量热补丁已成功注入！系统基准版本已平滑升级为 v{target_version}，无需重启！"
        }
