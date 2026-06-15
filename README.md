# MyChat — 智能陪伴聊天机器人

> 作者: 李文煜
> 日期: 2026-06-15
> 状态: M1 项目骨架搭建中

带**人格与记忆系统**的多模态 AI 陪伴聊天软件，服务端 + 客户端双端架构。

## 架构

- **服务端**：FastAPI，部署于 Ubuntu 22.04 云服务器（Docker），承载消息处理管道、人设、记忆、插件、LLM 对接、Web 管理面板，7×24 在线
- **客户端**：PySide6 桌面应用（Win11），多模态聊天 + 桌宠形态
- **存储**：Redis（云端权威）+ SQLite（客户端本地缓存）

## 目录结构

| 目录 | 说明 |
|---|---|
| `server/` | 服务端（FastAPI + Vue 面板） |
| `client/` | 客户端（PySide6） |
| `shared/` | 跨端共享：消息 schema、协议常量 |
| `docs/` | 设计文档体系（01~08） |
| `scripts/` | 部署/运维脚本 |
| `.jbeval/datasets/` | 评测数据 |
| `Ref/` | 参考资料与样本（仅本地，不入库） |

## 设计文档

详见 `docs/`：01 需求规格 / 02 技术架构 / 03 接口 / 04 数据模型 / 05 插件系统 / 06 记忆系统 / 07 开发规范 / 08 项目计划。

## 环境配置

复制 `.env.example` 为 `.env` 并填入真实凭据。**`.env`、数据库文件、用户上传资源均不入库**（见 `.gitignore`）。

## 快速开始（M1 骨架）

**环境**：Python 3.11（推荐 conda 环境 `mychat`）；`cp .env.example .env` 填写凭据。

**本地开发**：

- 服务端依赖：`pip install -r server/requirements.txt`；客户端依赖：`pip install -r client/requirements.txt`
- 服务端：`cd server/app && uvicorn main:app --reload --port 8000`，访问 `http://localhost:8000/health`
- 客户端：`python client/app/main.py`，窗口输入消息可见 `[echo]` 回显（M1 tracer bullet）

**Docker 部署**（服务器）：`docker compose up -d`，或 `bash scripts/deploy.sh`（Ubuntu 22.04 一键）。
