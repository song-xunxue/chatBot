# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目状态

这是一个**全新（greenfield）的 Python 聊天机器人项目**，目前尚无业务代码。PyCharm/IntelliJ 模块名为 `Mychat`（见 `.idea/Mychat.iml`，类型 `PYTHON_MODULE`）。本仓库的工作目录 `D:\code\Git_Local\ChatBot` 本身**不是 git 仓库**（属于 `D:\code\Git_Local` 多仓库工作区下的一个项目目录）。

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
    - `mychat` — **V1.0 专属**（V2.0 早期测试曾借用，现已区分开）
    - `qingxun` — **V2.0 / 清浔专属**（python 3.11，匹配 `server/Dockerfile`；打包启动器/工具链用此，2026-08-10 新建）
    - 其他通用：`mypytorch`（PyTorch/CUDA）、`langchain`、`coze_env`
  - 不确定用哪个时主动询问用户；conda.exe 完整路径 `C:/Users/26904/anaconda3/Scripts/conda.exe`
- **项目类型已确认：项目类型**（非作业类型）。所有代码文件统一采用项目类型头部注释风格：功能说明 + 作者（`李文煜`）+ 日期（`yyyy-mm-dd`）+ 变更日志
- 其余规范（中文文档/注释、Windows 兼容性、conda 环境等）见全局 `~/.claude/CLAUDE.md`

## 项目配置

- `.claude/skills-guide.md` — Matt Pocock Skills 开发流程指南（已从全局同步）
- `.claude/settings.local.json` — 本地权限配置（已同步全局 `permissions.allow` 通配规则）
- `.claude/chat.md` — 用于记录长文本（如运行报错日志），按需创建

## 部署访问（核心 · 每次会话必读，勿遗忘）

V2.0 线上部署在云服务器，访问凭证（曾因没记牢重复踩坑，特此固化为项目级记忆）：

- **服务器**：`43.140.219.99`，**用户 `ubuntu`**（非 root），**sudo 免密**
- **SSH 私钥**：`D:\code\Git_Local\ChatBot\.claude\ubuntu.pem`（**项目目录内，非 `~/.ssh/`**）
  - 命令：`ssh -i D:/code/Git_Local/ChatBot/.claude/ubuntu.pem ubuntu@43.140.219.99`
  - `~/.ssh/` 下**无私钥文件**（只有 config/known_hosts），认证必须 `-i` 指定 pem
- **部署目录**：`~/ChatBot-V2/`（ubuntu 家目录 `/home/ubuntu/ChatBot-V2/`，**非 `/root/`**）
- **面板**：`http://43.140.219.99:8000`（IP+8000 绕开域名未备案），token = `.env` 的 `ACCESS_TOKEN`
- **REST 鉴权 header**：`X-Access-Token: <token>`（**非 `Authorization: Bearer`**，见 `server/app/api/_auth.py`）
- **部署一条龙**：本地 `tar`（排除 `V2.0/tts-tools` / `V2.0/Ref` / `node_modules` / `.env`）→ `scp -i pem 包 ubuntu@43.140.219.99:~/` → 远端 `cd ~/ChatBot-V2 && tar xzf 包 --strip-components=1 && sudo bash scripts/deploy_v2.sh`
- 细节见记忆 [[deploy-ssh-authorization]] [[v2-0-deploy]]
