# -*- coding: utf-8 -*-
"""
core/workflow_market.py
【立体空间智能体系统 · 多智能体协作工作流市场与依赖补齐中枢 (Workflow Market Engine)】

职责：
1. 云端官方工作流目录加载与本地安装状态、版本比对；
2. 商业授权鉴权核验（未激活访客拦截，年度会员畅享装载）；
3. 拓扑依赖感知（智能体依赖缺失、技能依赖缺失状态实时计算）；
4. 工作流卡带 (.flow) 安全解包注入与 SHA-256 完整性核验；
5. 【亮点核心】一键批量自动补齐依赖 (install_dependencies)：串联智能体招募与技能装载；
6. 工作流卸载与安全归档。
"""

import io
import json
import shutil
import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import ConfigManager
from .market import parse_jwt_role, has_permission, OfficialMarketService
from .agent_market import AgentMarketService
from .registry import Registry
from .security import safe_extract_zip


CDN_WORKFLOW_CATALOG_URL = "https://cdn.litikj.com/capsules/workflow_catalog.json"
CDN_WORKFLOW_BACKUP_URL = "https://cdn.litikj.com/agent-os/capsules/workflow_catalog.json"


class WorkflowMarketService:
    """官方多智能体协作工作流市场与装载中枢"""

    @classmethod
    def load_workflow_catalog(cls, sync_remote: bool = True) -> List[Dict[str, Any]]:
        """
        加载官方工作流目录：
        1. 优先尝试从官方公网 CDN 同步最新清单，并热写入本地 configs/workflow_catalog.json 缓存；
        2. 离线/降级候选源：本地 configs/workflow_catalog.json > release/capsules/
        """
        cm = ConfigManager.get_instance()
        local_target = cm.root_dir / "configs" / "workflow_catalog.json"

        # 1. 优先尝试从云端 CDN 拉取最新上架目录
        if sync_remote and cm.gateway.mode == "cloud":
            from .agent_market import fetch_cdn_bytes
            for cdn_url in [CDN_WORKFLOW_CATALOG_URL, CDN_WORKFLOW_BACKUP_URL]:
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

        # 2. 离线/降级候选源
        candidates = [
            local_target,
            cm.root_dir / "release" / "capsules" / "workflow_catalog.json"
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
    def list_workflow_market(cls) -> List[Dict[str, Any]]:
        """获取工作流市场清单，比对已安装状态、依赖健康度与商业权限"""
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()

        user_role, user_role_name = parse_jwt_role(cm.gateway.license_key)
        catalog = cls.load_workflow_catalog()

        active_workflows = {w.name: w for w in reg.list_workflows()}
        active_agents = {a.name: a for a in reg.list_agents()}
        active_skills = {s.name: s for s in reg.list_skills()}

        market_list = []
        for item in catalog:
            wf_id = item["id"]
            is_installed = wf_id in active_workflows
            req_role = item.get("required_role", "annual")
            is_authorized = has_permission(user_role, req_role)
            req_role_name = item.get("role_name", "年度会员专享")

            # 依赖完整性计算
            deps = item.get("dependencies", {})
            req_agents = deps.get("agents", [])
            req_skills = deps.get("skills", [])

            missing_agents = [ag for ag in req_agents if ag not in active_agents]
            missing_skills = [sk for sk in req_skills if sk not in active_skills]
            is_deps_ready = (len(missing_agents) == 0 and len(missing_skills) == 0)

            wf_copy = dict(item)
            wf_copy["is_installed"] = is_installed
            wf_copy["installed"] = is_installed
            wf_copy["is_authorized"] = is_authorized
            wf_copy["user_role"] = user_role
            wf_copy["user_role_name"] = user_role_name
            wf_copy["required_role"] = req_role
            wf_copy["required_role_name"] = req_role_name
            wf_copy["missing_agents"] = missing_agents
            wf_copy["missing_skills"] = missing_skills
            wf_copy["is_deps_ready"] = is_deps_ready
            market_list.append(wf_copy)

        return market_list

    @classmethod
    def install_workflow(cls, workflow_id: str, force: bool = False) -> Dict[str, Any]:
        """一键鉴权安装工作流卡带，解包注入并即刻点亮协同调度台"""
        cm = ConfigManager.get_instance()
        reg = Registry.get_instance()

        catalog = cls.load_workflow_catalog()
        target_info = next((item for item in catalog if item["id"] == workflow_id), None)
        if not target_info:
            raise ValueError(f"未在工作流市场中找到指定流水线 [{workflow_id}]")

        # 1. 🛡️ 商业级前置权限核验
        user_role, user_role_name = parse_jwt_role(cm.gateway.license_key)
        req_role = target_info.get("required_role", "annual")
        req_role_name = target_info.get("role_name", "年度会员专享")

        if not has_permission(user_role, req_role) and not force:
            raise PermissionError(
                f"🔒 权限不足：多智能体接力协同工作流 [{target_info.get('name')}] 为【年度会员】专享权益！\n"
                f"您当前的系统身份为【{user_role_name}】。\n"
                f"请在【系统设置】中填入专属激活码升级为年度会员，即可一键装载所有商业协同流水线！"
            )

        # 2. 确定写入目录 workflows/{workflow_id}
        target_dir = cm.root_dir / "workflows" / workflow_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # 3. 定位卡带文件
        capsule_filename = target_info.get("capsule_filename", f"{workflow_id}_v{target_info.get('version', '1.0.0')}.flow")
        candidate_capsule = cm.root_dir / "release" / "capsules" / capsule_filename
        capsule_bytes: Optional[bytes] = None

        if candidate_capsule.exists():
            with open(candidate_capsule, "rb") as f:
                capsule_bytes = f.read()
            expected_sha = target_info.get("sha256", "")
            # 若本地卡带与远程哈希不一致，优先检查本地 release/capsules/ 自身元数据；若不匹配再尝试拉取远程
            if expected_sha and hashlib.sha256(capsule_bytes).hexdigest().lower() != expected_sha.lower():
                local_cat_path = cm.root_dir / "release" / "capsules" / "workflow_catalog.json"
                matched_local = False
                if local_cat_path.exists():
                    try:
                        with open(local_cat_path, "r", encoding="utf-8") as f:
                            loc_info = next((it for it in json.load(f) if it.get("id") == workflow_id), None)
                            if loc_info and loc_info.get("sha256", "").lower() == hashlib.sha256(capsule_bytes).hexdigest().lower():
                                matched_local = True
                    except Exception:
                        pass
                if not matched_local and target_info.get("download_url"):
                    try:
                        from .agent_market import fetch_cdn_bytes
                        auth_headers = {"Authorization": f"Bearer {cm.gateway.license_key}"} if cm.gateway.license_key else {}
                        downloaded = fetch_cdn_bytes(target_info["download_url"], timeout=20, headers=auth_headers)
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
                from .agent_market import fetch_cdn_bytes
                auth_headers = {"Authorization": f"Bearer {cm.gateway.license_key}"} if cm.gateway.license_key else {}
                downloaded = fetch_cdn_bytes(download_url, timeout=20, headers=auth_headers)
                if downloaded:
                    capsule_bytes = downloaded
                    candidate_capsule.parent.mkdir(parents=True, exist_ok=True)
                    with open(candidate_capsule, "wb") as f:
                        f.write(capsule_bytes)
            except Exception as e:
                print(f"[WorkflowMarket Warning] 从云端 CDN [{download_url}] 下载工作流卡带异常: {e}")

        if not capsule_bytes:
            raise FileNotFoundError(f"未在云端或本地归档中找到工作流卡带: {capsule_filename}")

        # 4. SHA-256 校验
        expected_sha = target_info.get("sha256", "")
        if expected_sha:
            actual_sha = hashlib.sha256(capsule_bytes).hexdigest().lower()
            if actual_sha != expected_sha.lower():
                raise ValueError("工作流卡带 SHA-256 校验不匹配，解包已终止")

        # 5. 安全沙盒解包 (防 Zip Slip SEC-02)
        safe_extract_zip(capsule_bytes, target_dir)

        # 6. 内存级热重载
        reg.auto_discover()

        return {
            "success": True,
            "status": "success",
            "workflow_id": workflow_id,
            "name": target_info["name"],
            "version": target_info.get("version", "1.0.0"),
            "path": str(target_dir.resolve()),
            "message": f"🎉 协同工作流 [{target_info['name']}] 已成功装载，流水线已就绪！"
        }

    @classmethod
    def install_workflow_dependencies(cls, workflow_id: str, force: bool = False) -> Dict[str, Any]:
        """【一键补齐依赖】全自动智能下载并装载该工作流所需的缺失智能体与技能"""
        catalog = cls.load_workflow_catalog()
        target_info = next((item for item in catalog if item["id"] == workflow_id), None)
        if not target_info:
            raise ValueError(f"未在工作流市场中找到指定流水线 [{workflow_id}]")

        deps = target_info.get("dependencies", {})
        req_agents = deps.get("agents", [])
        req_skills = deps.get("skills", [])

        reg = Registry.get_instance()
        active_agents = {a.name: a for a in reg.list_agents()}
        active_skills = {s.name: s for s in reg.list_skills()}

        installed_agents = []
        installed_skills = []

        # 1. 批量自动补齐智能体
        for ag in req_agents:
            if ag not in active_agents:
                try:
                    res = AgentMarketService.recruit_agent(ag, force=force)
                    if res.get("success"):
                        installed_agents.append(ag)
                except Exception as e:
                    print(f"[WorkflowMarket Warning] 自动招募依赖智能体 [{ag}] 异常: {e}")

        # 2. 批量自动补齐技能
        for sk in req_skills:
            if sk not in active_skills:
                try:
                    res = OfficialMarketService.install_official_skill(sk, force=force)
                    if res.get("success"):
                        installed_skills.append(sk)
                except Exception as e:
                    print(f"[WorkflowMarket Warning] 自动安装依赖技能 [{sk}] 异常: {e}")

        # 3. 动态热重载
        reg.auto_discover()

        return {
            "success": True,
            "status": "success",
            "workflow_id": workflow_id,
            "installed_agents": installed_agents,
            "installed_skills": installed_skills,
            "message": f"已成功补齐 {len(installed_agents)} 个员工与 {len(installed_skills)} 个技能依赖！"
        }

    @classmethod
    def uninstall_workflow(cls, workflow_id: str) -> Dict[str, Any]:
        """安全卸载工作流 (SEC-11)"""
        from .security import validate_safe_id, validate_safe_id_and_resolve_dir
        clean_id = validate_safe_id(workflow_id, "工作流")

        if clean_id == "system_health_audit":
            raise PermissionError("严禁卸载系统官方基准协同流水线 (system_health_audit)")

        cm = ConfigManager.get_instance()
        workflows_parent = cm.root_dir / "workflows"
        target_dir = validate_safe_id_and_resolve_dir(clean_id, workflows_parent, "工作流", must_exist=False)

        if not target_dir.exists():
            # 尝试单文件脚本形式
            single_script = workflows_parent / f"{clean_id}.py"
            if single_script.exists():
                single_script.unlink()
            else:
                raise FileNotFoundError(f"本地未找到工作流 [{clean_id}] 的物理代码")
        else:
            shutil.rmtree(target_dir, ignore_errors=True)

        reg = Registry.get_instance()
        reg.unregister_workflow(clean_id)
        reg.auto_discover()

        return {
            "success": True,
            "status": "success",
            "workflow_id": workflow_id,
            "message": f"协同工作流 [{workflow_id}] 已从本地安全卸载"
        }
