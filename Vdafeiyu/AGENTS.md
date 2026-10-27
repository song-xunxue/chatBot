# Vdafeiyu 项目规则（大肥鱼专属版）

> 给在这个目录里开工的会话读。大肥鱼本体住在这儿。

## 这是什么

- 从 V3.0 分出来的专属版本，给 QQ 3682822273「浔与昳的大肥鱼」一个人用。
- 和 V3.0 / V3.0-local 同源；**后续从 local 同步更新**（先看 diff，再挑和大肥鱼相关的搬）。
- 大肥鱼专属的改动（人设、面板标题、QQ 号、端口 8081、独立 Redis 6380）只留这里，不回灌 V3.0。
- **不含 dream / worldbook 两批次**（V3.0-local 专属功能，本栈后端无对应路由）。

## 运行

- 一键启动（幂等）：`powershell -File Vdafeiyu\scripts\start-dafeiyu.ps1`（redis→server→NapCat 顺序内部保证）
- 后端：`server/scripts/local_dev.py --port 8081 --token 114507xX --no-seed`
- Python：`C:\Users\26904\anaconda3\envs\mychat\python.exe`（conda 不在 PATH，必须完整路径）
- Redis：6380（独立实例，数据文件在 `Vdafeiyu\.data\redis`；**必须先于后端启动**，否则整进程退 FAKEREDIS 丢数据）
- NapCat：独立目录 `C:\Users\26904\.dsh\napcat-dafeiyu`，掉线看护=计划任务 `NapCat-Watchdog`（跑 `.dsh\runtime\napcat-keepalive.ps1`，精确匹配版）
- 模型：云端 DeepSeek（`.env` 里 `CHAT_PROVIDER=deepseek`）

## 规矩

- 项目文件不写作者（隐私规范）；文件头 = 功能说明 + 日期 + 变更日志。
- 文档与注释用中文；调库处行内注释说明作用与关键参数。
- **不主动 git commit / push**，改完留在工作区，等用户说。
- **不要强杀 QQ / NapCatWinBootMain 进程**：一强杀登录态就失效，要重新扫码；清理残留必须按 `-q 3682822273` + 目录精确匹配（V3.0-local 栈 QQ 同宿主，按进程名匹配必误杀）。
- **`dashboard/dist` 绝不能从 V3.0-local 拷贝**：那份含日记/世界书页，本栈后端无对应路由，拷了必坏（详见 README「面板更新红线」）。
- 面板与 API 同源同端口（8081），手机访问走局域网地址。
- 大肥鱼不是助手，是按「人」设计：有生活感、有私心、会主动找用户、记得小事。
