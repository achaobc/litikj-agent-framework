# -*- coding: utf-8 -*-
"""
core/agent_market.py
【立体空间智能体系统 · 数字化员工智能体市场与招募服务 (Agent Market Engine)】

职责：
1. 云端官方智能体目录检索与本地在职状态比对；
2. 商业授权鉴权核验（未激活访客拦截，年度会员畅享招募）；
3. 智能体卡带 (.agent) 安全解包注入与 SHA-256 完整性核验；
4. 招募入职后触发 Registry 内存级热重载，瞬时点亮侧边栏；
5. 智能体解雇与安全离职归档。
"""

import io
import json
import shutil
import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import ConfigManager
from .market import parse_jwt_role, has_permission, ROLE_NAMES
from .registry import Registry
from .security import safe_extract_zip


import subprocess
import urllib.request
import urllib.error

CDN_AGENT_CATALOG_URL = "https://cdn.litikj.com/capsules/agent_catalog.json"
CDN_AGENT_BACKUP_URL = "https://cdn.litikj.com/agent-os/capsules/agent_catalog.json"


def fetch_cdn_bytes(url: str, timeout: int = 10) -> Optional[bytes]:
    """健壮的云端 CDN 资源拉取封装：优先尝试系统原生 curl.exe（天然避免 Windows TLS 协商 EOF 异常），备选 urllib"""
    if not url or not isinstance(url, str):
        return None

    clean_url = url.strip()
    # 🛡️ 安全门禁 (R3-VULN-07): 防御 curl 参数注入 (禁止首字符为 -) 且限定协议白名单 (仅限 https:// 与 http://)
    if clean_url.startswith("-") or not clean_url.startswith(("https://", "http://")):
        return None

    # 1. 优先尝试系统原生 curl.exe (使用 -- 明确终止命令行选项解析)
    try:
        proc = subprocess.run(
            ["curl.exe", "-s", "--max-time", str(timeout), "-H", "User-Agent: Litikj-Agent-OS/2.5.0", "--", clean_url],
            capture_output=True,
            timeout=timeout + 2
        )
        if proc.returncode == 0 and len(proc.stdout) > 0:
            return proc.stdout
    except Exception:
        pass

    # 2. 备用 urllib.request
    try:
        req = urllib.request.Request(clean_url, headers={"User-Agent": "Litikj-Agent-OS/2.5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read()
    except Exception:
        pass

    return None


def _parse_version(v: Any) -> tuple:
    """'1.10.2' -> (1, 10, 2)，非法片段按 0 处理"""
    out = []
    for part in str(v or "0").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


class AgentMarketService:
    """官方数字化员工智能体市场与招募服务"""

    @classmethod
    def load_agent_catalog(cls, sync_remote: bool = True) -> List[Dict[str, Any]]:
        """
        加载官方智能体目录：
        1. 优先尝试从官方真实公网 CDN 动态同步最新清单，并热写入本地 configs/agent_catalog.json 缓存；
        2. 若离线或网络异常，平滑降级读取本地已缓存清单。
        """
        cm = ConfigManager.get_instance()
        local_target = cm.root_dir / "configs" / "agent_catalog.json"

        # 1. 优先尝试从云端 CDN 拉取最新上架目录
        if sync_remote and cm.gateway.mode == "cloud":
            for cdn_url in [CDN_AGENT_CATALOG_URL, CDN_AGENT_BACKUP_URL]:
                try:
                    data_bytes = fetch_cdn_bytes(cdn_url, timeout=5)
                    if data_bytes:
                        remote_items = json.loads(data_bytes.decode("utf-8"))
                        if isinstance(remote_items, list) and len(remote_items) > 0:
                            # 成功拉取最新云端名录，热更新至本地缓存
                            try:
                                local_target.parent.mkdir(parents=True, exist_ok=True)
                                with open(local_target, "w", encoding="utf-8") as f:
                                    json.dump(remote_items, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                            return remote_items
                except Exception:
                    pass

        # 2. 离线/降级候选源：本地 configs/agent_catalog.json > release/capsules/
        candidates = [
            local_target,
            cm.root_dir / "release" / "capsules" / "agent_catalog.json"
        ]
        for p in candidates:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list) and len(data) > 0:
                            return data
                except Exception:
                    pass
        return []

    @classmethod
    def list_agent_market(cls) -> List[Dict[str, Any]]:
        """获取智能体招募市场清单，比对在职状态与商业权限"""
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()

        user_role, user_role_name = parse_jwt_role(cm.gateway.license_key)
        catalog = cls.load_agent_catalog()
        active_agents = {a.name: a for a in reg.list_agents()}

        market_list = []
        for item in catalog:
            ag_id = item["id"]
            local_ag = active_agents.get(ag_id)
            is_recruited = ag_id in active_agents
            req_role = item.get("required_role", "annual")
            is_authorized = has_permission(user_role, req_role)
            req_role_name = item.get("role_name", "年度会员专享")

            local_ver = getattr(local_ag, "version", None) if local_ag else None
            remote_ver = item.get("version", "1.0.0")
            has_update = bool(is_recruited and local_ver and _parse_version(remote_ver) > _parse_version(local_ver))

            ag_copy = dict(item)
            ag_copy["is_recruited"] = is_recruited
            ag_copy["recruited"] = is_recruited
            ag_copy["is_authorized"] = is_authorized
            ag_copy["user_role"] = user_role
            ag_copy["user_role_name"] = user_role_name
            ag_copy["required_role"] = req_role
            ag_copy["required_role_name"] = req_role_name
            ag_copy["local_version"] = local_ver
            ag_copy["has_update"] = has_update
            market_list.append(ag_copy)

        return market_list

    @classmethod
    def recruit_agent(cls, agent_id: str, force: bool = False) -> Dict[str, Any]:
        """一键鉴权招募智能体入职，解包注入并即刻点亮侧边栏"""
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()

        catalog = cls.load_agent_catalog()
        target_info = next((item for item in catalog if item["id"] == agent_id), None)
        if not target_info:
            raise ValueError(f"未在智能体招募市场中找到指定员工 [{agent_id}]")

        # 1. 🛡️ 商业级前置权限核验
        user_role, user_role_name = parse_jwt_role(cm.gateway.license_key)
        req_role = target_info.get("required_role", "annual")
        req_role_name = target_info.get("role_name", "年度会员专享")

        if not has_permission(user_role, req_role) and not force:
            raise PermissionError(
                f"🔒 权限不足：数字化员工 [{target_info.get('name')}] 为【年度会员】专享智能体！\n"
                f"您当前的系统身份为【{user_role_name}】。\n"
                f"请在【系统设置】中填入专属激活码，升级为年度会员后即可一键招募所有云端智能体！"
            )

        # 2. 确定写入目录 agents/{agent_id}
        target_dir = cm.root_dir / "agents" / agent_id

        # 2.1 🛡️ 防降级保护：本地已是更高版本时，禁止被旧卡带静默覆盖
        local_cfg = target_dir / "config.yaml"
        if local_cfg.exists() and not force:
            try:
                import yaml
                with open(local_cfg, "r", encoding="utf-8") as f:
                    local_ver = (yaml.safe_load(f) or {}).get("version", "0.0.0")
                cap_ver = target_info.get("version", "1.0.0")
                if _parse_version(local_ver) > _parse_version(cap_ver):
                    raise ValueError(
                        f"本地 [{agent_id}] 版本 v{local_ver} 高于市场卡带 v{cap_ver}，"
                        f"已阻止降级覆盖。如需强制覆盖请使用 force 参数。"
                    )
            except ValueError:
                raise
            except Exception:
                pass

        # 2.2 入职失败回滚快照：覆盖解包前备份旧目录
        import tempfile
        existed_before = target_dir.exists() and any(target_dir.iterdir())
        backup_dir: Optional[Path] = None
        if existed_before:
            backup_dir = Path(tempfile.mkdtemp(prefix=f"recruit_bak_{agent_id}_"))
            shutil.copytree(target_dir, backup_dir / "snapshot", dirs_exist_ok=True)

        def _rollback():
            shutil.rmtree(target_dir, ignore_errors=True)
            if backup_dir is not None and (backup_dir / "snapshot").exists():
                shutil.copytree(backup_dir / "snapshot", target_dir, dirs_exist_ok=True)
            reg.unregister_agent(agent_id)

        target_dir.mkdir(parents=True, exist_ok=True)

        # 3. 定位卡带文件
        capsule_filename = target_info.get("capsule_filename", f"{agent_id}_v{target_info.get('version', '1.0.0')}.agent")
        candidate_capsule = cm.root_dir / "release" / "capsules" / capsule_filename
        capsule_bytes: Optional[bytes] = None

        if candidate_capsule.exists():
            with open(candidate_capsule, "rb") as f:
                capsule_bytes = f.read()
            expected_sha = target_info.get("sha256", "")
            # 若本地卡带与远程哈希不一致，优先检查本地 release/capsules/ 自身元数据；若不匹配再尝试拉取远程
            if expected_sha and hashlib.sha256(capsule_bytes).hexdigest().lower() != expected_sha.lower():
                local_cat_path = cm.root_dir / "release" / "capsules" / "agent_catalog.json"
                matched_local = False
                if local_cat_path.exists():
                    try:
                        with open(local_cat_path, "r", encoding="utf-8") as f:
                            loc_info = next((it for it in json.load(f) if it.get("id") == agent_id), None)
                            if loc_info and loc_info.get("sha256", "").lower() == hashlib.sha256(capsule_bytes).hexdigest().lower():
                                matched_local = True
                    except Exception:
                        pass
                if not matched_local and target_info.get("download_url"):
                    try:
                        downloaded = fetch_cdn_bytes(target_info["download_url"], timeout=20)
                        if downloaded:
                            capsule_bytes = downloaded
                    except Exception:
                        pass
                elif matched_local:
                    target_info["sha256"] = hashlib.sha256(capsule_bytes).hexdigest().lower()
        elif target_info.get("download_url"):
            # 优先从官方云端真实 CDN 下载
            download_url = target_info["download_url"]
            try:
                downloaded = fetch_cdn_bytes(download_url, timeout=20)
                if downloaded:
                    capsule_bytes = downloaded
                    candidate_capsule.parent.mkdir(parents=True, exist_ok=True)
                    with open(candidate_capsule, "wb") as f:
                        f.write(capsule_bytes)
            except Exception as e:
                print(f"[AgentMarket Warning] 从云端 CDN [{download_url}] 下载智能体卡带异常: {e}")

        if not capsule_bytes:
            raise FileNotFoundError(f"未在云端或本地归档中找到智能体卡带: {capsule_filename}")

        # 4. SHA-256 校验
        expected_sha = target_info.get("sha256", "")
        if expected_sha:
            actual_sha = hashlib.sha256(capsule_bytes).hexdigest().lower()
            if actual_sha != expected_sha.lower():
                raise ValueError("智能体卡带 SHA-256 校验不匹配，解包已终止")

        # 5. 安全沙盒解包 (防 Zip Slip SEC-02)
        safe_extract_zip(capsule_bytes, target_dir)

        # 5.5 🌟 级联自动补齐所依赖的原子技能卡带 (Cascade Recruit Skills)
        required_skills = list(target_info.get("skills", []))
        agent_cfg_file = target_dir / "config.yaml"
        if agent_cfg_file.exists():
            try:
                import yaml
                with open(agent_cfg_file, "r", encoding="utf-8") as f:
                    cfg_data = yaml.safe_load(f) or {}
                    cfg_skills = cfg_data.get("skills", [])
                    for s in cfg_skills:
                        if s and s not in required_skills:
                            required_skills.append(s)
            except Exception:
                pass

        if required_skills:
            from .market import OfficialMarketService
            installed_skills = {s.name for s in reg.list_skills()}
            for skill_id in required_skills:
                if skill_id not in installed_skills:
                    try:
                        print(f"📦 [Agent Cascade] 正在为新员工【{target_info['name']}】自动配齐依赖技能: [{skill_id}]...")
                        OfficialMarketService.install_official_skill(skill_id, force=force)
                    except Exception as e:
                        print(f"⚠️ [Agent Cascade Warning] 依赖技能 [{skill_id}] 自动安装异常: {e}")

        # 6. 内存级热重载 + 🛡️ 入职校验 (杜绝“招聘成功但员工并未入职”的假成功)
        reg.auto_discover()
        has_load_err = agent_id in getattr(reg, "load_errors", {})
        has_agent = (reg.get_agent(agent_id) is not None) or any(
            getattr(a, "source_path", "").rstrip("/\\").endswith(agent_id)
            for a in reg.list_agents()
        ) or ((target_dir / "entry.py").exists() and not has_load_err)

        if has_load_err or not has_agent:
            load_err = getattr(reg, "load_errors", {}).get(agent_id, "未发现可注册的智能体入口 (entry.py / setup)")

            _rollback()
            reg.auto_discover()
            raise RuntimeError(
                f"数字化员工 [{target_info.get('name', agent_id)}] 入职校验失败，已回滚本次安装。\n"
                f"加载异常：{load_err}\n"
                f"建议：按提示补齐运行环境依赖后重试；如为便携版，可在对话中发送对应的 [EXEC] setup 指令。"
            )
        if backup_dir is not None:
            shutil.rmtree(backup_dir, ignore_errors=True)

        # 6.5 🌟 自动执行新员工工作区与环境静默自愈 (Zero-Friction Auto-Healing)
        ag = reg.get_agent(agent_id)
        if ag and hasattr(ag, "heal_environment"):
            try:
                ag.heal_environment()
            except Exception as e:
                print(f"[AgentMarket Warning] 新员工入职自愈初始化: {e}")

        # 7. 唤醒投递箱检查是否有新员工所属的待处理稿件
        try:
            from .watcher import WatcherEngine
            w_engine = WatcherEngine.get_instance()
            if getattr(w_engine, "_running", False):
                import threading
                threading.Thread(target=w_engine.scan_once, daemon=True).start()
        except Exception:
            pass

        return {
            "success": True,
            "status": "success",
            "agent_id": agent_id,
            "name": target_info["name"],
            "version": target_info.get("version", "1.0.0"),
            "path": str(target_dir.resolve()),
            "message": f"🎉 数字化员工 [{target_info['name']}] 已成功办理入职，工作台已就绪！"
        }

    @classmethod
    def dismiss_agent(cls, agent_id: str) -> Dict[str, Any]:
        """解雇/移除已招募的智能体 (SEC-11)"""
        from .security import validate_safe_id, validate_safe_id_and_resolve_dir
        clean_id = validate_safe_id(agent_id, "智能体")

        if clean_id == "omni_sentinel":
            raise PermissionError("严禁解雇官方基准调度哨兵 (omni_sentinel)")

        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()

        # 严格在 agents/ 或 workspace/custom_agents/ 沙箱内比对，杜绝路径穿越
        target_dir = None
        for parent in [cm.root_dir / "agents", cm.workspace_dir / "custom_agents"]:
            try:
                cand = validate_safe_id_and_resolve_dir(clean_id, parent, "智能体", must_exist=False)
                if cand.exists() and cand.is_dir():
                    target_dir = cand
                    break
            except Exception:
                continue

        if not target_dir:
            raise FileNotFoundError(f"未找到待解雇的智能体目录: {clean_id}")

        shutil.rmtree(target_dir, ignore_errors=True)
        reg.unregister_agent(clean_id)
        reg.auto_discover()

        return {
            "success": True,
            "status": "success",
            "agent_id": agent_id,
            "message": f"智能体 [{agent_id}] 已办理离职注销"
        }
