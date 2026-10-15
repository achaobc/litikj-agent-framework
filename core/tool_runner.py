# -*- coding: utf-8 -*-
"""
core/tool_runner.py
【立体空间智能体系统 · 具身工具执行与产物交付引擎 (Agentic Tool Runner)】
职责：
1. 技能卡带规范注入：动态提取智能体装备的 skills，构建结构化 Tool Calling 系统提示词；
2. 工具调用代码块解析：从大模型输出中稳健提取 ```tool_call 代码块及参数 JSON；
3. 原子技能调度与产物包装：调度 Registry 执行对应技能，提取生成的文件/图片，计算耗时并生成交付元数据；
4. 离线意图智能感知 (Offline Intent Engine)：在无 API Key 或离线状态下，精准识别高频技能意图（如海报制作），
   实现 0-Token 零门槛即时交付。
"""

import os
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .config import ConfigManager
from .registry import Registry


class ToolRunner:
    """具身工具执行与产物交付引擎"""

    @classmethod
    def build_tool_system_prompt(cls, agent, base_prompt: str = "") -> str:
        """
        根据智能体已装备的 skills_list，动态生成具身能力工具库说明与调用协议
        """
        reg = Registry.get_instance()
        skills_list = getattr(agent, "skills_list", [])
        if not skills_list:
            return base_prompt

        tools_desc = []
        for s_id in skills_list:
            skill = reg.get_skill(s_id)
            if not skill:
                continue

            s_name = getattr(skill, "display_name", skill.name)
            s_desc = getattr(skill, "description", "")
            inputs = getattr(skill, "inputs", [])

            input_lines = []
            if inputs:
                for inp in inputs:
                    p_name = inp.get("name", "")
                    p_desc = inp.get("desc", inp.get("description", ""))
                    p_type = inp.get("type", "string")
                    input_lines.append(f"       * {p_name} ({p_type}): {p_desc}")
            else:
                # 默认常见技能输入提示
                if s_id == "bili_cover_generator":
                    input_lines.append("       * topic (string): 视频封面核心主题")
                elif s_id == "hello_skill":
                    input_lines.append("       * name (string): 问候对象名称")
                    input_lines.append("       * topic (string): 交互主题")

            inputs_str = "\n".join(input_lines) if input_lines else "       * (无特定参数要求)"

            tools_desc.append(
                f"- 工具ID: `{s_id}`\n"
                f"  工具名称: 【{s_name}】\n"
                f"  功能描述: {s_desc}\n"
                f"  输入参数:\n{inputs_str}"
            )

        if not tools_desc:
            return base_prompt

        tools_block = "\n".join(tools_desc)
        protocol = (
            f"\n\n========================================\n"
            f"🛠️ 【你已装备的专业具身工具库 (Equipped Tools)】：\n"
            f"你可以根据用户的实际业务需求，随时调用以下已装备的工具来执行真实物理操作并产出成果文件：\n\n"
            f"{tools_block}\n\n"
            f"📋 【具身工具调用协议 (Tool Call Protocol)】：\n"
            f"当你判断用户的输入需要使用上述工具时，请在你的回答中输出如下格式的执行代码块（不要输出多余格式，可以附带自然语言说明）：\n\n"
            f"```tool_call\n"
            f"{{\n"
            f'  "tool": "目标工具ID",\n'
            f'  "params": {{\n'
            f'    "参数1": "参数值"\n'
            f"  }}\n"
            f"}}\n"
            f"```\n"
            f"系统微内核会自动拦截该代码块并在本地调度执行，将生成的成果直观交付给用户。"
            f"\n========================================\n"
        )

        return (base_prompt + protocol).strip()

    @classmethod
    def parse_tool_calls(cls, text: str) -> List[Dict[str, Any]]:
        """
        从文本中稳健提取所有 ```tool_call 代码块或 <tool_call> 标签
        """
        calls = []
        if not text:
            return calls

        # 匹配 ```tool_call ... ``` 或 ```tool ... ``` 或 ```action ... ```
        pattern = r"```(?:tool_call|tool|action)\s*\n(\{.*?\})\s*```"
        matches = re.findall(pattern, text, flags=re.DOTALL)
        for m in matches:
            cleaned = m.strip()
            try:
                data = json.loads(cleaned)
                tool_id = data.get("tool") or data.get("skill") or data.get("name")
                params = data.get("params") or data.get("arguments") or {}
                if tool_id:
                    calls.append({"tool": tool_id, "params": params, "raw_block": cleaned})
            except Exception:
                # 容错：尝试清理尾随逗号
                try:
                    fixed = re.sub(r",\s*([\]}])", r"\1", cleaned)
                    data = json.loads(fixed)
                    tool_id = data.get("tool") or data.get("skill") or data.get("name")
                    params = data.get("params") or data.get("arguments") or {}
                    if tool_id:
                        calls.append({"tool": tool_id, "params": params, "raw_block": cleaned})
                except Exception:
                    pass

        # 匹配 <tool_call>{...}</tool_call>
        tag_pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
        tag_matches = re.findall(tag_pattern, text, flags=re.DOTALL)
        for tm in tag_matches:
            cleaned = tm.strip()
            try:
                data = json.loads(cleaned)
                tool_id = data.get("tool") or data.get("skill") or data.get("name")
                params = data.get("params") or data.get("arguments") or {}
                if tool_id:
                    calls.append({"tool": tool_id, "params": params, "raw_block": cleaned})
            except Exception:
                pass

        return calls

    @classmethod
    def execute_tool(cls, tool_id: str, params: Dict[str, Any], agent: Optional[Any] = None) -> Dict[str, Any]:
        """
        执行指定原子工具，并提取结构化产物元数据 (支持智能体装备作用域强隔离 R2-VULN-04)
        """
        if agent is not None:
            allowed_skills = set(getattr(agent, "skills_list", []))
            if hasattr(agent, "skills") and isinstance(agent.skills, dict):
                allowed_skills.update(agent.skills.keys())
            if tool_id not in allowed_skills:
                ag_name = getattr(agent, "display_name", getattr(agent, "name", "当前智能体"))
                return {
                    "tool": tool_id,
                    "tool_name": tool_id,
                    "icon": "🛡️",
                    "success": False,
                    "error": f"安全拦截：智能体 【{ag_name}】 未装备技能卡带 [{tool_id}]，已阻断越权调用 (SEC-04)",
                    "elapsed_ms": 0,
                    "params": params,
                    "result": {}
                }

        reg = Registry.get_instance()
        skill = reg.get_skill(tool_id)

        t0 = time.time()
        if not skill:
            return {
                "tool": tool_id,
                "tool_name": tool_id,
                "icon": "❌",
                "success": False,
                "error": f"未找到已装载的技能工具 [{tool_id}]",
                "elapsed_ms": 0,
                "params": params,
                "result": {}
            }

        s_name = getattr(skill, "display_name", skill.name)
        s_icon = getattr(skill, "icon", "🧩")

        try:
            result = skill.execute(params)
            elapsed_ms = max(1, int((time.time() - t0) * 1000))

            # 智能提取生成物路径 (如 poster_path, summary_excel, path, file_path)
            file_path = ""
            for k in ("poster_path", "summary_excel", "summary_markdown", "file_path", "output_path", "path"):
                if k in result and isinstance(result[k], str) and result[k]:
                    file_path = result[k]
                    break

            cm = ConfigManager.get_instance()
            outputs_dir = (cm.workspace_dir / "outputs").resolve()

            preview_url = ""
            file_name = ""
            is_image = False
            file_size_str = ""

            if file_path:
                p = Path(file_path).resolve()
                file_name = p.name
                if p.exists():
                    try:
                        sz = p.stat().st_size
                        if sz > 1024 * 1024:
                            file_size_str = f"{sz / (1024 * 1024):.1f} MB"
                        else:
                            file_size_str = f"{max(1, sz // 1024)} KB"
                    except Exception:
                        pass

                # 若在 outputs 目录下，计算 Web 访问路径 /outputs/...
                try:
                    rel = p.relative_to(outputs_dir)
                    preview_url = f"/outputs/{rel.as_posix()}"
                except ValueError:
                    # 不在 outputs 根目录，检查是否为相对路径
                    if "outputs" in p.parts:
                        idx = p.parts.index("outputs")
                        rel_parts = p.parts[idx+1:]
                        preview_url = f"/outputs/{'/'.join(rel_parts)}"

                # 识别图片类型
                suffix = p.suffix.lower()
                if suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
                    is_image = True

            return {
                "tool": tool_id,
                "tool_name": s_name,
                "icon": s_icon,
                "success": result.get("success", True) if isinstance(result, dict) else True,
                "error": result.get("error", "") if isinstance(result, dict) else "",
                "elapsed_ms": elapsed_ms,
                "params": params,
                "result": result,
                "file_path": str(Path(file_path).resolve()) if file_path else "",
                "file_name": file_name,
                "file_size": file_size_str,
                "preview_url": preview_url,
                "is_image": is_image,
                "message": result.get("message", f"工具 [{s_name}] 执行完成") if isinstance(result, dict) else "执行完成"
            }
        except Exception as e:
            elapsed_ms = max(1, int((time.time() - t0) * 1000))
            return {
                "tool": tool_id,
                "tool_name": s_name,
                "icon": s_icon,
                "success": False,
                "error": str(e),
                "elapsed_ms": elapsed_ms,
                "params": params,
                "result": {}
            }

    @classmethod
    def format_artifact_card_markdown(cls, artifact: Dict[str, Any]) -> str:
        """
        将工具执行产物序列化为结构化的 Markdown 标记块 :::skill-artifact
        """
        payload_str = json.dumps(artifact, ensure_ascii=False)
        return f"\n\n:::skill-artifact\n{payload_str}\n:::\n\n"

    @classmethod
    def detect_offline_skill_intent(cls, user_msg: str, agent) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        离线意图感知器 (Offline Heuristic Intent Engine)
        当无大模型 Key 或断网时，智能感知高频技能调用意图，实现 0-Token 零门槛即插即用
        """
        if not user_msg:
            return None

        skills_list = getattr(agent, "skills_list", [])
        msg = user_msg.strip()
        # 1. 开源示范技能意图识别 (hello_skill)
        if "hello_skill" in skills_list:
            keywords = ("hello", "你好", "打招呼", "打个招呼", "问候", "示范", "招呼")
            if any(k in msg.lower() for k in keywords):
                topic = ""
                m_title = re.search(r"《([^》]+)》", msg)
                if m_title:
                    topic = m_title.group(1).strip()
                name = topic or "开发者"
                return "hello_skill", {"name": name, "topic": topic or "开源实战"}


        # 1. B站视频合规元数据与简介生成意图识别 (bili_meta_generator)
        if "bili_meta_generator" in skills_list:
            meta_keywords = ("简介", "元数据", "标签", "发布准备", "生成简介", "视频简介")
            if any(k in msg for k in meta_keywords):
                topic = ""
                m_title = re.search(r"《([^》]+)》", msg)
                if m_title:
                    topic = m_title.group(1).strip()
                else:
                    m_topic = re.search(r"主题(?:是|为|：|:)\s*([^\s，,。\n]+)", msg)
                    if m_topic:
                        topic = m_topic.group(1).strip()
                    else:
                        topic = "立体空间智能体系统实战"
                return "bili_meta_generator", {
                    "topic": topic
                }
        return None
