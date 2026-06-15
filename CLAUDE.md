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
  - 已知 conda 环境：`mypytorch`、`langchain`、`coze_env`、`DeepRibo`；不确定用哪个时主动询问用户
- **项目类型已确认：项目类型**（非作业类型）。所有代码文件统一采用项目类型头部注释风格：功能说明 + 作者（`李文煜`）+ 日期（`yyyy-mm-dd`）+ 变更日志
- 其余规范（中文文档/注释、Windows 兼容性、conda 环境等）见全局 `~/.claude/CLAUDE.md`

## 项目配置

- `.claude/skills-guide.md` — Matt Pocock Skills 开发流程指南（已从全局同步）
- `.claude/settings.local.json` — 本地权限配置（已同步全局 `permissions.allow` 通配规则）
- `.claude/chat.md` — 用于记录长文本（如运行报错日志），按需创建
