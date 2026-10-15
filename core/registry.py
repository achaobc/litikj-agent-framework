# -*- coding: utf-8 -*-
"""
core/registry.py
【立体空间智能体系统 · 插件与注册中心 (Registry)】
职责：
1. 维护全系统已注册的智能体与技能清单；
2. 支持动态代码注册与目录自适应扫描发现 (Auto-Discovery)；
3. 为任务调度引擎提供统一定位查询接口。
"""

import os
import sys
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Any

from .contract import BaseAgent, BaseSkill, PromptSkill
from .config import ConfigManager


class Registry:
    """系统注册中心 (单例模式)"""
    _instance: Optional['Registry'] = None

    def __init__(self):
        self.config_mgr = ConfigManager.get_instance()
        self._agents: Dict[str, BaseAgent] = {}
        self._skills: Dict[str, BaseSkill] = {}
        self._workflows: Dict[str, Any] = {}
        # 智能体/技能加载失败记录 {目录名: 异常详情}，供招聘入职校验与前端诊断使用
        self.load_errors: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> 'Registry':
        if cls._instance is None:
            cls._instance = Registry()
        return cls._instance

    # ================= 智能体注册与查询 =================
    def register_agent(self, agent: BaseAgent):
        """显式注册一个智能体实例"""
        self._agents[agent.name] = agent

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """获取指定名称的智能体"""
        return self._agents.get(name)

    def list_agents(self) -> List[BaseAgent]:
        """列出所有已注册的智能体"""
        return list(self._agents.values())

    def unregister_agent(self, name: str) -> bool:
        """注销或移除一个智能体实例"""
        if name in self._agents:
            del self._agents[name]
            return True
        return False

    # ================= 技能注册与查询 =================
    def register_skill(self, skill: BaseSkill):
        """显式注册一个原子技能实例"""
        self._skills[skill.name] = skill

    def unregister_skill(self, name: str) -> bool:
        """注销或移除一个技能实例"""
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """获取指定名称的技能"""
        return self._skills.get(name)

    def list_skills(self) -> List[BaseSkill]:
        """列出所有已注册的技能"""
        return list(self._skills.values())

    def list_skills_by_origin(self, origin: str) -> List[BaseSkill]:
        """按来源分类获取技能：official | community | custom"""
        return [s for s in self._skills.values() if getattr(s, "origin", "official") == origin]

    # ================= 工作流注册与查询 =================
    def register_workflow(self, workflow: Any):
        """显式注册一个多智能体工作流"""
        self._workflows[workflow.name] = workflow

    def get_workflow(self, name: str) -> Optional[Any]:
        """获取指定名称的工作流"""
        return self._workflows.get(name)

    def list_workflows(self) -> List[Any]:
        """列出所有已注册的工作流"""
        return list(self._workflows.values())

    def unregister_workflow(self, name: str):
        """注销已注册的工作流"""
        self._workflows.pop(name, None)

    # ================= 动态自动发现 =================
    def auto_discover(self):
        """扫描内置目录与外部挂载目录，自动载入智能体、技能与工作流"""
        # 1. 扫描官方内置智能体
        self._discover_from_dir(self.config_mgr.agents_dir, is_agent=True, is_external=False)
        
        # 2. 扫描外部挂载智能体目录 (学员私有智能体仓库 / 任意绝对路径)
        for extra_dir in getattr(self.config_mgr, "extra_agent_dirs", []):
            if extra_dir.exists():
                self._discover_from_dir(extra_dir, is_agent=True, is_external=True)

        # 3. 扫描三级生态技能与多智能体工作流
        self._discover_skills(self.config_mgr.skills_dir)
        self._discover_workflows(self.config_mgr.workflows_dir)

    def _discover_skills(self, skills_root: Path):
        """三级技能体系发现引擎：扫描 official (官方), community (第三方), custom (自定义)"""
        if not skills_root.exists():
            return

        # 确保三级物理目录就绪
        official_dir = skills_root / "official"
        community_dir = skills_root / "community"
        custom_dir = skills_root / "custom"
        official_dir.mkdir(parents=True, exist_ok=True)
        community_dir.mkdir(parents=True, exist_ok=True)
        custom_dir.mkdir(parents=True, exist_ok=True)

        tiers = [
            (official_dir, "official"),
            (community_dir, "community"),
            (custom_dir, "custom"),
        ]

        # 扫描三级子目录中的各技能包
        for tier_dir, default_origin in tiers:
            for sub in tier_dir.iterdir():
                if sub.is_dir() and not sub.name.startswith((".", "_")):
                    self._load_single_skill_dir(sub, default_origin=default_origin)

        # 兼容性扫描：根目录平铺的技能包 (排除三级系统保留目录)
        for sub in skills_root.iterdir():
            if sub.is_dir() and sub.name not in ("official", "community", "custom") and not sub.name.startswith((".", "_")):
                self._load_single_skill_dir(sub, default_origin="official")

    def _load_single_skill_dir(self, skill_dir: Path, default_origin: str = "official"):
        """加载单个技能目录：读取 manifest.yaml / skill.py / prompt.md"""
        try:
            skill_dir_str = str(skill_dir.resolve())
            if skill_dir_str not in sys.path:
                sys.path.insert(0, skill_dir_str)

            # 读取元数据
            cfg_data = {}
            for manifest_name in ("manifest.yaml", "manifest.yml", "skill.yaml", "config.yaml"):
                mf = skill_dir / manifest_name
                if mf.exists():
                    try:
                        import yaml
                        with open(mf, "r", encoding="utf-8") as f:
                            cfg_data = yaml.safe_load(f) or {}
                            break
                    except Exception:
                        pass

            # 寻找 Python 入口脚本
            entry_py = skill_dir / "entry.py"
            skill_py = skill_dir / "skill.py"
            init_py = skill_dir / "__init__.py"
            candidate = entry_py if entry_py.exists() else (skill_py if skill_py.exists() else (init_py if init_py.exists() else None))

            before_skills = set(self._skills.keys())

            if candidate:
                module_name = f"skills_{default_origin}.{skill_dir.name}.{candidate.stem}"
                spec = importlib.util.spec_from_file_location(module_name, candidate)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    mod.__package__ = f"skills_{default_origin}.{skill_dir.name}"
                    sys.modules[module_name] = mod
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "setup") and callable(mod.setup):
                        mod.setup(self)
                    else:
                        # 自动寻找 BaseSkill 子类实例化
                        for attr_name in dir(mod):
                            attr = getattr(mod, attr_name)
                            if isinstance(attr, type) and issubclass(attr, BaseSkill) and attr is not BaseSkill and attr is not PromptSkill:
                                try:
                                    inst = attr()
                                    self.register_skill(inst)
                                except Exception:
                                    pass

            after_skills = set(self._skills.keys())
            new_skills = after_skills - before_skills

            # 若没有 Python 脚本，但有 prompt.md 或 SKILL.md，则装载为 PromptSkill
            if not candidate and not new_skills and ((skill_dir / "prompt.md").exists() or (skill_dir / "SKILL.md").exists()):
                prompt_file = skill_dir / "prompt.md" if (skill_dir / "prompt.md").exists() else skill_dir / "SKILL.md"
                prompt_text = ""
                try:
                    with open(prompt_file, "r", encoding="utf-8") as f:
                        prompt_text = f.read()
                except Exception:
                    pass
                skill_name = cfg_data.get("id", cfg_data.get("name", skill_dir.name))
                ps = PromptSkill(
                    name=skill_name,
                    description=cfg_data.get("description", "基于 SOP 提示词的执行技能"),
                    prompt_text=prompt_text
                )
                self.register_skill(ps)
                new_skills.add(skill_name)

            target_skill_names = set(new_skills)
            skill_id = cfg_data.get("id", cfg_data.get("name", skill_dir.name))
            if skill_id in self._skills:
                target_skill_names.add(skill_id)

            # 为新注册或重新载入的技能挂载元数据属性
            for s_name in target_skill_names:
                s_obj = self._skills.get(s_name)
                if s_obj:
                    s_obj.origin = default_origin if default_origin in ("official", "community", "custom") else cfg_data.get("origin", "custom")
                    s_obj.source_path = str(skill_dir.resolve())
                    s_obj.display_name = cfg_data.get("display_name", cfg_data.get("name", getattr(s_obj, "display_name", s_obj.name)))
                    s_obj.version = cfg_data.get("version", getattr(s_obj, "version", "1.0.0"))
                    default_author = "立体空间官方" if s_obj.origin == "official" else ("第三方社区" if s_obj.origin == "community" else "本地开发者")
                    s_obj.author = cfg_data.get("author", getattr(s_obj, "author", default_author))
                    s_obj.icon = cfg_data.get("icon", getattr(s_obj, "icon", "🧩"))
                    s_obj.category = cfg_data.get("category", getattr(s_obj, "category", "通用"))
                    s_obj.manifest = cfg_data
                    s_obj.inputs = cfg_data.get("inputs", getattr(s_obj, "inputs", []))
                    s_obj.outputs = cfg_data.get("outputs", getattr(s_obj, "outputs", []))
                    if cfg_data.get("description"):
                        s_obj.description = cfg_data["description"]
        except Exception as e:
            print(f"[Registry Warning] 自动加载技能 [{skill_dir.name}] 异常: {e}")

    def _discover_from_dir(self, target_dir: Path, is_agent: bool, is_external: bool = False):
        if not target_dir.exists():
            return

        target_dir_str = str(target_dir.resolve())
        if target_dir_str not in sys.path:
            sys.path.insert(0, target_dir_str)

        for sub in target_dir.iterdir():
            if sub.is_dir() and not sub.name.startswith((".", "_")):
                entry_py = sub / "entry.py"
                agent_py = sub / "agent.py"
                init_py = sub / "__init__.py"
                candidate = entry_py if entry_py.exists() else (agent_py if agent_py.exists() else (init_py if init_py.exists() else None))
                if candidate:
                    try:
                        sub_str = str(sub.resolve())
                        if sub_str not in sys.path:
                            sys.path.insert(0, sub_str)

                        package_prefix = "custom_agents" if is_external else ("agents" if is_agent else "skills")
                        module_name = f"{package_prefix}.{sub.name}.{candidate.stem}"
                        spec = importlib.util.spec_from_file_location(module_name, candidate)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            mod.__package__ = f"{package_prefix}.{sub.name}"
                            sys.modules[module_name] = mod
                            
                            before_agents = set(self._agents.keys())
                            spec.loader.exec_module(mod)
                            
                            # 如果模块提供了 setup(registry) 钩子函数，则调用它自动注册
                            if hasattr(mod, "setup") and callable(mod.setup):
                                mod.setup(self)

                            # 自动标记新注册的智能体来源、实际物理路径与元数据
                            after_agents = set(self._agents.keys())
                            cfg_file = sub / "config.yaml"
                            cfg_data = {}
                            if cfg_file.exists():
                                try:
                                    import yaml
                                    with open(cfg_file, "r", encoding="utf-8") as f:
                                        cfg_data = yaml.safe_load(f) or {}
                                except Exception:
                                    pass

                            discovered_names = (after_agents - before_agents) or {sub.name}
                            for ag_name in discovered_names:
                                if ag_name not in self._agents:
                                    continue
                                ag_obj = self._agents[ag_name]
                                ag_obj.source = "external" if is_external else "builtin"
                                ag_obj.source_path = str(sub.resolve())
                                ag_obj.display_name = cfg_data.get("display_name", getattr(ag_obj, "display_name", ag_obj.name))
                                ag_obj.icon = cfg_data.get("icon", getattr(ag_obj, "icon", "🤖"))
                                ag_obj.category = cfg_data.get("category", getattr(ag_obj, "category", "通用"))
                                ag_obj.version = cfg_data.get("version", getattr(ag_obj, "version", "1.0.0"))
                                ag_obj.quick_chips = cfg_data.get("quick_chips", getattr(ag_obj, "quick_chips", []))
                                ag_obj.actions = cfg_data.get("actions", getattr(ag_obj, "actions", []))
                                ag_obj.skills_list = cfg_data.get("skills", getattr(ag_obj, "skills_list", []))
                                ag_obj.system_prompt = cfg_data.get("system_prompt", getattr(ag_obj, "system_prompt", ""))
                                ag_obj.temperature = cfg_data.get("temperature", getattr(ag_obj, "temperature", 0.7))
                                if cfg_data.get("description"):
                                    ag_obj.description = cfg_data["description"]
                            if sub.name in self._agents or discovered_names & set(self._agents):
                                self.load_errors.pop(sub.name, None)
                    except Exception as e:
                        self.load_errors[sub.name] = f"{type(e).__name__}: {e}"
                        prefix_label = "外部挂载" if is_external else "内置"
                        print(f"[Registry Warning] 自动加载{prefix_label}插件 [{sub.name}] 异常: {e}")

    def _discover_workflows(self, target_dir: Path):
        """自动发现 workflows/ 目录下的工作流脚本与独立工作流包"""
        if not target_dir.exists():
            return
        for item in target_dir.iterdir():
            if item.name.startswith((".", "_")):
                continue
            
            entry_file = None
            cfg_file = None
            module_name = ""

            if item.is_file() and item.suffix == ".py":
                entry_file = item
                module_name = f"workflows.{item.stem}"
            elif item.is_dir():
                for c in ("entry.py", "workflow.py", "__init__.py"):
                    cand = item / c
                    if cand.exists():
                        entry_file = cand
                        module_name = f"workflows.{item.name}.{cand.stem}"
                        break
                cfg_file = item / "config.yaml"

            if entry_file and entry_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location(module_name, entry_file)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = mod
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "setup") and callable(mod.setup):
                            before_wfs = set(self._workflows.keys())
                            mod.setup(self)
                            after_wfs = set(self._workflows.keys())
                            
                            # 挂载额外元数据
                            if cfg_file and cfg_file.exists():
                                try:
                                    import yaml
                                    with open(cfg_file, "r", encoding="utf-8") as f:
                                        meta = yaml.safe_load(f) or {}
                                    for wf_name in (after_wfs - before_wfs):
                                        wf_obj = self._workflows.get(wf_name)
                                        if wf_obj:
                                            wf_obj.icon = meta.get("icon", getattr(wf_obj, "icon", "🔄"))
                                            wf_obj.category = meta.get("category", getattr(wf_obj, "category", "多智能体协同"))
                                            wf_obj.version = meta.get("version", getattr(wf_obj, "version", "1.0.0"))
                                            wf_obj.dependencies = meta.get("dependencies", getattr(wf_obj, "dependencies", {}))
                                except Exception:
                                    pass
                except Exception as e:
                    print(f"[Registry Warning] 自动加载工作流 [{item.name}] 异常: {e}")
