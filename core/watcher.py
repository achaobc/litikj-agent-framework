# -*- coding: utf-8 -*-
"""
core/watcher.py
【立体空间智能体系统 · 通用投递箱与外设监听引擎 (WatcherEngine)】
职责：
1. 业务中立的文件投放感知中枢：监控任意指定文件夹的文件新增与变动；
2. 工业级稳定性防抖与写入等待 (Settling)：自动检测文件写入进度，彻底避免大视频/大文件拷贝中途被误读；
3. 状态持久化防重放：已处理文件自动记录历史指纹，系统重启后绝不重复触发；
4. 调度分发契约：检测就绪后自动拉起对应的 Workflow 或 Agent。
"""

import os
import sys
import time
import json
import uuid
import fnmatch
import threading
from collections import deque
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Deque

from .config import ConfigManager, WatcherRule
from .registry import Registry
from .engine import Engine

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


class WatcherEventQueue:
    """投递箱事件队列 (线程安全单例，支撑前端实时推送与事件轮询)"""
    _instance: Optional['WatcherEventQueue'] = None

    def __init__(self, max_len: int = 100):
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max_len)
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'WatcherEventQueue':
        if cls._instance is None:
            cls._instance = WatcherEventQueue()
        return cls._instance

    def push(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            event = {
                "id": str(uuid.uuid4())[:8],
                "event_type": event_type,
                "timestamp": time.time(),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "consumed": False,
                **data
            }
            self._events.append(event)
            return event

    def get_unconsumed(self, since: float = 0.0) -> List[Dict[str, Any]]:
        with self._lock:
            if since <= 0.0:
                return [dict(e) for e in self._events if not e.get("consumed", False)]
            return [dict(e) for e in self._events if e["timestamp"] > since]

    def mark_consumed(self, event_ids: List[str]):
        with self._lock:
            for e in self._events:
                if e["id"] in event_ids:
                    e["consumed"] = True

    def clear(self):
        with self._lock:
            self._events.clear()


class WatcherEngine:
    """通用投递箱与事件监听引擎 (单例/常驻引擎)"""
    _instance: Optional['WatcherEngine'] = None

    def __init__(self):
        self.config_mgr = ConfigManager.get_instance()
        self.watcher_cfg = self.config_mgr.watcher
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 跟踪中文件: {str(file_path): {"size": int, "last_seen": float, "settle_start": float}}
        self._tracking_files: Dict[str, Dict[str, Any]] = {}
        # 防重复刷屏冷却记录: {str(file_path): last_notified_timestamp}
        self._notified_cooldown: Dict[str, float] = {}

        # 历史已处理持久化记录路径
        self.history_file = self.config_mgr.workspace_dir / "data" / "watcher_processed.json"
        self._processed_cache: Dict[str, float] = self._load_processed_history()

        # 自定义事件回调函数 (可选，用于测试或外部拦截)
        self.custom_callback: Optional[Callable[[WatcherRule, Path], Any]] = None

    @classmethod
    def get_instance(cls) -> 'WatcherEngine':
        if cls._instance is None:
            cls._instance = WatcherEngine()
        return cls._instance

    def _load_processed_history(self) -> Dict[str, float]:
        """加载已处理文件的指纹记录 (file_path -> mtime)"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_processed_history(self):
        """保存已处理记录"""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self._processed_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Watcher Warning] 无法保存已处理记录: {e}")

    def mark_processed(self, file_path: Path):
        """标记文件已处理完毕"""
        try:
            mtime = file_path.stat().st_mtime
        except Exception:
            mtime = time.time()
        self._processed_cache[str(file_path.resolve())] = mtime
        self._save_processed_history()

    def remove_processed(self, file_path: Path):
        """清除单个文件的已处理指纹"""
        key = str(file_path.resolve())
        if key in self._processed_cache:
            del self._processed_cache[key]
            self._save_processed_history()

    def reset_history(self, target_path: Optional[Path] = None):
        """重置已处理历史记录（传None清空全部，传Path清空单个）"""
        if target_path:
            self.remove_processed(target_path)
        else:
            self._processed_cache.clear()
            self._save_processed_history()
        self._notified_cooldown.clear()
        self._tracking_files.clear()
        print("🧹 [Watcher] 已重置投递箱已处理指纹库")

    def cleanup_missing_history(self):
        """自动清理已在物理磁盘中被移除或删除的投递箱文件的历史记录"""
        try:
            keys_to_remove = [k for k in list(self._processed_cache.keys()) if not Path(k).exists()]
            if keys_to_remove:
                for k in keys_to_remove:
                    del self._processed_cache[k]
                self._save_processed_history()
        except Exception:
            pass

    def archive_file(self, file_path_str: str) -> Dict[str, Any]:
        """将已处理的文件一键归档移入对应目录下的 .archive/ 文件夹中，保持投递箱清爽"""
        p = Path(file_path_str).resolve()
        if not p.exists() or not p.is_file():
            return {"success": False, "error": f"目标文件不存在: {file_path_str}"}

        try:
            archive_dir = p.parent / ".archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            target_dst = archive_dir / p.name
            # 如果目标已存在重名文件，加上时间戳避免覆盖
            if target_dst.exists():
                stem = p.stem
                suffix = p.suffix
                target_dst = archive_dir / f"{stem}_{int(time.time())}{suffix}"

            import shutil
            shutil.move(str(p), str(target_dst))
            self.remove_processed(p)
            self.cleanup_missing_history()
            return {
                "success": True,
                "archived_path": str(target_dst),
                "message": f"文件已成功归档移至: {target_dst.name}"
            }
        except Exception as e:
            return {"success": False, "error": f"归档失败: {str(e)}"}

    def is_processed(self, file_path: Path) -> bool:
        """检查文件是否已被成功处理过"""
        key = str(file_path.resolve())
        if key not in self._processed_cache:
            return False
        try:
            # 如果文件修改时间发生变化，允许重新触发
            current_mtime = file_path.stat().st_mtime
            recorded_mtime = self._processed_cache.get(key, 0)
            return abs(current_mtime - recorded_mtime) < 0.01
        except Exception:
            return True

    def scan_once(self) -> List[Path]:
        """
        单次全规则扫描
        遍历所有已启用的 rules 目录，识别新放入且已写入完成的合格文件并触发
        返回当前触发处理的文件列表
        """
        triggered_files: List[Path] = []
        now = time.time()
        settle_threshold = self.watcher_cfg.settle_seconds

        # 1. 自动对已移走/已删除的文件做历史记录清理，避免卡住二次测试
        self.cleanup_missing_history()

        for rule in self.watcher_cfg.rules:
            if not rule.enabled:
                continue

            target_dir = rule.directory
            if not target_dir.exists():
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    continue

            # 遍历目标目录 (包含顶级目录及各账号专属子目录)
            try:
                candidates = []
                for item in target_dir.iterdir():
                    if item.is_file():
                        candidates.append(item)
                    elif item.is_dir() and not item.name.startswith("."):
                        # 扫描专属子目录 (如各账号专属投递箱)
                        for sub_item in item.iterdir():
                            if sub_item.is_file():
                                candidates.append(sub_item)
            except Exception:
                continue

            for file_path in candidates:
                if not file_path.is_file():
                    continue

                # 检查文件名格式匹配
                matched = any(fnmatch.fnmatch(file_path.name.lower(), p.lower()) for p in rule.file_patterns)
                if not matched:
                    continue

                # 解析子文件夹账号
                subfolder_name = ""
                try:
                    rel = file_path.relative_to(target_dir)
                    if len(rel.parts) > 1:
                        subfolder_name = rel.parts[0]
                except Exception:
                    pass

                f_key = str(file_path.resolve())

                # 检查是否已处理过
                if self.is_processed(file_path):
                    # 避免反复刷屏，60 秒内对同一历史文件至多提示一次
                    last_seen = self._notified_cooldown.get(f_key, 0)
                    if (now - last_seen) > 60:
                        self._notified_cooldown[f_key] = now
                        file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
                        eq = WatcherEventQueue.get_instance()
                        target_name = rule.target if rule.trigger_type == "agent" else "omni_sentinel"
                        eq.push("file_already_processed", {
                            "target_agent": target_name,
                            "file_name": file_path.name,
                            "file_path": f_key,
                            "file_size_mb": file_size_mb,
                            "subfolder": subfolder_name,
                            "message": (
                                f"ℹ️ **【检测到历史稿件】** 投递箱中存在已处理过的视频：`{file_path.name}` ({file_size_mb} MB)\n\n"
                                f"• 若需强制重新生产交付，可输入 `[EXEC] run` 或指定路径 `[EXEC] run {file_path.name}`\n"
                                f"• 或输入 `[EXEC] reset-watcher` 重置投递箱防重放指纹。"
                            )
                        })
                    continue

                try:
                    stat = file_path.stat()
                    current_size = stat.st_size
                except Exception:
                    # 文件可能正在被独占打开
                    continue

                # 检查最小文件大小限制
                min_bytes = int(rule.min_file_size_mb * 1024 * 1024)
                if current_size < min_bytes:
                    continue

                # 失败任务防刷屏冷却 (60 秒内对同一未通过任务不重复广播)
                if f_key in self._notified_cooldown and (now - self._notified_cooldown[f_key]) < 60:
                    continue

                # 防抖稳定期校验 (Settle Check)
                if f_key not in self._tracking_files:
                    # 首次发现新文件，记录初始大小和时间
                    self._tracking_files[f_key] = {
                        "size": current_size,
                        "last_change": now,
                        "rule": rule
                    }
                    file_size_mb = round(current_size / (1024 * 1024), 2)
                    print(f"👀 [Watcher] 感知到新投递文件: {file_path.name} ({file_size_mb}MB)，进入写入静默稳定期...")
                    # 立即向前端抛出文件接入通知，消除感知延迟
                    eq = WatcherEventQueue.get_instance()
                    target_name = rule.target if rule.trigger_type == "agent" else "omni_sentinel"
                    eq.push("file_staged", {
                        "target_agent": target_name,
                        "file_name": file_path.name,
                        "file_path": f_key,
                        "file_size_mb": file_size_mb,
                        "subfolder": subfolder_name,
                        "message": f"📥 **【投递箱捕获新文件】** 检测到 `{file_path.name}` ({file_size_mb} MB)，正在校验写入完整度..."
                    })
                    continue

                track = self._tracking_files[f_key]
                if current_size != track["size"]:
                    # 文件大小仍在增长，说明写入未结束，重置计时
                    track["size"] = current_size
                    track["last_change"] = now
                    continue

                # 文件大小没有变化，检查是否持续满足稳定秒数
                if (now - track["last_change"]) >= settle_threshold:
                    # 文件写入已稳定就绪！触发执行
                    print(f"🎯 [Watcher] 投递文件写入完毕并就绪: 【{file_path.name}】 -> 触发规则 [{rule.name}]")
                    dispatched = self._dispatch_event(rule, file_path)
                    if dispatched:
                        self.mark_processed(file_path)
                        if f_key in self._notified_cooldown:
                            del self._notified_cooldown[f_key]
                    else:
                        # 任务受阻或环境未就绪：设置防刷屏冷却
                        self._notified_cooldown[f_key] = now
                    del self._tracking_files[f_key]
                    triggered_files.append(file_path)

        return triggered_files

    def _dispatch_event(self, rule: WatcherRule, file_path: Path) -> bool:
        """分发就绪文件至目标工作流或智能体，并向事件总线广播实时事件"""
        eq = WatcherEventQueue.get_instance()
        now = time.time()
        f_key = str(file_path.resolve())

        # 1. 优先调用自定义回调
        if self.custom_callback:
            try:
                self.custom_callback(rule, file_path)
                return True
            except Exception as e:
                print(f"[Watcher Error] 自定义回调异常: {e}")
                return False

        # 2. 判断是否属于子目录 (如各账号专属子文件夹)
        subfolder_name = ""
        try:
            rel = file_path.relative_to(rule.directory)
            if len(rel.parts) > 1:
                subfolder_name = rel.parts[0]
        except Exception:
            pass

        file_size_bytes = file_path.stat().st_size
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        # 构造通用投递载荷
        payload = {
            "file_path": str(file_path.resolve()),
            "video_path": str(file_path.resolve()),
            "file_name": file_path.name,
            "rule_name": rule.name,
            "subfolder": subfolder_name,
            "account_hint": subfolder_name,
            "trigger_source": "watcher_engine",
            "file_size": file_size_bytes
        }

        # 3. 调度工作流或智能体
        reg = Registry.get_instance()
        if rule.trigger_type == "workflow":
            wf = reg.get_workflow(rule.target)
            if wf:
                print(f"🚀 [Watcher] 自动调起多智能体流水线: 【{wf.name}】")
                eq.push("file_detected", {
                    "target_agent": "omni_sentinel",
                    "file_name": file_path.name,
                    "file_path": str(file_path.resolve()),
                    "file_size_mb": file_size_mb,
                    "subfolder": subfolder_name,
                    "status": "processing",
                    "message": (
                        f"📥 **【投递箱感知到新稿件】** 检测到待处理文件：`{file_path.name}` ({file_size_mb} MB)\n\n"
                        f"• 触发规则：`{rule.name}`\n"
                        f"• 正在自动调起流水线 **【{wf.name}】**..."
                    )
                })
                wf.execute(payload)
                return True
            else:
                print(f"⚠️ [Watcher] 未找到已注册的目标流水线: [{rule.target}]")
                return False

        elif rule.trigger_type == "agent":
            ag = reg.get_agent(rule.target)
            if ag:
                print(f"🤖 [Watcher] 自动调起目标智能体: 【{ag.name}】")
                # 3.1 广播感知事件到对话框
                display_agent_name = getattr(ag, "display_name", ag.name)
                eq.push("file_detected", {
                    "target_agent": ag.name,
                    "file_name": file_path.name,
                    "file_path": str(file_path.resolve()),
                    "file_size_mb": file_size_mb,
                    "subfolder": subfolder_name,
                    "status": "processing",
                    "message": (
                        f"📥 **【投递箱感知到新稿件】** 检测到待处理视频：`{file_path.name}` ({file_size_mb} MB)\n\n"
                        f"• 关联账号：`{subfolder_name or '默认单账号'}`\n"
                        f"• 正在由 **【{display_agent_name}】** 执行状态巡检、Cookie 探测与全自动交付流水线..."
                    )
                })

                # 3.2 执行核心业务
                engine = Engine(reg)
                task_res = engine.dispatch_quick(ag.name, payload)

                # 3.3 广播最终结果卡片到对话框
                eq.push("task_completed", {
                    "target_agent": ag.name,
                    "file_name": file_path.name,
                    "file_path": str(file_path.resolve()),
                    "file_size_mb": file_size_mb,
                    "subfolder": subfolder_name,
                    "status": "success" if task_res.success else "failed",
                    "message": task_res.message
                })
                return task_res.success
            else:
                print(f"⚠️ [Watcher] 未找到目标智能体: [{rule.target}]")
                # 检查防刷屏冷却 (60秒内对同一文件只提示一次)
                last_cooldown = self._notified_cooldown.get(f_key, 0)
                if (now - last_cooldown) > 60:
                    self._notified_cooldown[f_key] = now
                    target_name_cn = rule.target
                    eq.push("need_recruit", {
                        "target_agent": "omni_sentinel",
                        "missing_agent": rule.target,
                        "file_name": file_path.name,
                        "file_path": str(file_path.resolve()),
                        "file_size_mb": file_size_mb,
                        "subfolder": subfolder_name,
                        "status": "waiting_recruit",
                        "message": (
                            f"📥 **【投递箱感知到新任务】** 检测到 `drop_box/{subfolder_name or 'default'}` 投入了新文件：\n\n"
                            f"📁 **文件**：`{file_path.name}` ({file_size_mb} MB)\n"
                            f"⚠️ **岗位待聘**：当前系统尚未招募负责该业务的官方数字化员工 **【{target_name_cn}】**！\n\n"
                            f"👉 **一键极速入职**：\n"
                            f"输入 `[EXEC] recruit {rule.target}` 或在顶栏【招募库】点击招募该智能体，系统将自动就绪并接单处理该任务！"
                        )
                    })
                return False

    def start_in_thread(self) -> threading.Thread:
        """在后台常驻守护线程中运行监听引擎"""
        if self._running:
            return self._thread

        self._running = True

        def _loop():
            print(f"📡 [Watcher Engine] 通用投递箱监听引擎已启动 (轮询周期: {self.watcher_cfg.poll_interval}s)")
            while self._running:
                try:
                    self.scan_once()
                except Exception as e:
                    print(f"[Watcher Loop Error] 扫描异常: {e}")
                time.sleep(self.watcher_cfg.poll_interval)
            print("👋 [Watcher Engine] 监听引擎已平稳停止。")

        self._thread = threading.Thread(target=_loop, daemon=True, name="WatcherEngineThread")
        self._thread.start()
        return self._thread

    def stop(self):
        """停止监听引擎"""
        self._running = False
