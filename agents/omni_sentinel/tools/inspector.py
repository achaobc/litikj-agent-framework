# -*- coding: utf-8 -*-
"""
agents/omni_sentinel/tools/inspector.py
【全维调度演示智能体 · 0-Token 纯代码巡检工具】
特点：
1. 100% 纯 Python 原生标准库实现，零三方库强制依赖；
2. 毫秒级快速采集宿主系统信息、磁盘空间、工作区状态与框架运行指标；
3. 为 0-Token Fast-Path、定时打卡与事件诊断提供扎实的确定性数据底座。
"""

import os
import sys
import time
import shutil
import platform
from pathlib import Path
from typing import Dict, Any


class SystemInspector:
    """系统极速诊断巡检器 (0-Token)"""

    @staticmethod
    def get_system_metrics() -> Dict[str, Any]:
        """采集当前操作系统与宿主运行时指标"""
        # 1. 基础环境信息
        os_name = f"{platform.system()} {platform.release()} ({platform.machine()})"
        py_version = platform.python_version()

        # 2. 磁盘空间检测 (以当前工作目录所在盘符为准)
        try:
            cwd = Path.cwd()
            disk = shutil.disk_usage(cwd)
            disk_total_gb = round(disk.total / (1024 ** 3), 2)
            disk_used_gb = round(disk.used / (1024 ** 3), 2)
            disk_free_gb = round(disk.free / (1024 ** 3), 2)
            disk_percent = round((disk.used / disk.total) * 100, 1)
        except Exception:
            disk_total_gb = disk_used_gb = disk_free_gb = disk_percent = 0.0

        # 3. 内存与负载 (若环境安装了 psutil 则丰富采集，否则优雅降级)
        mem_info = "标准库环境 (未安装额外负载探针)"
        try:
            import psutil
            vm = psutil.virtual_memory()
            mem_info = f"总量 {round(vm.total / (1024**3), 1)}GB | 已用 {round(vm.used / (1024**3), 1)}GB ({vm.percent}%)"
        except ImportError:
            pass

        return {
            "os": os_name,
            "python": py_version,
            "disk_total_gb": disk_total_gb,
            "disk_used_gb": disk_used_gb,
            "disk_free_gb": disk_free_gb,
            "disk_percent": disk_percent,
            "memory": mem_info,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    @classmethod
    def format_quick_status(cls, agent_count: int = 0) -> str:
        """生成 0-Token 终端快速直达状态摘要 (标准 Markdown 规范)"""
        m = cls.get_system_metrics()
        return (
            f"### ⚡ [0-Token 快速直达] 全维哨兵底座巡检状态\n\n"
            f"- 🖥️ **系统环境**：`{m['os']}`\n"
            f"- 🐍 **Python 版本**：`v{m['python']}`\n"
            f"- 💾 **磁盘占用**：`{m['disk_used_gb']} GB / {m['disk_total_gb']} GB` ({m['disk_percent']}% 已用, 剩余 `{m['disk_free_gb']} GB`)\n"
            f"- 🧠 **内存状态**：`{m['memory']}`\n"
            f"- 🤖 **活跃智能体**：`{agent_count} 个已挂载`\n"
            f"- ⏱️ **巡检时间**：`{m['timestamp']}`\n"
            f"- 🏷️ **消耗 Token**：`0 Token (纯代码原生驱动，耗时 < 5ms)`"
        )

    @classmethod
    def generate_markdown_report(cls, agent_names: list, trigger_type: str = "定时周期调度") -> str:
        """生成 Markdown 格式的完整健康巡检报告"""
        m = cls.get_system_metrics()
        agent_list_md = "\n".join([f"- `[{name}]`" for name in agent_names]) if agent_names else "- (暂无已激活智能体)"

        return f"""# 🛡️ 立体空间系统健康巡检报告 (OmniSentinel Report)

- **生成时间**：{m['timestamp']}
- **触发机制**：`{trigger_type}`
- **Token 消耗**：`0 Token (纯确定性软件工程直达)`

---

## 🖥️ 1. 宿主底座与硬件资源
| 指标项 | 状态值 |
| :--- | :--- |
| **操作系统** | `{m['os']}` |
| **Python 解释器** | `v{m['python']}` |
| **磁盘总容量** | `{m['disk_total_gb']} GB` |
| **磁盘剩余空间** | `{m['disk_free_gb']} GB (使用率 {m['disk_percent']}%)` |
| **内存指标** | `{m['memory']}` |

---

## 🤖 2. 已激活智能体插槽 ({len(agent_names)} 个)
{agent_list_md}

---

## 💡 3. 架构理念提示 (Architecture Wisdom)
> "不要试图用大模型去替代确定性的 Python 循环与系统调用。  
> **软件归软件，AI 归 AI** —— 只有用坚固的软件架构做骨架，以大模型做认知大脑，才能打造低成本、零死循环、可商业交付的商业级 Agent 闭环！"
"""
