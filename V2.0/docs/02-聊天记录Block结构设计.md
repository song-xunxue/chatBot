# 聊天记录 Block 结构设计文档

> 文档编号：ChatBot-V2-02
> 版本：v0.1（初稿，待评审）
> 作者：李文煜
> 日期：2026-06-25
> 上游：`01-V2.0计划.md`
> 下游：`03-心情系统设计.md`（评分补偿 `mood_bias` 被本文 `score` 四元组引用）、里程碑 M2（核心复用 copy）/ M3（评分系统）/ M7（Web 面板历史/评分页）/ M8（代答连发）

---

## 1. 引言

V1.0 的聊天记录是一条扁平的 Redis List（`mychat:chat:{oid}`），严格一问一答、无评分、无分组、代答单 active 覆盖式连发会丢。V2.0 接入 QQ 官方机器人后，对话场景发生本质变化：**不等长对话**（一方连发多条对方未回）、**评分追溯**、**代答批量连发**、**训练样本与真实对话物理隔离**，扁平 List 已无法表达。

本文定义 V2.0 聊天记录的**三层逻辑结构**：会话（object）→ blocks（有序）→ messages（有序），并约定 Redis 物理存储键、Python API、REST 接口与 V1.0 字段迁移方案。心情系统的评分补偿细节见 `03-心情系统设计`，本文只引用其 `mood_bias` 产出。

## 2. 设计目标

| 目标 | 说明 | 对应章节 |
|---|---|---|
| 支持不等长对话 | block 内 messages 自由数组，允许一方连发 | §3、§7 |
| 评分可追溯 | 每条 message 带 score 四元组（base / mood_at / bias / final） | §5 |
| mid 稳定外键 | 弃 V1.0「List 索引删后前移」的不稳定 mid，全局 UUID | §5、§13 |
| 代答批量连发 | pending 改队列（多 pending 共存），替代 V1.0 单 active 覆盖 | §8 |
| 训练样本隔离 | roleplay block 物理隔离，绝不进 `get_history`/LLM 上下文 | §9 |
| 会话语义切分 | 按静默间隔/回合开闭 block，便于分段检索与上下文窗口管理 | §6 |

## 3. 三层数据模型总览

```
会话 Session（object_id）            一个 QQ 私聊对象 = 一个会话
  └─ blocks[]（有序，按 start_ts 升序）  会话被切分为若干 block
       └─ messages[]（有序，按 ts 升序） block 内自由数组，允许不等长连发
```

- **会话**：对应一个 `object_id`（QQ 私聊场景下 = QQ 用户 openid）。一个会话生命周期内有多个 block。
- **Block**：一个语义连续的对话片段。新建条件见 §6（静默超阈值或回合结束）。block 是 LLM 上下文窗口管理与分段检索的基本单位。
- **Message**：单条消息（user / ai / proxy / system）。block 内 messages 是**有序数组**，不强制配对，允许一方连发。

> 与 V1.0 的差异：V1.0 只有「会话 → messages」两层、严格一问一答；V2.0 增加中间层 block，且 messages 解除配对约束。

## 4. Block 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `block_id` | str(UUID) | block 唯一标识，全局生成 |
| `object_id` | str | 所属会话（外键） |
| `start_ts` | int(ms) | block 内首条消息时间戳 |
| `end_ts` | int(ms) | block 内末条消息时间戳（关闭时回填） |
| `status` | str | `open`（开放，可继续追加）/ `closed`（已关闭，新消息开新 block） |
| `source` | str | 来源：`live`（真实 QQ 对话）/ `roleplay`（训练样本）/ `proxy`（代答注入）/ `system` |
| `summary` | str | 可选，block 关闭时由编码器生成的情景摘要（供 M4 记忆 Episodic 层） |
| `close_reason` | str | 关闭原因：`silence`（静默超阈值）/ `turn_end`（回合结束）/ `manual`（手动） |

## 5. Message 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `mid` | str(UUID) | 消息全局唯一标识（弃 V1.0 List 索引），稳定外键 |
| `block_id` | str | 所属 block（外键） |
| `object_id` | str | 所属会话（冗余存，便于跨 block 查询） |
| `sender` | str | `user`（用户）/ `ai`（LLM 产出）/ `proxy`（代答人工产出）/ `system`（系统提示） |
| `content` | str | 文本内容 |
| `rich` | JSON | 富内容（图片/语音/表情包/卡片），M6 多模态与 M4 插件 ctx.rich 复用 |
| `ts` | int(ms) | 时间戳 |
| `source` | str | 来源：`live` / `roleplay` / `proxy` / `tool`（工具产出） |
| `status` | str | `active` / `edited` / `deleted`（软删，保留供人格负样本）/ `recalled`（仅 user） |
| `score_base` | int | **评分四元组①**：基础分（0-100），自动 LLM 评 + 手动覆盖；仅 ai/proxy 消息有 |
| `mood_at_score` | float | **评分四元组②**：评分时刻的 mood 值 [0,1]，追溯补偿依据 |
| `mood_bias` | float | **评分四元组③**：心情补偿（= 心情档位 `score_bias` + 噪声，见 03-心情系统）；user 消息恒 0 |
| `score` | int | **评分四元组④**：最终分 = `clamp(score_base + mood_bias, 0, 100)`，驱动 reverse_infer 反推阈值判断 |

### 5.1 评分四元组关系

```
score_base      ← 自动 LLM 评分（对照人设打 0-100）或 Web 面板手动改分
mood_at_score   ← 评分时读取 mychat:mood:{oid} 的当前 mood 值
mood_bias       ← lookup(mood) 得档位 → 档位.score_bias + uniform(-noise, noise)
score           ← clamp(round(score_base + mood_bias), 0, 100)    ← 驱动反推
```

- 仅 `sender in (ai, proxy)` 的消息产生 score；`user`/`system` 消息 score 字段为空。
- **反推驱动**（M3）：`score < 60` → 负样本；`score > 85` → 正样本；阈值见 `03-心情系统` 全局参数。

## 6. 分组决策 A：静默间隔与对话回合

新建 block 的触发条件（任一满足即关闭旧 block、开新 block）：

| 条件 | 默认阈值 | 可配 | 说明 |
|---|---|---|---|
| 静默间隔 | 10 分钟 | ✅ 全局参数 `block_silence_min` | 当前时间与 block 末条 `ts` 之差超阈值 |
| 回合结束 | — | — | 连发输入合并后 LLM 产出完成 + 用户下一轮输入前（见 §7） |
| 手动 | — | — | Web 面板「结束当前对话片段」按钮 |

**判定流程**（收到新 user 消息时）：

1. 取会话当前 open block（无则开新）；
2. 若 `now - block.end_ts > block_silence_min * 60000`：close 旧 block（`close_reason=silence`，回填 `end_ts`，触发摘要编码）→ 开新 block；
3. 否则追加进当前 open block；
4. 新 block `start_ts` = 首条消息 `ts`，初始 `status=open`。

> 设计意图：block 既用于语义切分（分段检索、情景摘要），也用于**控制 LLM 上下文窗口**——`get_history`（§10）默认只取最近 1-2 个 block，跨 block 历史走 Episodic 摘要（M4 记忆融合），避免长对话上下文爆炸。

## 7. 不等长对话与连发

QQ 私聊中用户常**连发多条**（如「在吗」「在不在」「看到回我」），V2.0 必须合并为一次 LLM 调用（否则 N 条 = N 次 LLM + N 次记忆读写 + N 次评分，成本与体验硬伤）。

**连发合并策略**（借鉴 AstrBot continuous_message，融入 QQ 适配层）：

1. 收到首条 user 消息 → 启动防抖计时器（默认 `input_debounce_sec=2`，可配）；
2. 计时器期间到达的后续 user 消息 → 追加进**同一 open block** 的 pending 输入缓冲，重置计时器；
3. 计时器超时（用户停止连发）→ 合并缓冲为一次输入 → 走 pipeline → LLM 产出一条或多条 ai 消息（见下）；
4. **输出连发**：LLM 可一次产出多条 ai 消息（人设口语化分段），逐条入库、逐条评分、逐条下发 QQ（借鉴 outputpro 分段回复）。

不等长体现：block 内 messages 是自由数组，允许出现 `[user, user, user, ai, ai]`、`[user, ai, user]` 等任意配比。

## 8. 代答连发：pending 队列（替代单 active）

### 8.1 V1.0 问题

V1.0 `takeover` 用 `mychat:takeover:active:{oid}` 存**单 active pending_id**，新请求 `SET` 覆盖旧 active（`open_takeover_request` 直接覆写）。结果：管理员连发多条代答时，只有最后一条保留，前面被覆盖丢失。

### 8.2 V2.0 改造：per-object 有序队列

| Key | 类型 | 说明 |
|---|---|---|
| `mychat:takeover:queue:{oid}` | **List** | per-object pending_id 顺序队列（FIFO，`LPUSH` 入队 `RPOP` 出队，或 `RPUSH`+`LPOP`） |
| `mychat:takeover:pending:{oid}:{pid}` | **Hash** | 待答详情：`user_text, created_ts, object_id, status`（沿用 V1.0 结构） |
| `mychat:takeover:enabled:{oid}` | **String** | per-object 代答开关（沿用 V1.0） |

**行为**：
- `open_request`：`INCR` 全局序生成 `pid` → 写 pending Hash → **`RPUSH` 入队**（不再覆盖）；
- `resolve_answer`：校验 pending 存在 + object_id 匹配 + **队首 pid**（或任意 pid，见下）→ 落 ai 消息（`sender=proxy`，进四级记忆，见 V1.1 决策）→ 出队；
- 管理员可**批量录入连发**：面板一次提交多条代答 → 服务端按序逐条下发 QQ REST（M8 代人聊天），全部入同一 block。

> 「任意 pid vs 队首」：默认按队列顺序消费（队首）；面板「跳过当前/指定应答」时允许按 pid 直接 resolve。具体由 M8 实现规格定，本文只约定队列结构与「不丢」语义。

## 9. Redis 键设计

> Key 前缀规范：`mychat:<域>:<id>[:<子>]`。所有时间戳 Unix 毫秒。

### 9.1 真实聊天（source=live）

| Key | 类型 | 说明 |
|---|---|---|
| `mychat:chat:{oid}:blocks` | **Sorted Set** | score=`block.start_ts`，member=`block_id`；按时间序索引该会话所有 block |
| `mychat:block:{block_id}` | **Hash** | block 元数据（§4 字段） |
| `mychat:block:{block_id}:msgs` | **Sorted Set** | score=`msg.ts`，member=`mid`；block 内消息时间序 |
| `mychat:msg:{mid}` | **Hash** | 消息详情（§5 字段，含 score 四元组） |
| `mychat:chat:{oid}:active_block` | **String** | 当前 open block_id（无则空，加速判定，可由 blocks 尾部推导） |

### 9.2 roleplay 物理隔离（source=roleplay）

**铁律**：训练样本绝不可进 `get_history`/LLM 上下文（守 V1.0 防污染）。独立前缀：

| Key | 类型 | 说明 |
|---|---|---|
| `mychat:block_roleplay:{oid}:blocks` | **Sorted Set** | roleplay block 索引 |
| `mychat:block_roleplay:{block_id}` | **Hash** | roleplay block 元数据 |
| `mychat:block_roleplay:{block_id}:msgs` | **Sorted Set** | roleplay block 内消息序 |
| `mychat:msg_roleplay:{mid}` | **Hash** | roleplay 消息详情 |
| `mychat:roleplay:neg:{oid}` | **List** | 被删 roleplay 样本（负样本信号，沿用 V1.0） |

> `get_history`（§10）**只读 `mychat:block:*` / `mychat:msg:*` 真实键**，扫描时按前缀天然隔离 roleplay。

### 9.3 与 V1.0 键对照

| V1.0 键 | V2.0 键 | 变化 |
|---|---|---|
| `mychat:chat:{oid}`（List） | `mychat:chat:{oid}:blocks` + `mychat:block:*` + `mychat:msg:*` | List 拆为 block 索引 + msg Hash，mid 改 UUID |
| `mychat:chat_roleplay:{oid}`（List） | `mychat:block_roleplay:{oid}:blocks` + ... | 同上，隔离前缀不变 |
| `mychat:roleplay:neg:{oid}` | 沿用 | 不变 |
| `mychat:takeover:active:{oid}`（单 active） | `mychat:takeover:queue:{oid}`（队列） | 单 active → 有序队列 |

## 10. get_history 策略（LLM 上下文拼装）

```python
async def get_history(redis, object_id, *, max_blocks=2, max_messages=20) -> list[Message]:
    """取最近 max_blocks 个 block 的最近 max_messages 条消息（时间正序），转 Message 供 LLM。
    只读真实聊天键，绝不读 roleplay 隔离键。"""
```

- **默认只取最近 2 个 block**：控制上下文窗口，跨 block 历史依赖 M4 Episodic 摘要（每个 closed block 的 `summary`）。
- **二次裁剪**：取到的 block 内 messages 若超 `max_messages`，按 ts 取最近 N 条。
- **只取 role/content**：转 `Message` 时忽略 score/rich 等附加字段（保持 LLM 输入稳定，与 V1.0 一致）。
- **软删过滤**：`status in (deleted, recalled)` 的消息不进 LLM 上下文，但保留在存储供人格负样本。
- **独立展示接口**：`list_messages`（含 score/rich/完整字段）供 Web 面板历史页，与 `get_history`（只给 LLM）分离。

## 11. Python API 设计

落点 `server/app/storage/chat_store.py`（copy 自 V1.0 后重写），保持 async + Redis 风格。核心函数：

```python
# Block 管理
async def open_or_get_block(redis, object_id, *, source="live") -> dict
    """取当前 open block；若过期（静默超阈值）或不存在，close 旧的并开新 block，返回 block dict"""
async def close_block(redis, block_id, *, reason="silence") -> None
    """关闭 block：回填 end_ts、status=closed、触发情景摘要编码（M4 钩子）"""

# Message 写
async def append_message(redis, object_id, *, sender, content, rich=None,
                         source="live", ts=0) -> str
    """追加消息：落进当前 open block，生成全局 UUID mid，返回 mid。
    ai/proxy 消息由调用方后续补 score 四元组（见 12 节 score 接口）"""
async def append_message_batch(redis, object_id, *, items: list[dict]) -> list[str]
    """批量追加（连发场景：user 连发或代答连发），同一 block，返回 mid 列表"""

# Message 读
async def get_history(redis, object_id, *, max_blocks=2, max_messages=20) -> list[Message]
    """LLM 上下文：最近 block 的最近消息，仅 role/content，roleplay 隔离"""
async def list_messages(redis, object_id, *, block_id=None, limit=500) -> list[dict]
    """完整字段（含 score 四元组），供 Web 面板历史页"""
async def get_message(redis, mid) -> dict | None
    """按 mid 取单条（全局 UUID，稳定外键）"""

# Message 改 / 删
async def update_message(redis, mid, *, content=None, sender=None) -> bool
async def delete_message(redis, mid, *, reason="out_of_character") -> bool
    """软删：status=deleted + delete_reason，保留供人格负样本（不物理删）"""

# 评分
async def set_score(redis, mid, *, score_base, mood_value, mood_bias) -> dict
    """写入 score 四元组：mood_at_score=mood_value，score=clamp(score_base+mood_bias)。
    返回完整四元组，供反推判断（M3）"""

# roleplay（物理隔离，API 对称）
async def append_roleplay_message(redis, object_id, *, role, content) -> str
async def list_roleplay(redis, object_id, *, limit=1000) -> list[dict]
async def update_roleplay(redis, mid, content) -> bool
async def delete_roleplay(redis, mid) -> bool   # 删→写入 neg 队列
```

> 实现细节（如 block 过期判定的原子性、msg Hash 的 TTL）留 M2 实现规格；本文只定契约。

## 12. REST 接口设计

落点 `server/app/api/rest_chat.py`（V2.0 新增，整合 V1.0 `rest_roleplay`）。鉴权沿用 V1.0 `X-Access-Token` 依赖。

### 12.1 真实聊天历史（M7 面板用）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/chat/{object_id}/blocks` | 列出会话所有 block（含 status/时间/summary） |
| GET | `/api/v1/chat/{object_id}/messages?block_id=&limit=` | 列消息（完整字段含 score 四元组） |
| GET | `/api/v1/chat/messages/{mid}` | 按 mid 取单条 |
| PATCH | `/api/v1/chat/messages/{mid}` | 编辑消息内容（改 → status=edited） |
| DELETE | `/api/v1/chat/messages/{mid}` | 软删消息（→ 负样本） |
| POST | `/api/v1/chat/{object_id}/blocks/close` | 手动关闭当前 block（close_reason=manual） |

### 12.2 评分（M3）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/chat/messages/{mid}/score` | 取该消息 score 四元组 |
| PATCH | `/api/v1/chat/messages/{mid}/score` | 手动改分（覆盖 score_base，重算 score） |
| GET | `/api/v1/chat/{object_id}/health` | 人设健康度：近 N 条均分、正/负样本计数 |

### 12.3 roleplay 训练（M8，整合 V1.0 rest_roleplay）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/roleplay/{object_id}/messages` | 录 roleplay 对话（隔离键） |
| POST | `/api/v1/roleplay/{object_id}/messages/batch` | **批量录连发**（V2.0 新增，替代 V1.0 单条/配对） |
| GET | `/api/v1/roleplay/{object_id}/messages` | 列 roleplay 样本 |
| PUT | `/api/v1/roleplay/{object_id}/messages/{mid}` | 改单条 |
| DELETE | `/api/v1/roleplay/{object_id}/messages/{mid}` | 删单条（→ neg 队列） |

### 12.4 代答（M8，整合 V1.0 rest_takeover）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/takeover/{object_id}/toggle` | 开关代答模式 |
| GET | `/api/v1/takeover/{object_id}/queue` | **列队列**（V2.0 改，V1.0 是 list_pending 全局） |
| POST | `/api/v1/takeover/{object_id}/answer` | 应答（按 pid 或队首），落 proxy 消息进四级记忆 |
| POST | `/api/v1/takeover/{object_id}/answer/batch` | **批量连发应答**（V2.0 新增，逐条下发 QQ） |

## 13. V1.0 → V2.0 字段迁移

| V1.0 message | V2.0 message | 迁移说明 |
|---|---|---|
| `role`(user/ai/proxy) | `sender`(user/ai/proxy/system) | 重命名 role→sender（避免与 LLM Message.role 歧义），增 system |
| `content` | `content` | 不变 |
| `ts` | `ts` | 不变 |
| `msg_type` | 并入 `rich` | 类型字段移入富内容结构 |
| `mid`(List 索引) | `mid`(UUID) | **重写**：迁移时为每条生成 UUID，弃索引 |
| `source`(user_turn) | `source`(live/roleplay/proxy/tool) | 枚举细化 |
| `status`/`deleted`/`recalled` | `status`(active/edited/deleted/recalled) | 合并为单 status 字段 |
| `mood`(消息附) | `mood_at_score` | 移入 score 四元组，仅 ai/proxy |
| — | `block_id` | **新增**：迁移时按静默间隔回溯切分 block |
| — | `score_base`/`mood_at_score`/`mood_bias`/`score` | **新增**：历史消息迁移时 score 留空（无追溯），新消息起算 |

**迁移脚本**（M9 部署时执行，一次性）：
1. 遍历每个 `object_id` 的 V1.0 `mychat:chat:{oid}` List；
2. 按相邻消息 `ts` 间隔 > `block_silence_min` 切分 block；
3. 为每条生成 UUID mid、映射字段、写入 V2.0 键结构；
4. roleplay List 同理迁移到隔离前缀；
5. V1.0 键保留只读（不删）直至验证完成。

## 14. 里程碑影响

| 里程碑 | 本文相关落点 |
|---|---|
| M2 复用核心 | copy V1.0 `chat_store.py` → 按 §9/§11 重写为 block 结构；pipeline 接入 block 开闭与连发合并 |
| M3 评分系统 | §5 score 四元组 + §12.2 评分接口；调用 `03-心情系统` 算 mood_bias |
| M4 记忆融合 | block `summary` 喂 Episodic 层；§10 跨 block 走摘要而非全量 |
| M7 Web 面板 | §12.1 历史/Block 页 + §12.2 评分/健康度页 + Mood.vue（见 03） |
| M8 代答 | §8 pending 队列 + §12.3/§12.4 批量连发 + roleplay 批量录 |
| M9 部署 | §13 字段迁移脚本 |

## 15. 变更日志

| 日期 | 变更说明 |
|---|---|
| 2026-06-25 | 初稿 v0.1：三层数据模型（会话→blocks→messages）、Block/Message 字段（含 score 四元组）、分组决策 A（静默间隔 10min）、连发合并、代答 pending 队列（替单 active）、Redis 键设计（含 roleplay 物理隔离）、get_history 策略、Python API、REST 接口、V1.0 字段迁移、里程碑影响 |
