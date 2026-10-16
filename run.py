# -*- coding: utf-8 -*-
"""
run.py
【立体空间智能体系统 · 微内核 CLI 总控入口】
核心功能：
1. 0-Token 本地快速直达控制台：支持命令行直接调用，无需大模型消耗；
2. 全系统微内核健康巡检 (diagnose)；
3. 列出已挂载的智能体与技能清单 (list)；
4. 调度特定智能体批处理任务 (run <agent_name> [payload])；
5. 唤醒智能体多轮交互式终端对话 (chat [agent_name])。
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import ConfigManager
from core.registry import Registry
from core.engine import Engine
from core.llm import LLMClient
from core.contract import TaskContext


def bootstrap():
    """系统引导：载入配置并自动发现 plugins"""
    cm = ConfigManager.get_instance()
    reg = Registry.get_instance()
    reg.auto_discover()
    return cm, reg, Engine(reg)


def run_diagnosis():
    """执行微内核综合诊断"""
    cm, reg, _ = bootstrap()

    print("\n" + "=" * 65)
    print(f"🚀 【{cm.system_name}】微内核底座环境巡检 (v{cm.version})")
    print("=" * 65)
    print(f"📂 根目录路径: {cm.root_dir}")
    print(f"⚙️ 配置文件:   {cm.config_path.relative_to(cm.root_dir) if cm.config_path.is_relative_to(cm.root_dir) else cm.config_path}")
    print(f"📥 工作区目录: {cm.workspace_dir.relative_to(cm.root_dir) if cm.workspace_dir.is_relative_to(cm.root_dir) else cm.workspace_dir}")
    print(f"🤖 智能体插槽: {cm.agents_dir.relative_to(cm.root_dir) if cm.agents_dir.is_relative_to(cm.root_dir) else cm.agents_dir}")
    print(f"🧩 技能插槽:   {cm.skills_dir.relative_to(cm.root_dir) if cm.skills_dir.is_relative_to(cm.root_dir) else cm.skills_dir}")
    print("-" * 65)

    print("🌐 【大模型网关与商业授权】")
    gw = cm.gateway
    ok, status_msg = LLMClient.verify_license()
    status_icon = "🟢" if ok else "🟡"
    print(f"  {status_icon} 运行模式: {gw.mode.upper()}")
    if gw.mode == "cloud":
        print(f"     • 官方中枢: {gw.endpoint}")
        print(f"     • 授权状态: {status_msg}")
    else:
        print(f"     • 接口地址: {gw.custom_base_url}")
        print(f"     • 自选模型: {gw.custom_model}")
        print(f"     • 连接状态: {status_msg}")

    agents = reg.list_agents()
    skills = reg.list_skills()

    print(f"\n🤖 【已激活智能体 ({len(agents)} 个)】")
    if not agents:
        print("  (暂无已激活智能体，可将智能体包放入 agents/ 目录)")
    for ag in agents:
        source_badge = "📁[外部挂载]" if getattr(ag, "source", "builtin") == "external" else "👑[官方内置]"
        guards_info = f" [门禁: 前置 {len(ag.pre_guards)} / 后置 {len(ag.post_guards)}]"
        print(f"  • {ag.name:20s} {source_badge} | {ag.description}{guards_info}")

    print(f"\n🧩 【已注册原子技能 ({len(skills)} 个)】")
    if not skills:
        print("  (暂无独立技能，可将技能包放入 skills/ 目录)")
    for sk in skills:
        print(f"  • {sk.name:20s} | {sk.description}")

    workflows = reg.list_workflows()
    print(f"\n🔄 【已注册多智能体流水线 ({len(workflows)} 条)】")
    if not workflows:
        print("  (暂无独立工作流，可放入 workflows/ 目录)")
    for wf in workflows:
        chain_str = " ➔ ".join([f"[{s.agent_name}]" for s in wf.steps])
        print(f"  • {wf.name:20s} | {chain_str} ({wf.description})")

    print("=" * 65 + "\n")


def list_plugins():
    """列出当前激活的插件"""
    _, reg, _ = bootstrap()
    print("\n[当前激活的智能体列表]")
    for ag in reg.list_agents():
        source_badge = "[外部挂载]" if getattr(ag, "source", "builtin") == "external" else "[官方内置]"
        print(f"  • {ag.name:18s} {source_badge} ({ag.description})")
    print("\n[当前激活的原子技能列表]")
    for sk in reg.list_skills():
        print(f"  • {sk.name} ({sk.description})")
    print("\n[当前激活的多智能体流水线列表]")
    for wf in reg.list_workflows():
        chain_str = " ➔ ".join([f"[{s.agent_name}]" for s in wf.steps])
        print(f"  • {wf.name} ({chain_str}) - {wf.description}")
    print()


def parse_payload(payload_str: str) -> dict:
    """健壮解析命令行传入的 JSON / 字典载荷，针对 Windows PowerShell 剥离引号进行智能容错"""
    if not payload_str:
        return {}
    s = payload_str.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return {"input": payload_str}

    # 1. 标准 JSON 解析
    try:
        return json.loads(s)
    except Exception:
        pass

    # 2. Python 字面量解析 (兼容单引号)
    try:
        import ast
        val = ast.literal_eval(s)
        if isinstance(val, dict):
            return val
    except Exception:
        pass

    # 3. 针对 Windows PowerShell 剥离引号进行键值对容错解析
    try:
        import re
        inner = s[1:-1].strip()
        result = {}
        parts = re.split(r',\s*(?=[a-zA-Z_]\w*\s*:)', inner)
        for part in parts:
            if ":" in part:
                k, v = part.split(":", 1)
                k = k.strip().strip('"').strip("'")
                v = v.strip().strip('"').strip("'")
                if v.lower() == "true":
                    val_conv = True
                elif v.lower() == "false":
                    val_conv = False
                elif v.lower() in ("null", "none"):
                    val_conv = None
                elif v.isdigit():
                    val_conv = int(v)
                else:
                    val_conv = v
                result[k] = val_conv
        if result:
            return result
    except Exception:
        pass

    return {"input": payload_str}


def dispatch_task(agent_name: str, payload_str: str):
    """分发批处理任务给指定智能体"""
    _, _, engine = bootstrap()
    payload = parse_payload(payload_str)

    ctx = TaskContext(
        task_id="task_" + os.urandom(3).hex(),
        agent_name=agent_name,
        payload=payload
    )

    result = engine.dispatch(ctx)
    print("=" * 65)
    print(f"📦 执行结果: {'[成功]' if result.success else '[失败]'}")
    print(f"💬 响应消息: {result.message}")
    if result.data:
        print(f"📊 产出数据: {json.dumps(result.data, ensure_ascii=False, indent=2)}")
    print("=" * 65 + "\n")


def dispatch_workflow(workflow_name: str, payload_str: str):
    """分发并驱动多智能体接力流水线"""
    _, reg, engine = bootstrap()
    workflows = reg.list_workflows()

    if not workflows:
        print("❌ 当前系统中暂无已注册的多智能体流水线！请先在 workflows/ 中添加工作流。")
        return

    target_wf = None
    if workflow_name:
        target_wf = reg.get_workflow(workflow_name)
        if not target_wf:
            print(f"❌ 未找到名为 [{workflow_name}] 的工作流！可用工作流: {[w.name for w in workflows]}")
            return
    else:
        if len(workflows) == 1:
            target_wf = workflows[0]
        else:
            print("\n请选择要执行的多智能体流水线：")
            for idx, wf in enumerate(workflows, 1):
                chain_str = " ➔ ".join([f"[{s.agent_name}]" for s in wf.steps])
                print(f"  {idx}. {wf.name:18s} ({chain_str}) - {wf.description}")
            try:
                choice = input(f"请输入序号 [1-{len(workflows)}, 默认 1]: ").strip()
                selected_idx = int(choice) - 1 if choice else 0
                target_wf = workflows[selected_idx]
            except Exception:
                target_wf = workflows[0]

    payload = parse_payload(payload_str)
    res = target_wf.execute(payload, engine)
    if res.suspended:
        print(f"\n💡 [人机协同提醒] 工作流已在人机审批节点 [{res.gate_info.get('title')}] 挂起！")
        print(f"   您可以在 Chatbox 桌面客户端中可视化选择，或使用命令行恢复：")
        print(f"   python run.py resume {res.workflow_id} '{{\"choice\": \"您的选择\"}}'\n")
    return res


def resume_workflow(workflow_id: str, decision_str: str):
    """恢复挂起等待人工决策的工作流"""
    bootstrap()
    from core.workflow import Workflow
    decision = parse_payload(decision_str)
    print(f"\n🔄 正在向工作流 [{workflow_id}] 注入人工审批决策: {decision}")
    res = Workflow.resume_by_id(workflow_id, decision)
    if res.suspended:
        print(f"💡 该工作流进入下一个审批节点: [{res.gate_info.get('title')}]")
    return res


def run_daemon():
    """启动系统常驻守护进程 (通用投递箱监听 + 定时服务)"""
    cm, reg, _ = bootstrap()
    from core.watcher import WatcherEngine
    watcher = WatcherEngine.get_instance()
    watcher.start_in_thread()

    print("\n" + "=" * 65)
    print(f"🛡️  【{cm.system_name}】后台常驻守护进程已就绪 (v{cm.version})")
    print(f"📂 投递箱与事件监听运行中... (按 Ctrl+C 可停止守护服务)")
    print("=" * 65 + "\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 守护进程已安全关闭。")
        watcher.stop()


def handle_new_command(sub_type: str, name: str, description: str, is_builtin: bool, category: str = "通用工具"):
    """处理 new 脚手架命令"""
    from core.scaffold import create_agent_scaffold, create_workflow_scaffold, create_skill_scaffold
    if sub_type == "agent":
        create_agent_scaffold(name, description, is_custom=not is_builtin)
    elif sub_type == "workflow":
        create_workflow_scaffold(name, description)
    elif sub_type == "skill":
        create_skill_scaffold(name, description, category=category, is_custom=not is_builtin)


def start_chat_session(agent_name: str = ""):
    """启动与指定智能体的多轮交互式对话 REPL"""
    cm, reg, _ = bootstrap()
    agents = reg.list_agents()

    if not agents:
        print("❌ 当前系统中暂无已激活的智能体！请先在 agents/ 中添加智能体。")
        return

    # 若未指定智能体，智能选路
    target_agent = None
    if agent_name:
        target_agent = reg.get_agent(agent_name)
        if not target_agent:
            print(f"❌ 未找到名为 [{agent_name}] 的智能体！")
            return
    else:
        if len(agents) == 1:
            target_agent = agents[0]
        else:
            print("\n请选择要对话的智能体：")
            for idx, ag in enumerate(agents, 1):
                print(f"  {idx}. {ag.name:18s} ({ag.description})")
            try:
                choice = input(f"请输入序号 [1-{len(agents)}, 默认 1]: ").strip()
                selected_idx = int(choice) - 1 if choice else 0
                target_agent = agents[selected_idx]
            except Exception:
                target_agent = agents[0]

    # 执行智能体前置安全门禁审查 (如 LicenseGuard)
    print("\n" + "=" * 65)
    print(f"🤖 正在连接智能体: 【{target_agent.name}】")
    if target_agent.pre_guards:
        print(f"🛡️  执行前置安全门禁审查 ({len(target_agent.pre_guards)} 项)...")
        probe_ctx = TaskContext(task_id="chat_probe", agent_name=target_agent.name, payload={"mode": "chat"})
        for guard in target_agent.pre_guards:
            res = guard.check(probe_ctx)
            res.print_summary()
            if not res.passed:
                print(f"⛔ 前置门禁拦截，无法开启对话会话！")
                print("=" * 65 + "\n")
                return

    print("💬 已成功进入多轮交互会话！")
    print("💡 提示: 输入 'exit' 或 'quit' 退出, 'clear' 清空记忆, 'save' 保存记录")
    print("=" * 65 + "\n")

    messages = []
    
    while True:
        try:
            user_input = input("👤 您: ").strip()
            user_input = user_input.encode('utf-8', 'ignore').decode('utf-8')
        except (KeyboardInterrupt, EOFError):
            print("\n👋 对话已退出。")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", ":q"):
            print("👋 感谢交流，智能体会话已安全关闭。")
            break

        if user_input.lower() == "clear":
            messages.clear()
            print("🧹 对话上下文历史已清空！\n")
            continue

        if user_input.lower() == "save":
            log_dir = cm.workspace_dir / "data" / "chat_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"chat_{target_agent.name}_{time.strftime('%Y%m%d_%H%M%S')}.json"
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            print(f"💾 当前会话记录已保存至: {log_file.relative_to(cm.root_dir)}\n")
            continue

        messages.append({"role": "user", "content": user_input})

        print(f"🤖 [{target_agent.name}]: ", end="", flush=True)
        try:
            reply = target_agent.chat(messages)
            print(reply + "\n")
            messages.append({"role": "assistant", "content": reply})
        except Exception as e:
            print(f"\n❌ [会话响应异常] {e}\n")


def main():
    parser = argparse.ArgumentParser(description="立体空间智能体系统 (Litikj Agent OS) 调度入口")
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")

    # diagnose
    subparsers.add_parser("diagnose", help="系统微内核健康巡检")
    # list
    subparsers.add_parser("list", help="列出已激活的智能体与技能")
    # run
    run_parser = subparsers.add_parser("run", help="调度执行指定智能体 (批处理任务)")
    run_parser.add_argument("agent", type=str, help="目标智能体名称")
    run_parser.add_argument("payload", nargs="?", default="", help="传递给智能体的数据 (字符串或JSON)")
    # chat
    chat_parser = subparsers.add_parser("chat", help="启动智能体交互式多轮对话 (终端模式)")
    chat_parser.add_argument("agent", nargs="?", default="", help="目标智能体名称 (选填)")
    # workflow
    wf_parser = subparsers.add_parser("workflow", help="调度执行多智能体接力流水线 (A ➔ B ➔ C 协作)")
    wf_parser.add_argument("name", nargs="?", default="", help="工作流名称 (选填，留空展示可选列表)")
    wf_parser.add_argument("payload", nargs="?", default="", help="传递给流水线的初始数据 (字符串或JSON)")
    # gui
    subparsers.add_parser("gui", help="启动 Chatbox 桌面可视化工作台 (高颜值客户端)")
    # daemon
    subparsers.add_parser("daemon", help="启动系统后台常驻守护进程 (通用投递箱监听 + 定时服务)")
    # resume
    resume_parser = subparsers.add_parser("resume", help="恢复挂起的人机协同工作流")
    resume_parser.add_argument("id", type=str, help="挂起工作流的 workflow_id")
    resume_parser.add_argument("decision", type=str, help="人工审批决策载荷 (字符串或JSON)")
    # new
    new_parser = subparsers.add_parser("new", help="工程脚手架：快速生成新智能体或工作流模板")
    new_sub = new_parser.add_subparsers(dest="new_type", help="创建类型 (agent / workflow)")
    # new agent
    new_agent_p = new_sub.add_parser("agent", help="初始化标准智能体工程")
    new_agent_p.add_argument("name", type=str, help="智能体唯一标识名称")
    new_agent_p.add_argument("-d", "--desc", type=str, default="", help="智能体功能描述")
    new_agent_p.add_argument("--builtin", action="store_true", help="是否作为官方内置智能体放入 agents/ (默认放入 workspace/custom_agents/)")
    # new workflow
    new_wf_p = new_sub.add_parser("workflow", help="初始化标准流水线脚本")
    new_wf_p.add_argument("name", type=str, help="工作流唯一标识名称")
    new_wf_p.add_argument("-d", "--desc", type=str, default="", help="工作流描述")
    # new skill
    new_skill_p = new_sub.add_parser("skill", help="初始化标准技能胶囊工程")
    new_skill_p.add_argument("name", type=str, help="技能唯一标识名称")
    new_skill_p.add_argument("-d", "--desc", type=str, default="", help="技能功能描述")
    new_skill_p.add_argument("-c", "--category", type=str, default="通用工具", help="技能业务分类")
    new_skill_p.add_argument("--builtin", action="store_true", help="是否作为官方技能放入 skills/official/ (默认放入 skills/custom/)")

    args = parser.parse_args()

    if args.subcommand == "diagnose" or not args.subcommand:
        run_diagnosis()
    elif args.subcommand == "list":
        list_plugins()
    elif args.subcommand == "run":
        dispatch_task(args.agent, args.payload)
    elif args.subcommand == "workflow":
        dispatch_workflow(args.name, args.payload)
    elif args.subcommand == "resume":
        resume_workflow(args.id, args.decision)
    elif args.subcommand == "daemon":
        run_daemon()
    elif args.subcommand == "new":
        if not args.new_type:
            new_parser.print_help()
        else:
            is_builtin = getattr(args, "builtin", False)
            category = getattr(args, "category", "通用工具")
            handle_new_command(args.new_type, args.name, args.desc, is_builtin, category=category)
    elif args.subcommand == "chat":
        start_chat_session(args.agent)
    elif args.subcommand == "gui":
        # 优先唤醒 Tauri 桌面端主程序，若无编译产物则拉起微内核 API 服务
        root = Path(__file__).resolve().parent
        main_exe_candidates = [
            root / "立体空间智能体系统.exe",
            root / "desktop" / "src-tauri" / "target" / "release" / "立体空间智能体系统.exe",
            root / "desktop" / "src-tauri" / "target" / "release" / "app.exe"
        ]
        target_exe = next((c for c in main_exe_candidates if c.exists()), None)
        if target_exe:
            print(f"🚀 正在唤醒原生桌面客户端: {target_exe.name}")
            subprocess.Popen([str(target_exe)])
        else:
            print("🪐 正在启动立体空间微内核 API 服务 (http://127.0.0.1:8765)...")
            from apps.server.api_server import start_server
            srv = start_server()
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                print("\n🛑 服务已安全退出。")


if __name__ == "__main__":
    main()
