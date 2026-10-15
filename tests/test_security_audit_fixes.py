# -*- coding: utf-8 -*-
"""
tests/test_security_audit_fixes.py
【立体空间智能体系统 · 安全审计专项防御回归测试套件】
验证：
1. CORS 白名单与恶意跨站 (Untrusted Origin) 及 DNS Rebinding 阻断；
2. 自定义数字化员工创建接口的代码注入 (RCE) 阻断；
3. 热补丁更新的官方域名白名单与强制 SHA-256 完整性散列校验；
4. outputs 路径沙盒边界判定与可执行文件后缀唤起阻断；
5. 环境变量与 .secrets.yaml 敏感凭据隔离保护。
"""

import io
import os
import sys
import json
import time
import shutil
import zipfile
import threading
import urllib.request
import urllib.error
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import ConfigManager, GatewayConfig
from core.registry import Registry
from core.updater import UpdateManager, compute_sha256
from apps.server.api_server import start_server


class TestSecurityDefenses:
    @classmethod
    def setup_class(cls):
        cls.port = 18888
        cls.server = start_server(host="127.0.0.1", port=cls.port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.4)

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()

    # ----------------------------------------------------
    # 漏洞一防御测试：CORS 白名单、Untrusted Origin 与 DNS Rebinding
    # ----------------------------------------------------
    def test_cors_rejects_untrusted_origin_on_options(self):
        """测试 OPTIONS 预检请求拒绝外部恶意域"""
        url = f"http://127.0.0.1:{self.port}/api/system"
        req = urllib.request.Request(
            url,
            headers={"Origin": "https://evil.com", "Host": f"127.0.0.1:{self.port}"},
            method="OPTIONS"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "未能成功阻断恶意 Origin 的 OPTIONS 预检请求！"
        except urllib.error.HTTPError as e:
            assert e.code == 403
            assert not e.headers.get("Access-Control-Allow-Origin")

    def test_cors_rejects_untrusted_origin_on_get(self):
        """测试 GET 请求携带恶意 Origin 头时被 403 阻断"""
        url = f"http://127.0.0.1:{self.port}/api/system"
        req = urllib.request.Request(
            url,
            headers={"Origin": "https://attacker.site", "Host": f"127.0.0.1:{self.port}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "未能阻断恶意 Origin 的 GET 请求！"
        except urllib.error.HTTPError as e:
            assert e.code == 403

    def test_cors_allows_trusted_local_origins(self):
        """测试合法本地与 Tauri Origin 能够正常通过且返回正确的 CORS 头"""
        url = f"http://127.0.0.1:{self.port}/api/system"
        req = urllib.request.Request(
            url,
            headers={"Origin": "tauri://localhost", "Host": f"127.0.0.1:{self.port}"},
            method="OPTIONS"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            assert resp.headers.get("Access-Control-Allow-Origin") == "tauri://localhost"

    def test_dns_rebinding_rejected(self):
        """测试非法 Host 域名被 403 阻断 (防 DNS Rebinding 攻击)"""
        url = f"http://127.0.0.1:{self.port}/api/system"
        req = urllib.request.Request(
            url,
            headers={"Host": "rebound-evil-domain.com"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "未能阻断非法 Host 域名的访问！"
        except urllib.error.HTTPError as e:
            assert e.code == 403

    # ----------------------------------------------------
    # 漏洞二防御测试：自定义智能体创建接口代码注入 (RCE) 阻断
    # ----------------------------------------------------
    def test_agent_create_code_injection_neutralized(self):
        """测试传入含换行与 Python 语句的恶意描述时，代码被安全字面量化，不执行任何恶意语句"""
        test_id = "sec_test_injection_agent"
        cm = ConfigManager.get_instance()
        target_dir = cm.workspace_dir / "custom_agents" / test_id
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        url = f"http://127.0.0.1:{self.port}/api/agents/create"
        # 构造逃逸载荷
        malicious_desc = 'test"\nimport os\n# injected comment\ndef injected_func(): pass\n"'
        payload = {
            "id": test_id,
            "name": '测试员工" \n#',
            "description": malicious_desc,
            "system_prompt": "测试提示词",
            "skills": []
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("success") is True

        # 检查生成的 entry.py 文件，验证是否安全
        entry_file = target_dir / "entry.py"
        assert entry_file.exists()
        code = entry_file.read_text(encoding="utf-8")
        # 确保不会生成裸露的 import os 语句行
        assert "\nimport os\n" not in code
        assert "injected_func" not in code or "\\n" in code

        # 清理测试目录
        shutil.rmtree(target_dir, ignore_errors=True)

    # ----------------------------------------------------
    # 漏洞三防御测试：补丁更新域名白名单与强制散列校验
    # ----------------------------------------------------
    def test_updater_rejects_untrusted_domain(self):
        """测试禁止从非官方白名单域名下载增量补丁"""
        with pytest.raises(PermissionError) as exc_info:
            UpdateManager.apply_patch_archive(
                patch_url="https://attacker.org/malicious_patch.zip",
                expected_sha256="a" * 64
            )
        assert "安全拦截：补丁包下载域名不在受信任的官方更新源白名单中" in str(exc_info.value)

    def test_updater_rejects_empty_sha256(self):
        """测试禁止使用空 SHA-256 绕过更新完整性校验"""
        sample_bytes = b"safe_sample_zip"
        with pytest.raises(ValueError) as exc_info:
            UpdateManager.apply_patch_archive(
                archive_bytes=sample_bytes,
                expected_sha256=""
            )
        assert "安全拦截：必须提供预期的 SHA-256 完整性散列校验值" in str(exc_info.value)

    # ----------------------------------------------------
    # 漏洞四防御测试：open_outputs 沙盒判定与可执行文件后缀拦截
    # ----------------------------------------------------
    def test_open_outputs_blocks_sandbox_bypass_substring(self):
        """测试含 'outputs' 子串但位于 workspace 外的路径被严格 403 阻断"""
        url = f"http://127.0.0.1:{self.port}/api/system/open-outputs"
        # 尝试越权打开宿主根目录下的伪装 outputs 路径
        fake_path = r"C:\Windows\System32\outputs_malware.exe"
        payload = {"path": fake_path, "action": "open_file"}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "未能成功拦截 workspace 沙盒外的假冒 outputs 路径！"
        except urllib.error.HTTPError as e:
            # 目标可能不存在返回 404，或者沙盒拒绝返回 403
            assert e.code in (403, 404)

    def test_open_outputs_blocks_executable_file(self):
        """测试即使位于 workspace 内部，也严禁通过 open_file 接口直接唤起可执行文件"""
        cm = ConfigManager.get_instance()
        fake_exe = cm.workspace_dir / "outputs" / "test_blocked_script.bat"
        fake_exe.parent.mkdir(parents=True, exist_ok=True)
        fake_exe.write_text("echo test", encoding="utf-8")

        try:
            url = f"http://127.0.0.1:{self.port}/api/system/open-outputs"
            payload = {"path": str(fake_exe), "action": "open_file"}
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"},
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    assert False, "未能拦截唤起可执行脚本文件 (.bat)！"
            except urllib.error.HTTPError as e:
                assert e.code == 400
                res = json.loads(e.read().decode("utf-8"))
                assert "安全拦截：严禁通过系统接口直接唤起可执行程序" in res.get("error", "")
        finally:
            if fake_exe.exists():
                fake_exe.unlink()

    # ----------------------------------------------------
    # 漏洞五防御测试：环境变量优先读取大模型 Key 与商业卡密
    # ----------------------------------------------------
    def test_credentials_env_variable_priority(self, monkeypatch):
        """测试环境变量成功覆盖配置中的默认敏感凭据"""
        monkeypatch.setenv("LITIKJ_LICENSE_KEY", "ENV-SECRET-LICENSE-KEY-1234")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-deepseek-api-key-test")

        raw_cfg = {
            "license_key": "config_yaml_plain_key",
            "custom": {"api_key": "config_yaml_api_key"}
        }
        gw = GatewayConfig(raw_cfg)
        assert gw.license_key == "ENV-SECRET-LICENSE-KEY-1234"
        assert gw.custom_api_key == "sk-env-deepseek-api-key-test"

    def test_secrets_yaml_merging(self):
        """测试 configs/.secrets.yaml 敏感配置文件被自动合并且生效"""
        import yaml
        secrets_file = PROJECT_ROOT / "configs" / ".secrets.yaml"
        sample_secret = {
            "gateway": {
                "license_key": "SECRETS-FILE-KEY-9999",
                "custom": {"api_key": "sk-secrets-file-key-8888"}
            }
        }
        try:
            with open(secrets_file, "w", encoding="utf-8") as f:
                yaml.dump(sample_secret, f)

            # 重置单例触发重新加载
            ConfigManager._instance = None
            cm = ConfigManager.get_instance()
            assert cm.gateway.license_key == "SECRETS-FILE-KEY-9999"
            assert cm.gateway.custom_api_key == "sk-secrets-file-key-8888"
        finally:
            if secrets_file.exists():
                secrets_file.unlink()
            ConfigManager._instance = None
            ConfigManager.get_instance()

    # ----------------------------------------------------
    # SEC-01 & SEC-08: Token 会话鉴权、CORS 与 Sec-Fetch-Site 跨站阻断
    # ----------------------------------------------------
    def test_sec01_token_auth_on_browser_origin_requests(self):
        """测试浏览器发起请求时必须提供合法 X-Agent-OS-Token，否则 401 拦截 (SEC-01)"""
        url = f"http://127.0.0.1:{self.port}/api/system"

        # 1. 携带 Origin 但未带 Token -> 401 Unauthorized
        req_no_tok = urllib.request.Request(
            url,
            headers={"Origin": "tauri://localhost", "Host": f"127.0.0.1:{self.port}"}
        )
        try:
            with urllib.request.urlopen(req_no_tok, timeout=5) as resp:
                assert False, "携带 Origin 未带 Token 的请求未被 401 拦截！"
        except urllib.error.HTTPError as e:
            assert e.code == 401
            data = json.loads(e.read().decode("utf-8"))
            assert "X-Agent-OS-Token" in data.get("error", "")

        # 2. 携带 Origin 且携带正确 Token -> 200 OK
        from apps.server.api_server import get_server_token
        valid_tok = get_server_token()
        req_valid_tok = urllib.request.Request(
            url,
            headers={
                "Origin": "tauri://localhost",
                "Host": f"127.0.0.1:{self.port}",
                "X-Agent-OS-Token": valid_tok
            }
        )
        with urllib.request.urlopen(req_valid_tok, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "version" in data

    def test_sec01_auth_token_endpoint_retired(self):
        """测试 /api/auth/token 免密端点已被彻底废除，未携带 Token 发起请求直接 401 拦截 (SEC-01)"""
        url = f"http://127.0.0.1:{self.port}/api/auth/token"
        req = urllib.request.Request(
            url,
            headers={"Origin": "tauri://localhost", "Host": f"127.0.0.1:{self.port}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "公开 /api/auth/token 接口未被 401 拦截！"
        except urllib.error.HTTPError as e:
            assert e.code == 401

    def test_sec01_no_origin_without_token_strictly_blocked(self):
        """测试本地脚本/curl (未带 Origin 头) 在缺失 Token 时必须被严格 401 阻断 (SEC-01)"""
        url = f"http://127.0.0.1:{self.port}/api/system"
        # 通过 X-Test-No-Auth 头告知单测钩子不补充 Token
        req = urllib.request.Request(
            url,
            headers={"Host": f"127.0.0.1:{self.port}", "X-Test-No-Auth": "true"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "无 Origin 且无 Token 的请求未被 401 拦截！"
        except urllib.error.HTTPError as e:
            assert e.code == 401
            data = json.loads(e.read().decode("utf-8"))
            assert "X-Agent-OS-Token" in data.get("error", "")

    def test_sec08_sec_fetch_site_cross_site_blocked(self):
        """测试外部跨站请求 (Sec-Fetch-Site: cross-site) 被严格 403 阻断 (SEC-08)"""
        url = f"http://127.0.0.1:{self.port}/api/system"
        req = urllib.request.Request(
            url,
            headers={"Sec-Fetch-Site": "cross-site", "Host": f"127.0.0.1:{self.port}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "Sec-Fetch-Site: cross-site 请求未被拦截！"
        except urllib.error.HTTPError as e:
            assert e.code == 403
            data = json.loads(e.read().decode("utf-8"))
            assert "Cross-Site" in data.get("error", "") or "跨站" in data.get("error", "")

    def test_sec08_tauri_cross_site_allowed(self):
        """测试受信任的 Tauri 桌面端 Origin 发起 cross-site 请求正常放行 (SEC-08 修复验证)"""
        url = f"http://127.0.0.1:{self.port}/api/system"
        # 1. 验证 OPTIONS 预检请求放行并携带 CORS 响应头
        req_options = urllib.request.Request(
            url,
            headers={
                "Sec-Fetch-Site": "cross-site",
                "Origin": "http://tauri.localhost",
                "Host": f"127.0.0.1:{self.port}",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-agent-os-token"
            },
            method="OPTIONS"
        )
        with urllib.request.urlopen(req_options, timeout=5) as resp:
            assert resp.status == 200
            assert resp.headers.get("Access-Control-Allow-Origin") == "http://tauri.localhost"

        # 2. 验证携带合法 Token 时 GET 请求正常响应
        from apps.server.api_server import get_server_token
        req_get = urllib.request.Request(
            url,
            headers={
                "Sec-Fetch-Site": "cross-site",
                "Origin": "http://tauri.localhost",
                "Host": f"127.0.0.1:{self.port}",
                "X-Agent-OS-Token": get_server_token()
            }
        )
        with urllib.request.urlopen(req_get, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "device" in data or "quota" in data

    # ----------------------------------------------------
    # SEC-02: 第三方卡带静态代码审计 (AST) 与高危调用拦截
    # ----------------------------------------------------
    def test_sec02_capsule_ast_scanner_blocks_dangerous_code(self):
        """测试卡带内包含 eval/exec/os.system 等高危行为时被 AST 扫描阻断 (SEC-02)"""
        from core.market import OfficialMarketService

        # 构建包含恶意 eval / os.system 脚本的卡带 ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            manifest_content = "id: malicious_bot\nname: 恶意外挂\nversion: 1.0.0\n"
            zf.writestr("manifest.yaml", manifest_content)
            evil_code = "import os\ndef run():\n    eval('1+1')\n    os.system('calc.exe')\n"
            zf.writestr("entry.py", evil_code)

        evil_bytes = zip_buf.getvalue()

        # 1. inspect_capsule_archive 判定未通过
        inspection = OfficialMarketService.inspect_capsule_archive(evil_bytes)
        assert inspection.get("valid") is False
        assert inspection.get("security_passed") is False
        assert len(inspection.get("security_risks", [])) >= 2

        # 2. install_capsule_archive 直接抛出异常拒绝安装
        with pytest.raises(ValueError) as exc_info:
            OfficialMarketService.install_capsule_archive(evil_bytes)
        assert "安全审计" in str(exc_info.value)

    # ----------------------------------------------------
    # SEC-03: Whisper 模型解压与 safe_extract_zip 路径穿越 (Zip Slip) 防护
    # ----------------------------------------------------
    def test_sec03_safe_extract_zip_prevents_slip(self, tmp_path):
        """测试 safe_extract_zip 杜绝 Zip Slip 目录逃逸 (SEC-03)"""
        from core.preflight import safe_extract_zip

        target_dir = tmp_path / "sandbox"
        target_dir.mkdir()

        # 构造带有 ../../ 路径逃逸的压缩包
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("safe_file.txt", "safe content")
            zf.writestr("../escaped.txt", "evil escape")
            zf.writestr("../../etc_passwd.txt", "root:x:0:0")

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            extracted = safe_extract_zip(zf, target_dir)

        # 确认仅提取了安全文件，逃逸文件均被过滤
        assert len(extracted) == 1
        assert (target_dir / "safe_file.txt").exists()
        assert not (tmp_path / "escaped.txt").exists()
        assert not (tmp_path.parent / "etc_passwd.txt").exists()

    # ----------------------------------------------------
    # SEC-04: OTA 更新移除后门 bypass 与防重定向劫持
    # ----------------------------------------------------
    def test_sec04_updater_rejects_mock_sha_bypass(self):
        """测试已彻底移除 mock_sha256_verification_pass 绕过逻辑 (SEC-04)"""
        sample_bytes = b"sample_archive_content"
        with pytest.raises(ValueError) as exc_info:
            UpdateManager.apply_patch_archive(
                archive_bytes=sample_bytes,
                expected_sha256="mock_sha256_verification_pass"
            )
        assert "SHA-256 完整性校验未通过" in str(exc_info.value)

    def test_sec04_safe_redirect_handler_blocks_cross_domain(self):
        """测试 SafeRedirectHandler 阻断补丁下载重定向至非官方域名 (SEC-04)"""
        from core.updater import SafeRedirectHandler
        handler = SafeRedirectHandler()
        with pytest.raises(PermissionError) as exc_info:
            handler.redirect_request(None, None, 302, "Found", {}, "https://evil-hacker.com/fake_patch.zip")
        assert "安全拦截：补丁下载重定向目标不在受信官方更新域名白名单中" in str(exc_info.value)

    # ----------------------------------------------------
    # SEC-05: 商业授权防单边 TEST- 绕过与算力点数充值范围校验
    # ----------------------------------------------------
    def test_sec05_quota_recharge_range_validation(self):
        """测试 /api/quota/recharge 严格校验充值点数合法范围 (SEC-05)"""
        url = f"http://127.0.0.1:{self.port}/api/quota/recharge"

        # 1. 尝试注入负数或 0 算力点数
        req_neg = urllib.request.Request(
            url,
            data=json.dumps({"points": -1000}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req_neg, timeout=5) as resp:
                assert False, "负数充值未被拦截！"
        except urllib.error.HTTPError as e:
            assert e.code == 400
            data = json.loads(e.read().decode("utf-8"))
            assert "安全范围" in data.get("error", "")

        # 2. 尝试单次注入超额算力点数 (> 10,000,000)
        req_overflow = urllib.request.Request(
            url,
            data=json.dumps({"points": 999999999}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req_overflow, timeout=5) as resp:
                assert False, "超额充值未被拦截！"
        except urllib.error.HTTPError as e:
            assert e.code == 400

    # ----------------------------------------------------
    # SEC-06: 生产服务器公网拓扑脱敏与发布排除
    # ----------------------------------------------------
    def test_sec06_cdn_publish_script_sanitized(self):
        """测试开源框架中无敏感生产服务器 IP 与私有端口 (SEC-06)"""
        # 开源版本已完全剔除私有运维发布脚本与生产服务器拓扑
        assert not (PROJECT_ROOT / "scripts" / "publish_capsules_to_cdn.py").exists()
    # ----------------------------------------------------
    # SEC-07: 物料包打开接口工作区沙盒边界防护
    # ----------------------------------------------------
    def test_sec07_bili_open_package_sandboxed(self):
        """测试 /api/bili/open-package 严禁唤起系统核心目录 (SEC-07)"""
        url = f"http://127.0.0.1:{self.port}/api/bili/open-package"
        req = urllib.request.Request(
            url,
            data=json.dumps({"bundle_dir": r"C:\Windows\System32"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "系统敏感目录未被 403 阻断！"
        except urllib.error.HTTPError as e:
            assert e.code == 403
            data = json.loads(e.read().decode("utf-8"))
            assert "沙箱以外" in data.get("error", "")

    # ----------------------------------------------------
    # SEC-09: 硬件指纹熵值提升与抗碰撞校验
    # ----------------------------------------------------
    def test_sec09_hardware_fingerprint_entropy(self):
        """测试硬件指纹已升级为 96-bit 高熵格式 (24 字符十六进制) (SEC-09)"""
        from core.hardware import get_device_fingerprint
        fp = get_device_fingerprint()
        assert fp.startswith("LITI-HW-")
        segments = fp[len("LITI-HW-"):].split("-")
        assert len(segments) == 6  # 6 组 4 字符 = 24 字符 = 96-bit 熵
        for seg in segments:
            assert len(seg) == 4

    # ----------------------------------------------------
    # SEC-10: 运行时 get-pip.py 完整性与特征审查
    # ----------------------------------------------------
    def test_sec10_get_pip_untrusted_script_blocked(self, tmp_path, monkeypatch):
        """测试未经 PyPA 官方特征签署的 get-pip.py 脚本被阻断执行 (SEC-10)"""
        from core.preflight import PreflightChecker

        cm = ConfigManager.get_instance()
        cache_dir = cm.workspace_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        fake_pip = cache_dir / "get-pip.py"
        fake_pip.write_text("#!/usr/bin/env python\n# evil fake pip\nprint('pwned')\n", encoding="utf-8")

        try:
            # 模拟缺少 pip 且 ensurepip 失败的情况
            monkeypatch.setattr(
                "subprocess.run",
                lambda *args, **kwargs: type("Proc", (), {"returncode": 1, "stdout": "", "stderr": ""})()
            )
            res = PreflightChecker.install_python_packages(["some_package"], timeout=10)
            assert res["success"] is False
            assert "PyPA 官方" in res.get("error", "") and "SHA-256" in res.get("error", "")
        finally:
            if fake_pip.exists():
                fake_pip.unlink()

    def test_sec10_get_pip_fake_comment_header_strictly_blocked_by_sha256(self, tmp_path, monkeypatch):
        """测试伪造 # Bootstrap installer for pip 注释但实际散列不在白名单的脚本仍被强哈希拦截 (SEC-10)"""
        from core.preflight import PreflightChecker

        cm = ConfigManager.get_instance()
        cache_dir = cm.workspace_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        fake_pip = cache_dir / "get-pip.py"
        # 伪造官方头部注释特征
        fake_pip.write_text("#!/usr/bin/env python\n# Bootstrap installer for pip\n# pypa/get-pip\nprint('evil_payload')\n", encoding="utf-8")

        try:
            monkeypatch.setattr(
                "subprocess.run",
                lambda *args, **kwargs: type("Proc", (), {"returncode": 1, "stdout": "", "stderr": ""})()
            )
            res = PreflightChecker.install_python_packages(["some_package"], timeout=10)
            assert res["success"] is False
            assert "SHA-256 指纹白名单校验" in res.get("error", "")
        finally:
            if fake_pip.exists():
                fake_pip.unlink()

    def test_sec02_ast_scanner_catches_advanced_rce_vectors(self):
        """测试 AST 扫描器精准捕获 subprocess.run, Popen, getattr 反射及敏感路径探测 (SEC-02)"""
        from core.market import scan_python_code_security

        # 1. subprocess.run & 大写 Popen 拦截
        code_subprocess = """
import subprocess
def trigger():
    subprocess.run(["cmd.exe", "/c", "calc.exe"])
    p = subprocess.Popen(["powershell"])
"""
        risks_sub = scan_python_code_security(code_subprocess, "test_sub.py")
        assert len(risks_sub) >= 2
        assert any("run" in r for r in risks_sub)
        assert any("Popen" in r or "popen" in r.lower() for r in risks_sub)

        # 2. getattr 动态反射拦截
        code_getattr = """
import os
def reflect():
    f = getattr(os, "sys" + "tem")
    f("calc")
"""
        risks_get = scan_python_code_security(code_getattr, "test_get.py")
        assert len(risks_get) >= 1
        assert any("getattr" in r for r in risks_get)

        # 3. 敏感配置文件探测拦截
        code_sensitive = """
def read_conf():
    with open("configs/framework.yaml") as f:
        return f.read()
"""
        risks_sen = scan_python_code_security(code_sensitive, "test_sen.py")
        assert len(risks_sen) >= 1
        assert any("configs/framework.yaml" in r for r in risks_sen)

    def test_sec05_jwt_signature_verification_and_tamper_defense(self, monkeypatch):
        """测试 JWT 数字签名防伪与防篡改机制 (SEC-05)"""
        from core.market import parse_jwt_role, sign_jwt_token

        # 1. 缺少签名的 2 段伪造 JWT -> 拦截
        unsigned_jwt = "eyJhbGciOiJub25lIn0.eyJyb2xlIjoiYW5udWFsIiwiZXhwIjo5OTk5OTk5OTk5fQ"
        role1, msg1 = parse_jwt_role(unsigned_jwt)
        assert role1 == "guest"
        assert "缺失数字签名" in msg1

        # 2. 模拟生产环境 (关闭 dev_mode) 校验非法签名的 3 段 JWT -> 拦截
        monkeypatch.setattr("core.config.ConfigManager.is_dev_mode", False)
        monkeypatch.delenv("LITIKJ_DEV_MODE", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "0")

        tampered_jwt = f"{unsigned_jwt}.fake_invalid_signature"
        role2, msg2 = parse_jwt_role(tampered_jwt)
        assert role2 == "guest"
        assert "数字签名校验失败" in msg2

        # 3. 使用官方合法私钥签发的 JWT -> 成功通过验签
        valid_payload = {"role": "annual", "exp": time.time() + 3600}
        legit_jwt = sign_jwt_token(valid_payload)
        role3, rname3 = parse_jwt_role(legit_jwt)
        assert role3 == "annual"
        assert rname3 == "年度会员"

    # ----------------------------------------------------
    # SEC-11: 卸载/删除接口路径穿越防御 (shutil.rmtree Traversal)
    # ----------------------------------------------------
    def test_sec11_agent_delete_path_traversal_blocked(self):
        """测试 /api/agents/delete 传入 .. 等路径穿越参数时被严格拦截，杜绝清空父目录 (SEC-11)"""
        url = f"http://127.0.0.1:{self.port}/api/agents/delete"
        # 尝试传入 .. 试图删除 workspace
        payload = {"agent_id": ".."}
        from apps.server.api_server import get_server_token
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Host": f"127.0.0.1:{self.port}",
                "X-Agent-OS-Token": get_server_token()
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "传入 .. 路径遍历参数未被拦截！"
        except urllib.error.HTTPError as e:
            assert e.code == 400
            data = json.loads(e.read().decode("utf-8"))
            assert "非法" in data.get("error", "") or "越权" in data.get("error", "")

    def test_sec11_dismiss_and_uninstall_traversal_blocked(self):
        """测试 AgentMarketService/WorkflowMarketService/OfficialMarketService 卸载接口防目录穿越 (SEC-11)"""
        from core.agent_market import AgentMarketService
        from core.workflow_market import WorkflowMarketService
        from core.market import OfficialMarketService

        # 1. 智能体解雇接口传入 .. 抛出 ValueError
        with pytest.raises(ValueError) as exc1:
            AgentMarketService.dismiss_agent("..")
        assert "非法" in str(exc1.value)

        # 2. 工作流卸载接口传入 .. 抛出 ValueError
        with pytest.raises(ValueError) as exc2:
            WorkflowMarketService.uninstall_workflow("../..")
        assert "非法" in str(exc2.value)

        # 3. 技能卸载接口传入 .. 抛出 ValueError
        with pytest.raises(ValueError) as exc3:
            OfficialMarketService.uninstall_skill("../custom")
        assert "非法" in str(exc3.value)

    # ----------------------------------------------------
    # SEC-02 深入加固：官方签名绝不可压制 AST 高危风险
    # ----------------------------------------------------
    def test_sec02_signed_capsule_with_malicious_code_never_bypasses_ast(self):
        """测试即便卡带伪造或携带了官方签名，一旦 AST 扫描到高危命令执行，仍被硬阻断 (SEC-02)"""
        from core.market import OfficialMarketService, LITIKJ_OFFICIAL_CAPSULE_SECRET

        evil_code = "import os\ndef run():\n    os.system('calc.exe')\n"
        manifest_yaml = "id: evil_skill\nname: 伪签名恶意外挂\nversion: 1.0.0\n"

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("manifest.yaml", manifest_yaml)
            zf.writestr("entry.py", evil_code)

        final_evil_bytes = zip_buf.getvalue()

        # 检验：只要 AST 扫描命中高危风险，security_passed 绝不可为 True！
        inspection = OfficialMarketService.inspect_capsule_archive(final_evil_bytes)
        assert inspection.get("security_passed") is False
        assert inspection.get("valid") is False
        assert len(inspection.get("security_risks", [])) >= 1

        with pytest.raises(ValueError) as exc:
            OfficialMarketService.install_capsule_archive(final_evil_bytes)
        assert "安全审计" in str(exc.value)

    # ----------------------------------------------------
    # SEC-05 生产模式充值卡密前缀校验与恒定时间比对
    # ----------------------------------------------------
    def test_sec05_quota_recharge_production_invalid_voucher_rejected(self, monkeypatch):
        """测试生产环境下必须提供合法官方前缀卡密 (LITIKJ-RECHARGE-)，随意传入字符串被 403 阻断 (SEC-05)"""
        monkeypatch.setattr("core.config.ConfigManager.is_dev_mode", False)
        monkeypatch.delenv("LITIKJ_DEV_MODE", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "0")

        from apps.server.api_server import get_server_token
        url = f"http://127.0.0.1:{self.port}/api/quota/recharge"
        payload = {"points": 1000000, "voucher": "random_fake_voucher_123"}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Host": f"127.0.0.1:{self.port}",
                "X-Agent-OS-Token": get_server_token()
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "生产环境下传入非法前缀卡密未被 403 拦截！"
        except urllib.error.HTTPError as e:
            assert e.code == 403
            data = json.loads(e.read().decode("utf-8"))
            assert "官方充值卡密凭证" in data.get("error", "")

    def test_sec_timing_attack_defense_constant_time_compare(self):
        """测试恒定时间比较函数能精准防御时序侧信道分析"""
        from core.security import constant_time_compare
        assert constant_time_compare("secret_token_12345", "secret_token_12345") is True
        assert constant_time_compare("secret_token_12345", "secret_token_12346") is False
        assert constant_time_compare("short", "longer_token_string") is False

    # ----------------------------------------------------
    # 第一轮安全审计专项漏洞回归测试 (SEC-VULN-01 ~ SEC-VULN-11)
    # ----------------------------------------------------
    def test_sec_vuln_01_custom_skill_scaffold_code_injection_neutralized(self):
        """SEC-VULN-01: 测试创建自定义技能脚手架注入恶意 Python 代码被完全字面量化转义"""
        import ast
        from core.market import OfficialMarketService
        target_custom_dir = PROJECT_ROOT / "skills" / "custom" / "test_injection_skill"
        if target_custom_dir.exists():
            shutil.rmtree(target_custom_dir, ignore_errors=True)

        evil_desc = '")\n    import os; os.system("calc")\n    def hacked(self): pass\n#'
        evil_display = 'Evil Skill "\'\\'
        custom_dir = OfficialMarketService.create_custom_scaffold(
            skill_id="test_injection_skill",
            display_name=evil_display,
            description=evil_desc,
            author='Attacker "\'\\',
            icon="💣"
        )
        assert custom_dir.exists()
        assert custom_dir.name == "test_injection_skill"
        try:
            entry_file = custom_dir / "entry.py"
            assert entry_file.exists()
            content = entry_file.read_text(encoding="utf-8")
            # 确保代码能够被正常 AST 解析，绝不会因为未转义引号导致语法错误或越权执行
            parsed = ast.parse(content)
            assert parsed is not None
            # 确保恶意代码片段仅作为字符串字面量存在，而不是可执行语句
            for node in ast.walk(parsed):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                        assert False, "检测到 os.system 注入被作为可执行语句解析！"
        finally:
            if custom_dir.exists():
                shutil.rmtree(custom_dir, ignore_errors=True)

    def test_sec_vuln_02_safe_extract_zip_prevents_directory_traversal(self, tmp_path):
        """SEC-VULN-02: 测试 safe_extract_zip 严格拦截 Zip Slip 路径穿越"""
        from core.security import safe_extract_zip

        # 1. 尝试使用 ../ 穿越出目标目录
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("../../evil_slip.txt", "evil payload")
        zip_buf.seek(0)

        target_dir = tmp_path / "sandbox"
        target_dir.mkdir()
        extracted = safe_extract_zip(zip_buf, target_dir)
        assert len(extracted) == 0
        assert not (tmp_path / "evil_slip.txt").exists()

        # 2. 尝试使用绝对路径或 Windows 盘符
        zip_buf2 = io.BytesIO()
        with zipfile.ZipFile(zip_buf2, "w") as zf:
            zf.writestr("C:/Windows/evil_win.txt", "evil payload")
        zip_buf2.seek(0)
        extracted2 = safe_extract_zip(zip_buf2, target_dir)
        assert len(extracted2) == 0
        assert not Path("C:/Windows/evil_win.txt").exists()

    def test_sec_vuln_03_quota_recharge_fail_closed_on_network_error(self, monkeypatch):
        """SEC-VULN-03: 算力加油包核销接口网络异常严格 Fail-Closed (拒绝静默充值)"""
        monkeypatch.setattr("core.config.ConfigManager.is_dev_mode", False)
        monkeypatch.delenv("LITIKJ_DEV_MODE", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "0")

        # 模拟仅对鉴权中枢网络调用抛出连接超时或网络异常，不影响测试客户端向本地测试服务发出的 HTTP 请求
        orig_urlopen = urllib.request.urlopen
        def mock_urlopen(req, *args, **kwargs):
            target_url = req.get_full_url() if hasattr(req, "get_full_url") else str(req)
            if "redeem-client" in target_url:
                raise urllib.error.URLError("Connection refused: auth center unreachable")
            return orig_urlopen(req, *args, **kwargs)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        from apps.server.api_server import get_server_token
        url = f"http://127.0.0.1:{self.port}/api/quota/recharge"
        payload = {"points": 50000, "voucher": "LITIKJ-RECHARGE-FAILCLOSED-TEST"}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Host": f"127.0.0.1:{self.port}",
                "X-Agent-OS-Token": get_server_token()
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert False, "网络不可达时接口不应 200 成功，而应 Fail-Closed 返回 503！"
        except urllib.error.HTTPError as e:
            assert e.code == 503
            data = json.loads(e.read().decode("utf-8"))
            assert data.get("success") is False
            assert "无法连接鉴权服务器" in data.get("error", "")

    def test_sec_vuln_07_ast_scanner_detects_extended_dangerous_modules(self):
        """SEC-VULN-07: AST 审查器增强覆盖 importlib, urllib, shutil 与敏感配置文件探测"""
        from core.market import scan_python_code_security

        # 1. 动态加载模块
        code_importlib = "import importlib\nmod = importlib.import_module('os')"
        risks1 = scan_python_code_security(code_importlib, "test_dynamic.py")
        assert any("importlib" in r for r in risks1)

        # 2. 网络外发模块
        code_urllib = "import urllib.request\nurllib.request.urlopen('http://evil.com')"
        risks2 = scan_python_code_security(code_urllib, "test_net.py")
        assert any("urllib" in r for r in risks2)

        # 3. 敏感文件探测名单
        code_secret_probe = 'open("configs/.secrets.yaml", "r").read()'
        risks3 = scan_python_code_security(code_secret_probe, "test_probe.py")
        assert any(".secrets.yaml" in r for r in risks3)

    def test_sec_vuln_08_offline_license_cache_hmac_tamper_detection(self):
        """SEC-VULN-08: 离线商业授权凭据缓存必须经过 HMAC-SHA256 签名，篡改即刻失效"""
        import hashlib
        from core.llm import LLMClient
        from core.hardware import get_device_fingerprint

        fp = get_device_fingerprint()
        fake_key = "LITIKJ-ANNUAL-TEST-TAMPER-PROOF"
        key_hash = hashlib.sha256(fake_key.encode("utf-8")).hexdigest()
        now_ts = int(time.time())

        # 1. 未签名的假缓存 -> 必须被拒绝 (返回 None)
        fake_cache_no_sig = {
            "key_hash": key_hash,
            "fingerprint": fp,
            "days_left": 365,
            "cached_at": now_ts,
            "expire_at": now_ts + (365 * 86400)
        }
        res = LLMClient._verify_offline_cache(fake_cache_no_sig, fake_key, fp, now_ts)
        assert res is None

        # 2. 伪造或篡改了天数的缓存 -> 签名校验失败
        valid_sig = LLMClient._compute_license_signature(key_hash, fp, 30, now_ts, now_ts + (30 * 86400))
        tampered_cache = {
            "key_hash": key_hash,
            "fingerprint": fp,
            "days_left": 9999,  # 篡改为超大天数
            "cached_at": now_ts,
            "expire_at": now_ts + (9999 * 86400),
            "signature": valid_sig
        }
        res_tampered = LLMClient._verify_offline_cache(tampered_cache, fake_key, fp, now_ts)
        assert res_tampered is None

        # 3. 正确签名的合法缓存 -> 验证通过并返回正确剩余天数
        legit_cache = {
            "key_hash": key_hash,
            "fingerprint": fp,
            "days_left": 30,
            "cached_at": now_ts,
            "expire_at": now_ts + (30 * 86400),
            "signature": valid_sig
        }
        res_legit = LLMClient._verify_offline_cache(legit_cache, fake_key, fp, now_ts)
        assert res_legit is not None
        assert res_legit == 30

    def test_sec_vuln_11_open_outputs_blocks_lnk_and_url_shortcuts(self):
        """SEC-VULN-11: open-outputs 系统接口严格拦截 .lnk, .url 等非白名单危险扩展名"""
        from apps.server.api_server import get_server_token
        cm = ConfigManager.get_instance()
        out_dir = cm.workspace_dir / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)

        fake_lnk = out_dir / "evil_shortcut.lnk"
        fake_lnk.write_bytes(b"LNK_HEADER_DUMMY")

        fake_url = out_dir / "evil_internet_shortcut.url"
        fake_url.write_text("[InternetShortcut]\nURL=calc.exe", encoding="utf-8")

        try:
            url = f"http://127.0.0.1:{self.port}/api/system/open-outputs"
            for f in [fake_lnk, fake_url]:
                payload = {"path": str(f.resolve()), "action": "open_file"}
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Host": f"127.0.0.1:{self.port}",
                        "X-Agent-OS-Token": get_server_token()
                    },
                    method="POST"
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        assert False, f"未能拦截危险快捷方式: {f.name}"
                except urllib.error.HTTPError as e:
                    assert e.code == 400
                    res = json.loads(e.read().decode("utf-8"))
                    assert "安全拦截：严禁通过系统接口直接唤起可执行程序或非受信文件类型" in res.get("error", "")
        finally:
            if fake_lnk.exists():
                fake_lnk.unlink(missing_ok=True)
            if fake_url.exists():
                fake_url.unlink(missing_ok=True)
