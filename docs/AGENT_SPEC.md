# 👑 立体空间商业级智能体开发与接入标准规约手册 (AGENT SPEC v2.5)

> **Liti Space Agent Studio · Standard Agent Development & Integration Specification**  
> **适用版本**：立体空间微内核操作系统 v2.5.0+  
> **适用对象**：后续所有参与智能体开发的 AI 编程助手、人类开发者及插件作者。  
> **核心宗旨**：保障每一个智能体具备高鲁棒性（Fail-Early 门禁防御）、真智能化（拒绝硬编码假模板）、易运维性（0-Token 极速直达通道）与统一界面规范（通用标准设置面板）。

---

## 零、 架构设计哲学与三大首要铁律 (Core Philosophy & Iron Laws)

在商业级 AI Agent 工程中，**“微内核底座（系统框架）”** 与 **“业务智能体（具体的私有代码与领域模型）”** 必须严格解耦。

### 1. 基础架构三大哲学
1. **软件归软件，AI 归 AI**：
   - 凡是确定性的逻辑（如数据抓取、文件扫描、格式转换、系统巡检），走 **0-Token 纯代码通道**；
   - 凡是开放性的推理（如痛点提炼、架构权衡、人设对话），走 **大模型网关通道**；
   - 严禁用大模型反复轮询浪费 Token 和引入不确定性。
2. **100% 动态元数据驱动 (Metadata-Driven UI)**：
   - **底座工作台 (GUI) 严禁为任何特定业务智能体硬编码专有按钮或专有逻辑**；
   - 智能体自身在 `config.yaml` 中声明其专属图标（Emoji）、中文名称、分类、快捷 Prompt Chips 与快捷 Action 操作项；
   - 前端工作台只做通用容器，即插即用、动态渲染。
3. **四维触发与人机协同 (Human-in-the-Loop)**：
   - 每个标准智能体具备四维统一接入能力（0-Token 快速直达、自然语言对话、定时打卡、事件驱动）；
   - 在复杂串联业务流中，通过 Human Gate 节点挂起交给人做最高决策，实现真正的商业闭环。

### 2. 智能体开发三大首要铁律 (Core Commandments)
> **最高红线**：所有后续开发、重构或接入本系统的商业智能体，必须将以下三条铁律作为最高纲领严格遵守：

#### 铁律一：出厂底座绝对纯净，杜绝臃肿预装 (Zero-Payload Base)
1. **严格控制出厂体积**：系统商业发售便携包（`release/立体空间智能体系统_vx.x.x_Portable.zip`）核心体积**严格压制在 25MB 以内**；
2. **严禁打包智能体私有依赖**：出厂便携包内**严禁预置**任何尚未被用户正式招募或启用的智能体专用重型依赖（包括但不限于 `torch`, `ctranslate2`, `onnxruntime`, `av`, `baidupcs_py`, `moviepy`, `playwright` 以及语音/图像离线模型权重等）；
3. **极简微内核架构**：内置宿主运行环境仅包含 Python 3.10 Embed 及微内核核心库（`yaml`, `psutil`, `PIL`）；
4. **按需装配生命周期**：智能体所需的一切外部重型依赖与模型权重，一律遵循“**按需拉取、独立自愈、即装即用**”的生命周期原则。

#### 铁律二：环境自检为开发一等公民 (Fail-Early Inspection)
1. **强制具备自检能力**：每一个商业智能体在开发时，**必须拥有且暴露环境自检能力**，严禁只写业务逻辑而不写环境门禁；
2. **统一契约接口**：优先继承 `StandardAgent`，或实现统一的 `get_preflight_items()` 与 `get_readiness_status()` 接口，显式声明 `DROP_BOX_DIRS`（投递箱子目录）、`REQUIRED_PACKAGES`（Python 依赖清单）、`REQUIRED_BINARIES`（底层工具链）；
3. **0-Token 极速自检通道**：智能体必须支持 0-Token 极速自检指令 `[EXEC] check`，耗时必须压在 300ms 以内；
4. **三态生命周期规范**：向前端精准上报生命周期状态（`INSTALLING_DEPENDENCIES` / `ACTION_REQUIRED` / `READY`），绝不在小白界面抛出刺眼的 Python 崩溃堆栈。

#### 铁律三：全自动静默自愈与一键环境装配 (Zero-Friction Self-Healing)
1. **必须具备一键装配/静默自愈能力**：智能体必须支持一键自动安装环境与静默自愈（实现 `heal()` 与 0-Token 指令 `[EXEC] heal` / `[EXEC] setup`）；
2. **双轨高可用保障**：自愈拉取依赖与模型时，必须优先检索本地缓存，次选国内高可用镜像（如 ModelScope 或官方专线加速），严禁裸连容易超时的海外源；
3. **非侵入与优雅降噪**：缺失环境时，静默由后台推进自愈流并上报百分比进度；仅在需要真人授权时（如网盘/微信扫码登录）才转为 `ACTION_REQUIRED` 并生成优雅引导卡片，扫码完成后秒级自动完成状态切换。

---

## 一、 智能体目录物理架构规范 (Directory Layout)

任何一个接入立体空间系统的智能体（无论放入官方内置目录 `agents/`，还是放入私有挂载目录 `workspace/custom_agents/`），必须遵循如下规范的目录布局：

```text
agents/<agent_name>/                 # 智能体英文唯一标识目录 (snake_case)
├── config.yaml                      # 【必选】智能体元数据、UI 动态配置与触发声明
├── entry.py                         # 【必选】智能体主入口类 (继承 StandardAgent 并导出 setup 钩子)
├── README.md                        # 【必选】智能体业务价值、功能清单与接入说明
├── persona/                         # 【推荐】提示词工程与领域认知人设
│   └── prompt.md                    # 系统人设提示词 (System Prompt)
├── tools/                           # 【可选】0-Token 确定性私有工具集
│   ├── __init__.py
│   └── helper.py
└── skills/                          # 【可选】该智能体独占的复合技能包
```

---

## 二、 配置文件规范 (`config.yaml`)

`config.yaml` 是智能体向系统注册中心和前端工作台声明自身能力的**单一真实来源 (Single Source of Truth)**。

### 标准配置模板：
```yaml
name: "omni_sentinel"
display_name: "全维调度哨兵 (Omni Sentinel)"
version: "1.0.0"
icon: "🎬"
category: "自媒体矩阵"
description: "立体空间商业级自媒体总监：全自动素材扫描、语音转写、智能打标与一键发布闭环"
author: "Litikj Developer"

# 底部输入框快捷芯片 (Quick Chips)
quick_chips:
  - "⚡ [EXEC] ping (0-Token 基础连通测试)"
  - "🔍 [EXEC] check (全景环境与依赖体检)"
  - "🩹 [EXEC] heal (一键环境全自动静默自愈)"
  - "⚙️ [EXEC] config (查看通用设置面板)"
  - "你好，请介绍你的核心业务能力"

# 顶部工具栏动作按钮 (Actions)
actions:
  - label: "环境巡检"
    command: "[EXEC] check"
    icon: "🔍"
  - label: "一键自愈"
    command: "[EXEC] heal"
    icon: "🩹"
  - label: "设置配置"
    command: "[EXEC] config"
    icon: "⚙️"
  - label: "连通测试"
    command: "[EXEC] ping"
    icon: "⚡"

# 四维触发模式声明
triggers:
  fast_path:
    enabled: true
    prefix: "[EXEC]"
    commands: ["ping", "check", "heal", "config", "set", "help"]
```

---

## 三、 智能体通用标准面板开发规范 (Config Schema)

### 1. 为什么必须支持通用标准面板？
桌面端拥有统一的 `AgentSettingsModal.vue`（通用标准面板弹窗）。智能体无须编写一行前端代码，只需暴露 JSON Schema，前端即可动态自适应渲染出：
- 下拉选择框（单账号/多账号矩阵、出片模式等）；
- 时间选择器（晚间黄金发布档期、定时器）；
- 开关（布尔值配置）；
- 文本框（分区 TID、风格偏好等）。

### 2. 标准继承机制
直接继承 `StandardAgent`，自动获得配置面板能力与落盘持久化（`StandardConfigMixin`）：
```python
from core.standard_agent import StandardAgent

class MyBusinessAgent(StandardAgent):
    CONFIG_SCHEMA = {
        "title": "业务智能体预置配置",
        "type": "object",
        "properties": {
            "target_account": {
                "type": "string",
                "title": "运行账号矩阵",
                "enum": ["default", "main_account"],
                "enumNames": ["默认测试账号 (default)", "主矩阵账号 (main_account)"],
                "default": "default"
            },
            "auto_notify": {
                "type": "boolean",
                "title": "任务完成后桌面通知",
                "default": True
            }
        }
    }
    DEFAULT_CONFIG = {
        "target_account": "default",
        "auto_notify": True
    }
```

---

## 四、 0-Token 极速直达通道设计规范 (Fast-Path)

### 1. 原则
用户或界面经常需要触发：环境检查、列出列表、查看配置、切换账号等日常高频指令。这些指令**绝不允许调用大模型**，必须在本地毫秒级拦截并响应。

### 2. 基础指令自动集成
`StandardAgent` 的 `StandardFastPathMixin` 已经内置处理了：
- `[EXEC] ping`：毫秒级心跳回路；
- `[EXEC] check`：全景就绪度体检看板；
- `[EXEC] heal`：全自动静默自愈启动；
- `[EXEC] config`：当前生效配置看板；
- `[EXEC] set <key> <val>`：快捷配置修改并落盘；
- `[EXEC] help`：快速指令清单。

若智能体有专属业务指令，只需重写 `handle_custom_fast_path(self, command: str) -> Optional[str]` 即可。

---

## 五、 前置环境门禁与自愈设计规范 (Preflight Check & AutoHealer)

### 1. Fail-Early 原则（及早失败）
当音视频、图像、模型环境（如缺少 FFmpeg、缺少 faster_whisper、显卡 CUDA 异常、未登录平台账号）缺少必备依赖时：
- **禁止**：假装成功跑完生成虚假物料；
- **禁止**：直接抛出未捕获的 Python 异常使程序崩溃；
- **必须**：在第一道工序立即拦截阻断，直接向用户呈现标准诊断卡片。

### 2. 第三方依赖顶层导入禁令与懒加载规范 (Zero Top-Level Third-Party Imports)
- **【红线禁令】**：`entry.py` 与所属 `tools/*.py` 的顶层（模块全局作用域），**严禁直接 `import` 任何非 Python 标准库的第三方包**（例如 `requests`, `baidupcs_py`, `faster_whisper`, `PIL` 等）；
- **【根因机理】**：Tauri 伴生的便携式 Python 3.10 微内核默认零第三方依赖。若模块顶层导入第三方包，系统注册中心在扫描发现时会立即触发 `ImportError` 导致**整个智能体无法加载入职**，Fail-Early 门禁甚至来不及运行；
- **【标准范式】**：
  1. 顶层作用域**仅允许导入 Python 原生标准库**与系统统一基座（`core.*`）；
  2. 所有可选第三方包一律在**具体的类方法或工具函数内部按需懒加载 (Lazy Import)**；
  3. 导入失败时抛出结构化错误或返回友好提示，并在 Fast-Path 中挂载 `[EXEC] setup <target>`，调用 `PreflightChecker.install_python_packages` 实现一键自愈装配。

---

## 六、 内容提炼与兜底设计规范 (Content-First & NLP)

### 1. 绝对杜绝硬编码假模板
- 严格禁止在代码中写死“在 Android 自动化领域...一套工业级架构彻底搞定实操痛点”这类与具体视频毫无关系的通用套话；
- 每次输出的标题、简介、章节时间轴**必须严格来源于输入文本或音视频的真实内容**。

### 2. 双轨制动态生成范式
所有内容型智能体必须支持「双轨制」：
1. **优先轨 (LLM)**：调用 `LLMClient.chat(messages)`，在 Prompt 中要求大模型精读具体内容并生成标准 JSON；
2. **兜底轨 (Heuristic NLP)**：若大模型未联网、超出额度或返回解析失败，自动切换至 `core.nlp_extractor.HeuristicNLPExtractor`，使用纯 Python 本地算法从真实文本中提取前沿句子、高频专有名词以及转折点时间轴，保证 100% 真实。

---

## 七、 任务上报与交付闭环规范 (TaskReporter & Delivery)

### 1. 任务工序流转规范
在批处理任务中，必须使用 `TaskReporter` 划分工序，驱动桌面端实时展示任务阶梯进度条：

```python
reporter = context.get_reporter(title=f"{self.name} 交付流水线")

# 工序 1：环境与门禁巡检 (Fail-Early 零心智防御)
with reporter.step("环境与输入门禁体检"):
    readiness = self.get_readiness_status()
    if readiness.get("state") != "READY":
        heal_res = self.heal_environment()
        if heal_res.get("state") != "READY":
            return TaskResult(success=False, message="环境自愈受阻...")

# 工序 2：业务处理与内容提炼
with reporter.step("内容提炼与业务处理"):
    # 动态业务逻辑...
```

### 2. 交付成果卡片规范
任务完成后的 `TaskResult.message` 必须输出统一格式的 Markdown 交付简报：
1. **主标题与备选物料清单**；
2. **带真实章节时间戳的合规纯净简介**；
3. **标签 Tags 与关键元数据**；
4. **本地产物归档目录**；
5. **0-Token 一键确认按钮**（例如 `[EXEC] upload_draft`、`[EXEC] open_package`）。

---

## 八、 第三方账号鉴权与“主动服务横幅”规范 (Proactive Auth Banner & Fast-Path Login)

凡涉及外部第三方平台（如百度网盘、B站、公众号、小红书、抖音等）账户体系的智能体，必须遵从以下交互与凭据规范：

1. **聊天视窗常驻引导横幅（Proactive Banner）**：
   - 不能将登录动作仅放在欢迎界面的临时切片卡片中；
   - 在进入该智能体时，聊天顶部必须具备公告横幅：明确提示当前鉴权状态，右侧附带高优先级药丸按钮（如 `[📱 扫码登录]`、`[⚡ 状态诊断]`）。
2. **0-Token 快速直达指令对齐**：
   - 必须在 Fast-Path 中支持 `[EXEC] login` 和 `[EXEC] status`；
   - 扫码登录应优先拉起独立终端或图片查看器展示二维码，并异步监听凭据回传；
3. **凭据隔离与持久化安全**：
   - 凭据文件（Cookie、Token 等）必须统一落盘到 `workspace/data/<service>_credentials.json`；
   - 严禁将凭据写在智能体代码目录中，防止卡带打包时泄露私密数据。

---

## 九、 数字化员工全生命周期与版本透出规约 (Lifecycle & Version Visibility)

1. **招聘市场三态状态机**：
   - **态①（未在岗）**：展示 `📥 一键招募`（附带商业角色鉴权拦截，如未激活访客转导向设置页）；
   - **态②（发现新版）**：本地已安装但云端版本高于本地版本时，自动呈现琥珀色 `🔄 一键更新 (v{local} ➔ v{remote})`，支持平滑覆写解包并触发 Registry 热重载；
   - **态③（已是最新）**：展示 `🟢 已在岗 (v{version}) ✓`。
2. **全局版本显式透出**：
   - 左侧边栏列表名称右侧、顶部标题栏旁均必须渲染精致的 `vX.Y.Z` 标签；
   - 招聘市场卡片必须同时标注 `云端 v{version}` 与 `本地 v{version}`，彻底杜绝版本黑盒。

---

## 十、 工作流与人机断点协同接入 (Workflow Integration & Human Gate)

当智能体需要参与多智能体接力协同流水线时，在 `workflows/` 对应脚本中声明：

```python
flow = Workflow(name="my_flow", description="协同流水线说明")

# 步骤 1: 智能体 A 产出
flow.add_step(agent_name="agent_a", step_name="前置推演")

# 步骤 2: 人机协同审批断点 (Human Gate: 挂起等待人在工作台决策)
flow.add_human_gate(
    gate_id="choose_decision",
    title="决策审定节点",
    description="请核验数据并作出决策：",
    options_field="candidate_options"
)

# 步骤 3: 依据人做出的选择，后续智能体恢复执行
flow.add_step(
    agent_name="agent_b",
    step_name="执行后续动作",
    transformer=lambda shared_state, payload: {"chosen": shared_state.get("choose_decision")}
)
```

---

## 十一、 脚手架极速初始化指南 (Scaffold 2.0)

当需要创建新的工业级智能体时，直接使用脚手架命令一键生成标准工程：

```bash
# 生成自媒体/音视频类标准智能体
python -c "from core.scaffold import create_agent_scaffold; create_agent_scaffold('xiaohongshu_director', '小红书爆款图文与视频运营智能体', is_custom=False, agent_type='media')"

# 生成通用任务类标准智能体
python -c "from core.scaffold import create_agent_scaffold; create_agent_scaffold('customer_service_agent', '电商多平台智能客服总监', is_custom=False, agent_type='general')"
```

生成的工程会自动具备：
- ✅ 通用标准面板契约与落盘 (`StandardConfigMixin`)；
- ✅ 0-Token 快速直达与自定义通道 (`StandardFastPathMixin`)；
- ✅ 全自动环境自检与静默自愈声明 (`StandardSelfHealingMixin`)；
- ✅ 真实启发式 NLP 兜底 (`HeuristicNLPExtractor`)；
- ✅ TaskReporter 动态流水线进度上报；
- ✅ 100% 通过合规扫描的配套自动化测试脚本 (`tests/test_{name}.py`)。

---

## 十二、 单智能体准入验收清单 (Checklist)

新开发或重构智能体时，必须完成以下 **6 项严格验收** 方可发布：

- [ ] **1. 元数据完整性**：`config.yaml` 包含 `name`, `display_name`, `icon`, `quick_chips`, `actions`；
- [ ] **2. 0-Token 快速通道验证**：输入 `[EXEC] ping`、`[EXEC] check`、`[EXEC] heal` 能在 10 毫秒内响应，且绝对不产生任何大模型 Token 消耗；
- [ ] **3. UI 动态自适应验证**：在工作台左侧选中该智能体后，面包屑、图标、顶部 Action 按钮、底部 Chips 能够**全自动无缝切换**，前端无控制台报错；
- [ ] **4. 环境自检与自愈验证**：继承 `StandardAgent`，在缺失依赖或模型时触发静默自愈，绝不在界面抛出未捕获红色报错堆栈；
- [ ] **5. SOP 静态合规扫描**：运行 `python -c "from core.scaffold import check_agent_sop_compliance; from pathlib import Path; assert check_agent_sop_compliance(Path('agents/{name}')) == []"`；
- [ ] **6. 单体单元测试验证**：在 `tests/` 中编写针对该智能体的独立测试脚本，通过 `pytest` 自动化回归全绿。
