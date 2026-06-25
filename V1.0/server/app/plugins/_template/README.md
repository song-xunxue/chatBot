# 插件开发模板

本目录以 `_` 开头，**不会被 PluginManager 自动加载**，仅供复制参考。
开发新插件：复制本目录到 `plugins/` 下并重命名为插件名（kebab-case），然后改 `plugin.yaml` 与 `plugin.py`。

## 1. 三步开发

1. 改 `plugin.yaml`：`name`（唯一）、`description`、`hooks`（订阅的钩子+优先级）、`config_schema`（可配置项+默认值）
2. 在 `plugin.py` 实现 `Plugin` 子类的钩子方法（按需覆盖 `on_after_llm` / `on_before_llm` / ...）
3. 启动时自动发现；通过 REST 开启：
   - 全局：`POST /api/v1/plugin/{name}/enable`
   - 按对象：`PUT /api/v1/plugin/object/{object_id}/{name}` body `{"enabled": true, "params": {...}}`

## 2. 钩子（docs/05 §6）

| 钩子 | 触发点 | STOP 影响 |
|---|---|---|
| `on_message_in` | 用户消息到达 | 丢弃该消息 |
| `on_before_llm` | 调 LLM 前 | 跳过 LLM（插件可自产 `reply_text`） |
| `on_after_llm` | LLM 产出后 | 跳过回复增强 |
| `on_message_out` | 回复发出前 | —— |
| `on_tick` | 定时（M4.4 调度器驱动） | —— |
| `on_delete` | 消息标记删除（persona_evolve 负样本） | —— |

钩子签名：`async def on_xxx(self, ctx) -> HookResult | None`（`None` 视为 `CONTINUE`）

## 3. 可读写的上下文字段（MessageContext）

- 读：`ctx.object_id` / `ctx.user_text` / `ctx.reply_text` / `ctx.persona_card` / `ctx.history`
- 写：`ctx.reply_text`（改回复）、`ctx.rich`（收集 `audio`/`sticker`/`image` 富内容）、`ctx.plugin_meta`（插件间协调暂存）
- 返回 `HookResult.STOP` 中断；默认 `CONTINUE`

## 4. 取参数

```python
params = await self.get_params(ctx.object_id)   # 合并 config_schema 默认值与按对象覆盖
```

## 5. 优先级与隔离（docs/05 §6/§8）

- `priority` 小先执行；同一钩子被多插件订阅时按优先级串联
- 单插件抛异常被 EventBus 捕获、记录、跳过，**不影响**其他插件与主流程
