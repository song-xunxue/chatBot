# 服务端单元测试目录

> 作者: 李文煜
> 日期: 2026-06-24

## 1. 目录组织

按**里程碑**分层管理测试，每个子目录对应一个里程碑。测试文件归属"**被测功能所属里程碑**"（非测试编写批次）——例如 `shared/protocol` 属 M1 通信主干，其测试入 `m1/`（即便测试代码是 M2 验证批次补写的）。

```
server/tests/
├── conftest.py        # 顶层公共夹具（所有子目录继承）
├── m1/                # M1 骨架 / tracer bullet 通信主干
├── m2/                # M2 服务端核心管道
├── m3/                # M3 人设 + 记忆系统
├── m4/                # M4 插件系统
└── README.md
```

## 2. 各里程碑落点

| 目录 | 里程碑 | 覆盖模块 |
|---|---|---|
| `m1/` | M1 骨架/通信主干 | `shared/protocol` |
| `m2/` | M2 服务端核心管道 | `llm`(openai_compat/registry) + `pipeline`(runner/stages) + `storage`(chat_store) |
| `m3/` | M3 人设+记忆 | `persona`(store/renderer/importer/rest) + `memory`(store/encoder/forgetting/forget_tick/coordinator/rest) + 端到端集成(`pipeline_e2e`/`e2e_memory`) |
| `m4/` | M4 插件系统 | `plugin_manager` / `eventbus` / 模板示例 / 各类插件 |

> 当前规模：M1=5 项 / M2=30 项 / M3=101 项，合计 136 项。

## 3. 运行方式

```bash
# 全量（在 server/ 目录下执行）
python -m pytest

# 单个里程碑
python -m pytest tests/m2/

# 单个文件
python -m pytest tests/m3/test_memory_store.py

# 详细输出
python -m pytest tests/m3/ -v
```

## 4. 约定

- **新增测试**放入对应里程碑目录（如 M4 插件测试入 `m4/`），不再平铺在顶层。
- **跨模块集成测试**（`*_e2e.py`）并入其验证功能所属的里程碑目录（如 `pipeline_e2e`/`e2e_memory` 入 `m3/`）。
- **局部夹具**：某期专用夹具放该期子目录的 `conftest.py`（如 `m4/conftest.py` 放 mock 插件目录 / fake EventBus）；**公共夹具**（fakeredis / reset_llm / coord / client）留在顶层 `conftest.py`。
- 顶层 `conftest.py` 的 `sys.path` 注入对子目录测试自动生效，子目录测试的 `import` 无需改动。
