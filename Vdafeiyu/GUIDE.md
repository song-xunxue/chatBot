# Vdafeiyu 操作指南（给会话看）

> 在这个目录开工的会话：先读 `AGENTS.md`（规矩），再读这份（怎么跑）。

## 一句话

大肥鱼（QQ 3682822273）的专属后端，源码在这个目录，**以后都从这里跑，不要用 `C:\Users\26904\.dsh\daifeiyu\app` 那份副本**（C 盘空间紧张，那份已弃用）。

## 一键启动（推荐）

```powershell
powershell -File D:\code\Git_Local\ChatBot\Vdafeiyu\scripts\start-dafeiyu.ps1
```

幂等可重复执行：redis 6380 → server 8081 → NapCat 顺序由脚本内部保证（防 FAKEREDIS），已在监听的组件自动跳过，全程无窗。双击桌面「大肥鱼 启动器」即此脚本。

## 启动顺序（三件套，手动兜底）

### 1. Redis（记忆库，6380）

```powershell
New-Item -ItemType Directory -Force -Path 'D:\code\Git_Local\ChatBot\Vdafeiyu\.data\redis' | Out-Null
Start-Process -FilePath 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-server.exe' `
  -ArgumentList '--port','6380','--appendonly','yes','--dir','D:\code\Git_Local\ChatBot\Vdafeiyu\.data\redis' `
  -WindowStyle Hidden
```

检查：`Test-NetConnection 127.0.0.1 -Port 6380`

### 2. 后端（8081）

```powershell
Start-Process -FilePath 'C:\Users\26904\anaconda3\envs\mychat\python.exe' `
  -ArgumentList 'D:\code\Git_Local\ChatBot\Vdafeiyu\server\scripts\local_dev.py','--port','8081','--token','114507xX','--no-seed' `
  -WorkingDirectory 'D:\code\Git_Local\ChatBot\Vdafeiyu' `
  -RedirectStandardOutput 'D:\code\Git_Local\ChatBot\Vdafeiyu\logs\server.out.log' `
  -RedirectStandardError 'D:\code\Git_Local\ChatBot\Vdafeiyu\logs\server.err.log' `
  -WindowStyle Hidden
```

检查：`Invoke-RestMethod http://127.0.0.1:8081/health` → 要看到 `"onebot_connected": true`

### 3. NapCat（QQ 那头）

```powershell
launcher\start-napcat.cmd
```

- NapCat 独立目录：`C:\Users\26904\.dsh\napcat-dafeiyu`
- 用快速登录（`3682822273`），不扫码
- 掉线看护：计划任务 `NapCat-Watchdog`（每 5 分钟探 3000 端口，跑 `.dsh\runtime\napcat-keepalive.ps1`）
  - ⚠️ 2026-10-26 事故与修复：旧版看护按进程名**无差别强杀双栈所有 QQ**（另一栈同宿主被殃及，双号重扫+触发账号风控 168）且重启调的 vbs 不存在（杀完拉不起）。现改为**只精确匹配大肥鱼自己的进程**（`-q 3682822273` + `napcat-dafeiyu` 目录）+ 拉起走 `scripts\start-dafeiyu.ps1` 幂等启动器。`launcher\` 下的 `napcat-autostart.ps1`/`start-napcat-silent.vbs` 旧残留已删除，勿再引用

## 配置

`.env` 在项目根（本目录），关键项：

| 键 | 值 | 说明 |
|---|---|---|
| `ONEBOT_WS_TOKEN` | `daifeiyu-local-8081` | 与 NapCat 的 WS 配置一致 |
| `ONEBOT_SELF_ID` | `3682822273` | 大肥鱼的 QQ |
| `REDIS_URL` | `redis://127.0.0.1:6380/0` | 独立记忆库 |
| `ACCESS_TOKEN` | `114507xX` | 面板/API 鉴权 |
| `CHAT_PROVIDER` | `deepseek` | 云端模型 |

## 面板

<http://127.0.0.1:8081>（token `114507xX`）；手机走局域网 `http://10.170.5.251:8081`。

## 数据在哪

- 对话/记忆/心情：Redis 6380，数据文件在 `Vdafeiyu\.data\redis`
- 日志：`Vdafeiyu\logs\server.out.log`
- 人设：`server/app/persona/default.py`（默认已是大肥鱼）

## 常见问题

| 症状 | 原因 | 处理 |
|---|---|---|
| `onebot_connected: false` | NapCat 没连上 | 等 30 秒重连；还不行看 NapCat 窗口/3000 端口 |
| QQ 不回消息 | NapCat 登录态失效 | 重新扫码（二维码在 `napcat-dafeiyu\app\napcat\cache\qrcode.png`） |
| 窗口一堆 | 启动壳残留 | 关掉不带 `NapCatWinBootMain` 的窗口 |

## 铁律

1. **不要强杀 QQ / NapCatWinBootMain**——一强杀登录态就失效，要重新扫码。清理残留必须按 `-q 3682822273` + `napcat-dafeiyu` 目录精确匹配（V3.0-local 栈 QQ 同宿主 QQ.exe，按进程名匹配必误杀双栈）。
2. **改完不提交 git**，留在工作区等用户说。
3. **不与 V3.0-local 栈共用**：V3.0-local 用 `D:\code\Git_Local\ChatBot\.local\napcat`（1145077465），大肥鱼用 `C:\Users\26904\.dsh\napcat-dafeiyu`（3682822273）。
4. 和 V3.0-local 同步更新时，只搬和大肥鱼相关的改动；专属改动不回灌 V3.0。
5. **`dashboard/dist` 绝不能从 V3.0-local 拷贝**——那份含日记/世界书页，本栈后端无对应路由，拷了必坏（详见 README「面板更新红线」）。
