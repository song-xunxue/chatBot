# 08 表情包增强（sticker_plus 插件）与库管理 REST

> 2026-10-25 新增。配套代码：`server/app/plugins/sticker_plus/`、`server/app/api/rest_sticker.py`、
> `server/app/storage/sticker_store.py`（追加库管理函数）、`server/app/main.py`（tick 活跃源修复 + 路由挂载）。
> 同批修复：on_tick 调度活跃源集成 bug（见 §2）。全量后端测试 599 项全绿（mychat 环境）。

## 1. 功能一览

| 能力 | 入口 | 默认状态 |
| --- | --- | --- |
| 自动配图（回复追加表情包 token） | sticker_plus 插件 `on_message_out`（优先级 350） | **关闭**（default_enabled: false，面板插件页开启） |
| 文字表情包生成（PIL 底图叠字） | `POST /api/v1/sticker/render` | 随服务可用 |
| 表情包库管理（列/传/删/重描述） | `/api/v1/sticker/*` REST | 随服务可用 |

## 2. on_tick 活跃源修复（bug 前后差异）

TickScheduler 每 `plugin_tick_interval`（默认 60s）对"活跃 oid"触发 on_tick（驱动
time_aware 时辰缓存 / proactive_reply 主动搭话）。

| | 修复前 | 修复后（`main.py tick_object_ids`） |
| --- | --- | --- |
| 活跃源 | 仅 `mychat:mood:oids`（只有命中过 mood 情感词的会话） | 最近会话（`chat_store.list_recent_sessions`，SCAN `mychat:chat:*:blocks`）∪ mood oids 并集 |
| 真实私聊 | 未命中情感词就永不进 tick，须手动 `SADD` | 只要有聊天 block 自动进活跃源 |
| 非数字 oid（seed 的 demo 等） | 下游 `onebot.send_text` 内 `int(oid)` 抛 invalid literal（被捕获记 error，主动搭话静默失败） | `isascii()+isdigit()` 双卡过滤，跳过并 debug 日志（`²`/`２` 这类 Unicode 数字也拦） |
| 单数据源故障 | — | 降级用另一源，调度器不停摆 |

单测：`server/tests/test_tick_object_ids.py`（5 项）。

## 3. sticker_plus 插件（自动配图）

### 3.1 工作方式

回复发出前（pipeline 的 `on_message_out` 钩子，在 **存历史之前** 触发）按可解释算法从
表情包库挑一张，向 `ctx.reply_text` 末尾追加一行 `[表情包: 描述]` token——出站由
`onebot.send_text` 解析为真实图片**独立成条**发出；token 同步进历史/训练数据（与
OUTPUT_CONTRACT 机制一致）。

排除规则（跳过即不配图，debug 日志带原因）：`ctx.reply_sent`（TTS 已发语音等更早插件截胡）/
空白回复（含纯语音）/ 本条已含表情包 token（**最多 1 张/条**）/ 概率未命中。

### 3.2 面板参数（plugin.yaml config_schema，全部即时可配）

| 键 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| attach_prob | number | 0.35 | 触发概率，0=从不，1=每条必配 |
| mood_weight_enable | bool | true | 按当前心情档位过滤候选（无命中回退全库） |
| mood_keywords | string | "" | 档位附加关键词，格式 `档位:词,词;档位:词`（冒号/逗号/分号均兼容全角；留空仅用档位名匹配） |
| usage_window | number | 10 | 最近使用降权窗口条数（0=不记使用） |
| render_template | string | "" | 文字表情默认底图路径（面板预填给 render 用） |
| render_font | string | C:/Windows/Fonts/msyh.ttc | 文字表情字体路径 |
| render_font_size | number | 48 | 字号（像素），12~200 |
| render_stroke | number | 2 | 描边宽度像素，0=不描边 |
| render_position | string | bottom | 文字位置 top/center/bottom |

### 3.3 挑选算法（可解释，日志 reason 形如 `心情过滤[开心]候选3/49;重叠2;降权-1.5`）

1. 候选 = 库内描述非空且文件存在的条目；
2. 心情过滤：当前档位 label + mood_keywords 附加词，desc 含任一关键词（casefold 子串）即命中收窄，无命中回退全库；
3. 重叠打分：回复与描述的字符二元组（bigram）交集数；
4. 最近使用降权：`mychat:sticker:recent_usage` 队列第 i 位扣 `(window-i)*0.5`；
5. 同分并列随机（避免总发同一张）。

## 4. 文字表情渲染与底图白名单

`POST /api/v1/sticker/render` 用 PIL 在底图上叠字生成 PNG 入库并注册描述（描述=文字本身，
≤40 字）。**底图白名单：仅允许 `server/data/stickers/templates/` 目录内的文件**——白名单外、
不存在或损坏的底图一律回退纯色画布（深灰底白字黑描边）并 warning。同文字同底图幂等覆盖
（文件名 `render_{md5(文字|底图全路径)[:16]}.png`）。小底图放不下文字时自动纵向扩画布。
渲染在线程池执行（`asyncio.to_thread`），不阻塞事件循环。

## 5. 库管理 REST（全部 `X-Access-Token` 鉴权，未带 token → 401）

| 方法/路径 | 入参 | 返回 | 错误 |
| --- | --- | --- | --- |
| GET `/api/v1/sticker/list` | — | `{items:[{file,desc,size,last_used,exists}]}` | 401 |
| POST `/api/v1/sticker/upload` | `{data_base64 必填, name 可选, desc 可选}` | `{file,desc,registered}`（vision 判非表情包 → registered:false + warning） | 400：缺字段/非法 base64/解码前>7MB/解码后>5MB/魔数非 gif·png·jpg·webp/名字非法/同名已存在/desc 超 40 字或含 `]` |
| DELETE `/api/v1/sticker/{name}` | 路径名 | `{deleted}` | 404：不存在/名字非法（白名单 `[A-Za-z0-9_.-]`，拒 `..`、全点名、Windows 保留名） |
| POST `/api/v1/sticker/{name}/describe` | 路径名 | `{name,desc}`（重跑 vision 更新描述） | 400：文件不存在/vision 失败或判非表情包 |
| POST `/api/v1/sticker/render` | `{text 必填, template 可选, font/font_size/stroke_width/position 可选}` | `{token,file,desc}` | 400：文字空/超 40 字/参数非整数；503：Pillow 未装 |

使用示例（token 即面板 ACCESS_TOKEN）：

```bash
# 列库
curl -H "X-Access-Token: <token>" http://127.0.0.1:8091/api/v1/sticker/list
# 生成文字表情（自动入库注册，返回的 token 可直接贴进代答/回复文本发出真图）
curl -X POST -H "X-Access-Token: <token>" -H "Content-Type: application/json" \
  -d '{"text":"今天也在摸鱼"}' http://127.0.0.1:8091/api/v1/sticker/render
# 上传（desc 留空自动走 vision 描述）
curl -X POST -H "X-Access-Token: <token>" -H "Content-Type: application/json" \
  -d "{\"data_base64\":\"$(base64 -w0 图.png)\"}" http://127.0.0.1:8091/api/v1/sticker/upload
```

## 6. Redis 键速查（前缀 `mychat:`）

| 键 | 类型 | 含义 |
| --- | --- | --- |
| `sticker:lib` | Hash | 文件名 → 描述（库注册表，出站匹配源） |
| `sticker:recent_usage` | List | 最近使用文件名队列（最新在前，picker 降权读） |
| `sticker:last_used` | Hash | 文件名 → 最近使用 iso 时间（REST list 展示） |
| `sticker:desc:{md5前16}` | String | 内容 → token 描述缓存（vision 免重复调用） |

## 7. 附：time_aware 为何没写 timelabel

实测本地实例 `mychat:timelabel:*` 为空——**不是调度器问题**（TickScheduler 在跑，
proactive_reply 22:21 真发即证），根因是 time_aware 插件 `default_enabled: false` 且
Redis 无启用键（`get_global_enabled` 缺省回退 manifest 默认值）。启用：面板插件页开关，或
`SET mychat:plugin:time_aware:enabled 1`；启用后 ≤60s 应出现 `mychat:timelabel:<qq号>`。
注意它同时挂 `on_before_llm`（往 system prompt 注入当前时辰），会影响 LLM 行为，是否开由用户拍板。

## 8. 测试

- `tests/test_tick_object_ids.py`（5）：并集口径/非数字跳过/空库/双源降级。
- `tests/m6/test_sticker_plus.py`（27）：picker 全算法路径、插件排除链与概率门、render 落盘注册幂等、manifest 校验。
- `tests/m7/test_rest_sticker.py`（21）：鉴权/CRUD/渲染/路径穿越/全部加固回归。
- 全量：`cd V3.0/server && mychat/python.exe -m pytest` → **599 passed**。

依赖变更：`requirements.txt` `pillow>=10.1`（本机 mychat 环境已装 13.0.0；load_default 需
10.1+ 才是可缩放 FreeTypeFont）。容器/Linux 部署时默认字体路径无效，需挂载字体并在
render_font 配置路径。
