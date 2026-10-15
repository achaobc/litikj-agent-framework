# 🧩 【通用原子技能仓 (Skills Directory)】

本目录是 **立体空间智能体系统** 的可复用原子技能仓。  
技能是细粒度的动作执行器（如：调用某大模型、处理图片格式、音视频切片、网页提取等）。

---

## 📂 技能开发规范

每个独立的技能为一个子目录，标准结构如下：

```text
skills/
└── my_tool/
    ├── __init__.py
    └── entry.py                 # 实现 BaseSkill 并暴露 setup(registry)
```

---

## 📝 技能标准代码模板 (`entry.py`)

```python
from core.contract import BaseSkill
from core.registry import Registry

class MyToolSkill(BaseSkill):
    def __init__(self):
        super().__init__(name="my_tool", description="通用的数据清洗转换工具")

    def execute(self, params: dict) -> dict:
        text = params.get("text", "")
        # 执行具体的数据处理
        return {"processed": text.strip().upper()}

def setup(registry: Registry):
    """框架加载插件时的自动注册钩子"""
    registry.register_skill(MyToolSkill())
```
