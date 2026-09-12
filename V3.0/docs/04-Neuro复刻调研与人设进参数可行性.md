# Neuro 复刻调研与"人设进参数"路线可行性报告

> 2026-09-11 · 基于 deep-research workflow(118 份已验证结果,含 3 票对抗验证)+ zread 一手仓库侦察
> 所有关键主张均经反方验证(refuted 仅 2 条,已剔除);来源链接见文末
> 作者: 李文煜

## 0. 一页纸结论

1. **四个开源起点全部是"提示词人格"**——没有一个把人设微调进参数。你的想法超出当前所有开源实现的范围,属于无人区,但有充分学术证据支持可行。
2. **想法①(LLM 调用解耦)完全可行且已是行业标配模式**(AIRI/Open-LLM-VTuber/My-neuro 三家均实现);V3.0 已有 `llm/registry + openai_compat` 抽象,接入本地模型只是加一个 provider 配置的事。
3. **想法②(人设微调进参数)有同行评审级证据**:RoleLLM(ACL 2024)证明 7B LoRA 微调可达 GPT-4 提示词水平;CharacterBot(ACL 2025)证明微调能注入提示词无法传达的"深层人格";从业者经验:单角色 <1000 条高质量样本即可起效。**V3.0 的评分/纠正/手动回复系统就是现成的数据生产线**——这是四个开源项目都没有的独特资产。
4. **想法③(RL 微调)**:在线 RL(GRPO/在线 DPO)研究级配置是 8×H100 起步,消费级不可行;但 **semi-online 迭代 DPO ≈ 在线 GRPO 效果**(arXiv 2506.21495),即"收集→评分→DPO→部署→再收集"的循环正是效果与算力的最优交点——恰好就是 V3.0 评分闭环的形状。
5. **硬件结论**:RTX 4060 8GB(被 GSV 占用部分)→ **推理可用**(Qwen3-8B Q4 ≈5GB, ~30-50 tok/s),**训练只够 4B 级 QLoRA**(8B QLoRA 最低 6GB 无余量,14B 8.5GB 超限);认真训练 → 云端租 24GB 4090(约 ¥1-3/小时,单次微调几块钱)或 Kaggle 免费 2×T4。
6. **基座推荐 Qwen3 系列**(注意没有 7B 档:Dense = 0.6/1.7/4/8/14/32B)。主力 **Qwen3-8B**(≈上代 14B/32B 水平,128K 上下文,Apache 2.0,LLaMA-Factory 官方一等公民支持)。

---

## 1. 四项目对比(全部一手验证)

| 维度 | AIRI | Open-LLM-VTuber | My-neuro | LocalAIVtuber2 |
|---|---|---|---|---|
| 规模/活跃 | 22k★ MIT,TS monorepo,多端(web/桌面/移动) | 活跃,v2.0 重写规划中 | 1.36k★,中文社区活跃 | 235★,个人项目 |
| **LLM 接入** | xsAI 统一抽象,**29 个 provider**(含 Ollama/vLLM/SGLang 本地;桌面版 candle 原生 CUDA/Metal) | **引擎无关**:StatelessLLMInterface+工厂,`llm_provider` 配置切换(openai_compatible/llama_cpp 进程内 GGUF/ollama/claude/gemini/智谱/deepseek…) | 单一 LLMClient 类,OpenAI 兼容 `/chat/completions`,云端(DMXAPI)/本地纯配置切换;**专门写了 Qwen3 reasoning_content 兼容** | **硬编码 llama.cpp 本地栈**,无 provider 抽象 |
| **记忆** | DuckDB-WASM/pglite(客户端)+ memory-pgvector(PostgreSQL);Memory Alaya WIP | basic_memory_agent(短期+对话记录持久化);**Mem0 已移除**(记不住 LLM 回复/触发不稳);Letta 外接 | **MemOS**(Qdrant 向量+BM25+NetworkX 图谱三路召回→bge-reranker-v2-m3 精排;重要性评分/晋升/衰减/合并/候选池治理) | Qdrant+fastembed RAG |
| **人格机制** | 纯提示词(Velin 有状态 prompt 模板);无任何训练代码(唯一训练是游戏 agent 的 YOLO) | 纯提示词(`persona_prompt` YAML 字段);无训练依赖 | 纯提示词("肥牛"人设=配置文本);**"支持微调"名不副实——LLM-studio 文件夹不在仓库,无训练代码**,仅百度网盘整合包文字指引 | **README 声称 custom finetuned language model + "对话编辑→导出为训练数据"闭环**(唯一例外,但项目小、无可验证训练管线) |
| 对我们的参考价值 | 架构分层+provider 抽象样板 | **解耦接口最清晰样板**;TTS 列表含 GPT-SoVITS(与你现有栈兼容) | MemOS 记忆治理与 V3.0 useful_score 同源,可对照借鉴 | "对话→训练数据导出"闭环与你想法同构 |

**关键事实**(验证员逐条核对过仓库代码):四项目的记忆全部是外挂 RAG,人格全部靠 system prompt。Neuro-sama 本体闭源,社区普遍推断也是前沿大模型+提示词+海量 few-shot。

## 2. 想法①:服务层 LLM 解耦 —— ✅ 可行,且半成品已在手上

三家项目的共同模式 = **接口抽象 + 配置切换 + OpenAI 兼容协议做统一方言**:

```
业务逻辑 ──依赖──> StatelessLLMInterface(抽象接口)
                     ├─ openai_compatible(任意云端/本地 vLLM/Ollama/LM Studio)
                     ├─ llama_cpp(进程内直载 GGUF)
                     ├─ ollama(原生客户端)
                     └─ claude/gemini/...
```

**V3.0 现状**:`llm/registry.py`(ProviderSpec 单一注册表)+ `llm/openai_compat.py`(OpenAI 兼容基类)+ `llm/resolver.py`(按任务路由)——架构上已经就是 Open-LLM-VTuber 的模式。**缺的只是**:
1. 一个 `local` provider 条目(api_base 指向 `http://<本地机>:11434/v1` 或 frp 穿透的 vLLM);
2. `.env` 加 `LOCAL_LLM_API_BASE/LOCAL_LLM_MODEL` 配置;
3. resolver 里 chat 任务可选路由到 local。

Qwen 官方明确支持 vLLM/SGLang 建 OpenAI 兼容端点、本地推荐 Ollama/llama.cpp——**与现有 GSV 的 frp 隧道模式完全同构**,云服务器(无 GPU)经 frp 调本地 4060 上的 Ollama 即可,零架构变更。

## 3. 想法②:人设微调进参数 —— ✅ 可行,学术+实践双证据

### 3.1 学术证据(全部同行评审)

| 论文 | 结论 | 对我们的意义 |
|---|---|---|
| **RoleLLM**(ACL 2024 Findings) | RoCIT(LoRA rank8)微调 LLaMA-7B/ChatGLM2-6B,角色扮演达到 GPT-4 提示词(RoleGPT)可比水平;中文 RoleGLM 全指标略超 RoleGPT;"embeds role-specific knowledge into their weights" | 7B 级 LoRA 微调 ≈ 前沿提示词,路线成立的直接实证;学术数据规模 168k 样本/100 角色(每角色~1.7k) |
| **CharacterBot**(ACL 2025 Findings) | 纯传记/对话数据只能注入**表层**人格;预训练任务+3 微调任务+CharLoRA(Qwen2.5-7B)能复现**语言风格+思想模式**,自适配指标超 GPT-4o(0.880 vs 0.734) | "深层人格必须进参数"的学术论据;提示词天花板存在 |
| **Neeko**(EMNLP 2024) | 每角色独立 LoRA 块动态加载;7B LoRA 训练仅 13.49GB/1.72h(A100)vs 全参 107.84GB/48.55h;"FT 系整体优于 ICL/RAG"(优势 0.02-0.15,幅度有限) | "清浔=挂在 Qwen3 底座上的一个 LoRA"形态可行;多角色可扩展;注意对现代前沿模型的优势不保证 |
| 灾难性遗忘综述(arXiv 2501.13669) | 窄域微调会覆盖通用能力;缓解=参数重要性正则/通用数据回放/小学习率 | 风险与对策都有手册 |

### 3.2 从业者经验(火山引擎角色扮演微调 + 社区)

- **数据量**:单角色专有模型"不到一千条高质量数据就可以取得不错效果";LIMA 法则 ~2000 条;Unsloth 用户数万条微调 70B 成功。
- **数据配比**:通用数据 0-50%(作者个人 30%);纯专有数据可行但强过拟合(单人格+prompt 稳定时甚至可能反而好)。
- **LoRA 局限**:低秩近似有信息损失,易残留"简单重复高频词"的机械感,全参微调是上限(但消费级不可及)——**建议 LoRA rank 取高些(32-64)缓解**。
- **DPO**:对可明确定义的 bad case 很有效;"最好有线上产品,方便构建 chosen/rejected"——**V3.0 就是那个线上产品**。

### 3.3 V3.0 的独特数据资产(四项目都没有)

```
SFT 数据(chosen):pos 样本(score≥85 的 ai 回复)+ manual(手动回复,金)
                 + correction(纠正文本,金)+ roleplay 高分剧本
DPO 偏好对:      同一上下文 —— corrected(理想) vs 原回复(被纠正)
                 即"纠正回复"功能天然产出 chosen/rejected 对!
裁判:           _llm_score 评审 prompt(对照人设打分)直接复用为 LLM-as-judge
```

构造管线:chat_store 对话历史(上下文)+ score 样本队列(标签)→ 导出 alpaca/sharegpt JSONL(LLaMA-Factory 原生支持 `system`(人设)+`history`(多轮)字段)→ QLoRA 训练 → `llamafactory-cli export` 合并 → 本地推理服务。

### 3.4 风险清单(诚实)

1. 单用户数据分布窄(只有你一个人的对话)→ 过拟合到单一交互模式;对策:混 30% 通用对话数据
2. 灾难性遗忘 → 小学习率(5e-6 起)+ LoRA 限制容量 + 通用数据回放
3. 人设演进 = 重训(反推现在是改 prompt 即时生效,微调后变成周/月级迭代)→ **混合架构:事实类人设(记忆/关系)留 prompt+RAG,风格类人格进参数**——RoleLLM 也证明微调模型对"未见角色"仍可用提示词切换人格,两层互补
4. LoRA 机械感 → rank 32-64 + 高质量数据筛分
5. 评测:微调前后用现有评分系统盲测对比(同一批上下文,人设契合均分变化)——**评分系统兼任 benchmark**

## 4. 想法③:RL 作为参数的额外微调 —— ⚠️ 改形态后可行

| 路线 | 证据 | 硬件现实 |
|---|---|---|
| 在线 GRPO | TRL GRPOTrainer 支持**自定义 reward 函数**(你的评分逻辑直接接入);TRL+vLLM colocate 单卡可跑(0.5B 演示) | 研究级配置 32×H200(8B);Unsloth 称 24GB 可跑 Qwen3 级 QLoRA GRPO |
| 在线 DPO(OAIF) | TRL OnlineDPOTrainer(实验性):**prompt-only 数据集**+LLM 裁判,**裁判指令可控**("按清浔人设评优"直接写进 judge prompt);原生 PEFT | 官方验证 8×H100;消费级不现实 |
| **离线 DPO** | 一次性静态偏好对 | ❌ 效果差:比在线低 45-57%(AlpacaEval 口径) |
| **semi-online 迭代 DPO** ⭐ | **效果 ≈ 在线 GRPO**(论文核心发现);每轮用更新后的模型重新收集偏好;DPO 比 GRPO 省显存(每步只需一对回复) | **单次训练就是普通 DPO 的算力**,迭代循环而已 |

**推荐形态**:semi-online 迭代闭环 = "部署当前 LoRA → 线上收集评分/纠正 → 攒一批 DPO 数据 → 云端训练下一版 LoRA → 替换部署"。这正是 V3.0 评分闭环的天然延伸,**不需要在线 RL 基础设施**。奖励函数注意长度偏置(reward hacking 使回复变长)→ 判分时长度归一化。

## 5. 部署方案

### 5.1 显存/内存速查(已验证数字)

| 任务 | 7B/8B | 14B | 备注 |
|---|---|---|---|
| 推理 fp16 | ~14-16GB | ~28GB | 8GB 卡不可行 |
| **推理 Q4 量化(GGUF/AWQ)** | **~5GB** | ~8.5GB | 4060 可跑 8B(~33 tok/s);14B 占满无 KV 余量,且与 GSV 冲突 |
| QLoRA 4-bit 训练(最低) | 5-6GB | 8.5-12GB | "绝对最低值";4060 共享 GSV 后 8B 无余量 |
| LoRA 16-bit 训练 | 16-22GB | 32-33GB | 需 24GB 卡(8B 紧)/48GB(14B) |
| 全参微调 | ~70-120GB | ~240GB | 不考虑 |
| GRPO/在线DPO(QLoRA) | ~24GB 内可行(27B 口径) | — | 消费级单卡上限区 |

### 5.2 两场景方案

**场景 A:本地 4060(8GB,GSV 常驻占 ~2-3GB)**
- **推理**:Ollama/llama.cpp 跑 **Qwen3-8B-Q4**(≈5GB;GSV+LLM 同时在线时退 Qwen3-4B-Q4≈3GB),经 frp 供云服务器调用(复用 GSV 隧道模式);thinking 模式关掉(`/no_think` 或 enable_thinking=False)换低延迟。内存 16GB+ 足够;CPU 无瓶颈(llama.cpp GPU offload)。
- **训练**:只够 **Qwen3-4B QLoRA**(seq≤2048、batch 1-2、PagedAdamW8bit、fp16)做小规模实验;8B 训练需暂停 GSV 且贴极限。
- 内存/CPU 需求:推理 16GB RAM / 4 核;训练建议 32GB RAM(梯度卸载用)。

**场景 B:云服务器升级**
- **推荐:训练上云、推理留本地**。租用 24GB 4090 级(autoDL/RunPod 类,约 ¥1-3/小时):Qwen3-8B QLoRA SFT+DPO 一轮(数千样本,1-3 epoch)≈ 几小时内,单次成本几块钱;14B QLoRA 也可(12GB)。
- 免费路径:Unsloth 官方 Kaggle notebook(2×T4 30h/周)。
- 若要在云上常驻推理:加一张 24GB 卡跑 vLLM(Qwen3-8B-AWQ),`/v1` OpenAI 兼容端点直接被 V3.0 的 openai_compat 消费。
- **纯 CPU 服务器推理(不升级 GPU)**:Ollama 跑 8B-Q4 约 5-10 tok/s——对 QQ 聊天(本就有 3-5s 思考延迟)勉强可用,但体验降级,不推荐主力。

### 5.3 模型选型

- **主力:Qwen3-8B**(Apache 2.0;≈上代 14B/32B 水平;128K 原生上下文;思考/非思考双模式;LLaMA-Factory 官方文档一等公民;Qwen 官方后训练本身就是 SFT→RL→SFT→RL 四段,证明该系列对后训练原生适配)。
- 备选:Qwen3-4B(显存紧张时,官方称匹敌 Qwen2.5-72B-Instruct——厂商自述)/ Qwen3-14B(云训云推时)。
- GLM-4-9B:LLaMA-Factory 也支持(SFT/RLHF/DPO/SimPO),但 14B 级内 Qwen3 生态更新更全。
- 数据格式:LLaMA-Factory alpaca/sharegpt JSON(`system` 字段载人设摘要,`history` 字段载多轮上下文)。

## 6. 分阶段路线图(建议)

| 阶段 | 内容 | 门槛 | 产出 |
|---|---|---|---|
| **A. 解耦+基线** | local provider 接入(Ollama on 4060);同一批上下文跑 云端 GLM vs 本地 Qwen3-8B-Q4,用现有评分系统盲测对比 | 0 成本 | 确认本地基座人设契合基线分;接口解耦完成 |
| **B. 数据管线** | 对话历史+score/correction/manual/roleplay 队列 → 导出 alpaca JSONL(SFT 集+DPO 偏好对);面板加"导出训练数据"按钮 | 小 | 可复现的数据集生成器(V3.0 变成数据飞轮) |
| **C. 首次微调** | 云租 4090:Qwen3-8B QLoRA SFT(金样本)→DPO(纠正对);合并导出;本地部署;评分盲测 A/B(vs 未微调) | 几块钱+1天 | "清浔 LoRA v1";量化人设增益 |
| **D. 迭代闭环** | 每 N 周重复 B→C(semi-online DPO 形态);稳定后可选:GRPO 在线微调(裁判=人设评审 prompt) | 常态化 | 人格真正"长在参数里",评分闭环→训练闭环 |

阶段 A/B 纯软件工作可直接在 V3.0 做;C/D 涉及训练环境(建议新建 V3.0/training/ 目录承载,与 server 解耦)。

## 7. 主要来源

- 项目:[AIRI](https://github.com/moeru-ai/airi) · [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)([Agent 文档](https://open-llm-vtuber.github.io/en/docs/user-guide/backend/agent/)) · [My-neuro](https://github.com/morettt/my-neuro) · [LocalAIVtuber2](https://github.com/0Xiaohei0/LocalAIVtuber2)
- 论文:[RoleLLM (arXiv:2310.00746, ACL 2024 Findings)](https://arxiv.org/abs/2310.00746) · [CharacterBot/Beyond Profile (arXiv:2502.12988, ACL 2025 Findings)](https://arxiv.org/abs/2502.12988) · [Neeko (arXiv:2402.13717, EMNLP 2024)](https://arxiv.org/abs/2402.13717) · [灾难性遗忘 (arXiv:2501.13669)](https://arxiv.org/abs/2501.13669) · [在线vs离线RL (arXiv:2506.21495)](https://arxiv.org/html/2506.21495v1) · [RTX 4060 微调实测 (arXiv:2509.12229)](https://arxiv.org/abs/2509.12229)
- 工具链:[TRL GRPOTrainer](https://huggingface.co/docs/trl/en/grpo_trainer) · [TRL OnlineDPOTrainer](https://huggingface.co/docs/trl/en/online_dpo_trainer) · [TRL×vLLM 在线训练](https://huggingface.co/learn/cookbook/en/grpo_vllm_online_training) · [Unsloth Qwen3 指南](https://unsloth.ai/docs/models/qwen3.8/train) · [Unsloth 显存要求表](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements) · [Qwen 官方 LLaMA-Factory 教程](https://qwen.readthedocs.io/zh-cn/latest/training/llama_factory.html) · [Qwen3 发布博客](https://qwenlm.github.io/zh/blog/qwen3/) · [LLaMA-Factory Qwen3 显存实战(知乎)](https://zhuanlan.zhihu.com/p/1920861612211954053) · [火山引擎角色扮演微调经验](https://developer.volcengine.com/articles/7439940856175394853) · [Modal 显存科普](https://modal.com/blog/how-much-vram-need-fine-tuning) · [RunPod 预算微调](https://www.runpod.io/articles/guides/how-to-fine-tune-large-language-models-on-a-budget) · [r/LocalLLaMA 数据量讨论](https://www.reddit.com/r/LocalLLaMA/comments/1fmw744/when_to_prompt_vs_finetune_and_how_much_data_for/)
