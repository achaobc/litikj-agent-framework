# -*- coding: utf-8 -*-
"""
core/scheduler.py
【立体空间智能体系统 · 定时计划任务守护中枢 (SchedulerEngine)】
职责：
1. 纯标准库轻量调度常驻线程：支持每日定时时刻 (Daily)、固定时间间隔 (Interval)、单次延时 (Once) 与标准 Cron 表达式；
2. 任务状态持久化：存储至 workspace/data/schedules.json，开机与重启后自动无缝接续；
3. 自然语言时间意图解析 (Natural Language Parser)：支持对话中自动提取定时计划；
4. 调度分发契约：到时自动唤醒目标智能体的 0-Token 快速直达、自然语言推理或 scheduled_run()。
"""

import os
import sys
import time
import json
import uuid
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable

from .config import ConfigManager
from .registry import Registry

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def _match_cron_field(val: int, expr: str, min_val: int, max_val: int) -> bool:
    """极简无依赖 Cron 单字段匹配器 (*, */n, n, n-m, n,m)"""
    expr = expr.strip()
    if expr == "*":
        return True
    if expr.startswith("*/"):
        try:
            step = int(expr[2:])
            return val % step == 0
        except ValueError:
            return False
    if "," in expr:
        return any(_match_cron_field(val, sub, min_val, max_val) for sub in expr.split(","))
    if "-" in expr:
        try:
            low, high = map(int, expr.split("-"))
            return low <= val <= high
        except ValueError:
            return False
    try:
        return int(expr) == val
    except ValueError:
        return False


def is_cron_match(dt: datetime, cron_expr: str) -> bool:
    """检查 datetime 是否满足 5 字段标准 Cron 表达式 (分 时 日 月 周)"""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False
    m_exp, h_exp, dom_exp, mon_exp, dow_exp = parts
    # Python weekday(): 0 is Monday, 6 is Sunday. Cron: 0 is Sunday or Monday depending on standard.
    # Standard cron: 0=Sun, 1=Mon, ..., 6=Sat
    cron_dow = (dt.weekday() + 1) % 7
    return (
        _match_cron_field(dt.minute, m_exp, 0, 59) and
        _match_cron_field(dt.hour, h_exp, 0, 23) and
        _match_cron_field(dt.day, dom_exp, 1, 31) and
        _match_cron_field(dt.month, mon_exp, 1, 12) and
        _match_cron_field(cron_dow, dow_exp, 0, 6)
    )


class SchedulerEngine:
    """智能体计划任务常驻调度引擎 (单例)"""
    _instance: Optional['SchedulerEngine'] = None

    def __init__(self):
        self.config_mgr = ConfigManager.get_instance()
        self.storage_file = self.config_mgr.workspace_dir / "data" / "schedules.json"
        self._lock = threading.Lock()
        self._tasks: Dict[str, Dict[str, Any]] = self._load_tasks()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 记录每分钟已触发的时间戳指纹，防止同一分钟内重复多次触发
        self._fired_minute_stamps: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> 'SchedulerEngine':
        if cls._instance is None:
            cls._instance = SchedulerEngine()
        return cls._instance

    # ================= 状态持久化存储 =================

    def _load_tasks(self) -> Dict[str, Dict[str, Any]]:
        """从 workspace/data/schedules.json 加载持久化任务"""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    elif isinstance(data, list):
                        return {item["id"]: item for item in data if "id" in item}
            except Exception as e:
                print(f"[Scheduler Warning] 读取计划任务文件失败: {e}")
        return self._get_default_seed_tasks()

    def _save_tasks(self):
        """保存任务到文件"""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self._tasks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Scheduler Warning] 保存计划任务失败: {e}")

    def _get_default_seed_tasks(self) -> Dict[str, Dict[str, Any]]:
        """初始化官方预设的种子任务 (示例标杆)"""
        task_id = "sched_default_sentinel_report"
        return {
            task_id: {
                "id": task_id,
                "name": "每日晨间全维底座健康巡检",
                "agent_name": "omni_sentinel",
                "schedule_type": "daily",       # "daily" | "interval" | "once" | "cron"
                "time_value": "09:00",          # 每天 09:00
                "cron_expr": "0 9 * * *",
                "action_type": "fast_path",     # "fast_path" | "chat" | "scheduled_run"
                "command": "[EXEC] report",
                "description": "每天早晨 09:00 自动执行一次底座健康诊断，并保存巡检报告至 outputs/sentinel_report.md",
                "enabled": True,
                "created_at": time.time(),
                "last_run": None,
                "last_status": "WAITING",
                "last_result_summary": "等待首次定时触发"
            }
        }

    # ================= 任务增删改查 =================

    def list_tasks(self, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取任务清单 (附带下次执行时间预测)"""
        with self._lock:
            tasks_list = []
            now = datetime.now()
            for t in self._tasks.values():
                if agent_name and t.get("agent_name") != agent_name:
                    continue
                task_copy = dict(t)
                task_copy["next_run_hint"] = self._compute_next_run_hint(task_copy, now)
                tasks_list.append(task_copy)
            # 按创建时间降序
            tasks_list.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return tasks_list

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._tasks.get(task_id)

    def add_or_update_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """新增或更新定时任务"""
        with self._lock:
            task_id = task_data.get("id") or f"sched_{uuid.uuid4().hex[:8]}"
            name = task_data.get("name") or "未命名定时任务"
            agent_name = task_data.get("agent_name") or "omni_sentinel"
            sched_type = task_data.get("schedule_type") or "daily"
            time_val = str(task_data.get("time_value") or "09:00")
            cmd = task_data.get("command") or "[EXEC] report"
            desc = task_data.get("description") or f"针对智能体 [{agent_name}] 的定时调度"
            enabled = bool(task_data.get("enabled", True))
            cron_expr = task_data.get("cron_expr", "")

            # 自动映射 cron 表达式
            if sched_type == "daily" and not cron_expr and ":" in time_val:
                try:
                    h, m = time_val.split(":")
                    cron_expr = f"{int(m)} {int(h)} * * *"
                except Exception:
                    cron_expr = "0 9 * * *"
            elif sched_type == "interval" and not cron_expr:
                try:
                    mins = max(1, int(time_val))
                    cron_expr = f"*/{mins} * * * *" if mins < 60 else "0 * * * *"
                except Exception:
                    cron_expr = "0 * * * *"

            action_type = "fast_path" if cmd.startswith("[EXEC]") else "chat"

            record = {
                "id": task_id,
                "name": name,
                "agent_name": agent_name,
                "schedule_type": sched_type,
                "time_value": time_val,
                "cron_expr": cron_expr,
                "action_type": action_type,
                "command": cmd,
                "description": desc,
                "enabled": enabled,
                "created_at": task_data.get("created_at") or time.time(),
                "last_run": task_data.get("last_run"),
                "last_status": task_data.get("last_status") or "ACTIVE",
                "last_result_summary": task_data.get("last_result_summary") or "计划已配置就绪"
            }

            self._tasks[task_id] = record
            self._save_tasks()
            return record

    def toggle_task(self, task_id: str, enabled: Optional[bool] = None) -> bool:
        """启用或停用指定计划任务"""
        with self._lock:
            if task_id in self._tasks:
                curr = self._tasks[task_id]["enabled"]
                self._tasks[task_id]["enabled"] = (not curr) if enabled is None else bool(enabled)
                self._save_tasks()
                return self._tasks[task_id]["enabled"]
        return False

    def delete_task(self, task_id: str) -> bool:
        """删除指定定时任务"""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self._save_tasks()
                return True
        return False

    # ================= 下次执行预测 =================

    def _compute_next_run_hint(self, task: Dict[str, Any], now: datetime) -> str:
        """计算人类可读的下次执行提示"""
        if not task.get("enabled"):
            return "已暂停"

        sched_type = task.get("schedule_type")
        time_val = task.get("time_value", "")

        if sched_type == "daily":
            try:
                h, m = map(int, time_val.split(":"))
                target_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if now < target_today:
                    return f"今天 {h:02d}:{m:02d}"
                else:
                    return f"明天 {h:02d}:{m:02d}"
            except Exception:
                return f"每日 {time_val}"

        elif sched_type == "interval":
            try:
                mins = int(time_val)
                last_run = task.get("last_run")
                if last_run:
                    next_time = datetime.fromtimestamp(last_run) + timedelta(minutes=mins)
                    if next_time > now:
                        diff_sec = int((next_time - now).total_seconds())
                        return f"约 {diff_sec // 60} 分钟后 ({next_time.strftime('%H:%M')})"
                return f"每隔 {mins} 分钟循环"
            except Exception:
                return f"每隔 {time_val} 分钟"

        elif sched_type == "once":
            try:
                mins = int(time_val)
                created = task.get("created_at", time.time())
                target_time = datetime.fromtimestamp(created) + timedelta(minutes=mins)
                if now < target_time:
                    diff_sec = int((target_time - now).total_seconds())
                    return f"倒计时 {diff_sec // 60} 分钟后 ({target_time.strftime('%H:%M')})"
                else:
                    return "已到期执行完毕"
            except Exception:
                return f"{time_val} 分钟后单次"

        elif sched_type == "cron":
            return f"Cron: {task.get('cron_expr', time_val)}"

        return "按规则自动触发"

    # ================= 执行驱动中枢 =================

    def execute_task_now(self, task_id: str) -> Dict[str, Any]:
        """立即手动试运行一次指定任务"""
        task = self.get_task(task_id)
        if not task:
            return {"success": False, "error": f"未找到任务: {task_id}"}
        return self._dispatch_task(task)

    def _dispatch_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """触发执行单个任务的核心业务"""
        agent_name = task.get("agent_name", "omni_sentinel")
        command = task.get("command", "[EXEC] report")
        reg = Registry.get_instance()
        agent = reg.get_agent(agent_name)

        start_t = time.time()
        print(f"\n⏰ [Scheduler 守护触发] 执行定时任务: 【{task.get('name')}】 (目标: {agent_name}, 指令: {command})")

        if not agent:
            res_summary = f"未找到已挂载的智能体: {agent_name}"
            self._update_task_result(task["id"], success=False, summary=res_summary, start_time=start_t)
            return {"success": False, "error": res_summary}

        try:
            output_text = ""
            if command.startswith("[EXEC]"):
                sub_cmd = command[len("[EXEC]"):].strip()
                res = agent.handle_fast_path(sub_cmd)
                output_text = res if res is not None else "0-Token 快轨执行完成"
            else:
                res = agent.chat([{"role": "user", "content": command}])
                output_text = str(res)

            elapsed = round(time.time() - start_t, 2)
            summary = f"✅ 执行成功 (耗时 {elapsed}s): {output_text.splitlines()[0] if output_text else '完成'}"
            print(f"⏰ [Scheduler 成功] {summary}")

            self._update_task_result(task["id"], success=True, summary=summary, start_time=start_t)

            # 单次任务自动停用
            if task.get("schedule_type") == "once":
                self.toggle_task(task["id"], enabled=False)

            return {
                "success": True,
                "output": output_text,
                "elapsed": elapsed,
                "summary": summary
            }
        except Exception as e:
            elapsed = round(time.time() - start_t, 2)
            err_summary = f"❌ 执行异常 ({elapsed}s): {str(e)}"
            print(f"⏰ [Scheduler 失败] {err_summary}")
            self._update_task_result(task["id"], success=False, summary=err_summary, start_time=start_t)
            return {"success": False, "error": str(e)}

    def _update_task_result(self, task_id: str, success: bool, summary: str, start_time: float):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["last_run"] = start_time
                self._tasks[task_id]["last_status"] = "SUCCESS" if success else "FAILED"
                self._tasks[task_id]["last_result_summary"] = summary
                self._save_tasks()

    # ================= 守护线程与生命周期 =================

    def start_daemon(self):
        """拉起后台常驻检测守护线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="SchedulerDaemon")
        self._thread.start()
        print(f"🚀 [Scheduler 守护引擎] 计划任务调度器已就绪 (监控 {len(self._tasks)} 个定时规则)")

    def stop_daemon(self):
        self._running = False

    def _worker_loop(self):
        """轮询常驻循环 (每 2 秒自检一次)"""
        while self._running:
            try:
                self._check_and_trigger_due_tasks()
            except Exception as e:
                print(f"[Scheduler Loop Error] {e}")
            time.sleep(2.0)

    def _check_and_trigger_due_tasks(self):
        now = datetime.now()
        current_minute_str = now.strftime("%Y-%m-%d %H:%M")

        tasks_to_run = []
        with self._lock:
            for t_id, task in self._tasks.items():
                if not task.get("enabled"):
                    continue

                sched_type = task.get("schedule_type")
                time_val = task.get("time_value", "")
                last_run = task.get("last_run")

                # 防重放：同一分钟内同一任务只触发一次
                if self._fired_minute_stamps.get(t_id) == current_minute_str:
                    continue

                should_fire = False

                # 1. 每日固定时刻
                if sched_type == "daily":
                    try:
                        h, m = map(int, time_val.split(":"))
                        if now.hour == h and now.minute == m:
                            should_fire = True
                    except Exception:
                        pass

                # 2. 固定间隔循环 (分钟)
                elif sched_type == "interval":
                    try:
                        interval_sec = int(time_val) * 60
                        if last_run is None or (time.time() - last_run) >= interval_sec:
                            should_fire = True
                    except Exception:
                        pass

                # 3. 单次延时倒计时 (分钟)
                elif sched_type == "once":
                    try:
                        delay_sec = int(time_val) * 60
                        created = task.get("created_at", time.time())
                        if (time.time() - created) >= delay_sec and last_run is None:
                            should_fire = True
                    except Exception:
                        pass

                # 4. 标准 Cron 表达式
                elif sched_type == "cron":
                    cron_exp = task.get("cron_expr", time_val)
                    if is_cron_match(now, cron_exp):
                        should_fire = True

                if should_fire:
                    self._fired_minute_stamps[t_id] = current_minute_str
                    tasks_to_run.append(task)

        # 在锁外异步调度执行，杜绝阻塞主轮询
        for task in tasks_to_run:
            threading.Thread(target=self._dispatch_task, args=(task,), daemon=True).start()

    # ================= 自然语言语义识别 =================

    @staticmethod
    def parse_natural_language_schedule(query: str, current_agent: str = "omni_sentinel") -> Optional[Dict[str, Any]]:
        """从用户对话自然语言中智能提取定时计划意图"""
        import re
        q = query.strip()

        # 检查是否包含时间调度意向
        time_keywords = ["每天", "每隔", "定时", "小时后", "分钟后", "点整", "提醒我", "自动巡检", "自动打卡"]
        if not any(k in q for k in time_keywords):
            return None

        # 1. 提取指令或动作
        cmd = "[EXEC] report"
        if "巡检" in q or "报告" in q or "诊断" in q:
            cmd = "[EXEC] report"
        elif "状态" in q or "底座" in q:
            cmd = "[EXEC] status"
        elif "心跳" in q or "ping" in q:
            cmd = "[EXEC] ping"

        # 2. 匹配每日固定时刻 (如 "每天早上9点" / "每天 09:30")
        daily_match = re.search(r"每天(?:早上|上午|下午|晚上)?\s*(\d{1,2})(?:[点:：时](\d{1,2})?)?", q)
        if daily_match:
            h = int(daily_match.group(1))
            m = int(daily_match.group(2) or 0)
            if "下午" in q or "晚上" in q:
                if h < 12:
                    h += 12
            time_val = f"{h:02d}:{m:02d}"
            return {
                "matched": True,
                "name": f"每日 {time_val} 自动执行",
                "agent_name": current_agent,
                "schedule_type": "daily",
                "time_value": time_val,
                "cron_expr": f"{m} {h} * * *",
                "command": cmd,
                "description": f"由自然语言创建：{q}",
                "reply": f"⏰ 已为您智能识别定时计划：**每天 {time_val}** 自动调度智能体 `[{current_agent}]` 执行 `{cmd}`。"
            }

        # 3. 匹配间隔循环 (如 "每隔2小时" / "每隔30分钟")
        interval_match = re.search(r"每隔\s*(\d+)\s*(小时|分钟)", q)
        if interval_match:
            num = int(interval_match.group(1))
            unit = interval_match.group(2)
            mins = num * 60 if unit == "小时" else num
            return {
                "matched": True,
                "name": f"每隔 {num}{unit} 自动执行",
                "agent_name": current_agent,
                "schedule_type": "interval",
                "time_value": str(mins),
                "command": cmd,
                "description": f"由自然语言创建：{q}",
                "reply": f"⏰ 已为您智能识别定时循环：**每隔 {num}{unit}** 自动调度智能体 `[{current_agent}]` 执行 `{cmd}`。"
            }

        # 4. 匹配单次倒计时 (如 "30分钟后" / "1小时后")
        once_match = re.search(r"(\d+)\s*(小时|分钟)后", q)
        if once_match:
            num = int(once_match.group(1))
            unit = once_match.group(2)
            mins = num * 60 if unit == "小时" else num
            return {
                "matched": True,
                "name": f"{num}{unit}后 单次执行",
                "agent_name": current_agent,
                "schedule_type": "once",
                "time_value": str(mins),
                "command": cmd,
                "description": f"由自然语言创建：{q}",
                "reply": f"⏰ 已为您智能识别延时计划：**{num}{unit}后** 自动调度智能体 `[{current_agent}]` 执行一次 `{cmd}`。"
            }

        return None
