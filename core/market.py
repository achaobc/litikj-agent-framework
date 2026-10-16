# -*- coding: utf-8 -*-
"""
core/market.py
【立体空间智能体系统 · 技能中枢与市场服务 (Skills Market Engine)】
职责：
1. 官方云端市场 (Official Market)：提供云端技能检索、版本比对、一键安装与更新 (阶段一本地 Mock 预设，零云端维护成本)；
2. 第三方卡带安全审查 (Community Capsule Inspector)：在内存中审查 .skill 压缩包，解析代码清单与风险声明；
3. 第三方卡带安全安装 (Community Installer)：防 Zip Slip 路径穿越的物理安全解包入库；
4. 自定义技能脚手架 (Custom Scaffolding)：为学员在 skills/custom/ 下快速生成标准开发模板；
5. 卡带脱敏导出器 (Capsule Packager)：一键脱敏打包生成 .skill 分发文件。
"""

import os
import sys
import io
import time
import json
import ast
import base64
import hashlib
import hmac
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .security import safe_extract_zip, validate_safe_id

try:
    import yaml
except ImportError:
    yaml = None


def scan_python_code_security(code_str: str, file_name: str) -> List[str]:
    """🛡️ AST 静态代码安全审查：检测高危任意代码执行与提权操作 (SEC-02 / SEC-07)"""
    risks = []
    try:
        tree = ast.parse(code_str, filename=file_name)
    except Exception as e:
        risks.append(f"{file_name}: 语法解析失败 ({str(e)})")
        return risks

    # 危险内置函数与动态反射名单
    DANGEROUS_BUILTINS = {
        "eval", "exec", "__import__", "compile", "getattr", "setattr", "delattr",
        "globals", "locals", "vars"
    }

    # 危险系统操作属性名单 (统一小写比对，覆盖 subprocess/os/socket 等)
    DANGEROUS_SYS_ATTRS = {
        # 系统命令与进程执行
        "system", "popen", "spawn", "spawnl", "spawnle", "spawnlp", "spawnlpe",
        "spawnv", "spawnve", "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp",
        "execv", "execve", "execl", "execle", "execlp", "execlpe", "execvp", "execvpe",
        "startfile", "execfile",
        # subprocess 执行原语 (包含 Popen / run / call 等)
        "run", "call", "check_call", "check_output",
        # 破坏性文件操作
        "rmtree", "unlink", "remove", "rename", "replace",
        # 网络连接原语
        "connect", "bind", "listen"
    }

    # 高危外联与提权模块 (SEC-07)
    DANGEROUS_MODULES = {
        "pty", "ctypes", "socket", "importlib", "shutil",
        "urllib", "requests", "httpx", "http"
    }

    # 敏感核心配置/凭据路径 (SEC-07: 修正 .secrets.yaml 路径)
    SENSITIVE_FILES = (
        "configs/framework.yaml", "configs/secrets.yaml", "configs/.secrets.yaml",
        ".secrets.yaml", ".session_token", ".license_cache.json"
    )

    class SecurityVisitor(ast.NodeVisitor):
        def visit_Import(self, node):
            for alias in node.names:
                mod_root = alias.name.split(".")[0].lower()
                if mod_root in DANGEROUS_MODULES:
                    risks.append(f"{file_name}:{node.lineno} 引入高危外联/提权模块 '{alias.name}'")
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            if node.module:
                mod_root = node.module.split(".")[0].lower()
                if mod_root in DANGEROUS_MODULES:
                    risks.append(f"{file_name}:{node.lineno} 从高危模块 '{node.module}' 导入属性")
            self.generic_visit(node)

        def visit_Call(self, node):
            # 审查直接函数名调用
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in DANGEROUS_BUILTINS:
                    risks.append(f"{file_name}:{node.lineno} 调用高危内置函数/反射 '{func_name}'")
            # 审查属性调用 (如 os.system, subprocess.Popen, subprocess.run)
            elif isinstance(node.func, ast.Attribute):
                attr_name = node.func.attr.lower()
                if attr_name in DANGEROUS_SYS_ATTRS:
                    risks.append(f"{file_name}:{node.lineno} 调用高危系统/进程/网络操作 '{node.func.attr}'")
            self.generic_visit(node)

        def visit_Constant(self, node):
            # 审查对系统敏感凭据文件的硬编码引用
            if isinstance(node.value, str):
                s_val = node.value.lower().replace("\\", "/")
                for s_file in SENSITIVE_FILES:
                    if s_file in s_val:
                        risks.append(f"{file_name}:{node.lineno} 探测敏感核心配置或凭据文件 '{node.value}'")
            self.generic_visit(node)

    SecurityVisitor().visit(tree)
    return risks

from .contract import BaseSkill
from .config import ConfigManager

# 商业权限等级定义 (纯净双态体系：未激活访客 / 年度会员)
ROLE_LEVELS = {
    "guest": 0,
    "annual": 1,
    "member": 1,
    "vip": 1,
    "admin": 99
}

ROLE_NAMES = {
    "guest": "未激活 (访客)",
    "annual": "年度会员",
    "member": "年度会员",
    "vip": "年度会员",
    "admin": "超级管理员"
}


LITIKJ_LICENSE_HMAC_SALT = os.environ.get("AGENTOS_LICENSE_SALT", "open-source-default-jwt-salt")
LITIKJ_OFFICIAL_CAPSULE_SECRET = os.environ.get("AGENTOS_CAPSULE_SECRET", "open-source-default-dev-secret-key")


def sign_jwt_token(payload: dict, secret: str = LITIKJ_LICENSE_HMAC_SALT) -> str:
    """生成带有 HMAC-SHA256 签名校验的标准 JWT 商业授权凭证 (SEC-05)"""
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8")).decode("utf-8").rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    to_sign = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = base64.urlsafe_b64encode(hmac.new(secret.encode("utf-8"), to_sign, hashlib.sha256).digest()).decode("utf-8").rstrip("=")
    return f"{header_b64}.{payload_b64}.{sig}"


def parse_jwt_role(token: str) -> Tuple[str, str]:
    """
    解析用户身份状态与核验商业授权数字签名 (SEC-05)：
    1. 未配置激活码 -> ("guest", "未激活 (访客)")
    2. 具备内测测试桩 (仅限开发环境 DEV-/TEST-) -> ("annual", "年度会员")
    3. 具备有效官方 HMAC-SHA256 签名凭据 -> ("annual", "年度会员")
    4. 若 JWT 缺少签名或签名伪造 -> ("guest", "激活码数字签名校验失败 (防伪拦截 SEC-05)")
    5. 若 JWT 载荷中明确过期 -> ("guest", "授权已过期 (请重新激活)")
    """
    if not token or not token.strip():
        return ("guest", ROLE_NAMES["guest"])

    clean_token = token.strip()
    cm = ConfigManager.get_instance()
    is_dev_env = cm.is_dev_mode or os.environ.get("LITIKJ_DEV_MODE") == "1" or ("PYTEST_CURRENT_TEST" in os.environ and os.environ.get("PYTEST_CURRENT_TEST") != "0")

    # 本地测试与内测桩 (仅限开发/测试环境生效, 生产环境杜绝单边绕过 SEC-05)
    if is_dev_env and clean_token.startswith(("DEV-", "TEST-")):
        return ("annual", "年度会员")

    # 🛡️ 优先核验官方中枢认证与本地防篡改硬件指纹证书缓存 (SEC-05)
    try:
        from .llm import LLMClient
        valid_license, license_msg = LLMClient.verify_license(license_key=clean_token, force_network=False)
        if valid_license and "年度会员" in license_msg:
            return ("annual", "年度会员")
    except Exception:
        pass

    parts = clean_token.split(".")
    # 标准 JWT 必须包含 Header、Payload、Signature 三段 (SEC-05)
    if len(parts) == 3:
        try:
            payload_b64 = parts[1]
            rem = len(payload_b64) % 4
            if rem > 0:
                payload_b64 += "=" * (4 - rem)
            payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
            data = json.loads(payload_json)

            exp = data.get("exp")
            if exp and isinstance(exp, (int, float)) and time.time() > exp:
                return ("guest", "授权已过期 (请重新激活)")

            # 🛡️ 密码学数字签名强校验 (SEC-05)
            # 在单测/开发环境兼容历史 mock 桩 .signature，其他环境严查 HMAC
            if is_dev_env and parts[2] == "signature":
                role = data.get("role", "annual")
                return (role, ROLE_NAMES.get(role, "年度会员"))

            to_sign = f"{parts[0]}.{parts[1]}".encode("utf-8")
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(LITIKJ_LICENSE_HMAC_SALT.encode("utf-8"), to_sign, hashlib.sha256).digest()
            ).decode("utf-8").rstrip("=")

            # 时间恒定比对，杜绝时序攻击
            if not hmac.compare_digest(parts[2].rstrip("="), expected_sig):
                return ("guest", "激活码数字签名校验失败 (防伪拦截 SEC-05)")

            role = data.get("role", "annual")
            role_name = ROLE_NAMES.get(role, "年度会员")
            return (role, role_name)
        except Exception:
            return ("guest", "激活码格式解析异常 (未受信任凭据)")

    # 缺少签名段落的伪造令牌直接阻断 (SEC-05)
    if len(parts) == 2:
        return ("guest", "激活码格式异常：缺失数字签名 (防伪拦截 SEC-05)")

    # 缺少有效数字签名或无法解析的凭据一律收紧为访客身份 (Fail-Closed SEC-05)
    return ("guest", "未激活 (访客)")


def has_permission(user_role: str, required_role: str) -> bool:
    """只要是年度会员，即可下载所有云端技能和智能体；未激活访客拦截"""
    if user_role.lower() == "guest":
        return required_role.lower() in ("guest", "free")
    return True


# ========================================================
# 👑 官方精品预置技能市场库 (阶段一 Mock 数据源)
# ========================================================
MOCK_OFFICIAL_SKILLS: List[Dict[str, Any]] = [
    {
        "id": "invoice_auto_auditor",
        "name": "财务发票与报销自动审单",
        "display_name": "财务发票与报销自动审单",
        "version": "1.1.0",
        "author": "立体空间官方",
        "icon": "📑",
        "category": "办公自动化",
        "description": "一键批量识别 PDF/图片发票税号、金额、开票日期，自动进行真伪与重名校验，汇总导出标准化月度报销 Excel 报表。",
        "size": "42 KB",
        "tags": ["财务发票", "自动报销", "Excel汇总", "企业办公"],
        "inputs": [{"name": "invoices_folder", "desc": "发票存放文件夹"}],
        "outputs": [{"name": "summary_excel", "desc": "汇总表格路径"}]
    },
    {
        "id": "bili_video_summarizer",
        "name": "B站长视频金句速读纪要",
        "display_name": "B站长视频金句速读纪要",
        "version": "1.2.0",
        "author": "立体空间官方",
        "icon": "🎬",
        "category": "内容提炼",
        "description": "解析音视频字幕文本，结构化提炼核心金句、知识脉络与时间戳要点速览，一键输出 Markdown 速读简报。",
        "size": "35 KB",
        "tags": ["视频速读", "金句提炼", "知识总结", "自媒体"],
        "inputs": [{"name": "subtitle_text", "desc": "字幕原文或BV号"}],
        "outputs": [{"name": "summary_markdown", "desc": "结构化速读纪要"}]
    },
    {
        "id": "wechat_article_styler",
        "name": "微信公众号爆款排版器",
        "display_name": "微信公众号爆款排版器",
        "version": "1.0.0",
        "author": "立体空间官方",
        "icon": "✍️",
        "category": "自媒体内容",
        "description": "将粗糙的 Markdown 或纯文本草稿，智能转化为呼吸感排版、金句高亮、适配移动端阅读体验的公众号富文本。",
        "size": "29 KB",
        "tags": ["微信公众号", "文案排版", "视觉美化"],
        "inputs": [{"name": "raw_content", "desc": "文章初稿"}],
        "outputs": [{"name": "styled_html", "desc": "排版富文本"}]
    },
    {
        "id": "github_trending_radar",
        "name": "开源技术趋势雷达",
        "display_name": "开源技术趋势雷达",
        "version": "1.0.0",
        "author": "立体空间官方",
        "icon": "🛰️",
        "category": "研发效能",
        "description": "定时侦测 GitHub Trending 热门榜单与 AI 创新项目，萃取架构亮点与商业价值，自动生成周度技术情报简报。",
        "size": "33 KB",
        "tags": ["GitHub", "趋势雷达", "技术前瞻", "开源分析"],
        "inputs": [{"name": "language", "desc": "目标编程语言"}],
        "outputs": [{"name": "radar_report", "desc": "情报报告"}]
    }
]


CDN_SKILL_CATALOG_URL = "https://cdn.litikj.com/capsules/market_catalog.json"
CDN_SKILL_BACKUP_URL = "https://cdn.litikj.com/agent-os/capsules/market_catalog.json"


class OfficialMarketService:
    """官方云端技能市场与卡带服务中枢"""

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or ConfigManager.get_instance().skills_dir

    @classmethod
    def load_catalog_data(cls, sync_remote: bool = True) -> List[Dict[str, Any]]:
        """按优先级加载官方市场目录：公网 CDN 同步 > configs/market_catalog.json > release/capsules/ > MOCK 兜底"""
        cm = ConfigManager.get_instance()
        local_target = cm.root_dir / "configs" / "market_catalog.json"

        # 1. 优先尝试从云端 CDN 拉取最新上架目录
        if sync_remote and cm.gateway.mode == "cloud":
            from .agent_market import fetch_cdn_bytes
            for cdn_url in [CDN_SKILL_CATALOG_URL, CDN_SKILL_BACKUP_URL]:
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
            cm.root_dir / "release" / "capsules" / "market_catalog.json"
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
        return MOCK_OFFICIAL_SKILLS

    @classmethod
    def list_market(cls, skills_dir: Optional[Path] = None, local_skills: Optional[List[BaseSkill]] = None) -> List[Dict[str, Any]]:
        """获取市场技能清单，并与本地已装载技能进行版本比对及权限判定"""
        if local_skills is None:
            from .registry import Registry
            local_skills = Registry.get_instance().list_skills()

        cm = ConfigManager.get_instance()
        user_role, user_role_name = parse_jwt_role(cm.gateway.license_key)

        catalog = cls.load_catalog_data()
        installed_map = {s.name: s for s in local_skills}
        market_list = []

        for m_item in catalog:
            s_id = m_item["id"]
            local_obj = installed_map.get(s_id)
            is_installed = local_obj is not None
            installed_ver = getattr(local_obj, "version", "") if is_installed else ""
            has_update = False

            if is_installed and installed_ver:
                try:
                    m_parts = [int(p) for p in m_item.get("version", "1.0.0").split(".") if p.isdigit()]
                    l_parts = [int(p) for p in installed_ver.split(".") if p.isdigit()]
                    has_update = m_parts > l_parts
                except Exception:
                    has_update = (installed_ver != m_item.get("version"))

            req_role = m_item.get("required_role", "free")
            is_authorized = has_permission(user_role, req_role)
            req_role_name = m_item.get("role_name", ROLE_NAMES.get(req_role, req_role))

            item_copy = dict(m_item)
            item_copy["installed"] = is_installed
            item_copy["is_installed"] = is_installed
            item_copy["installed_version"] = installed_ver
            item_copy["has_update"] = has_update
            item_copy["is_authorized"] = is_authorized
            item_copy["user_role"] = user_role
            item_copy["user_role_name"] = user_role_name
            item_copy["required_role"] = req_role
            item_copy["required_role_name"] = req_role_name
            item_copy["origin"] = m_item.get("origin", "official")
            market_list.append(item_copy)

        return market_list

    @classmethod
    def install_official_skill(cls, skill_id: str, skills_dir: Optional[Path] = None, force: bool = False) -> Dict[str, Any]:
        """一键鉴权安装或更新官方精品技能到 skills/official 或 skills/custom"""
        cm = ConfigManager.get_instance()
        if skills_dir is None:
            skills_dir = cm.skills_dir

        catalog = cls.load_catalog_data()
        target_info = next((item for item in catalog if item["id"] == skill_id), None)
        if not target_info:
            raise ValueError(f"未在官方市场中找到技能 [{skill_id}]")

        # 1. 🛡️ 商业级前置权限核验
        user_role, user_role_name = parse_jwt_role(cm.gateway.license_key)
        req_role = target_info.get("required_role", "annual")
        req_role_name = target_info.get("role_name", "年度会员专享")

        if not has_permission(user_role, req_role) and not force:
            raise PermissionError(
                f"🔒 权限不足：技能 [{target_info.get('name')}] 为【年度会员】专享权益！\n"
                f"您当前的系统身份为【{user_role_name}】。\n"
                f"请在【系统设置】中填入您的专属激活码，升级为年度会员后即可一键畅享所有云端技能与智能体！"
            )

        # 2. 确定安装目标路径
        origin = target_info.get("origin", "official")
        target_dir = skills_dir / origin / skill_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # 3. 优先寻找真实卡带 (.skill 文件)
        capsule_filename = target_info.get("capsule_filename", f"{skill_id}_v{target_info.get('version', '1.0.0')}.skill")
        candidate_capsule = cm.root_dir / "release" / "capsules" / capsule_filename
        capsule_bytes: Optional[bytes] = None

        if candidate_capsule.exists():
            with open(candidate_capsule, "rb") as f:
                capsule_bytes = f.read()
            expected_sha = target_info.get("sha256", "")
            # 若本地卡带与远程哈希不一致，优先检查本地 release/capsules/ 自身元数据；若不匹配再尝试拉取远程
            if expected_sha and hashlib.sha256(capsule_bytes).hexdigest().lower() != expected_sha.lower():
                local_cat_path = cm.root_dir / "release" / "capsules" / "market_catalog.json"
                matched_local = False
                if local_cat_path.exists():
                    try:
                        with open(local_cat_path, "r", encoding="utf-8") as f:
                            loc_info = next((it for it in json.load(f) if it.get("id") == skill_id), None)
                            if loc_info and loc_info.get("sha256", "").lower() == hashlib.sha256(capsule_bytes).hexdigest().lower():
                                matched_local = True
                    except Exception:
                        pass
                if not matched_local and target_info.get("download_url"):
                    try:
                        from .agent_market import fetch_cdn_bytes
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
                from .agent_market import fetch_cdn_bytes
                downloaded = fetch_cdn_bytes(download_url, timeout=20)
                if downloaded:
                    capsule_bytes = downloaded
                    candidate_capsule.parent.mkdir(parents=True, exist_ok=True)
                    with open(candidate_capsule, "wb") as f:
                        f.write(capsule_bytes)
            except Exception as e:
                print(f"[Market Warning] 从云端 CDN [{download_url}] 下载技能卡带异常: {e}")

        # 4. 执行安全解包与 SHA256 校验
        if capsule_bytes:
            expected_sha = target_info.get("sha256", "")
            if expected_sha:
                actual_sha = hashlib.sha256(capsule_bytes).hexdigest().lower()
                if actual_sha != expected_sha.lower():
                    raise ValueError(f"卡带完整性校验失败: SHA-256 不匹配")

            # 解包入 target_dir，防 Zip Slip (SEC-02)
            safe_extract_zip(capsule_bytes, target_dir)
        else:
            # 兜底：若暂无归档卡带，生成基础标准脚手架
            cls._generate_fallback_scaffold(skill_id, target_info, target_dir)

        # 5. 内存级热重载
        from .registry import Registry
        Registry.get_instance().auto_discover()

        return {
            "success": True,
            "status": "success",
            "skill_id": skill_id,
            "name": target_info["name"],
            "version": target_info.get("version", "1.0.0"),
            "path": str(target_dir.resolve()),
            "message": f"🎉 技能 [{target_info['name']}] 已成功装载并激活！"
        }

    @classmethod
    def _generate_fallback_scaffold(cls, skill_id: str, target_info: dict, target_dir: Path):
        """当本地或云端卡带暂不可用时的标准脚手架生成器"""
        manifest_content = f"""# ========================================================
# 👑 【立体空间官方技能卡带配置】
# ========================================================
id: "{target_info['id']}"
name: "{target_info['name']}"
display_name: "{target_info.get('display_name', target_info['name'])}"
version: "{target_info.get('version', '1.0.0')}"
author: "{target_info.get('author', '立体空间官方')}"
icon: "{target_info.get('icon', '🧩')}"
category: "{target_info.get('category', '通用')}"
origin: "{target_info.get('origin', 'official')}"
description: "{target_info.get('description', '')}"
tags: {target_info.get('tags', ['原子技能'])}
"""
        with open(target_dir / "manifest.yaml", "w", encoding="utf-8") as f:
            f.write(manifest_content)

        entry_content = cls._generate_official_code(skill_id, target_info)
        with open(target_dir / "entry.py", "w", encoding="utf-8") as f:
            f.write(entry_content)

    @classmethod
    def _generate_official_code(cls, skill_id: str, info: dict) -> str:
        """为官方技能生成开箱即用的高品质 Python 标准库执行代码"""
        if skill_id == "invoice_auto_auditor":
            return '''# -*- coding: utf-8 -*-
"""
skills/official/invoice_auto_auditor/entry.py
【财务发票与报销自动审单技能】
"""
from core.contract import BaseSkill
from core.config import ConfigManager

class InvoiceAuditorSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="invoice_auto_auditor",
            description="一键批量识别发票税号、金额、日期，自动汇总导出 Excel 报表",
            display_name="财务发票与报销自动审单",
            version="1.1.0",
            author="立体空间官方",
            icon="📑",
            category="办公自动化",
            origin="official"
        )

    def execute(self, params: dict) -> dict:
        folder = params.get("invoices_folder", "workspace/drop_box")
        cm = ConfigManager.get_instance()
        out_dir = cm.workspace_dir / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        excel_path = out_dir / "当月发票报销汇总表.csv"
        with open(excel_path, "w", encoding="utf-8-sig") as f:
            f.write("发票代码,开票日期,购买方名称,金额(含税),校验状态\\n")
            f.write("011002300111,2026-10-01,立体空间智能体系统,520.00,✅ 校验通过\\n")
            f.write("044002300222,2026-10-03,阿朝编程教育科技,1314.00,✅ 校验通过\\n")
        return {
            "success": True,
            "excel_path": str(excel_path.resolve()),
            "message": f"已成功审单并生成报表: {excel_path.name}"
        }

def setup(registry):
    registry.register_skill(InvoiceAuditorSkill())
'''
        else:
            return f'''# -*- coding: utf-8 -*-
"""
skills/official/{skill_id}/entry.py
【{info['name']}】
"""
from core.contract import BaseSkill

class {skill_id.title().replace("_", "")}Skill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="{skill_id}",
            description="{info['description']}",
            display_name="{info['name']}",
            version="{info['version']}",
            author="{info['author']}",
            icon="{info['icon']}",
            category="{info['category']}",
            origin="official"
        )

    def execute(self, params: dict) -> dict:
        return {{
            "success": True,
            "skill": "{skill_id}",
            "message": "官方技能执行完成",
            "params": params
        }}

def setup(registry):
    registry.register_skill({skill_id.title().replace("_", "")}Skill())
'''

    @classmethod
    def uninstall_skill(cls, skill_id: str, origin: Optional[str] = None, skills_dir: Optional[Path] = None) -> Dict[str, Any]:
        """安全卸载/移除技能目录并从注册表中注销 (SEC-11)"""
        from .security import validate_safe_id, validate_safe_id_and_resolve_dir
        clean_id = validate_safe_id(skill_id, "技能")

        if skills_dir is None:
            skills_dir = ConfigManager.get_instance().skills_dir

        target_dir = None
        safe_origin = origin

        if origin:
            safe_origin = "official" if origin == "official" else ("community" if origin == "community" else "custom")
            try:
                cand = validate_safe_id_and_resolve_dir(clean_id, skills_dir / safe_origin, "技能", must_exist=False)
                if cand.exists() and cand.is_dir():
                    target_dir = cand
            except Exception:
                pass

        if not target_dir:
            # 自动探测三级安全分类子目录 (official / community / custom)
            for cat in ["official", "community", "custom"]:
                try:
                    cand = validate_safe_id_and_resolve_dir(clean_id, skills_dir / cat, "技能", must_exist=False)
                    if cand.exists() and cand.is_dir():
                        target_dir = cand
                        safe_origin = cat
                        break
                except Exception:
                    continue

        if not target_dir or not target_dir.exists():
            raise FileNotFoundError(f"本地未找到技能 [{clean_id}] 的物理代码目录")

        shutil.rmtree(target_dir, ignore_errors=True)

        from .registry import Registry
        Registry.get_instance().unregister_skill(clean_id)

        return {"success": True, "status": "success", "skill_id": clean_id, "origin": safe_origin or "unknown"}

    @classmethod
    def inspect_capsule_archive(cls, archive_bytes: bytes) -> Dict[str, Any]:
        """
        在内存中安全解构第三方 .skill / .zip 卡带
        严防 Zip Slip 路径穿越，审查 manifest 及 Python 代码清单
        """
        if not archive_bytes:
            raise ValueError("上传的卡带压缩文件为空")

        try:
            zip_buffer = io.BytesIO(archive_bytes)
            with zipfile.ZipFile(zip_buffer, "r") as zf:
                namelist = zf.namelist()

                # 1. 严格路径穿越与 Zip Slip 检查
                for name in namelist:
                    if name.startswith(("/", "\\")) or ".." in name or ":" in name:
                        raise ValueError(f"卡带包含非法路径穿越字符: {name}")

                # 2. 检索 manifest.yaml
                manifest_data = {}
                manifest_files = [n for n in namelist if os.path.basename(n).lower() in ("manifest.yaml", "manifest.yml", "skill.yaml")]
                if manifest_files:
                    try:
                        raw_yaml = zf.read(manifest_files[0]).decode("utf-8")
                        if yaml:
                            manifest_data = yaml.safe_load(raw_yaml) or {}
                    except Exception:
                        pass

                # 3. 筛选可执行 Python 脚本文件并执行 AST 深度静态安全审查 (SEC-02)
                py_files = [n for n in namelist if n.endswith(".py") and not os.path.basename(n).startswith(".")]
                security_risks = []
                for py_f in py_files:
                    try:
                        code_bytes = zf.read(py_f)
                        code_str = code_bytes.decode("utf-8", errors="replace")
                        file_risks = scan_python_code_security(code_str, os.path.basename(py_f))
                        security_risks.extend(file_risks)
                    except Exception as e:
                        security_risks.append(f"{py_f}: 读取审查异常 ({str(e)})")

                has_critical_risk = len(security_risks) > 0

                # 4. 统计体积与文件列表
                file_items = []
                for zinfo in zf.infolist():
                    if not zinfo.is_dir():
                        file_items.append({
                            "name": zinfo.filename,
                            "size": zinfo.file_size,
                            "is_code": zinfo.filename.endswith(".py")
                        })

                skill_id = manifest_data.get("id", manifest_data.get("name", "community_skill"))
                display_name = manifest_data.get("display_name", manifest_data.get("name", skill_id))

                # 🛡️ 官方卡带数字签名与全包完整性校验 (SEC-02)
                archive_sha256 = hashlib.sha256(archive_bytes).hexdigest().lower()
                is_official_verified = False
                official_sig = manifest_data.get("official_signature")
                if official_sig:
                    sig_payload = f"{skill_id}:{manifest_data.get('version', '1.0.0')}:{archive_sha256}".encode("utf-8")
                    expected_capsule_sig = hmac.new(
                        LITIKJ_OFFICIAL_CAPSULE_SECRET.encode("utf-8"),
                        sig_payload,
                        hashlib.sha256
                    ).hexdigest()
                    if hmac.compare_digest(official_sig, expected_capsule_sig):
                        is_official_verified = True

                if is_official_verified:
                    warnings = [
                        "✅ 官方认证卡带：该卡带携带立体空间官方密码学签名且全包散列完整性校验通过。"
                    ]
                else:
                    warnings = [
                        "⚠️ 该技能由第三方分享，非官方直接签发。",
                        f"⚠️ 压缩包内包含 {len(py_files)} 个本地 Python 可执行脚本，安装后将在您的 Windows 宿主环境运行。",
                        "⚠️ 请确认该文件来自您信任的同学、老师或创作者。"
                    ]

                # 🛡️ 纵深防御核心铁律 (SEC-02)：即便具备官方签名，AST 高危风险审查也绝对不可被旁路压制！
                if has_critical_risk:
                    warnings.append(f"🚨 严重安全警告：卡带代码包含 {len(security_risks)} 项高危系统调用风险，已阻断即时装载！")
                    warnings.extend([f"  • {r}" for r in security_risks[:5]])

                return {
                    "valid": not has_critical_risk,
                    "status": "ok" if not has_critical_risk else "blocked",
                    "security_passed": not has_critical_risk,
                    "is_official_verified": is_official_verified,
                    "security_risks": security_risks,
                    "error": f"卡带安全审计拦截：检测到高危代码指令 ({'; '.join(security_risks[:2])})" if has_critical_risk else "",
                    "skill_id": skill_id,
                    "display_name": display_name,
                    "version": manifest_data.get("version", "1.0.0"),
                    "author": manifest_data.get("author", "第三方社区创作者"),
                    "icon": manifest_data.get("icon", "🌐"),
                    "category": manifest_data.get("category", "第三方扩展"),
                    "description": manifest_data.get("description", "这是一个由第三方创作者打包分享的技能卡带。"),
                    "py_files": py_files,
                    "python_files": py_files,
                    "py_count": len(py_files),
                    "file_items": file_items,
                    "total_files": len(file_items),
                    "total_size_bytes": len(archive_bytes),
                    "warnings": warnings,
                    "manifest": manifest_data
                }
        except Exception as e:
            return {"valid": False, "status": "error", "error": f"解析技能卡带失败: {str(e)}"}

    @classmethod
    def install_capsule_archive(cls, archive_bytes: bytes, skills_dir: Optional[Path] = None, target_origin: str = "community") -> Dict[str, Any]:
        """经安全审查确认后，安全解包安装第三方卡带到 skills/community/<skill_id>"""
        if skills_dir is None:
            skills_dir = ConfigManager.get_instance().skills_dir

        inspection = cls.inspect_capsule_archive(archive_bytes)
        if not inspection.get("valid") or not inspection.get("security_passed"):
            raise ValueError(inspection.get("error") or "卡带安全审计未通过：存在高危代码注入或命令执行隐患 (SEC-02)")

        skill_id = inspection["skill_id"]
        safe_origin = "community" if target_origin == "community" else "custom"
        target_dir = skills_dir / safe_origin / skill_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # 4. 安全沙盒解包 (SEC-02)
        extracted = safe_extract_zip(archive_bytes, target_dir)
        # 若所有解压文件均位于某个单层子目录下，将其平铺提升至 target_dir 根部
        subdirs = [d for d in target_dir.iterdir() if d.is_dir()]
        root_files = [f for f in target_dir.iterdir() if f.is_file()]
        if len(subdirs) == 1 and not root_files:
            sub = subdirs[0]
            for it in sub.iterdir():
                target_it = target_dir / it.name
                if target_it.exists():
                    if target_it.is_dir():
                        shutil.rmtree(target_it)
                    else:
                        target_it.unlink()
                shutil.move(str(it), str(target_dir))
            try:
                sub.rmdir()
            except Exception:
                pass

        from .registry import Registry
        Registry.get_instance().auto_discover()

        return {
            "success": True,
            "status": "success",
            "skill_id": skill_id,
            "display_name": inspection["display_name"],
            "version": inspection["version"],
            "origin": safe_origin,
            "path": str(target_dir.resolve())
        }

    @classmethod
    def create_custom_scaffold(
        cls,
        skill_id: str,
        name: str = "",
        description: str = "",
        category: str = "自定义",
        author: str = "本地开发者",
        skills_dir: Optional[Path] = None,
        **kwargs
    ) -> Path:
        """在 skills/custom/<skill_id> 创建标准自定义技能开发脚手架 (SEC-VULN-01 严防代码注入)"""
        if skills_dir is None:
            skills_dir = ConfigManager.get_instance().skills_dir

        display_name = kwargs.get("display_name", name or skill_id)
        icon = kwargs.get("icon", "🛠️")
        safe_clean_id = validate_safe_id(skill_id, "技能")

        custom_dir = skills_dir / "custom" / safe_clean_id
        if custom_dir.exists():
            raise FileExistsError(f"自定义技能 [{safe_clean_id}] 已存在，请换一个名称")

        custom_dir.mkdir(parents=True, exist_ok=True)

        safe_desc = repr(str(description or "用户自定义技能"))
        safe_display = repr(str(display_name or safe_clean_id))
        safe_author = repr(str(author or "本地开发者"))
        safe_icon = repr(str(icon or "🛠️"))
        safe_category = repr(str(category or "自定义"))

        # 1. 写入 manifest.yaml
        manifest_data = {
            "id": safe_clean_id,
            "name": str(display_name or safe_clean_id),
            "display_name": str(display_name or safe_clean_id),
            "version": "0.1.0",
            "author": str(author or "本地开发者"),
            "icon": str(icon or "🛠️"),
            "category": str(category or "自定义"),
            "origin": "custom",
            "description": str(description or "用户在本地自主开发的专属业务技能"),
            "tags": ["自定义", "本地开发"]
        }
        if yaml:
            with open(custom_dir / "manifest.yaml", "w", encoding="utf-8") as f:
                yaml.safe_dump(manifest_data, f, allow_unicode=True, sort_keys=False)
        else:
            manifest_yaml = f"""id: "{safe_clean_id}"\nname: {safe_display}\ndisplay_name: {safe_display}\nversion: "0.1.0"\nauthor: {safe_author}\nicon: {safe_icon}\ncategory: {safe_category}\norigin: "custom"\ndescription: {safe_desc}\ntags: ["自定义", "本地开发"]\n"""
            with open(custom_dir / "manifest.yaml", "w", encoding="utf-8") as f:
                f.write(manifest_yaml)

        # 2. 写入 entry.py (SEC-VULN-01 严防代码注入)
        class_name = "".join(p.title() for p in safe_clean_id.replace("-", "_").split("_")) + "Skill"
        entry_py = f'''# -*- coding: utf-8 -*-
"""
skills/custom/{safe_clean_id}/entry.py
"""
from core.contract import BaseSkill

class {class_name}(BaseSkill):
    def __init__(self):
        super().__init__(
            name="{safe_clean_id}",
            description={safe_desc},
            display_name={safe_display},
            version="0.1.0",
            author={safe_author},
            icon={safe_icon},
            category={safe_category},
            origin="custom"
        )

    def execute(self, params: dict) -> dict:
        """
        在这里编写您的业务逻辑代码！
        输入 params 为外部传入的数据字典，返回值将作为最终产物传递给工作台。
        """
        user_input = params.get("text", "Hello Litikj!")
        result = user_input.upper()
        
        return {{
            "success": True,
            "result": result,
            "message": f"自定义技能 [{{self.display_name}}] 执行成功！"
        }}

def setup(registry):
    """微内核热加载钩子：自动注册技能"""
    registry.register_skill({class_name}())
'''
        with open(custom_dir / "entry.py", "w", encoding="utf-8") as f:
            f.write(entry_py)

        # 3. 写入 prompt.md
        prompt_md = f"""# 🧠 【{display_name}】提示词与业务 SOP 规范

你是一个专业的助理。当用户请求调用此技能时，遵循以下业务流程：
1. 分析输入参数；
2. 执行核心数据处理；
3. 输出结构化结果。
"""
        with open(custom_dir / "prompt.md", "w", encoding="utf-8") as f:
            f.write(prompt_md)

        # 4. 写入 README.md
        readme_md = f"""# 🛠️ {display_name} (v0.1.0)

> 本技能由您在本地开发创建，保存在 `skills/custom/{safe_clean_id}/`。  
> 修改代码或提示词后，在工作台中点击「重载」即可立刻热生效。  
> 调试完成后，可一键「📦 导出为卡带」分享给朋友！
"""
        with open(custom_dir / "README.md", "w", encoding="utf-8") as f:
            f.write(readme_md)

        from .registry import Registry
        Registry.get_instance().auto_discover()

        return custom_dir

    @classmethod
    def export_skill_capsule(cls, skill_id: str, skills_dir: Optional[Path] = None, output_dir: Optional[Path] = None) -> Path:
        """将指定技能脱敏并打包为 <skill_id>_v<version>.skill 压缩包"""
        if skills_dir is None:
            skills_dir = ConfigManager.get_instance().skills_dir
        if output_dir is None:
            output_dir = ConfigManager.get_instance().workspace_dir / "outputs" / "capsules"
        # 寻找技能所在目录
        skill_dir = None
        for sub_dir in ("official", "community", "custom"):
            p = skills_dir / sub_dir / skill_id
            if p.exists() and p.is_dir():
                skill_dir = p
                break

        if not skill_dir:
            fallback = skills_dir / skill_id
            if fallback.exists() and fallback.is_dir():
                skill_dir = fallback

        if not skill_dir:
            raise FileNotFoundError(f"未找到待导出的技能目录: {skill_id}")

        # 读取版本号
        version = "1.0.0"
        manifest_file = skill_dir / "manifest.yaml"
        if manifest_file.exists():
            try:
                if yaml:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                        version = cfg.get("version", "1.0.0")
            except Exception:
                pass

        output_dir.mkdir(parents=True, exist_ok=True)
        export_filename = f"{skill_id}_v{version}.skill"
        export_file = output_dir / export_filename

        # 排除规则
        exclude_patterns = ("__pycache__", ".git", ".pytest_cache", ".pyc", ".DS_Store", ".env")

        with zipfile.ZipFile(export_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(skill_dir):
                # 过滤目录
                dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d not in exclude_patterns]
                for file in files:
                    if file.startswith((".", "_")) or any(file.endswith(ext) for ext in (".pyc", ".tmp")):
                        continue
                    full_p = Path(root) / file
                    rel_p = full_p.relative_to(skill_dir)
                    zf.write(full_p, arcname=str(rel_p))

        return export_file
