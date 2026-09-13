# 清浔人设训练(阶段 C · 本地 4060)

> 2026-09-12 建立 · 依据 docs/04 调研报告 · 数据 = 评分系统导出(阶段 B 管线)

## 环境

- conda env:**llmtrain**(python 3.11 + unsloth;Windows 原生,无需 WSL)
- GPU:RTX 4060 Laptop 8GB —— **4B 稳**(可语音同开);**8B 贴极限**(必须关语音启动器,
  batch=1/seq≤2048,OOM 即退 4B);14B 本机不可
- 模型缓存:HF 模型下载到 `D:\llmtrain-cache`(run_train.bat 里设 HF_HOME,不占 C 盘)

## 流程(每轮重训都走这三步)

```bat
rem 1. 面板导出数据(System 页「训练数据导出」,或 curl)
rem    产物在服务器 server/data/training/qingxun_sft_*.jsonl,先 docker cp / scp 拉回本地

rem 2. 冒烟(环境验证,不耗真数据)
run_train.bat smoke

rem 3. 正式训练(数据攒到 100+ 条起;500-1000 条出正式版)
run_train.bat v0 ..\server\data\training\qingxun_sft_2026xxxx.jsonl
```

## 产物与部署

- adapter:`training/outputs/qingxun-lora-vN/`(几百 MB safetensors,**每版永久存档,回滚=换目录**)
- 部署回 Ollama:训练后在 llmtrain 环境跑 `deploy_ollama.py`(merge→GGUF→`ollama create qingxun-vN`)
  → 服务器 `.env` 改 `LOCAL_LLM_MODEL=qingxun-vN` → 面板「重载配置」
- 盲测对比:System 页「人设盲测基准」:local(qingxun-vN) vs glm —— **微调前后同法对比,量化人设增益**

## 数据策略(长期积累)

1. 日常使用:手动回复 / 纠正回复 每次自动 +1 条金样本(评分系统自动沉淀)
2. roleplay 面板批量录入剧本(assistant 打分 ≥85 入 SFT)
3. 可选加速:云端 GLM 合成人设对话扩充(待做,RoleLLM 路线)

配比注意(调研报告 §3.4):通用数据 0-30% 混入防过拟合;单角色 <1000 条高质量即可起效。

## 作者

李文煜 · 2026-09-12
