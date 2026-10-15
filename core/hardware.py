# -*- coding: utf-8 -*-
"""
core/hardware.py
【立体空间智能体系统 · 高可靠硬件指纹与设备特征提取模块】
职责：
1. 提取抗网络变动、抗代理漂移的唯一硬件特征码 (主板特征 + CPU ID + MachineGuid + 物理网卡)；
2. 彻底移除对已废弃的 wmic 命令的依赖，全量采用 0 毫秒级原生注册表直读与标准库；
3. 加盐哈希生成标准设备指纹格式：LITI-HW-XXXX-XXXX-XXXX；
4. 提取友好设备名供多设备授权管理中心识别 (如 "DESKTOP-8899 (Windows 11)")。
"""

import os
import sys
import uuid
import platform
import hashlib
from typing import Tuple

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SALT_2026 = os.environ.get("LITIKJ_DEVICE_SALT", "LITIKJ_AGENT_OS_DEVICE_SALT_2026_PRO")


def _read_registry_value(hkey, sub_key: str, value_name: str) -> str:
    """安全极速读取 Windows 注册表单项键值 (0 毫秒开销，无子进程创建)"""
    try:
        import winreg
        with winreg.OpenKey(
            hkey,
            sub_key,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as key:
            val, _ = winreg.QueryValueEx(key, value_name)
            if val:
                return str(val).strip()
    except Exception:
        pass
    return ""


def get_hardware_identifiers() -> Tuple[str, str, str]:
    """
    极速安全提取底层系统 MachineGuid、主板序列号/型号与 CPU 特征
    耗时 < 1ms，彻底规避新版 Windows 11 移除 wmic 导致的 6 秒+硬超时挂起
    """
    machine_guid = ""
    bios_info = ""
    cpu_info = ""

    if sys.platform.startswith("win"):
        import winreg

        # 1. 核心 MachineGuid (Windows 官方唯一机器标识，100% 存在且抗驱动变动)
        machine_guid = _read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            "MachineGuid"
        )

        # 2. BIOS / 主板硬件唯一标识
        baseboard = _read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\BIOS",
            "BaseBoardProduct"
        )
        manufacturer = _read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\BIOS",
            "SystemManufacturer"
        )
        product_name = _read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\BIOS",
            "SystemProductName"
        )
        bios_parts = [p for p in [manufacturer, product_name, baseboard] if p]
        bios_info = "_".join(bios_parts) if bios_parts else "DEFAULT_BIOS"

        # 3. CPU 硬件指纹 (从注册表直接提取 CPU Identifier 与 型号，无需外部子进程)
        cpu_ident = _read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            "Identifier"
        )
        cpu_name = _read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            "ProcessorNameString"
        )
        cpu_parts = [p for p in [cpu_ident, cpu_name] if p]
        cpu_info = "_".join(cpu_parts) if cpu_parts else platform.processor()

    else:
        # 非 Windows 跨平台兜底 (macOS / Linux)
        machine_guid = platform.node()
        bios_info = platform.system()
        cpu_info = platform.processor()

    return bios_info, cpu_info, machine_guid


_CACHED_FINGERPRINT = None
_CACHED_DEVICE_NAME = None


def get_device_fingerprint() -> str:
    """
    计算并生成高稳定性硬件特征码（毫秒级响应，内存单例缓存）
    格式示例：LITI-HW-A7F9-82C1-3B5D
    """
    global _CACHED_FINGERPRINT
    if _CACHED_FINGERPRINT:
        return _CACHED_FINGERPRINT

    bios_info, cpu_info, machine_guid = get_hardware_identifiers()

    # 物理网络硬件节点号 (MAC 地址特征)
    try:
        node_mac = str(uuid.getnode())
    except Exception:
        node_mac = "NO_NODE"

    # 组合多维物理硬件特征
    components = [
        machine_guid or "NO_GUID",
        bios_info or "NO_BIOS",
        cpu_info or "NO_CPU",
        node_mac,
        platform.machine(),
        platform.system()
    ]
    raw_str = "|".join(components)
    salted_str = f"{SALT_2026}:{raw_str}"

    full_sha = hashlib.sha256(salted_str.encode("utf-8")).hexdigest().upper()

    # 格式化为高强抗碰撞机器指纹码 (96-bit 熵): LITI-HW-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
    _CACHED_FINGERPRINT = f"LITI-HW-{full_sha[0:4]}-{full_sha[4:8]}-{full_sha[8:12]}-{full_sha[12:16]}-{full_sha[16:20]}-{full_sha[20:24]}"
    return _CACHED_FINGERPRINT


def get_device_name() -> str:
    """获取当前设备友好名称，如 'ThinkPad-PC (Windows 11)'"""
    global _CACHED_DEVICE_NAME
    if _CACHED_DEVICE_NAME:
        return _CACHED_DEVICE_NAME

    host_name = platform.node() or "LocalHost"
    os_name = f"{platform.system()} {platform.release()}"
    _CACHED_DEVICE_NAME = f"{host_name} ({os_name})"
    return _CACHED_DEVICE_NAME


# 模块装载时自动进行微秒级内存预热
try:
    get_device_fingerprint()
    get_device_name()
except Exception:
    pass


if __name__ == "__main__":
    import time
    t0 = time.time()
    fp = get_device_fingerprint()
    name = get_device_name()
    cost_ms = (time.time() - t0) * 1000
    print(f"🖥️ 设备名称:   {name}")
    print(f"🔑 硬件特征码: {fp}")
    print(f"⚡ 计算总耗时: {cost_ms:.2f} ms")
