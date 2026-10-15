# 🪐 Litikj Agent Framework

<p align="center">
  <img src="desktop/src/assets/logo.png" alt="Litikj Agent Framework" width="120"/>
</p>

<p align="center">
  <b>面向未来的端侧智能体微内核开发框架 | Local-First AI Agent Operating Framework</b>
</p>

<p align="center">
  <a href="#-核心四大特性"><img src="https://img.shields.io/badge/Microkernel-%3C40MB-emerald.svg" alt="Kernel Size"></a>
  <a href="#-离线自治-local-first"><img src="https://img.shields.io/badge/Local--First-100%25%20Offline-blue.svg" alt="Local First"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-orange.svg" alt="License"></a>
  <a href="#-测试与质量"><img src="https://img.shields.io/badge/Tests-100%25%20Passed-brightgreen.svg" alt="Tests"></a>
</p>

---

## 📖 框架简介

**Litikj Agent Framework**（立体空间智能体开发框架）是一套采用**微内核解耦架构**、专为工业级与桌面端应用打造的智能体开发底座。

不同于传统高度依赖云端黑盒的 Agent 框架，Litikj Agent Framework 秉持 **100% 离线本地自治（Local-First）** 哲学：
- **微内核体积 <40MB**：极简宿主运行底座，无需臃肿的重型依赖预装；
- **0-Token 极速直达通道**：高频环境检查、心跳、配置修改 0-Token <10ms 拦截，拒绝昂贵的大模型轮询；
- **零摩擦环境自愈（Fail-Early & Auto-Healing）**：三态就绪感知，后台自动补齐缺失工具链；
- **元数据驱动 UI（Metadata-Driven UI）**：通过 `config.yaml` 与 JSON Schema 自动渲染 Vue 3 + Tauri 桌面控制面板；
- **人机协同工作流引擎（Human-in-the-Loop）**：基于 Human Gate 审批断点与断点持久化恢复机制。

---

## ⚡ 四大核心特性

```
┌─────────────────────────────────────────────────────────────────┐
│                    Litikj Agent Framework                       │
├──────────────────┬──────────────────┬───────────────────────────┤
│ ⚡ 0-Token 极速通道 │ 🩹 零摩擦环境自愈 │ 🎨 Metadata-Driven UI     │
│  <10ms 本地指令响应│  Fail-Early 门禁 │  JSON Schema 自动渲染面板  │
├──────────────────┴──────────────────┴───────────────────────────┤
│               🔄 Human-in-the-Loop 协作流水线引擎                │
│            节点审批门禁 (Human Gate) + 状态断点安全恢复             │
└─────────────────────────────────────────────────────────────────┘
```

1. **⚡ 0-Token 快速直达协议 (Fast-Path)**：
   日常运维指令（如 `[EXEC] ping`、`[EXEC] check`、`[EXEC] config`、`[EXEC] set key val`）由 `StandardAgent` 基类本地毫秒级直接响应，不耗费 1 点 Token。

2. **🩹 Fail-Early 零摩擦环境自愈**：
   通过 `PreflightItem` 严密守护 Python 依赖包、底层二进制和投递箱目录，发现缺失自动在后台静默自愈拉取，告别传统 Agent 运行时突然崩溃报错。

3. **🎨 元数据驱动 UI (Metadata-Driven UI)**：
   智能体在 `config.yaml` 中声明参数与 JSON Schema，Tauri 桌面端自动自适应生成下拉列表、开关、数值滑动条等控制面板，无需开发者编写前端代码。

4. **🔄 人机在环工作流 (Human-in-the-Loop)**：
   复杂业务流不仅支持多智能体串联、并发扇出（Fan-out），更内置 Human Gate 决策门禁，挂起保存并在用户审批后秒级恢复。

---

## 🚀 5 分钟极速上手

### 1. 克隆与环境就绪
```bash
git clone https://github.com/litikj/litikj-agent-framework.git
cd litikj-agent-framework

# 系统微内核健康巡检 (零配置即可运行，输出全绿灯状态)
python run.py diagnose
```

### 2. 交互式多轮对话
无需连接任何官方云端，默认使用 `custom` 模式。若已安装 [Ollama](https://ollama.com/) 或自备 API Key，修改 `configs/framework.yaml` 后即可畅享：
```bash
# 启动与标杆哨兵智能体的终端会话
python run.py chat omni_sentinel
```

### 3. 一键初始化你的全新智能体工程
```bash
# 使用脚手架在 workspace/custom_agents/ 生成标准智能体模板
python run.py new agent my_trader -d "高频量化交易监控专员"

# 再次巡检，微内核自动动态热发现新智能体！
python run.py diagnose
```

### 4. 配合 Cursor / Claude Code AI 零代码开发
本仓库已深度预置 `.cursorrules` 与 `CLAUDE.md`。使用 Cursor 或 Claude Code 打开本项目后，直接用自然语言描述需求：
> *"请帮我在 workspace/custom_agents/ 下开发一个自动解析 Markdown 转换为 HTML 报告的智能体，要求严格遵守 AGENT_SPEC 规约，实现 StandardAgent 与 0-Token check 指令。"*

AI 助手将 100% 遵守 SOP §4.3 规范，零顶层依赖、自动生成合规卡带！

---

## 🧪 自动化测试与质量保障

本项目包含覆盖核心微内核、安全审计、沙箱隔离、计划调度、自愈门禁与脚手架的完整自动化测试套件：

```bash
pytest tests/ -v
```

所有测试用例已全面解耦商业资产，支持在无商业卡密、离线状态下 **100% 绿灯全通过**。

---

## 📁 目录架构全景

```text
litikj-agent-framework/
├── core/                        # 微内核核心引擎 (契约、注册表、调度器、自愈门禁、网关)
├── apps/server/                 # 跨平台 Headless 与 RESTful HTTP/SSE 服务
├── desktop/                     # Vue 3 + Tailwind CSS + Tauri 2.0 桌面端
├── agents/                      # 官方标杆智能体目录
│   └── omni_sentinel/           # 全维调度哨兵 (StandardAgent 最佳实践)
├── skills/                      # 原子具身技能中心
│   ├── official/                # 官方认证技能
│   ├── community/               # 社区共享卡带
│   └── custom/hello_skill/      # 极简示范技能
├── workflows/                   # 多智能体协同流水线
│   └── system_health_audit.py   # 基准人机审批工作流
├── workspace/                   # 用户本地工作区 (物理隔离业务资产)
│   ├── custom_agents/           # 开发者私有智能体挂载区
│   ├── drop_box/                # 外设投递箱
│   └── outputs/                 # 产物生成归档区
├── configs/                     # 系统核心配置与目录清单
├── docs/                        # 工业级开发规约与设计白皮书
└── run.py                       # CLI 总控调度入口
```

---

## 💼 商业化分发与变现

您使用 **Litikj Agent Framework** 开发的任何智能体与技能，**版权 100% 归您所有**。

如果您希望将自己打造的工业级数字员工或垂直行业卡带进行商业化变现：
- **卡带加密编译**：使用 `scripts/package_agent.py` 一键编译为独立分发卡带；
- **分发变现网络**：欢迎入驻【立体空间商业数字员工分发网络】（Litikj Agent OS 商业旗舰版），将您的智能体作为知识付费产品或企业级 SaaS 交付给全球客户！
- 官方微信联系：`achaobc`（阿朝编程）

---

## 📄 开源许可证

本项目源码基于 [Apache-2.0 License](LICENSE) 协议开源。
框架代码遵循 Apache-2.0，但“立体空间”及“Litikj”品牌商标受专有保护。
