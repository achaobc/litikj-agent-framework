# -*- coding: utf-8 -*-
"""
core/llm.py
【立体空间智能体系统 · 统一大模型网关客户端 (LLMClient)】
职责：
1. 纯原生标准库实现，零第三方 pip 依赖 (免 requests / openai 安装困扰)；
2. 双轨制通信路由：
   - cloud 模式：自动携带 license_key 鉴权请求立体空间官方云端中枢；
   - custom 模式：请求用户自备的兼容 OpenAI 规范的任何大模型接口 (DeepSeek/Qwen/Ollama等)；
3. 支持同步完整响应与流式分块输出 (Streaming)。
"""

import os
import sys
import time
import json
import ssl
import hashlib
import hmac
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional, Iterator, Tuple

from .config import ConfigManager, GatewayConfig
from .quota import (
    QuotaManager,
    LLMError,
    LLMQuotaError,
    QuotaExhaustedError,
    RateLimitError,
    DailyLimitExceededError
)


class AuthError(LLMError):
    """授权鉴权失效异常"""
    pass


class LLMClient:
    """统一大模型网关客户端"""

    @classmethod
    def _get_config(cls) -> GatewayConfig:
        return ConfigManager.get_instance().gateway

    @classmethod
    def _build_request_params(cls, messages: List[Dict[str, str]], temperature: Optional[float] = None) -> Tuple[str, Dict[str, str], dict]:
        cfg = cls._get_config()
        temp = temperature if temperature is not None else cfg.custom_temperature

        if cfg.mode == "custom":
            # 极客自备 Key 模式 / Ollama 离线本地模式
            url = f"{cfg.custom_base_url.rstrip('/')}/chat/completions"
            headers = {
                "Content-Type": "application/json"
            }
            if cfg.custom_api_key.strip():
                headers["Authorization"] = f"Bearer {cfg.custom_api_key.strip()}"
            body = {
                "model": cfg.custom_model,
                "messages": messages,
                "temperature": temp
            }
        else:
            # 官方云端中枢模式 (携带 License 鉴权)
            url = f"{cfg.endpoint.rstrip('/')}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.license_key.strip()}",
                "X-Litikj-OS-Version": ConfigManager.get_instance().version
            }
            body = {
                "messages": messages,
                "temperature": temp
            }

        return url, headers, body

    @classmethod
    def _create_ssl_context(cls) -> ssl.SSLContext:
        """创建安全的 SSL 传输凭证（默认校验对端证书，仅在显式配置时允许忽略）"""
        ctx = ssl.create_default_context()
        if os.environ.get("LITIKJ_ALLOW_INSECURE_SSL") == "1":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    @classmethod
    def _parse_and_raise_gateway_error(cls, e: urllib.error.HTTPError, qm: QuotaManager):
        """
        统一解析云端大模型网关返回的标准化错误 JSON 并分流为精准异常：
        1. 401: AuthError (授权失效或未激活)
        2. 429/402:
           - DAILY_LIMIT_EXCEEDED -> DailyLimitExceededError (单日硬顶限额 100,000 Token/日)
           - QUOTA_EXHAUSTED / 402 -> QuotaExhaustedError (总算力额度耗尽)
           - RATE_LIMIT_EXCEEDED -> RateLimitError (30 RPM 短时限频)
        """
        if e.code == 401:
            raise AuthError("❌ [商业授权拦截] 您的授权凭证无效或已到期，请登录官网控制台 (litikj.com) 激活续费或联系阿朝微信！")

        if e.code in (429, 402):
            err_text = ""
            try:
                err_text = e.read().decode("utf-8")
            except Exception:
                pass

            server_code = ""
            server_msg = ""
            if err_text:
                try:
                    err_json = json.loads(err_text)
                    if isinstance(err_json, dict) and "error" in err_json:
                        err_obj = err_json["error"]
                        server_code = str(err_obj.get("code", "")).upper()
                        server_msg = str(err_obj.get("message", "")).strip()
                except Exception:
                    pass

            # 1. 单日硬顶限额拦截 (方案 A 严格风控)
            if server_code == "DAILY_LIMIT_EXCEEDED" or "daily_limit" in err_text.lower() or "单日" in err_text:
                daily_limit_val = qm.get_status().daily_limit or 100_000
                msg = server_msg or f"今日 AI 算力限额已达上限 ({daily_limit_val:,} Token/日)，将于明日 0:00 自动恢复。如需加急使用请联系助教/管理员提额。"
                raise DailyLimitExceededError(f"🛡️ [单日防刷保护] {msg}")

            # 2. 剩余总算力配额耗尽
            if (
                server_code == "QUOTA_EXHAUSTED"
                or e.code == 402
                or "exhaust" in err_text.lower()
                or ("quota" in err_text.lower() and "exceed" not in err_text.lower())
            ):
                qm.get_status().remaining = 0
                qm._save_cache()
                msg = server_msg or (
                    "您的专属官方体验算力总配额已达到上限！\n"
                    "请前往官网学员中心 (litikj.com) 增购算力加油包，或一键切换自备 Key / 离线 Ollama。"
                )
                raise QuotaExhaustedError(f"❌ [官方算力额度已耗尽] {msg}")

            # 3. 短时 RPM 限频 (30 次/分钟)
            if server_code == "RATE_LIMIT_EXCEEDED" or "rate_limit" in err_text.lower() or "频繁" in err_text or "频" in err_text:
                msg = server_msg or "短时请求过于频繁 (已达 30 次/分钟 RPM 限频保护)，请稍等片刻后重试。"
                raise RateLimitError(f"⚠️ [频控保护] {msg}")

            fallback_msg = server_msg or "当前请求受限，请稍候再试。"
            raise RateLimitError(f"⚠️ [请求受限] {fallback_msg}")

        try:
            err_msg = e.read().decode("utf-8")
        except Exception:
            err_msg = str(e)
        raise LLMError(f"HTTP 错误 ({e.code}): {err_msg}")

    @classmethod
    def chat(cls, messages: List[Dict[str, str]], temperature: Optional[float] = None, timeout: int = 45) -> str:
        """同步发起对话，返回完整文本"""
        cfg = cls._get_config()
        qm = QuotaManager.get_instance()

        # 1. 客户端本地高频防刷防抖 (仅针对官方云端模式)
        if cfg.mode == "cloud":
            qm.check_rate_limit(cfg.rate_limit_interval)

        # 2. 单次最大输入字符截断与上下文安全保护
        messages, was_truncated, total_chars = qm.truncate_messages(messages, cfg.max_input_chars)

        # 3. 官方云端模式下检查当前配额是否已用尽
        if cfg.mode == "cloud" and qm.get_status().remaining <= 0:
            raise QuotaExhaustedError(
                "❌ [官方算力额度已耗尽] 您的专属体验算力池已用尽 (剩余 0 点)！\n\n"
                "💡 解决方案：\n"
                "1. 增购算力加油包即充即用；\n"
                "2. 在系统设置中一键切换为【自备 API Key】或【本地 Ollama 私有模型】，永久免额度无限制！"
            )

        url, headers, body = cls._build_request_params(messages, temperature)
        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        ctx = cls._create_ssl_context()

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                # 捕获并解析云端配额响应头
                qm.update_from_headers(resp.headers)

                resp_text = resp.read().decode("utf-8")
                resp_json = json.loads(resp_text)
                choices = resp_json.get("choices", [])
                reply_text = ""
                if choices:
                    reply_text = choices[0].get("message", {}).get("content", "").strip()
                else:
                    reply_text = resp_json.get("reply", resp_text).strip()

                # 如果云端未返回专用配额 Header，在 cloud 模式下按字数进行本地额度预扣记账
                has_quota_header = any(
                    h.lower() == "x-litikj-quota-remaining"
                    for h, _ in getattr(resp, "headers", {}).items()
                ) if hasattr(getattr(resp, "headers", None), "items") else False

                if cfg.mode == "cloud" and not has_quota_header:
                    qm.consume_local_estimate(total_chars, len(reply_text))

                return reply_text
        except urllib.error.HTTPError as e:
            cls._parse_and_raise_gateway_error(e, qm)
        except urllib.error.URLError as e:
            raise LLMError(f"❌ [网络连接失败] 无法连通大模型服务器 ({url}): {e.reason}")
        except Exception as e:
            if isinstance(e, LLMError):
                raise e
            raise LLMError(f"大模型通信异常: {e}")

    @classmethod
    def stream_chat(cls, messages: List[Dict[str, str]], temperature: Optional[float] = None, timeout: int = 45) -> Iterator[str]:
        """流式分块输出 (SSE 增量推送)"""
        cfg = cls._get_config()
        qm = QuotaManager.get_instance()

        # 1. 客户端本地高频防刷防抖 (仅针对官方云端模式)
        if cfg.mode == "cloud":
            qm.check_rate_limit(cfg.rate_limit_interval)

        # 2. 单次最大输入字符截断与上下文安全保护
        messages, was_truncated, total_chars = qm.truncate_messages(messages, cfg.max_input_chars)

        # 3. 官方云端模式下检查当前配额是否已用尽
        if cfg.mode == "cloud" and qm.get_status().remaining <= 0:
            raise QuotaExhaustedError(
                "❌ [官方算力额度已耗尽] 您的专属体验算力池已用尽 (剩余 0 点)！\n\n"
                "💡 解决方案：\n"
                "1. 增购算力加油包即充即用；\n"
                "2. 在系统设置中一键切换为【自备 API Key】或【本地 Ollama 私有模型】，永久免额度无限制！"
            )

        url, headers, body = cls._build_request_params(messages, temperature)
        body["stream"] = True
        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        ctx = cls._create_ssl_context()

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                qm.update_from_headers(resp.headers)
                accumulated_len = 0
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if not line_str or line_str.startswith(":"):
                        continue
                    if line_str.startswith("data:"):
                        payload = line_str[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            delta_json = json.loads(payload)
                            choices = delta_json.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {}).get("content", "")
                                if delta:
                                    accumulated_len += len(delta)
                                    yield delta
                        except Exception:
                            continue

                has_quota_header = any(
                    h.lower() == "x-litikj-quota-remaining"
                    for h, _ in getattr(resp, "headers", {}).items()
                ) if hasattr(getattr(resp, "headers", None), "items") else False

                if cfg.mode == "cloud" and not has_quota_header:
                    qm.consume_local_estimate(total_chars, accumulated_len)

        except urllib.error.HTTPError as e:
            cls._parse_and_raise_gateway_error(e, qm)
        except Exception as e:
            if isinstance(e, LLMError):
                raise e
            raise LLMError(f"流式通信中断: {e}")

    _license_mem_cache: Dict[str, Any] = {}
    _LICENSE_HMAC_SALT = os.environ.get("AGENTOS_OFFLINE_SALT", "open-source-default-offline-salt").encode("utf-8")

    @classmethod
    def _compute_license_signature(cls, key_hash: str, fingerprint: str, days_left: int, cached_at: int, expire_at: int) -> str:
        payload = f"{key_hash}:{fingerprint}:{int(days_left)}:{int(cached_at)}:{int(expire_at)}".encode("utf-8")
        return hmac.new(cls._LICENSE_HMAC_SALT, payload, hashlib.sha256).hexdigest()

    @classmethod
    def _verify_offline_cache(cls, c_data: dict, key: str, fingerprint: str, now_ts: float) -> Optional[int]:
        """校验本地离线授权凭据的完整性与防篡改签名 (SEC-VULN-08)。若合法返回剩余天数，否则返回 None"""
        if not isinstance(c_data, dict):
            return None
        key_hash = c_data.get("key_hash")
        fp = c_data.get("fingerprint")
        sig = c_data.get("signature")
        cached_at = c_data.get("cached_at", 0)
        expire_at = c_data.get("expire_at", 0)
        days_left = c_data.get("days_left", 0)

        if not (key_hash and fp and sig):
            return None

        # 1. 验证卡密 SHA-256 与设备指纹
        expected_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(key_hash, expected_hash):
            return None
        if fp != fingerprint:
            return None

        # 2. 验证宽限期（最长离线7天）与到期日
        if now_ts > cached_at + (7 * 86400) or now_ts > expire_at:
            return None

        # 3. 验证 HMAC-SHA256 签名，杜绝本地篡改伪造
        expected_sig = cls._compute_license_signature(key_hash, fp, days_left, int(cached_at), int(expire_at))
        if not hmac.compare_digest(sig, expected_sig):
            return None

        return max(0, int((expire_at - now_ts) / 86400))

    @classmethod
    def verify_license(cls, target_mode: Optional[str] = None, license_key: Optional[str] = None, force_network: bool = False) -> Tuple[bool, str]:
        """轻量检查当前授权或模型连接状态（包含硬件设备特征校验与 3 台配额管理）"""
        cfg = cls._get_config()
        current_mode = target_mode or cfg.mode
        if current_mode != "cloud":
            return True, "Local Developer Mode (Offline Ready)"
        

        
        # cloud 模式
        key = (license_key if license_key is not None else cfg.license_key).strip()
        if not key:
            return False, "官方中枢模式：缺少专属卡密 (请在系统设置中绑定微店激活卡密)"
        
        from .hardware import get_device_fingerprint, get_device_name
        fingerprint = get_device_fingerprint()
        dev_name = get_device_name()

        # 本地开发与单元测试桩白名单 (仅在严格处于开发/测试环境直通, 生产环境杜绝单边绕过 SEC-05)
        cm = ConfigManager.get_instance()
        is_dev_env = cm.is_dev_mode or os.environ.get("LITIKJ_DEV_MODE") == "1" or "PYTEST_CURRENT_TEST" in os.environ or "unittest" in sys.modules
        if is_dev_env and key.startswith(("TEST-", "DEV-")):
            masked = key if len(key) <= 8 else f"{key[:4]}****{key[-4:]}"
            return True, f"立体空间·商业级 AI 智能体操作系统 (Litikj Agent OS) - 年度会员 [内测授权: {masked}] (设备指纹: {fingerprint})"

        cache_dir = ConfigManager.get_instance().workspace_dir / "data"
        cache_file = cache_dir / ".license_cache.json"

        # 🚀 快速路径：非强制联网模式下优先命中内存缓存与本地凭据，0ms 秒级响应，杜绝日常发消息阻塞
        now_ts = time.time()
        if not force_network:
            mem = cls._license_mem_cache.get(key)
            if mem and mem.get("valid") and now_ts <= mem.get("ts", 0) + 600:
                return True, mem.get("msg", "商业授权正常")

            if cache_file.exists():
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                    remaining_days = cls._verify_offline_cache(c_data, key, fingerprint, now_ts)
                    if remaining_days is not None:
                        msg = f"立体空间·商业级 AI 智能体操作系统 (Litikj Agent OS) - 年度会员 [有效: {remaining_days}天] (设备指纹: {fingerprint})"
                        cls._license_mem_cache[key] = {"valid": True, "msg": msg, "ts": now_ts}
                        return True, msg
                except Exception:
                    pass

        # 尝试向官方中枢 /api/licenses/client-verify 进行联网设备校验
        endpoint_base = cfg.endpoint.rstrip('/')
        if "api.litikj.com" in endpoint_base:
            endpoint_base = endpoint_base.replace("api.litikj.com", "www.litikj.com")
        if endpoint_base.endswith("/v1"):
            verify_url = endpoint_base[:-3].rstrip('/') + "/api/licenses/client-verify"
        elif endpoint_base.endswith("/api"):
            verify_url = endpoint_base + "/licenses/client-verify"
        else:
            verify_url = endpoint_base + "/api/licenses/client-verify"
        if not verify_url.startswith("http"):
            verify_url = "https://www.litikj.com/api/licenses/client-verify"

        payload = {
            "code": key,
            "deviceId": fingerprint,
            "deviceName": dev_name,
            "clientVersion": ConfigManager.get_instance().version
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                verify_url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            ctx = cls._create_ssl_context()

            with urllib.request.urlopen(req, context=ctx, timeout=4) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if res_data.get("valid"):
                    dev_info = res_data.get("device") or {}
                    seat_info = f"设备席位: {dev_info.get('deviceCount', 1)}/3 台"
                    days_left = res_data.get("daysLeft", 365)

                    # 写入经硬件指纹、卡密哈希与 HMAC 防篡改数字签名的本地离线安全缓存凭据 (宽限期7天 SEC-VULN-08)
                    try:
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        now_int = int(time.time())
                        expire_int = now_int + (days_left * 86400)
                        k_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
                        server_sig = res_data.get("signature") or res_data.get("server_signature")
                        sig = server_sig or cls._compute_license_signature(k_hash, fingerprint, days_left, now_int, expire_int)
                        cache_payload = {
                            "key_hash": k_hash,
                            "fingerprint": fingerprint,
                            "days_left": days_left,
                            "cached_at": now_int,
                            "expire_at": expire_int,
                            "signature": sig,
                            "server_verified": bool(server_sig)
                        }
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(cache_payload, f)
                    except Exception:
                        pass

                    msg = f"立体空间·商业级 AI 智能体操作系统 (Litikj Agent OS) - 年度会员 [有效: {days_left}天, {seat_info}]"
                    cls._license_mem_cache[key] = {"valid": True, "msg": msg, "ts": time.time()}
                    return True, msg
                else:
                    msg = res_data.get("message", "商业授权无效")
                    cls._license_mem_cache[key] = {"valid": False, "msg": msg, "ts": time.time()}
                    return False, msg
        except urllib.error.HTTPError as he:
            try:
                err_body = json.loads(he.read().decode("utf-8"))
                if err_body.get("code") == "DEVICE_LIMIT_EXCEEDED":
                    return False, "❌ 设备授权超限：当前卡密已达到 3 台设备上限！请在立体空间官网【学员交付控制台】解绑闲置设备后再试。"
                return False, err_body.get("message", f"商业授权校验未通过 (HTTP {he.code})")
            except Exception:
                pass
            return False, f"商业授权校验未通过 (HTTP {he.code})"
        except Exception:
            # 网络离线或连接超时：严格核验最近 7 天内的合法离线缓存凭据与防篡改签名 (SEC-VULN-08)
            try:
                if cache_file.exists():
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                    remaining_days = cls._verify_offline_cache(cache_data, key, fingerprint, time.time())
                    if remaining_days is not None:
                        return True, f"立体空间·商业级 AI 智能体操作系统 (Litikj Agent OS) - 年度会员 [离线安全容灾模式: 剩余 {remaining_days}天] (设备指纹: {fingerprint})"
            except Exception:
                pass

            return False, "无法连接官方鉴权中枢，且未检测到有效的离线安全授权凭据。首次使用请保持网络畅通进行激活！"

    @classmethod
    def test_connection(cls, mode: str = "custom", base_url: str = "", api_key: str = "", model: str = "", timeout: int = 8) -> Tuple[bool, int, str]:
        """统一连通性测试探针 (测速与健康度)"""
        import time
        t0 = time.time()
        if mode == "cloud":
            valid, msg = cls.verify_license(target_mode="cloud", force_network=True)
            latency = int((time.time() - t0) * 1000)
            return valid, latency, msg

        # custom / ollama 模式
        target_url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key.strip():
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        
        test_body = {
            "model": model or "default",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5
        }
        data_bytes = json.dumps(test_body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(target_url, data=data_bytes, headers=headers, method="POST")
        ctx = cls._create_ssl_context()

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                resp_text = resp.read().decode("utf-8")
                latency = int((time.time() - t0) * 1000)
                return True, latency, f"连通成功！往返延迟 {latency}ms"
        except urllib.error.HTTPError as e:
            latency = int((time.time() - t0) * 1000)
            if e.code == 401:
                return False, latency, "认证失败 (HTTP 401: API Key 无效或未授权)"
            elif e.code == 404:
                return False, latency, f"模型或接口未找到 (HTTP 404: 请检查 Model 名称 '{model}' 或路径)"
            return False, latency, f"接口返回 HTTP {e.code}"
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            return False, latency, f"连接失败: {str(e)}"

    @classmethod
    def generate_image(cls, prompt: str, model: str = "black-forest-labs/flux-1-schnell", size: str = "1280x720", timeout: int = 60) -> Optional[bytes]:
        """
        调用大模型网关生图能力（兼容 OpenRouter / OpenAI Images 规范）
        :param prompt: 画面提示词
        :param model: 生图模型（默认 flux-1-schnell）
        :param size: 画布尺寸（默认 1280x720 对应 16:9）
        :return: 图片的二进制字节流 (bytes) 或 None
        """
        cfg = cls._get_config()
        qm = QuotaManager.get_instance()

        # 计入用户配额开销 (预扣/计量生图单次当量约为 2000 token)
        if cfg.mode == "cloud":
            qm.check_rate_limit(cfg.rate_limit_interval)
            if qm.get_status().remaining <= 0:
                raise QuotaExhaustedError("❌ [算力额度已耗尽] 您的算力点数已不足以生成 AI 封面！")
            qm.consume_local_estimate(len(prompt), 2000)

        # 构造请求参数
        if cfg.mode == "custom":
            base_url = cfg.custom_base_url.rstrip('/')
            api_key = cfg.custom_api_key.strip()
            # 兼容 OpenRouter: 如果 base_url 包含 openrouter，则生图走 /api/v1/images
            target_model = model
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            if "openrouter.ai" in base_url:
                url = f"{base_url}/images" if base_url.endswith("/v1") else f"{base_url}/api/v1/images"
                body = {
                    "model": target_model,
                    "prompt": prompt
                }
            elif base_url.endswith("/v1"):
                url = f"{base_url}/images/generations"
                body = {
                    "prompt": prompt,
                    "model": target_model,
                    "n": 1,
                    "size": size,
                    "response_format": "b64_json"
                }
            else:
                url = f"{base_url}/v1/images/generations" if "api" in base_url else f"{base_url}/images/generations"
                body = {
                    "prompt": prompt,
                    "model": target_model,
                    "n": 1,
                    "size": size,
                    "response_format": "b64_json"
                }
        else:
            # 官方云端中枢
            url = f"{cfg.endpoint.rstrip('/')}/images/generations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.license_key.strip()}",
                "X-Litikj-OS-Version": ConfigManager.get_instance().version
            }
            body = {
                "prompt": prompt,
                "model": model,
                "size": size
            }

        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        ctx = cls._create_ssl_context()

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                resp_text = resp.read().decode("utf-8")
                resp_json = json.loads(resp_text)
                data_list = resp_json.get("data", [])
                if not data_list:
                    return None
                
                first_item = data_list[0]
                # 1. 优先提取 b64_json
                if "b64_json" in first_item:
                    import base64
                    return base64.b64decode(first_item["b64_json"])
                # 2. 提取 url 并下载
                elif "url" in first_item:
                    img_url = first_item["url"]
                    dl_req = urllib.request.Request(img_url, headers={"User-Agent": "LitikjAgentOS/2.5.0"})
                    with urllib.request.urlopen(dl_req, context=ctx, timeout=30) as dl_resp:
                        return dl_resp.read()
                return None
        except Exception as e:
            # 打印警告日志并优雅降级，允许外层回退至本地确定性排版
            print(f"[LLMClient Image Warning] 调用生图模型失败 ({e})，将回退至本地渲染引擎。")
            return None

    @classmethod
    def detect_ollama(cls, host: str = "http://127.0.0.1:11434", timeout: int = 3) -> Tuple[bool, List[str]]:
        """探测本地 Ollama 实例并获取已下载的模型列表"""
        tags_url = f"{host.rstrip('/')}/api/tags"
        req = urllib.request.Request(tags_url, headers={"Content-Type": "application/json"}, method="GET")
        ctx = cls._create_ssl_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                return True, models
        except Exception:
            return False, []

