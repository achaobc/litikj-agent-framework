# -*- coding: utf-8 -*-
"""
core/security.py
【立体空间智能体系统 · 核心安全治理与沙箱防御组件】

职责：
1. 统一标识符安全白名单审查（防目录穿越与任意文件/目录删除 SEC-11）
2. 物理目录沙箱边界断言（严格限制操作范围在指定父目录内）
3. 恒定时间密码学比对（防时序侧信道分析攻击）
"""

import re
import hmac
from pathlib import Path
from typing import Union, List, Optional, Any

# 严格的合法标识符正则：仅限英文字母、数字、下划线及连字符 (1-64位)
SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_safe_id(identifier: str, entity_name: str = "实体") -> str:
    """
    🛡️ SEC-11: 严格校验标识符字符集
    阻断任何 ..、/、\\、空格、冒号、空字节等路径穿越与特殊字符
    """
    clean_id = (identifier or "").strip()
    if not clean_id or not SAFE_ID_REGEX.match(clean_id):
        raise ValueError(
            f"非法{entity_name}标识符 [{clean_id}]：仅允许包含英文字母、数字、下划线及连字符 (1-64位)，严禁包含路径遍历字符 (SEC-11)"
        )
    return clean_id


def validate_safe_id_and_resolve_dir(
    identifier: str,
    parent_dir: Union[str, Path],
    entity_name: str = "实体",
    must_exist: bool = False
) -> Path:
    """
    🛡️ SEC-11: 严格校验标识符并在沙箱父目录下安全解析目标物理路径
    
    安全断言：
    1. 标识符必须满足 SAFE_ID_REGEX 白名单；
    2. 目标路径 resolve() 后的直接父目录必须严格等于 parent_dir 的 resolve() 路径；
    3. 目标路径绝对不可等于 parent_dir 或系统根目录自身；
    4. 若 must_exist=True，则要求物理目录必须已存在。
    """
    clean_id = validate_safe_id(identifier, entity_name)
    parent_path = Path(parent_dir).resolve()

    target_path = (parent_path / clean_id).resolve()

    # 断言 1: 真实父级目录必须严格等于预期的父目录
    if target_path.parent != parent_path:
        raise PermissionError(f"安全拦截：检测到跨目录越权操作 [{clean_id}]，已阻断潜在路径遍历攻击 (SEC-11)")

    # 断言 2: 目标路径绝对不可等于父目录自身或上一级
    if target_path == parent_path or target_path == target_path.parent:
        raise PermissionError(f"安全拦截：禁止操作受保护的沙箱容器根目录 (SEC-11)")

    # 断言 3: 归属边界检查
    try:
        if not target_path.is_relative_to(parent_path):
            raise PermissionError(f"安全拦截：目标路径超出所属沙箱范围 (SEC-11)")
    except AttributeError:
        if not str(target_path).startswith(str(parent_path)):
            raise PermissionError(f"安全拦截：目标路径超出所属沙箱范围 (SEC-11)")

    if must_exist and not target_path.exists():
        raise FileNotFoundError(f"未找到目标{entity_name}目录: {clean_id}")

    return target_path


def constant_time_compare(val1: str, val2: str) -> bool:
    """
    🛡️ 恒定时间字符串比对（防御时序侧信道分析攻击 Timing Attacks）
    """
    if not isinstance(val1, str) or not isinstance(val2, str):
        return False
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


def safe_extract_zip(
    zip_source: Union[Any, bytes, str, Path],
    target_dir: Union[str, Path],
    ignore_files: Optional[set] = None
) -> List[Path]:
    """
    🛡️ 严防 Zip Slip 与任意路径穿越的安全解压函数 (SEC-02 / SEC-03)
    1. 支持 zipfile.ZipFile 对象、二进制字节流 (bytes) 或 zip 物理文件路径；
    2. 严格拦截 ':' (Windows盘符/流)、'..'、绝对路径、UNC 路径；
    3. 校验 dest.resolve().is_relative_to(target_dir.resolve())，防止同名同前缀绕过；
    4. 自动创建安全目标目录，返回所有解压落盘的物理文件绝对路径列表。
    """
    import os
    import shutil
    import zipfile
    import io

    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    ignore_set = ignore_files or set()
    extracted_paths: List[Path] = []

    def _do_extract(zf: zipfile.ZipFile):
        target_str = str(target_dir)
        if not target_str.endswith((os.sep, "/")):
            target_str += os.sep

        for member in zf.infolist():
            filename = member.filename.replace("\\", "/")
            if not filename or filename in ignore_set:
                continue
            if member.is_dir():
                continue
            # 严格拦截跨平台路径穿越与 Windows 盘符特征
            if ":" in filename or ".." in filename or filename.startswith(("/", "\\")):
                continue

            dest_path = (target_dir / filename).resolve()
            # 物理边界严格断言
            try:
                if not dest_path.is_relative_to(target_dir):
                    continue
            except (ValueError, AttributeError):
                if not str(dest_path).startswith(target_str):
                    continue

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(dest_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted_paths.append(dest_path)

    if isinstance(zip_source, zipfile.ZipFile):
        _do_extract(zip_source)
    elif isinstance(zip_source, (bytes, bytearray)):
        with zipfile.ZipFile(io.BytesIO(zip_source), "r") as zf:
            _do_extract(zf)
    elif hasattr(zip_source, "read") and hasattr(zip_source, "seek"):
        with zipfile.ZipFile(zip_source, "r") as zf:
            _do_extract(zf)
    else:
        zip_path = Path(zip_source).resolve()
        with zipfile.ZipFile(zip_path, "r") as zf:
            _do_extract(zf)

    return extracted_paths

