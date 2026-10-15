# 📁 学员私有外部智能体挂载区 (Custom Agents Directory)

欢迎来到立体空间智能体操作系统 (Litikj Agent OS) 的私有智能体扩展区！

---

## 🌟 核心理念：框架与业务彻底物理隔离

在商业级 AI Agent 工程中，**微内核底座（系统框架）** 与 **业务智能体（具体的业务逻辑与私有代码）** 必须严格解耦：
1. **官方内置目录 (`agents/`)**：随系统框架发布，包含官方提供的标准智能体范式（如 `echo_demo`、`mentor_achao`、`omni_sentinel`）；
2. **私有挂载目录 (`workspace/custom_agents/`)**：专门存放学员自己开发、调试的私有商业智能体或独立 Git 仓库；
3. **安全防泄露**：系统构建脚本 (`scripts/build_release.py`) 在打包时会自动**完全排除**私有智能体代码，确保您的商业资产安全不外泄。

---

## 🚀 两种外部智能体引入方式

### 方式一：直接放入当前私有工作区（推荐）
直接在 `workspace/custom_agents/` 下新建一个子文件夹，例如 `workspace/custom_agents/my_market_analyst/`。
只需要该文件夹下包含一个 `entry.py`（或 `__init__.py`），启动系统时框架即可**自动感知、动态热加载**！

```text
workspace/custom_agents/
└── my_market_analyst/
    ├── config.yaml
    ├── entry.py         <-- 必须包含 setup(registry) 钩子
    └── README.md
```

### 方式二：挂载电脑上的任意绝对路径 / 独立 Git 仓库
如果你的智能体代码存放在电脑上的其他目录（例如 `D:\Work\awesome_agent`），或者使用独立的 Git 子仓库进行团队协同管理：
只需打开 `configs/framework.yaml`，在 `system.extra_agent_dirs` 下追加你的物理路径即可：

```yaml
system:
  # ... 其他配置保持不变 ...
  extra_agent_dirs:
    - "workspace/custom_agents"
    - "D:/Work/awesome_agent"
    - "E:/GitRepos/bilibili_crawler_agent"
```

---

## 📝 编写一个外部智能体的极简模板

在你的外部智能体目录下创建 `entry.py`：

```python
# -*- coding: utf-8 -*-
from core.contract import BaseAgent, TaskContext, TaskResult
from core.guards import LicenseGuard
from core.registry import Registry

class MyCustomAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="my_custom_agent",
            description="我的学员私有专属智能体"
        )
        # 1. (选填) 挂载官方商业防盗版门禁
        self.add_pre_guard(LicenseGuard())
        
        # 2. 人设设定
        self.system_prompt = "你是我的私有专属智能体助手。"

    def run(self, context: TaskContext) -> TaskResult:
        """批处理入口"""
        return TaskResult(success=True, message="执行成功", data={"res": "hello"})

    def handle_fast_path(self, command: str):
        """0-Token 快速直达入口"""
        if command == "ping":
            return "pong! (来自外部私有智能体)"
        return None

def setup(registry: Registry):
    """插件自动注入钩子 (微内核动态发现规范)"""
    registry.register_agent(MyCustomAgent())
```

---

## 🔍 验证生效
保存后，在系统根目录执行以下任一命令即可看到挂载效果：
```bash
python run.py list        # 智能体列表中会标注 [外部挂载]
python run.py diagnose    # 巡检界面会自动列出已挂载的外部智能体
```
或者启动可视化桌面工作台：
```bash
python run.py gui
```
在左侧智能体列表中直接选择并开启交互！
