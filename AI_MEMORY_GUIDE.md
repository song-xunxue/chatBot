# ChatBot 项目 AI 记忆指南

> **用途**：给任意 AI 助手（Claude Code / Codex / Cursor / 其他）首次接触本项目时快速建立完整认知。
> **写于** 2026-10-25。文中"线上状态"是时点快照（最近一次巡检 2026-10-01），动手前先核实。
> **权威优先级**：代码 > 各版本 `docs/` > 本指南 > 任何二手摘要。指南与代码冲突时，以代码为准并反馈更新本指南。
> **敏感约定**：本指南只含路径与指向，**不含任何密钥明文**（token 一律看服务器 `.env` / `docker logs`）。

---

## 0. 30 秒速览

- **项目**：单人开发的拟人化 AI 伴侣「清浔」——真实 QQ 号聊天机器人 + 评分驱动自我迭代 + 人设微调训练数据飞轮。
- **作者**：李文煜（git author 名 `song-xunxue`）。项目类型（非作业），2026-06-15 启动。
- **当前主线**：**V3.0 本地双栈**（清浔 V3.0-local 8091 + 大肥鱼 Vdafeiyu 8081，2026-10-26 起；`V3.0/` 目录冻结、云端容器组仍在），正处于「训练阶段 C 的数据积累期」：手动聊天沉淀金样本 → 攒 100+ 条 → QLoRA 训 v0 → 部署回本地 Ollama。
- **三代并存**：`V1.0/`（归档只读，FastAPI+PySide6 桌面版）→ `V2.0/`（QQ 官方机器人，容器已停但代码保留并行演进）→ `V3.0/`（现役）。
- **最新 commit**：`8b595bc`（2026-10-01，语音 1s 截断修复），分支 `v2.0`（**注意：V3.0 的所有开发都提交在名为 v2.0 的分支上**），双远程 Gitee(origin)+GitHub(github) 同步。
- **测试基线**：V3.0 后端 505 个测试函数（提交口径 508 项全绿，含参数化）+ 前端 16 测；V2.0 后端 489 + 前端 14。
- **一句话架构**：QQ ⇄ NapCat(OneBot 反向WS) ⇄ FastAPI 管线(人设+四级记忆+心情+评分+插件) ⇄ LLM(云端 GLM / 本地 qwen3:8b) ⇄ TTS(本地 GPT-SoVITS 经 frp) ，全量状态存 Redis。

---

## 1. 项目是什么

「清浔」是一个以**拟人化**为最高目标的 AI 伴侣系统，服务单一用户（QQ 主号 2690468347「浔的昳」）。演进的大方向始终是三步：

1. **聊得像人**（V1/V2 奠定）：人设卡、四级记忆、心情起伏、分段连发、思考延迟、语音、表情包；
2. **自我迭代**（V2/V3 核心）：每条 AI 回复被 LLM 对照人设打分（0-100）+ 人工改分/纠正/手动回复，高分正样本、低分负样本 → **反推**回人设与记忆（人在环确认）；
3. **人设进参数**（V3.0 当前）：评分系统天然是数据生产线，沉淀 SFT/DPO 数据 → 本地 4060 QLoRA 微调 Qwen3 → 盲测基准量化「人设契合度」增益 → 部署回 Ollama 替换云端 LLM。

参考实现为 **AstrBot**（https://github.com/AstrBotDevs/AstrBot，clone 在 `V2.0/Ref/AstrBot` 不入库）。借鉴其平台适配/插件/记忆思想，但代码全部自研。

---

## 2. 三代版本沿革

| 版本 | 时间 | 形态 | 里程碑 | 现状 |
|---|---|---|---|---|
| **V1.0** | 2026-06-15~24 | FastAPI 服务端 + PySide6 桌面客户端（含桌宠）+ Vue 面板 + Redis | M0~M8 全完成 | **归档只读**，核心模块被后两代 copy 复用 |
| **V1.1** | 2026-06-24 | 同上（dev/v1.1 分支）：人设扩字段、代人聊天 A(训练样本)+B(实时接管)、反推两步契约 | M9~M14 全完成 | 随 V1.0 归档 |
| **V2.0** | 2026-06-25 起 | **砍桌面客户端** → QQ 官方机器人私聊（AppID+AppSecret，Ed25519 Webhook 验签，nginx 443 反代，端口 8000） | M1~M9 + 大量增强（评分/记忆/心情/TTS GPT-SoVITS/移动端代答） | **容器 2026-09-15 全停（正式下线）**，代码保留；与 V3.0 九成文件相同，优化可双向同步（同步与否待拍板） |
| **V3.0** | 2026-08-12 起 | **纯 QQ 号**：NapCat Docker（NTQQ 逆向）登录真实小号 1145077465，OneBot v11 反向 WS 连服务端 | M-V3-0 风控验证 → M-V3-1/2 适配 → M-V3-3 上线；后续 10+ 增强批次 | **现役**（8091 + 独立 redis `mychat-redis-v3`），数据与 V2.0 完全隔离 |

**两次关键转向的理由**（防翻案）：

- **V1→V2 砍桌面客户端**：改 QQ 官方机器人后消息走 IM、无需启动客户端、7×24 持久运行；重心转向拟人化 + agent + 评分反推。
- **V2→V3 转纯 QQ 号**：① 官方机器人消息带「机器人」标记，拟人感打折；② 主动消息受月配额限制；③ 富消息能力弱（无戳一戳/撤回/转发/长文本）。代价是**封号风险**（逆向协议违反用户协议），对策=专用小号当消耗品 + NapCat Docker（社区最活跃）+ 控频/分段/思考延迟兼作防风控。
- **V3.0 数据隔离**：用户要求与 V2.0 完全分开存储（独立 redis 容器/网络），起步时 `scripts/migrate_seed_from_v2.sh` 只迁人设/心情档位/插件开关，**不迁**记忆/历史/评分（干净起步）。

**风控史（V3.0 立项依据，重要经验）**：旧测试号 3682822273 三次被腾讯处置（冻结 1 天→踢下线要求官方客户端→静默拒发 retcode=1200，均在早 8 点左右，疑批量风控扫描）。**双号对照实验判决**（08-16）：旧号持续拒发 / 新号全天全绿 → **账号标记假设成立**（NapCat 环境特征非主因）。现接管号 1145077465（高等级号）登录态 09-16 早扫码 → 10-01 已 **15 天零掉线**（最长纪录）。

---

## 3. 当前状态快照（2026-10-27 更新，动手前先核实）

- **⚠️ 双栈同步铁律（2026-10-27 用户立规，所有 AI 遵守）**：清浔（V3.0-local）与大肥鱼（Vdafeiyu）**共架构处（server 核心、共有插件、launcher/看护脚本、共用公共件 `scripts/launcher-common.ps1`）的任何改动必须双向同步落地，只改一栈视为未完成**；单栈专属功能（V3.0-local 的 dream/worldbook、Vdafeiyu 的人设/dist）免同步；汇报须注明「两栈已同步」或「单栈专属」。
- **本地双栈为当前主战场**（2026-10-26 起）：清浔栈 V3.0-local（服务 8091 / redis 6390 / NapCat 6099，QQ 1145077465，conda mychat，计划任务 ChatBotLocalServer + ChatBotLocalWatchdog 每 2 分钟看护）+ 大肥鱼栈 `Vdafeiyu/`（服务 8081 / redis 6380 / NapCat HTTP 3000，QQ 3682822273，一键启动 `Vdafeiyu/scripts/start-dafeiyu.ps1`，NapCat 掉线看护=计划任务 NapCat-Watchdog 跑精确匹配版 keepalive；redis/server 看护=计划任务 DafeiyuStackWatchdog 每 2 分钟跑 `Vdafeiyu/scripts/watch-stack.ps1`，2026-10-26 晚建）。TTS 9880 两栈共用。两栈源码关系：Vdafeiyu = V3.0-local **去掉 dream/worldbook 两批次** + 独立人设（persona/default.py），其余逐字节一致；**Vdafeiyu 无 dashboard/src，dist 绝不能从 V3.0-local 拷贝**（含日记/世界书页，后端无路由必坏）。桌面「ChatBot启动器」文件夹七件套+双栈关闭器（2026-10-26~27，制作脚本 `scripts/make_launchers.ps1` 幂等）。
- **双栈整体审查与修复（2026-10-26 傍晚，9-agent workflow 对抗复核）**：①high 已修——旧 napcat-keepalive.ps1 按进程名无差别强杀双栈 QQ + 重启 vbs 断链（当日 15:37-16:22 肇事 11 次，双号重扫+清浔触发账号风控 168），已改为精确匹配（`-q 3682822273` + napcat-dafeiyu 目录）+ 拉起走 start-dafeiyu.ps1，napcat-autostart.ps1/start-napcat-silent.vbs 危险残留已删；②high 已修——.gitignore 补 `Vdafeiyu/` `.local/`（此前 `git add -A` 会卷 443 文件含双号登录态/聊天数据）；③V3.0/ 工作区 13 改+16 新证实为 V3.0-local 严格子集，已提交 v3.0 分支定格冻结基线；④medium 12 项 2026-10-26 晚已全部修复（V3.0-local 690 测全绿）；low 4 项 2026-10-27 修复（日志轮转+UTF-8/dream tmp 残骸/docs09 删除语义），双栈同步生效。清浔 168 风控 2026-10-27 用户已手机验证解除；大肥鱼扫码 2026-10-26 晚完成。
- **proactive_reply 晚安事故修复（2026-10-27，详情见 Claude 记忆 proactive-fabrication-incident）**：用户报「晚安消息回复不适合」——真凶非 reply_enhance（双栈默认关），是 proactive_reply 按对象配置放宽（quiet_hours 改 02:00-09:30 放出深夜段）+开场白编造共同记忆（「说好早点睡的」）+对道别零感知（晚安后 7h40m 静默，静默段一结束 09:40 即补发）。修复：①晚安感知门控（`is_farewell` 词表+`farewell_aware` 参数默认 true，对方末条为道别语→静默直到再开口）；②开场白指令加禁编造约束；三件套双栈镜像同步，V3.0-local 696 测/Vdafeiyu 603 测全绿，双栈 13:18/13:20 无窗重启生效。潜伏未修：晚安块已被 proxy 新块挤出 2-block×20 条窗口、reply_enhance 休眠地雷（accumulate 若启用有无 TTL/空轮双写/跨夜时差三类坑）。
- **遗留待办（2026-10-27 用户报障）**：①「记忆/人设/场景设置丢失」**已解决**——真身分别是 V3 云文件人设卡与 V2 云 redis 记忆，全包迁移进 6390 已验证（详见 Claude 记忆 cloud-data-migration-2026-10-27；金样本 103 条同时入 training）；②continuous_send 分段失效**已解决**——根因是清浔栈从未置 `mychat:plugin:continuous_send:enabled`（default_enabled=false 总闸常闭），已开闸；策略升级备选（DSH 按空行拆+固定间隔 / AstrBot 标点正则拆+按字数对数间隔模拟打字）待用户点头再改。
- **工作目录已切 V3.0-local**（2026-10-26 起）：`V3.0-local/` 为从 V3.0 完整移植的本地演进分支（基线 599 测全绿，含 dream/worldbook 后 **685 测全绿**），**`V3.0/` 目录冻结不再改动**（冻结基线已入库 v3.0 分支）；云端部署仍为 V3.0 容器组（见下）。V3.0-local 与 Vdafeiyu 均在 .gitignore 内、未入库。
- **世界书式记忆批次（2026-10-26，未提交，685 测全绿 = 625+60；`V3.0-local/docs/09` §8 实施记录）**：`memory/worldbook|worldbook_store|worldbook_runtime.py` + REST `/api/v1/worldbook/entries CRUD|stats|rebuild` + 面板世界书页（桌面侧栏+移动第 9 tab）+ 迁移脚本 `scripts/migrate_worldbook.py`（--dry-run）。**`MEMORY_MODE=legacy` 默认未切**（legacy 拼装有逐字回归测试锁定，验收后再切 worldbook）；记忆写入/遗忘全路径自动同步条目（_upsert_fact_dedup/mark_forgotten 收口，diary 按 tags 分流 dream/diary）；注入锚点在 stage_build_messages 拼装（5 position），兜底 topup 复用 coordinator.retrieve 且 hit_mids 回填维持评分回流；Redis 键 `mychat:wb:*`（条目 hash/ids zset/by_key/by_ref 反向索引/stats）；坑：redis hset 不收 bool/list——to_redis 转 int/JSON，from_dict 双向容错。
- **dream 做梦与日记批次（2026-10-26，未提交，625 测全绿 = 599+26）**：第 3 个插件 `plugins/dream/`（on_tick pri 130，凌晨 dream_hour 对"昨天"生成一段梦+第一人称日记，**默认关**、绝不发 QQ 消息）；落盘 `server/data/diary/YYYY-MM-DD.json` + Redis 索引 `mychat:diary:index`(zset)/缓存 `mychat:diary:{date}`；精炼版走 `MemoryCoordinator.upsert_facts_batch` 写事件记忆（**source=diary**，emotion 必须传 0.0 不能空串）；按 dream_tone 给 mood ±dream_mood_delta 偏移（clamp 不为负）；REST `/api/v1/diary/list|{date}|run`；面板桌面"日记"侧栏 + 移动第 8 tab（Diary.vue/DiaryMobile.vue，tokens.css 工具类首个消费者）；文档 `V3.0-local/docs/10-做梦与日记.md`。测试坑：dream 模块测试须单路径导入 `plugins.dream.*`（双 sys.path 会造双模块实例，monkeypatch DIARY_DIR 打偏 + 误写真实 data 目录）；`_persona_brief` 走 `get_default_persona` 会真写 persona 文件，测试须预种 persona 绑定。

- **现役容器**（云服务器 43.140.219.99，仅此三个）：`mychat-server-v3`（宿主 8091→容器 8000）、`mychat-redis-v3`、`napcat-v4`（host 网络，WebUI 6080）。V2 全套 / napcat-v3 / V1 遗留 redis 均已 stop（数据在卷，可复活）。
- **全链路在线**：QQ 登录态 ✓ / WS 绑定 ✓ / 掉线监控 online ✓；最近消息 10-01 00:00 落库。
- **AI 静默开关：开**（`mychat:takeover:enabled:{oid}`=1 → AI 不自动回复，用户用接管号手动聊，手动回复=恒正金样本 score=100）。与「AI 自动对话攒数据」工作流互斥，切换由用户拍板。
- **数据基线**：34+ blocks；金样本 SFT ~46 条（连发合并口径）；表情包库 55 文件、49 张已注册 vision 描述。
- **盲测基线**：本地 qwen3:8b（Ollama 经 frp）= 82 分 vs 云端 GLM = 90 分——量化出微调要填的差距。
- **挂起事项**：① `deploy_ollama.py` 待做（merge→GGUF→ollama create→切 LOCAL_LLM_MODEL）② 用户消息批注注入 live 上下文（有 prompt 泄漏风险，待拍板）③ RL 闭环 8 缺口（见 §5.3）④ QQ 登录态存活持续观察。
- **本地运行（2026-10-25 起）**：`V3.0/server/scripts/local_dev.py` 本机 Windows 一条命令跑全套（REDIS_URL 探测失败自动回退 fakeredis + 幂等种子 + `0.0.0.0:8091` 面板局域网手机可访问），用法见 `V3.0/docs/06-本地运行指引.md`；本地边界：无 NapCat/LLM/TTS 闭环；后端 511 测全绿（mychat 环境）。
- **sticker_plus 批次（2026-10-25 晚，未提交 git，599 测全绿）**：① on_tick 活跃源 bug 修复——`main.py tick_object_ids` = 最近会话 ∪ mood oids 并集，`isascii+isdigit` 过滤非数字 oid（真实私聊不再依赖手动 sadd，demo 类不再触发 onebot `int()` 报错）；② sticker_plus 表情包增强插件（on_message_out pri 350 自动配图：心情过滤+bigram 重叠+recent 降权可解释挑选，attach_prob=0.35，**默认关**，面板插件页开启）；③ `/api/v1/sticker/*` 库管理+render REST（底图白名单 `server/data/stickers/templates/`，上传魔数/描述/同名校验，路径穿越已拦）；④ mychat 环境新装 Pillow 13.0.0（requirements 抬至 >=10.1）；⑤ time_aware 仍默认关——本地 `mychat:timelabel:*` 为空的根因是插件未启用（非调度器），启用方式见 docs/07 附注。详见 `V3.0/docs/08-表情包增强与REST.md`。

---

## 4. V3.0 架构（当前主线）

### 4.1 部署拓扑

```
[用户 QQ 主号] ⇄ [QQ 服务器]
                    ⇅ (NTQQ 逆向)
[云服务器 43.140.219.99]
  ├─ napcat-v4 容器 (mlikiowa/napcat-docker, host 网络, WebUI :6080)
  │     登录真实小号 1145077465，OneBot v11 反向WS 主动连 ↓
  ├─ mychat-server-v3 容器 (宿主 8091, API+WS+面板同端口)
  │     ⇅ redis 协议 (chatbot_v3_net 内网)
  ├─ mychat-redis-v3 容器 (独立数据, 前缀 mychat:)
  └─ frps (宿主 :7000)
        ↑ tcp 隧道 ×2（由用户本地 Windows frpc 建立）
        ├─ 9880  → 本地 GPT-SoVITS (E:\GPT-SoVITS, 4060, 语音合成)
        └─ 11434 → 本地 Ollama (D:\ollama, qwen3:8b, local LLM provider)
```

- V3.0 部署目录：服务器 `~/ChatBot-V3/`；重部署：本地 tar → scp → `sudo bash scripts/deploy_v3.sh`。
- 面板：`http://43.140.219.99:8091`（暗色仿 NapCat 风格，PC 七页 + 移动端 `/m/*` 七页），登录 token = 服务器 `V3.0/.env` 的 `ACCESS_TOKEN`。
- REST 鉴权：header **`X-Access-Token`**（不是 `Authorization: Bearer`！），实现在 `server/app/api/_auth.py`。
- 掉线监控真实路径：`GET /api/v1/system/napcat-status`（裸 `/system/...` 会落 SPA catch-all 返 HTML）。

### 4.2 server/app 模块地图

```
V3.0/server/app/
├── main.py            # 入口：create_app + lifespan(适配器→Redis 预热→人设/mood 种子→插件→
│                      #   star 兼容→工具/MCP→NapCat 掉线监控→mood 衰减/记忆遗忘后台循环)
├── core/config.py     # Settings(pydantic-settings 读项目根 .env)，全部配置唯一来源
├── onebot/            # ★ V3.0 新增：入站协议层
│   ├── ws_client.py   #   /ws 反向WS：self_id 过滤接管号；AI 静默判定；连发防抖合并；
│   │                  #   message_sent 手动回复感知(message_id 去重区分自发/手动)；
│   │                  #   图片/表情包 vision 提取
│   └── watch.py       #   两级掉线探测：WS 连接态 + WebUI QQ 登录态(最隐蔽事故=WS 活着但 QQ 离线)
├── adapter/           # ★ 出站适配层(平台无关内核的边界)
│   ├── onebot.py      #   send_text(array 格式防 CQ 注入；[表情包: x] token→image 段独立成条+拟人间隔)
│   │                  #   send_voice(音频 bytes 直传, NapCat 自转 silk——修 1s 截断)
│   ├── protocol.py    #   PlatformAdapter 协议(V2.0 曾双栈 official|onebot, V3.0 已精简为纯 onebot)
│   └── reply_guard.py #   出站守卫 sanitize_reply(错误堆栈/429→拟人化兜底; human_authored=True 跳过)
├── pipeline/          # ★ 消息流水线(平台无关, 零 import 平台代码)
│   ├── runner.py      #   run_stream 九阶段编排(见 §4.3)
│   ├── stages.py      #   各 stage + run_post_reply_chain(pipeline 与 takeover 共用的回合后副作用链)
│   └── tool_loop.py   #   function calling 工具循环
├── llm/               # Provider 抽象: registry(glm/deepseek/siliconflow/local 四家)
│   ├── local.py       #   ★ 本地 provider: Ollama 经 frp, 同步 httpx+to_thread(防 frp 断连), 剥 <think>
│   └── resolver.py    #   按任务解析 provider: override→任务专用→chat_provider
├── memory/            # 四级记忆(见 §5.4): coordinator/store/encoder/retriever/forgetting/consolidation
├── persona/           # 人设: store(Redis+JSON 双写 data/persona/) + renderer(含 OUTPUT_CONTRACT)
├── mood/              # 心情: service(5 档种表/评分补偿) + decay(衰减循环)
├── score/             # 评分: quad(四元组唯一公式) + service(LLM 评分/正负样本) + reverse_infer(反推)
├── storage/           # redis_client / chat_store(block 三层) / takeover_store / sticker_store
├── takeover/          # 对话控制: record_manual_reply(手动回复落库+金样本+静默窗) + send_proactive
├── training/          # ★ 训练前置: benchmark.py(盲测基准) + export.py(SFT/DPO 数据导出)
├── api/               # REST 路由: _auth + rest_{chat,memory,mood,persona,plugin,system,takeover,
│                      #   roleplay,multimodal,tts,training,score}
├── plugins/           # 插件(EventBus 6 钩子): tts_reply / continuous_send(分段连发+思考延迟) /
│                      #   time_aware / reply_enhance / star_compat(AstrBot .star 兼容层)
├── modality/          # tts.py(CosyVoice2 云端 + GPT-SoVITS 本地双 provider) + glm.py(vision) + silk.py(弃用存档)
└── tools/ + mcp_client.py   # 自研工具(web_search 等) + MCP 外部 server
```

代码风格：**同级导入**（`from core.config import settings`，无包名前缀），`pytest.ini: pythonpath=app`。

### 4.3 消息主链路（九阶段管线）

```
入站: QQ → NapCat → 反向WS /ws (query access_token 鉴权 fail-closed)
  → ws_client: self_id 过滤 → AI 静默判定(静默中→直录历史不进 LLM)
  → 连发防抖(2s 窗口合并, 图片先过 GLM vision 转描述)
  → pipeline.run_stream:
      ① load_history(最近 20 条)
      ② persona_inject(render_system_prompt, 人设可绑定 provider/model)
      ③ memory_retrieve(core 常驻 + BM25/向量 RRF 融合 top-5 加权随机采样)
      ④ mood_inject(心情 prompt_hint 影响语气)
      ⑤ [钩子 on_before_llm: 思考延迟 3-5s]
      ⑥ tool_loop(有注册工具时) 或 llm_stream(SSE 流式)
      ⑦ mood_update(关键词词表 ±step)
      ⑧ [钩子 on_message_out: tts_reply 语音 / continuous_send 分段连发]
      ⑨ run_post_reply_chain: save(硬契约)→score(软)→memory_write(软,后台)
出站: ctx.reply_text → adapter.send_text(守卫+句号 strip+表情包 token 翻译)
      / send_voice(音频直传) → call_action 经 WS → NapCat → QQ
```

**软失败哲学**：除「落库」是硬契约外，评分/记忆/心情/TTS/插件全部 try 吞异常降级——主回复链路永不因附属系统挂掉而中断。

### 4.4 训练管线三件套（阶段 A+B+C 已通）

| 件 | 位置 | 作用 |
|---|---|---|
| 盲测基准 | `server/app/training/benchmark.py` + `POST /api/v1/training/{oid}/benchmark` | 取真实上下文，A/B 两 provider 各生成，固定裁判（同人设口径）打分，量化人设契合度；微调前后同法对比 |
| 数据导出 | `export.py` + `POST /api/v1/training/{oid}/export` | 聊天历史 → LLaMA-Factory 格式 JSONL（`server/data/training/`）。SFT chosen=①score≥85 ②manual 手动回复 ③corrected 纠正 ④roleplay 剧本；DPO 偏好对=correction 天然 chosen/rejected；**连发 burst 用 \n 合并成一条、纯占位([图片]等)不入训练目标** |
| SFT 训练 | `V3.0/training/train_sft.py` + `run_train.bat`（本地 4060，conda **llmtrain** + unsloth） | QLoRA（4B 稳/8B 贴极限）。冒烟已通过（Qwen3-4B, loss 7.13→6.89, adapter 253MB）。重训 SOP：面板导出 JSONL → scp 回本地 → `run_train.bat vN <jsonl>` |

数据闭环：手动回复/纠正自动+1 金样本 → 攒 100+ 条 → 训 v0 → 盲测 local vs glm → `deploy_ollama.py`（**待做**：merge→GGUF→`ollama create qingxun-vN`→服务器 .env 切 `LOCAL_LLM_MODEL`）。

---

## 5. 核心机制（必须理解的 8 件事）

### 5.1 评分四元组与正负样本
每条 AI 回复：`score_base`（LLM 对照人设打 0-100）+ `mood_at_score` + `mood_bias`（心情档位补偿+噪声）→ `score = clamp(round(base+bias), 0, 100)`，唯一公式收口在 `score/quad.py`。**≥85 入正样本、<60 入负样本**（`mychat:score:pos|neg:{oid}`），neutral 不采样。人工干预三类黄金信号（权重高于自动评分）：**手动改分 / 纠正回复（corrected，恒正样本）/ 管理员手动 QQ 回复（manual，恒正 score=100）**。

### 5.2 反推（reverse_infer）
正负样本 → LLM 提炼人设字段修改建议 → **dry_run 返 diff + confirm_token → 人工面板确认 apply**（两步契约，预览不可绕过；14 字段白名单、drift 幅度校验、快照可回滚）。**绝不自动改人设**（防漂移）。样本来源三级权威：[管理员纠正/手动回复] > [真实对话] > [训练剧本]。

### 5.3 RL 闭环（诚实定位：bandit 式离线策略优化 + 人在环，非在线梯度学习）
策略（人设+记忆召回+心情）→ 行动（回复）→ 奖励（LLM-as-judge + 人工四类信号）→ 更新（θ1 反推改人设 / θ2 记忆 useful_score / θ3 mood）。已知 **8 缺口**（改进方向，2026-09-10 架构审查确认）：①neutral 不采样 ②反推须人工 apply 无自动触发 ③用户真实不满只进 mood 不回流 score ④mood_bias 噪声使阈值边界不可复现 ⑤credit assignment 粗粒度且每 6 轮才结算 ⑥主动发送不评分 ⑦roleplay 与 live 分数口径共用阈值 ⑧T2 升 core 未实现。

### 5.4 四级记忆 + 三要素 + 三档衰减
- **四层**：Core（常驻注入，不靠检索运气）/ Working（复用聊天历史）/ Episodic（摘要+反思）/ Long-term（事实，BM25+向量 RRF 检索+加权随机采样避确定性偏见）。
- **三要素**（借鉴 angel_memory）：`content` + `reason`（为什么值得记）+ `tags`（≤5）；面板可编辑。LLM prompt 只注 content（省 token）。
- **useful_score（0~1）用进废退**：本轮被召回的记忆随本轮评分集体 ±0.1（≥85 强化/<60 衰减，`_apply_score_to_recalled`）；手动档 tier≥0 与 locked 跳过。
- **三档衰减**（`forgetting.should_forget`）：T2（useful_score≥0.7）永不 / T1（≥0.3）评分驱动 / T0 自然衰减（retain_score=0.4·重要+0.3·近期+0.15·访问+0.15·情感，72h 半衰期，被召回重置=间隔重复）。后台 `forget_tick` 每 6h（软遗忘→上限 200 淘汰→物理清理→睡眠巩固）。
- **防幻觉铁律**：抽取 prompt 强制「只把 user 说的话当事实源」——根治「椰子鸡幻觉自我固化」（AI 编的承诺被抽成长期记忆→召回→再强化）。人称用第一人称视角（「我叫清浔」「煜君喜欢我」），绝不用「用户」疏离称呼（`persona.user_alias`="煜君"）。

### 5.5 心情系统
mood∈[0,1]（0.5 中性），默认 5 档（开心/愉悦/平静/低落/难过，各档含 kaomoji/score_bias/prompt_hint，Redis 可 CRUD）。关键词词表 ±step、独立 asyncio 循环向中性衰减。作用：①prompt_hint 影响语气 ②score_bias 补偿评分（心情好宽容/差苛刻才拟人）③面板曲线可视化。

### 5.6 OUTPUT_CONTRACT 输出契约
renderer 末尾恒追加的硬约束（位置最后=权重最高）：**禁括号动作描写**（根治「（轻声笑了）」舞台指示）、**句号铁律**（整条回复绝不用句号结尾，语气靠换行+~呀嗯；`reply_guard.strip_trailing_period` 出口确定性双保险）、诚实优先不编造、表情包 token 规则（单独一行、最多一个）。

### 5.7 AI 静默模式 + 手动回复感知（2026-09-13 重构，原 FIFO 待答队列已删）
- **静默开关**（原代答开关复用）：开=AI 全静默，用户消息**直录历史**不进 pipeline。
- **手动静默窗**：自动模式下手动 QQ 回复后 10 分钟 AI 闭嘴（Redis TTL 键）。
- **手动回复感知**：NapCat 开 reportSelfMessage → `message_sent` 事件 → message_id 去重区分服务器自发/管理员手动 → `record_manual_reply`（落 proxy 消息 source='manual' + 恒正金样本 + 记忆/心情全链）。⚠️ NapCat 坑：message_sent 的 `user_id`=发送者自己，**接收方在 `target_id`**。

### 5.8 表情包与语音
- **表情包收发**：入站 image/mface 下载存 `server/data/stickers/`（md5 去重）+ vision 描述成语义 token `[表情包: 描述]` 入消息 content（训练上下文语义完整）；出站 token → 表情库双向子串匹配 → image 段 base64 真图，**独立成条**（文本一条+每表情各一条，条间随机 0.4-0.9s）。GLM vision 不收 gif → Pillow 归一化 PNG（gif 取首帧）。
- **语音链路**：`tts_reply` 插件 → GPT-SoVITS（本地 4060 经 frp 9880；面板可调 sample_steps/top_k/句间停顿）→ **音频 bytes 直传 NapCat 自转 silk**（2026-10-01 修复：自编 silk NapCat 时长解析 0s，QQ 只显 1s——V3.0 语音出站此前从来没完整过）。

---

## 6. 数据模型（Redis key 速查，统一前缀 `mychat:`）

| Key | 类型 | 用途 |
|---|---|---|
| `chat:{oid}:blocks` | ZSet | 会话→block 索引（静默 10min 自动切新 block） |
| `block:{bid}` | Hash | block 元数据（start/end_ts/status/source） |
| `block:{bid}:msgs` + `msg:{mid}` | ZSet+Hash | 消息（mid 全局 UUID；sender=user/ai/proxy/system；score 四元组；score_note 批注；corrected 纠正文本；source） |
| `block_roleplay:*` / `msg_roleplay:*` | — | **roleplay 训练剧本物理隔离**，绝不进 LLM 上下文 |
| `mem:{oid}:{core|episodic|reflect|long}` / `mem:{oid}:vec:{mid}` | Hash/ZSet | 四级记忆 + 向量 |
| `score:pos|neg:{oid}` | List | 正负样本（LTRIM 留 20 只服务反推；**训练导出直读聊天历史，不怕截断**） |
| `mood:{oid}` / `mood:kinds` / `mood:params` | — | 心情值/档位表/参数 |
| `persona:{pid}` / `persona_version:{pid}` | — | 人设卡+版本快照（JSON 双写 `data/persona/`） |
| `takeover:enabled:{oid}` / `takeover:silence:{oid}` | TTL 键 | AI 静默开关 / 手动静默窗 |
| `sticker:lib` / `sticker:desc:{md5}` | Hash | 表情包库 file→desc / vision 描述缓存 |
| `system:napcat_status` | — | 掉线监控状态（面板红横幅数据源） |
| `tts:gptsovits:heartbeat` | TTL 90s | 本地 TTS 启动器心跳 |
| `plugin:{name}:enabled` / `plugin_cfg:{oid}:{name}` | — | 插件开关/参数 |

---

## 7. 部署与运维

### 7.1 服务器凭证（核心，曾因没记牢反复踩坑）
- **服务器** `43.140.219.99`，用户 **`ubuntu`**（非 root），**sudo 免密**；docker 命令须 `sudo docker ...`。
- **SSH 私钥**：`D:\code\Git_Local\ChatBot\.claude\ubuntu.pem`（项目目录内，非 `~/.ssh/`，已 gitignore）。
  `ssh -i D:/code/Git_Local/ChatBot/.claude/ubuntu.pem ubuntu@43.140.219.99`
- V3.0 部署目录 `~/ChatBot-V3/`；NapCat 容器 `napcat-v4`。
- Claude Code 注意：SSH/scp 部署命令首次会被权限分类器拦，需用户明确授权（「自动吧」）后同会话不再拦。

### 7.2 部署一条龙（V3.0）
```
本地: tar czf /tmp/v3.tgz --exclude='./tts-tools' --exclude='./server/data' \
        --exclude='./node_modules' --exclude='./.env' --exclude='./training/outputs' -C V3.0 .
      ⚠️ -C V3.0 后成员路径带 ./ 前缀，exclude 必须写 './xxx' 才匹配得上
      ⚠️ dashboard/dist 绝不能排除（Dockerfile COPY dist 进镜像；曾两次误排致前端改动没上面板）
scp -i .claude/ubuntu.pem /tmp/v3.tgz ubuntu@43.140.219.99:~/
ssh ... 'cd ~/ChatBot-V3 && tar xzf v3.tgz --strip-components=1 && sudo bash scripts/deploy_v3.sh'
```

### 7.3 NapCat 掉线处置 SOP
1. 面板掉线横幅/`GET /api/v1/system/napcat-status` 发现异常（两级探测：WS 连接态 + WebUI QQ 登录态）。
2. **常规**：开 WebUI `http://43.140.219.99:6080/webui`（token 见服务器 docker logs 或 onebot11 配置）扫码重登；扫码后 WS 自动重连绑定。
3. **卡死态**（WebUI 二维码刷新失败/isOffline 卡住）：`sudo docker restart napcat-v4` → ~20s 出新码。
4. 掉线期间的消息：QQNT 重登后会同步好友历史，用 `scripts/backfill_qq_history.py`（NapCat 热开 HTTP `get_friend_msg_history`）回填——**回填前必须摘 `active_block` 指针，灌完恢复**（open_or_get_block 对旧 ts 恒并当前块）。
5. `reportSelfMessage` 等配置改文件不热生效 → WebUI API `OB11Config/SetConfig` 热应用（但 httpServers 热开随容器重启丢失）。

### 7.4 本地 Windows 工具链（语音/本地 LLM/训练）
| 组件 | 位置 | 说明 |
|---|---|---|
| GPT-SoVITS | `E:\GPT-SoVITS`（api_v2 :9880，dania 清浔模型） | 桌面「清浔 3.0.lnk」启动器一键拉起 api_v2+frpc+心跳；**与 V2.0 启动器共享隧道，不能同时跑** |
| frpc | `V3.0/tts-tools/frp/` | 两条隧道：9880 GSV / 11434 Ollama；frps 在云服务器 :7000 |
| Ollama | `D:\ollama`（zip 版，qwen3:8b 5.2GB） | **重启后须手动启动 serve**；OLLAMA_MODELS=D:\ollama\models |
| 训练 | conda `llmtrain` + `V3.0/training/` | HF 缓存 D:\llmtrain-cache；HF_ENDPOINT=hf-mirror.com；产物 outputs/ 永久存档不入库 |

---

## 8. 开发环境

### 8.1 conda 环境（不混用；conda 不在 bash PATH，用完整路径）
| 环境 | 用途 |
|---|---|
| `mychat` | **跑测试**（V1/V2/V3 后端 pytest 都用它）：`C:/Users/26904/anaconda3/envs/mychat/python.exe` |
| `qingxun` | V2.0 运行时/启动器打包（py3.11，同 Dockerfile） |
| `llmtrain` | QLoRA 训练（unsloth+trl+peft，torch 2.12.1+cu126） |
| `mypytorch` | demucs 人声分离等杂项 |

### 8.2 常用命令
```bash
# V3.0 后端测试（505 个测试函数，提交口径 508 项）：cd V3.0/server && <mychat>/python.exe -m pytest tests
# V3.0 前端（16 测+构建）：cd V3.0/dashboard && npx vitest run && npm run build
# V2.0 同构：cd V2.0/server ...（489 测）/ cd V2.0/dashboard ...
# 本地面板开发（V2.0 专属）：cd V2.0/server && <mychat>/python.exe scripts/panel_dev.py
#   → fakeredis+种子数据+静态托管 :8000，token=dev-token（V3.0 无此脚本，冒烟降级为 dist 静态检查）
# 测试特点：conftest 注入 fakeredis+httpx MockTransport+清空全部 LLM key，全程不真调 LLM；
#           真链路验证走 scripts/real_*_check.py
```

### 8.3 git
- 双远程：`origin`→gitee.com/song-xunxue/chatBot，`github`→github.com/song-xunxue/chatBot；**先 Gitee 后 GitHub**。
- 分支：`v2.0`（**当前开发主线，V3.0 工作也在此分支**）/ `master`（稳定线）/ `dev/v1.1`（归档）。
- 145 commits（2026-06-15 起），提交信息格式「V3.0 xxx(N测全绿)」。GitHub 推送走代理 7890，梯子未开时积压不阻塞（部署用本地 tar 不依赖远程）。
- **绝不推送**：`.env`、`*.pem`、`*.db`、`tts-tools/`、`Ref/`、`server/data/`、`training/outputs/`（.gitignore 已覆盖，曾需 `git add -f` 救回被自身 ignore 的 .gitignore）。

---

## 9. 工程规范与协作约定（对 AI 助手的行为要求）

- **代码头部**：项目类型风格（功能说明 + 作者 `李文煜` + 日期 yyyy-mm-dd + 变更日志）；注释/文档全中文。
- **事前确认**：每个里程碑/模块动手编码前，先出方案（做什么/改哪些文件/取舍）给用户确认再动代码；调研读码不算。
- **事后汇报**：每完成一部分，说明「做了什么 + 实现什么功能」；长任务每 ~10 分钟汇报进度。
- **推送完即存档**：每次 git 推送后主动更新项目记忆（进度/commit 号）。
- **系统性修改**：多文件改动用 Grep 全量排查引用；改代码同步更新所有相关文档。
- **双语回复**：用户英语输入时 prose 英+中双语（表格/代码不译）；中文输入则纯中文（默认工作语言中文）。
- **画图**优先 LaTeX（latex-figure skill/TikZ 矢量 PDF），非 matplotlib 位图。
- **Windows 兼容**：print 避免 Unicode 特殊字符（终端 GBK）；路径/脚本跨平台。

---

## 10. 踩坑清单（高价值资产，防重蹈覆辙）

**网络/协议类**
1. **frp tcp 隧道 × httpx.AsyncClient = RemoteProtocolError 断连**——必须用同步 `httpx.Client` + `asyncio.to_thread`（GPTSoVitsProvider 与 llm/local.py 均如此）。
2. QQ 官方机器人被动回复：同 msg_id 多段必须 **msg_seq 递增**（V2.0 遗产，V3.0 不适用但保留认知）。
3. NapCat 反向 WS 连**根 path /** 非 /ws；websockets 17 须去掉 subprotocol 否则协商 400；反向 WS 模式调 API 用 WS Action（未配 httpServers 时）。
4. NapCat `message_sent` 的 user_id=发送者自己，接收方看 `target_id`（曾致手动回复被陌生人门控误拦）。
5. 自编 silk（pysilk/tencent=True）NapCat 时长解析为 0 → QQ 只显 1s；**音频直传让 NapCat 内置 ffmpeg 自转**。
6. GLM vision 不支持 gif/webp 误存 .jpg（code 1210）→ Pillow 归一化 PNG。
7. ghcr.io 国内拉不动 → `ghcr.nju.edu.cn` 镜像代理 pull 后 tag 回原名。
8. torch pip 默认装 CPU 版；须 `--index-url download.pytorch.org/whl/cu126` **直连**（走 7890 代理反而 No matching distribution）。

**部署/打包类**
9. `tar -C V3.0 .` 后成员带 `./` 前缀，exclude 须写 `./tts-tools` 形式（写 `V3.0/xxx` 匹配不上）。
10. **dashboard/dist 绝不能排除**（Dockerfile COPY dist；曾误排致前端改动未上面板）。正确排除=tts-tools/server/data/node_modules/.env/training/outputs。
11. docker compose v5 不识别 `${VAR:+...}` shell 扩展会把 `}` 传给 redis-server 致崩溃。
12. 容器内 .env 不可写（compose env_file 注入 env vars，pydantic env 优先）→ 面板可改配置走 **Redis 持久化**（如 QQ 凭证）。
13. 服务器 `~/ChatBot-V3/server/data/stickers`（55 张表情包）勿被部署覆盖（排除 ./server/data 即不触碰）。
14. docker 命令须 sudo；`docker logs` 看 NapCat WebUI token。

**代码类**
15. Windows 时钟粒度 ~15ms：测试里 `sleep(0.002)` 无效致 ZSet 同分随机排序 flaky，用 ≥30ms 间隔。
16. `join(异步生成器)` 拿不到结果（PEP 530 陷阱）——join 里不能 await，须显式循环。
17. renderer 字符串里敲 ASCII 引号会断 Python 语法（"Perhaps you forgot a comma"）。
18. 构造 .url/.lnk 的反斜杠用 python `chr(92)`（bash 双引号/printf 会把 `\t` 吃成 TAB）。
19. **单测若用替身绕过真实分发路径，会掩盖结构性缺陷**（race 测试直写内部集合骗过自己——29-agent 对抗审查才抓到 WS 接收循环内联 await 的结构性失效）。
20. `git log --reverse --format=%ad -1` 的 `-1` 在 reverse 前生效，返回的是最新提交日期。

**运维类**
21. NapCat 重启后登录态可能失效需重扫码；卡死态（二维码不刷新）只能 restart 容器。
22. QQ 掉线是**静默丢数据**（WS 活着但 QQ 离线，消息全不到服务器）——曾 8 天未察觉；现已有两级监控+面板红横幅。
23. 回填历史前必须摘 `active_block` 指针（旧 ts 恒并当前块）。
24. `score_sample_keep=20` 只影响反推，训练导出直读聊天历史，不丢训练数据。

---

## 11. 重要设计决策存档（含理由，勿轻易翻案）

| 决策 | 理由 |
|---|---|
| 平台无关内核 | pipeline/记忆/评分/人设零 import 平台代码；OneBot 适配只发生在 onebot/ws_client.py（入站）与 adapter/onebot.py（出站）两个边界——这是 V3.0 能一夜完成 M-V3-1/2 的根本原因 |
| 反推绝不自动改人设 | 防漂移；人在环确认是设计原则 |
| 删消息前 neg 联动保留 | 有 score 的 ai/proxy 文本副本进负样本队列，训练价值不丢（QQ 不可撤回，面板真删但样本留） |
| 纠正回复不改原 content | 原 QQ 已发不重发；corrected 存独立字段恒正样本；「编辑内容」功能已删（有纠正即够） |
| 插件分类原则 | 与架构重合的融入（angel_memory→记忆参考、mood_dynamic→心情系统），其余纯插件（aiimg/apis）；避免钩子冲突与重复注入 |
| 混合人格架构 | 事实类人设（记忆/关系）留 prompt+RAG 即时生效；**风格类人格进参数**（微调）——两层互补，学术依据 RoleLLM/CharacterBot |
| RL 形态=semi-online 迭代 DPO | 在线 GRPO 需研究级算力（8×H100）；纯离线 DPO 差 45-57%；semi-online 效果≈在线且单次训练就是普通 DPO 算力 |
| V2.0 代码保留不删 | 与 V3.0 九成文件逐字节相同，优化双向同步的低成本基线（V2 侧同步与否待拍板，部分事项已随 V2 下线作废） |
| 单人设（单人项目） | 面板去新建/删除/导入人设；per-object 插件配置已删；全局共享 object_id |

---

## 12. 待办与下一步（截至 2026-10-25）

1. **攒数据训 v0**：金样本 ~46 条 → 100+ 条后 `run_train.bat v0`（数据靠日常手动聊/AI 自动聊积累）。
2. **deploy_ollama.py**（待做）：merge LoRA→GGUF→`ollama create qingxun-vN`→服务器 .env 切 `LOCAL_LLM_MODEL`→盲测验证。
3. 用户消息批注（score_note）注入 live LLM 上下文——有 prompt 泄漏风险，待用户拍板。
4. RL 闭环 8 缺口逐项收敛（§5.3）。
5. QQ 登录态存活持续观察（基线 15 天）；频次加剧则评估换 Lagrange 协议端。
6. V2.0↔V3.0 优化同步的存量事项已随 V2 下线基本作废，如需复活 V2 栈：容器数据都在卷，`docker start` 即可。

---

## 13. 文档地图（去哪深挖）

| 想了解 | 去读 |
|---|---|
| **V3.0 全量机制详解（最权威）** | `V3.0/docs/03-架构审查与机制详解.md`（含四张 TikZ 架构图 figures/、九阶段管线逐行、RL 闭环判定与 8 缺口、REST 速查） |
| V3.0 立项与适配器设计 | `V3.0/docs/01-V3.0计划.md`；风控验证 `docs/M-V3-0验证指引.md` |
| 训练路线调研（为什么微调/怎么微调） | `V3.0/docs/04-Neuro复刻调研与人设进参数可行性.md`（118 份来源）；`V3.0/training/README.md`（实操） |
| 面板暗色重设计 | `V3.0/docs/05-面板暗色重设计计划.md` |
| V2.0 设计（block 结构/心情/插件分类/评分） | `V2.0/docs/01~04`（01 计划 / 02 Block 结构 / 03 心情系统 / 04 插件分类） |
| V1.0/V1.1 完整设计文档体系 | `V1.0/docs/01~11`（需求/架构/接口/数据模型/插件/记忆/规范/计划/M3 规格/V1.1 规格/使用说明） |
| 参考实现 | 根目录 `Reference` 文件（AstrBot 链接）；`V2.0/Ref/AstrBot`（clone，不入库） |
| 变更历史 | 无 CHANGELOG——看 git log（提交信息极详）+ Claude 记忆文件 |

---

## 14. Claude Code 记忆系统（本项目特有）

本项目使用 Claude Code 持久记忆，**目录**：`C:\Users\26904\.claude\projects\D--code-Git-Local-ChatBot\memory\`（路径缓存于 `.claude/memory_path.txt` 第一行）。`MEMORY.md` 是索引，16 个记忆文件是本指南的上游素材（本指南即其全量浓缩+代码核实版）。其他 AI 工具无条件读该目录时，以本指南代替；Claude Code 会话则两者皆可命中。

**指南维护约定**：大变更（新里程碑/架构调整/部署形态变化）后应同步更新本指南对应章节，并在 §3 状态快照标注新时点。
