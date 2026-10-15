# -*- coding: utf-8 -*-
"""
tests/test_skills_hub.py
【立体空间智能体系统 · v2.3 三级技能卡带生态系统自动化测试套件】
测试范围：
1. 官方云端市场能力（列出官方市场、一键安装预置官方技能、版本比对）
2. 自定义技能开发脚手架生成（manifest/entry/prompt 模板生成、热重载发现）
3. 技能卡带导出引擎（一键打包成 .skill 分发格式，排除垃圾文件）
4. 内存级安全审查与第三方社区卡带装载（Zip Slip 漏洞防御、代码审查报告生成、安全安装）
5. REST API 端点集成测试（/api/skills, /api/market/skills, /api/capsule/inspect 等）
"""

import sys
import json
import time
import base64
import shutil
import threading
import urllib.request
import urllib.parse
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.registry import Registry
from core.market import OfficialMarketService
from apps.server.api_server import start_server


@pytest.fixture(scope="module")
def market_service():
    return OfficialMarketService()


def test_market_service_list_market(market_service):
    """测试官方技能市场列表获取与版本比对"""
    items = market_service.list_market()
    assert isinstance(items, list)
    assert len(items) >= 1
    
    ids = [it["id"] for it in items]
    assert "bili_poster_designer" not in ids
    assert "hello_skill" in ids
    assert "bili_cover_generator" not in ids
    assert "bili_meta_generator" not in ids

    for it in items:
        assert "name" in it
        assert "version" in it
        assert "category" in it
        assert "is_installed" in it


def test_market_service_install_and_uninstall_official_skill(market_service):
    """测试一键安装与卸载官方技能流程"""
    test_skill_id = "hello_skill"
    target_dir = PROJECT_ROOT / "skills" / "custom" / test_skill_id
    backup_dir = PROJECT_ROOT / "skills" / "custom" / f"{test_skill_id}_testbak"
    if target_dir.exists():
        shutil.copytree(target_dir, backup_dir)
        shutil.rmtree(target_dir)

    try:
        # 1. 执行安装 (force=True 绕过未激活访客拦截，验证解包逻辑)
        res = market_service.install_official_skill(test_skill_id, force=True)
        assert res.get("status") == "success"
        
        # 验证文件结构与注册表
        assert target_dir.exists()
        assert (target_dir / "manifest.yaml").exists()
        
        reg = Registry.get_instance()
        skill = reg.get_skill(test_skill_id)
        assert skill is not None
        
        # 2. 执行卸载
        unres = market_service.uninstall_skill(test_skill_id)
        assert unres.get("status") == "success"
        assert not target_dir.exists()
        assert reg.get_skill(test_skill_id) is None
    finally:
        if backup_dir.exists():
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(backup_dir, target_dir)
            shutil.rmtree(backup_dir)
            Registry.get_instance().auto_discover()


def test_custom_scaffold_and_export_lifecycle(market_service):
    """测试自定义技能脚手架生成、动态发现、脱敏打包与导出全生命周期"""
    custom_id = "test_custom_scaffold_skill"
    custom_dir = PROJECT_ROOT / "skills" / "custom" / custom_id
    
    try:
        # 1. 生成脚手架
        created_path = market_service.create_custom_scaffold(
            skill_id=custom_id,
            display_name="自动化测试自定义技能",
            description="用于测试脚手架生成的技能",
            author="TestAuthor",
            category="测试分类",
            icon="🧪",
            create_python_entry=True
        )
        assert created_path.exists()
        assert (created_path / "manifest.yaml").exists()
        assert (created_path / "entry.py").exists()
        assert (created_path / "prompt.md").exists()
        
        # 2. 检查注册表热重载
        reg = Registry.get_instance()
        skill = reg.get_skill(custom_id)
        assert skill is not None
        assert skill.origin == "custom"
        assert skill.author == "TestAuthor"
        
        # 3. 导出为 .skill 卡带
        pkg_path = market_service.export_skill_capsule(custom_id)
        assert pkg_path.exists()
        assert pkg_path.suffix == ".skill"
        assert pkg_path.stat().st_size > 0
        
        # 4. 审查导出的卡带
        with open(pkg_path, "rb") as f:
            raw_bytes = f.read()
            
        report = market_service.inspect_capsule_archive(raw_bytes)
        assert report.get("status") == "ok"
        assert report.get("skill_id") == custom_id
        assert report.get("security_passed") is True
        assert "entry.py" in report.get("python_files", [])
        
    finally:
        # 清理环境
        market_service.uninstall_skill(custom_id)
        if custom_dir.exists():
            shutil.rmtree(custom_dir, ignore_errors=True)


def test_inspect_and_install_community_capsule(market_service):
    """测试第三方社区卡带的在内存审查与安全安装流程"""
    comm_id = "test_community_capsule"
    comm_dir = PROJECT_ROOT / "skills" / "community" / comm_id
    
    try:
        # 先利用脚手架生成并导出一个合法的临时卡带
        market_service.create_custom_scaffold(
            skill_id=comm_id,
            display_name="社区测试卡带",
            description="社区卡带测试",
            author="CommunityUser",
            category="社区分享"
        )
        pkg_path = market_service.export_skill_capsule(comm_id)
        # 立即卸载 custom 目录的副本
        market_service.uninstall_skill(comm_id)
        
        # 读取字节流
        with open(pkg_path, "rb") as f:
            capsule_bytes = f.read()
            
        # 1. 内存审查
        report = market_service.inspect_capsule_archive(capsule_bytes)
        assert report.get("status") == "ok"
        assert report.get("skill_id") == comm_id
        
        # 2. 安装至 community 目录
        inst_res = market_service.install_capsule_archive(capsule_bytes)
        assert inst_res.get("status") == "success"
        assert comm_dir.exists()
        
        # 3. 检查注册表
        reg = Registry.get_instance()
        installed_skill = reg.get_skill(comm_id)
        assert installed_skill is not None
        assert installed_skill.origin == "community"
        
    finally:
        market_service.uninstall_skill(comm_id)
        if comm_dir.exists():
            shutil.rmtree(comm_dir, ignore_errors=True)


class TestSkillsHubHttpApi:
    """测试 HTTP 端点集成交互"""

    @classmethod
    def setup_class(cls):
        cls.port = 18798
        cls.server = start_server(host="127.0.0.1", port=cls.port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.4)

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()

    def _get(self, path: str):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "TestClient"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, data: dict):
        url = f"http://127.0.0.1:{self.port}{path}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "TestClient"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_api_skills_and_market_list(self):
        """测试 /api/skills 与 /api/market/skills"""
        status, data = self._get("/api/skills")
        assert status == 200
        assert data.get("status") == "success"
        assert "skills" in data
        assert isinstance(data["skills"], list)

        m_status, m_data = self._get("/api/market/skills")
        assert m_status == 200
        assert m_data.get("status") == "success"
        assert len(m_data.get("market_skills", [])) >= 1

    def test_api_custom_create_and_export_and_uninstall(self):
        """测试 /api/skills/custom/create 和 /api/skills/export 接口"""
        skill_id = "test_api_custom_unit"
        custom_dir = PROJECT_ROOT / "skills" / "custom" / skill_id

        try:
            # 1. 创建自定义技能
            status, res = self._post("/api/skills/custom/create", {
                "skill_id": skill_id,
                "display_name": "API 创建技能",
                "description": "通过 API 创建",
                "author": "APITester",
                "category": "API测试",
                "icon": "⚡"
            })
            assert status == 200
            assert res.get("status") == "success"
            assert custom_dir.exists()

            # 2. 导出
            e_status, e_res = self._post("/api/skills/export", {"skill_id": skill_id})
            assert e_status == 200
            assert e_res.get("status") == "success"
            pkg_path = Path(e_res.get("package_path", ""))
            assert pkg_path.exists()

            # 3. 内存审查 (Base64)
            with open(pkg_path, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode("utf-8")
            
            i_status, i_res = self._post("/api/capsule/inspect", {
                "file_name": pkg_path.name,
                "file_content_b64": b64_content
            })
            assert i_status == 200
            assert i_res.get("status") == "success"
            report = i_res.get("report", {})
            token = i_res.get("inspect_token")
            assert report.get("skill_id") == skill_id
            assert token is not None

            # 4. 卸载 custom
            u_status, u_res = self._post("/api/market/uninstall", {"skill_id": skill_id})
            assert u_status == 200
            assert u_res.get("status") == "success"

            # 5. 确认安装审查过的社区卡带
            inst_status, inst_res = self._post("/api/capsule/install", {
                "token": token,
                "skill_id": skill_id
            })
            assert inst_status == 200
            assert inst_res.get("status") == "success"

            comm_dir = PROJECT_ROOT / "skills" / "community" / skill_id
            assert comm_dir.exists()

            # 6. 最终清理社区卡带
            self._post("/api/market/uninstall", {"skill_id": skill_id})
            assert not comm_dir.exists()

        finally:
            if custom_dir.exists():
                shutil.rmtree(custom_dir, ignore_errors=True)
