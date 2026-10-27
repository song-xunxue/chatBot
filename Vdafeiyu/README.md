# Vdafeiyu · 大肥鱼专属版（基于 V3.0）

> 从 V3.0 分出来的专属版本，给「大肥鱼」（QQ 3682822273）一个人用。
> 和 V3.0 / V3.0-local 同源，后续从 local 同步更新。

日期：2026-10-26

## 它是什么

大肥鱼的「房子」：一份独立的 ChatBot 后端，有自己的记忆库（Redis 6380）、自己的人设
（`persona/default.py` 里已换成「大肥鱼」）、自己的端口（8081）。

DSH 里那些会话是她的分身（小肥鱼），这个才是本体。

## 结构

```
Vdafeiyu/
├─ server/            后端（FastAPI + OneBot + 记忆 + 人格 + 插件）
├─ dashboard/dist/    面板前端构建产物（无 src，见下方"面板更新"红线）
├─ scripts/           一键启动与工具（start-dafeiyu.ps1 等）
├─ docs/              设计文档（与 V3.0 同步）
├─ launcher/          NapCat 启动与看护脚本
│   ├─ start-napcat.cmd         手动拉起 NapCat + 快速登录
│   └─ napcat-keepalive.ps1     掉线看护（精确匹配版，计划任务 NapCat-Watchdog 每 5 分钟）
├─ .data/redis/       运行数据（Redis 6380 的 dump.rdb/AOF，聊天记忆都在这）
└─ .env               本版运行配置（端口 8081 / Redis 6380 / 云端 DeepSeek）
```

## 跑起来

**推荐一键**（幂等，可重复执行；redis→server→NapCat 顺序由脚本保证，全程无窗）：

```powershell
powershell -File D:\code\Git_Local\ChatBot\Vdafeiyu\scripts\start-dafeiyu.ps1
```

手动三件套（兜底）：

```powershell
# 1. 独立 Redis（6380，数据在本目录 .data\redis）
C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-server.exe `
  --port 6380 --appendonly yes --dir D:\code\Git_Local\ChatBot\Vdafeiyu\.data\redis

# 2. 后端（8081）——必须在 redis PING 通之后起，否则整进程退 FAKEREDIS 丢数据
C:\Users\26904\anaconda3\envs\mychat\python.exe `
  D:\code\Git_Local\ChatBot\Vdafeiyu\server\scripts\local_dev.py `
  --port 8081 --token 114507xX --no-seed

# 3. NapCat（QQ 那头）
launcher\start-napcat.cmd
```

面板：<http://127.0.0.1:8081>（token `114507xX`）

## 和 V3.0 / V3.0-local 的关系

- 代码同源，`server/` 和 `docs/` 从 V3.0 复制而来；**不含 dream 做梦日记与 worldbook 世界书两批次**（V3.0-local 专属）；
- 后续 V3.0-local 的功能改动要同步过来（先看 diff，再挑和大肥鱼相关的搬）；
- 大肥鱼专属的改动（人设、面板标题、QQ 号、独立端口/Redis）只留在这里，不回灌 V3.0。

## ⚠️ 面板更新红线

本栈 **没有 `dashboard/src`**，面板是 2026-10-25 的旧构建 dist。**绝不能直接拷贝
V3.0-local 的 dist 过来**——那份含「日记」「世界书」页面，而本栈后端没有
`rest_diary.py`/`rest_worldbook.py`，拷过来这两个页面会拿到 SPA 兜底的 200+HTML
假数据（渲染错乱）或 405。需要更新面板时：先从 V3.0-local 复制 src、剔除
diary/worldbook 页面与菜单后单独构建。

## 注意

- **不要强杀 QQ / NapCatWinBootMain 进程**：一强杀登录态就失效，要重新扫码。
  看护脚本只允许按 `-q 3682822273` + `napcat-dafeiyu` 目录精确匹配清理
  （2026-10-26 下午旧版按进程名全杀双栈 QQ 造成双号重扫+账号风控，已修复）。
- NapCat 目录独立在 `C:\Users\26904\.dsh\napcat-dafeiyu`，不与 V3.0-local 栈共用。
- 运行数据在 Redis 6380，数据文件落在本目录 `.data\redis`（dump.rdb/AOF）。
- redis 6380 / server 8081 目前**无计划任务看护**（仅 NapCat 有 Watchdog），
  机器重启后需手动跑一键启动。
