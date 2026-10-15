# -*- coding: utf-8 -*-
"""
skills/custom/hello_skill/entry.py
【开源示范原子技能 · Hello Skill】
职责：
1. 演示 BaseSkill 标准子类契约；
2. 接收结构化入参并执行业务逻辑；
3. 输出标准化落盘产物至 workspace/outputs/hello/ 并返回 file_path；
4. 暴露 setup(registry) 动态注册钩子。
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any

from core.contract import BaseSkill
from core.config import ConfigManager
from core.registry import Registry


class HelloSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="hello_skill",
            display_name="示范问候与打卡技能",
            description="开源微内核标准示范技能：演示参数传递、结构化输出与产物落盘",
            version="1.0.0",
            author="Litikj Open Source Team",
            icon="👋",
            category="开发示范",
            origin="custom"
        )
        self.inputs = [
            {"name": "name", "type": "string", "desc": "问候对象名称"},
            {"name": "topic", "type": "string", "desc": "交互主题"}
        ]
        self.outputs = [
            {"name": "message", "type": "string", "desc": "生成的问候消息"},
            {"name": "file_path", "type": "string", "desc": "落盘保存的成果文件路径"}
        ]

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        核心执行入口
        :param params:
          - name (str, 可选): 问候对象
          - topic (str, 可选): 交互主题
        """
        target_name = params.get("name") or params.get("topic") or "开发者"
        topic = params.get("topic") or "开源智能体开发"

        cm = ConfigManager.get_instance()
        out_dir = cm.workspace_dir / "outputs" / "hello"
        out_dir.mkdir(parents=True, exist_ok=True)

        out_file = out_dir / f"hello_{int(time.time())}.json"
        payload = {
            "name": target_name,
            "topic": topic,
            "greeting": f"你好，{target_name}！欢迎使用 Litikj Agent Framework 开源框架。",
            "timestamp": time.time(),
            "status": "ready"
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "message": payload["greeting"],
            "file_path": str(out_file.resolve()),
            "data": payload
        }


def setup(registry: Registry):
    """插件自动注册钩子"""
    registry.register_skill(HelloSkill())
