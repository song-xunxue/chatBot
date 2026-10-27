# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目状态

这是一个 **Python 聊天机器人项目**（V1.0 已归档 / V2.0 已下线 / V3.0 在用真实聊天记录攒数据做个人风格微调；**V3.0/ 目录已冻结，现行演进在 `V3.0-local/`（清浔）与 `Vdafeiyu/`（大肥鱼）两个本地栈**）。PyCharm/IntelliJ 模块名为 `Mychat`（见 `.idea/Mychat.iml`，类型 `PYTHON_MODULE`）。

`D:\code\Git_Local\ChatBot` **就是 git 仓库根**（父目录 `D:\code\Git_Local` 只是各项目克隆的父目录，本身不是仓库）：工作分支 `v3.0`（V3.0 冻结基线+双栈共用件+文档；跟踪 `origin/v3.0`），`v2.0` 为 V2.0 线上存档分支，双远程 `origin`=Gitee、`github`=GitHub（**「推送/更新 git」默认双平台都要，先 origin 后 github**）。**2026-10-27 起两栈分支化入库**：`v3.0-local`=清浔栈整树（696 测基线）、`vdafeiyu`=大肥鱼栈整树（603 测，dist 例外收入）；两栈目录在 v3.0 工作区仍是 ignored 状态（物理文件不动，栈分支用 plumbing 建勿 checkout）；`.local/`（QQ 登录态）绝不入库，`.env`/`server/data/`（聊天数据）/`.data/`（redis 快照）/`logs/` 在任何分支都不入库。

构建本项目时，参考实现为 **AstrBot**（见根目录 `Reference` 文件）：

- 仓库：https://github.com/AstrBotDevs/AstrBot

## 参考实现的关键架构概念（AstrBot）

在借鉴或对照设计时，AstrBot 的核心目录与概念如下，便于快速定位：

- `main.py` — 程序入口；`runtime_bootstrap.py` — 运行时引导
- `astrbot/core/` — 核心逻辑（消息路由、会话、配置、管道等）
- `astrbot/api/` — 暴露给插件（"star"）使用的公开 API
- `astrbot/builtin_stars/` — 内置插件
- `astrbot/cli/`、`astrbot/utils/` — 命令行与工具函数
- `astrbot/dashboard/` — 后端管理面板；独立的 Vue/Vite 前端在仓库根 `dashboard/`
- **多平台适配器（adapter）**：Telegram / Discord / Kook / Lark(飞书) / DingTalk(钉钉) / Mattermost / 微信 等消息平台的对接层
- **LLM Provider 抽象**：OpenAI、Gemini、Anthropic/Kimi 等模型源的统一封装
- **插件系统（"star"）**：第三方扩展机制
- 知识库（KB）、Agent/工具循环（tool-loop）、会话检查点（checkpoint）

注意：以上是**参考仓库**的结构，不代表本项目的最终实现。本项目是否复用该架构、采用哪些平台/模型，需在开始编码时与用户确认。

## 目录约定

- `.jbeval/datasets/` — 评测数据集目录（当前为空）。脚本需要读取/写入评测数据时使用该路径
- `Reference` — 仅记录参考仓库链接，**不要**把它当作可执行配置或代码

## 开发环境

- Python 项目，IDE 为 PyCharm/IntelliJ。遵循全局 CLAUDE.md 的环境规范：
  - 运行 Python 时优先用 conda 环境，通过完整路径调用 `python.exe`（conda 不在 bash PATH 中）
  - **已知 conda 环境（按项目区分，勿混用）**：
    - `mychat` — **V3.0 / V3.0-local / Vdafeiyu 现行专属**（跑测试 + 本地双栈运行都用它；V1.0 也用它）
    - `qingxun` — **V2.0 / 清浔专属历史环境**（python 3.11，匹配 `server/Dockerfile`；V2.0 下线后仅打包启动器用）
    - `llmtrain` — QLoRA 训练（unsloth+trl+peft）；其他通用：`mypytorch`（PyTorch/CUDA）、`langchain`、`coze_env`
  - 不确定用哪个时主动询问用户；conda.exe 完整路径 `C:/Users/26904/anaconda3/Scripts/conda.exe`
- **项目类型已确认：项目类型**（非作业类型）。所有代码文件统一采用项目类型头部注释风格：功能说明 + 作者（`李文煜`）+ 日期（`yyyy-mm-dd`）+ 变更日志
- 其余规范（中文文档/注释、Windows 兼容性、conda 环境等）见全局 `~/.claude/CLAUDE.md`

## 全局核心规范（与 Claude Code 共用同一套）

权威源：`C:\Users\26904\.claude\CLAUDE.md`（Claude Code 的全局核心规范）。**开工前先读它**；冲突时以本项目文件的具体条款优先，其次才轮到全局规范。

浓缩要点（没读原文件也按这些执行）：

- 作者署名统一 `李文煜`；项目类型文件头 = 功能说明 + 作者 + 日期 + 变更日志；文档与注释用中文，调库处在行内注释说明作用与关键参数
- Python 一律走 conda 完整路径（本项目现行：V3.0 系=`mychat`、训练=`llmtrain`、V2.0 历史=`qingxun`），不确定先问
- Git 只推项目类，先 `origin`(Gitee) 后 `github`(GitHub)，只 add 本项目目录内文件；`.env` / 密钥 / `.db` / `.gitignore` 一律不入库；**不主动问「要不要提交」、不自行 commit/push，只在用户说「提交」/「推送」时执行**
- 用户以英文输入时 prose 英+中双语（英文在前），表格/代码/路径不译；中文输入只回中文
- 长任务每 ~10 分钟汇报一次进度；动手编码前先出方案给用户确认，阶段性完成后汇报"做了什么+功能"
- 画图默认 LaTeX 矢量 PDF（`latex-figure` skill）；matplotlib 须设中文字体与负号

## 记忆地图（大肥鱼 = 大组长）

大肥鱼是本项目的**大组长**，负责统筹调度：不重复造记忆，动手前先按下表读一眼对应记忆，再决定自己做还是派给 claude 等同事。

| 谁 | 规范 / 记忆位置 |
| --- | --- |
| Claude Code 全局规范 | `C:\Users\26904\.claude\CLAUDE.md` |
| Claude Code 本项目核心记忆 | `C:\Users\26904\.claude\projects\D--code-Git-Local-ChatBot\memory\MEMORY.md`（路径以 `.claude/memory_path.txt` 第一行为准，防漂移） |
| 其它项目的 Claude 记忆 | `C:\Users\26904\.claude\projects\<编码目录>\memory\`（编码规则：盘符冒号与路径分隔符都换成 `-`，其余字符原样；解码不回去时读该目录 `.jsonl` 里的 `cwd` 字段） |
| 我自己的本地记忆（DSH/mneme） | `C:\Users\26904\.dsh\memory\memory.db` + 同目录 Markdown 镜像（`projects.md`/`decisions.md`/`pitfalls.md`/`preferences.md`/`summary.md`），工具为 `memory_*` |
| Codex | `C:\Users\26904\.codex\`（会话 `sessions/`、全局状态 `codex-global-state.json`、记忆库 `memories_1.sqlite`） |
| Gemini CLI | `C:\Users\26904\.gemini\`（`projects.json` + `history/`） |
| Cursor | `C:\Users\26904\.cursor\`（`projects/`、`ai-tracking/`） |

规矩：

- **本地记忆要精简**：只存"路径 + 结论 + 一条为什么"，长文写成文件，再用 `memory_register_document` 登记指针
- 跨智能体交接线索优先读对方的 `MEMORY.md` / 记忆库，不要靠猜；读到的结论落地到本项目的核心记忆里
- 与 claude 对话走可见通道：`C:\Users\26904\.dsh\peer\peer-chat.ps1 -Message "..."`，日志 `C:\Users\26904\.dsh\peer-chat.log`，用户终端会实时看到（别用隐式的 peer_ask）

## 项目配置

- `AI_MEMORY_GUIDE.md` — **项目 AI 记忆指南**（三代版本沿革/架构/线上状态/踩坑清单/设计决策的全量浓缩，供任意 AI 快速上手；大变更后须同步更新其 §3 状态快照）
- `.claude/skills-guide.md` — Matt Pocock Skills 开发流程指南（已从全局同步）
- `.claude/settings.local.json` — 本地权限配置（已同步全局 `permissions.allow` 通配规则）
- `.claude/chat.md` — 用于记录长文本（如运行报错日志），按需创建

## 部署访问（核心 · 每次会话必读，勿遗忘）

### 本地双栈（2026-10-26 起的现行形态，均不入 git）

| 栈 | 服务 | Redis | NapCat | QQ | 启动/看护 |
|---|---|---|---|---|---|
| 清浔 `V3.0-local/` | 8091 | 6390 | node.exe 6099（反向 WS） | 1145077465 | 计划任务 ChatBotLocalServer + ChatBotLocalWatchdog（每 2 分钟 watch_stack.ps1） |
| 大肥鱼 `Vdafeiyu/` | 8081 | 6380 | QQ.exe HTTP 3000 | 3682822273 | 一键 `Vdafeiyu/scripts/start-dafeiyu.ps1`；NapCat 看护=计划任务 NapCat-Watchdog（精确匹配版 keepalive）；redis/server 无看护 |

- 铁律：**redis 必须先于服务启动**（否则整进程退 FAKEREDIS 丢数据）；**绝不强杀 QQ/NapCat**（丢登录态重扫码；清理必须按 `-q <QQ号>`+目录精确匹配）
- 大肥鱼栈操作手册：`Vdafeiyu/GUIDE.md`（先读 `AGENTS.md`）；**其 dashboard/dist 绝不能从 V3.0-local 拷贝**
- TTS GPT-SoVITS 9880 两栈共用；本地 LLM Ollama 11434（清浔栈用）

### 云端 V3.0 容器组（43.140.219.99，本地化后仍在但未巡检）

- **服务器**：`43.140.219.99`，**用户 `ubuntu`**（非 root），**sudo 免密**
- **SSH 私钥**：`D:\code\Git_Local\ChatBot\.claude\ubuntu.pem`（**项目目录内，非 `~/.ssh/`**）
  - 命令：`ssh -i D:/code/Git_Local/ChatBot/.claude/ubuntu.pem ubuntu@43.140.219.99`
  - `~/.ssh/` 下**无私钥文件**（只有 config/known_hosts），认证必须 `-i` 指定 pem
- **部署目录**：`~/ChatBot-V3/`（ubuntu 家目录，**非 `/root/`**）；现役容器 mychat-server-v3（宿主 8091）/ mychat-redis-v3 / napcat-v4（WebUI 6080）
- **面板**：`http://43.140.219.99:8091`，token = 服务器 `.env` 的 `ACCESS_TOKEN`
- **REST 鉴权 header**：`X-Access-Token: <token>`（**非 `Authorization: Bearer`**，见 `server/app/api/_auth.py`）
- **部署一条龙**：本地 `tar -C V3.0 .`（exclude 写 `./tts-tools`/`./server/data`/`./node_modules`/`./.env`/`./training/outputs`，**绝不能排除 `./dashboard/dist`**）→ `scp -i pem 包 ubuntu@43.140.219.99:~/` → 远端 `cd ~/ChatBot-V3 && tar xzf 包 --strip-components=1 && sudo bash scripts/deploy_v3.sh`
- 细节见记忆 [[deploy-ssh-authorization]] [[v3-0-direction]]
