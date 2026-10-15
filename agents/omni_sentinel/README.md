# 🛡️ OmniSentinel 全维调度演示智能体

> **“软件归软件，AI 归 AI”** —— 拒绝盲目的全模型狂热，构建低延迟、0成本、确定性与认知力兼备的工业级商业 Agent。

---

## 🎯 诞生背景与架构哲学

在现实商业场景中，许多初学者陷入了一个误区：**“既然有了大模型，那我就把所有循环、检测、定时、文件解析全部写成 Prompt 让大模型跑”**。

这种“AI狂热”往往带来灾难性的后果：
1. **费用爆炸**：一个简单的每分钟系统巡检，如果调用大模型，一个月就要烧掉数万甚至数十万 Token；
2. **响应迟缓**：纯 Python 执行只需 1 毫秒，调大模型网关却需要 1~3 秒；
3. **脆弱不稳定**：网络波动、大模型幻觉或者返回格式漂移，会导致系统随时崩溃。

**立体空间智能体操作系统 (Litikj Agent OS)** 通过 `OmniSentinel` 示范了**四维全触发范例**，向学员展示如何用优雅的软件工程解耦确定性逻辑与认知推理。

---

## ⚡ 四维全触发模式详解

### 1. 0-Token 快速直达 (Fast-Path / Zero-Token)
- **触发方式**：在对话输入框或命令中以 `[EXEC]` 开头，例如：
  ```text
  [EXEC] status
  [EXEC] ping
  [EXEC] report
  [EXEC] help
  ```
- **核心原理**：框架在 `BaseAgent.chat()` 中自动拦截前缀，直接分流至智能体本地的 `handle_fast_path()` 处理，**完全不经过大模型网关，Token 消耗为 0，延时 < 5ms**。

### 2. 对话认知启动 (Dialogue Trigger)
- **触发方式**：直接发送自然语言问题，例如：
  > “请分析下为什么确定性任务不应该调用大模型？”  
  > “系统目前的安全巡检状态如何，有什么优化建议？”
- **核心原理**：自动挂载 `LicenseGuard` 授权门禁后，携带智能体人设 `persona/prompt.md` 与会话上下文，调用云端大模型中枢（或自备 Key）进行深度参谋。

### 3. 定时周期启动 (Scheduled Trigger)
- **触发方式**：外部调度器或后台线程定时调用智能体的 `scheduled_run()` 方法。
- **产出沉淀**：自动执行健康巡检打卡，生成规范的 Markdown 格式报告并保存至 `workspace/outputs/sentinel_report.md`。

### 4. 事件驱动启动 (Event-Driven Trigger)
- **触发方式**：当底层发生特定系统事件时，调用 `on_event(event_name, data)`。
- **支持事件范例**：
  - `file_changed`：工作区文件产生变更时静默响应；
  - `alert_triggered`：系统指标超限时发出告警；
  - `license_expired`：商业授权状态变更预警。

---

## 🛠️ CLI 命令行操作指南

### ① 进行 0-Token 系统健康巡检
```bash
python run.py run omni_sentinel
```

### ② 触发一次定时打卡报告生成
```bash
python run.py run omni_sentinel '{"action": "schedule"}'
```

### ③ 模拟触发一次事件响应
```bash
python run.py run omni_sentinel '{"action": "event", "event": "file_changed", "data": {"file_path": "test.txt", "action": "created"}}'
```

### ④ 开启终端交互式会话 (体验 0-Token 快速直达与大模型对话无缝切换)
```bash
python run.py chat omni_sentinel
```
在会话中输入：
- `[EXEC] ping` ➔ 毫秒级返回心跳包 (0 Token)
- `[EXEC] status` ➔ 毫秒级返回硬件与智能体状态 (0 Token)
- `你觉得 AI Agent 商业落地的关键是什么？` ➔ 唤醒大模型智能回答
