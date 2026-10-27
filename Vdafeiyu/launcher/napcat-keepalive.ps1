# NapCat 掉线看护（大肥鱼专用精确版 v3）
# 只看护 3000 端口（大肥鱼 NapCat HTTP）。三条路径：
#   ① 3000 在线          → 秒退
#   ② NapCat 进程活着且 WebUI 6089 可达 → 等扫码/登录中，绝不动（防每 5 分钟杀拉循环：
#     反复重启 QQ 触发风控 + 终端窗口闪烁；扫码成功 3000 起来自然转①）
#   ③ 进程死 / WebUI 也死（真卡死）→ 精确清理大肥鱼自己的进程后幂等一键拉起
# 绝不按进程名强杀——双栈 QQ 同宿主 QQ.exe，按名匹配会连V3.0-local 栈一起杀掉
# （2026-10-26 下午事故实锤：无差别强杀 11 次致双栈登录态尽失+触发账号风控 168）。
# 拉起统一走 Vdafeiyu\scripts\start-dafeiyu.ps1（幂等：redis/8081 在监听即跳过）。
$ErrorActionPreference = 'Continue'
$log = 'C:\Users\26904\.dsh\runtime\napcat-keepalive.log'
$dafeiyuDir = 'C:\Users\26904\.dsh\napcat-dafeiyu\app\napcat'
$dafeiyuQQ = '3682822273'

function Log($m) {
  try { Add-Content -Path $log -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + '  ' + $m) -Encoding UTF8 } catch {}
}

# 1.探测 3000（大肥鱼 NapCat HTTP 端口）
$online = $false
try {
  $c = New-Object System.Net.Sockets.TcpClient
  $online = $c.ConnectAsync('127.0.0.1', 3000).Wait(1500)
  $c.Close()
} catch {}

if ($online) { exit 0 }

Log '3000 不在线'

# 2.大肥鱼 NapCat 进程与 WebUI(6089,napcat-dafeiyu\config\webui.json)探测。
#   进程活着 + WebUI 可达 = 健康等扫码（快速登录失效，二维码在 WebUI 上）——不动它
$alive = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  ($_.Name -eq 'QQ.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape("-q $dafeiyuQQ")) -or
  ($_.Name -eq 'NapCatWinBootMain.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($dafeiyuDir)) -or
  ($_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($dafeiyuDir))
}
$webuiOk = $false
try {
  $c2 = New-Object System.Net.Sockets.TcpClient
  $webuiOk = $c2.ConnectAsync('127.0.0.1', 6089).Wait(1200)
  $c2.Close()
} catch {}

# 多实例告警(2026-10-26 双实例事故教训:同号多 QQ 互踢=闪窗+风控;不自动杀,提示人工收敛)
# 计数口径=QQ 主进程(-q 形态)——NapCatWinBootMain+node 是同一实例的组成,不能都算实例
$qqAlive = @($alive | Where-Object { $_.Name -eq 'QQ.exe' })
if ($qqAlive.Count -gt 1) {
  Log ("警告:大肥鱼疑似多开({0} 个 QQ 主进程,PID={1})——同号多实例互踢,建议保留持有 3000 的链并清理多余" -f $qqAlive.Count, (($qqAlive | ForEach-Object { $_.ProcessId }) -join ','))
}

if ($alive -and $webuiOk) {
  Log ('NapCat 进程在且 WebUI 6089 可达(登录态待扫码): http://127.0.0.1:6089/webui —— 本轮不动,保持扫码窗口稳定')
  exit 0
}
if ($alive -and -not $webuiOk) {
  Log 'NapCat 进程在但 WebUI 不可达(疑似卡死):清理后重拉'
}

# 3.真死/卡死:只杀大肥鱼自己的进程(QQ.exe 带 -q 3682822273,taskkill /T 连 utility 子进程;
#   NapCatWinBootMain/node 只匹配命令行含 napcat-dafeiyu 目录;写法同 revive-napcat.ps1)
foreach ($t in $alive) {
  Log ("清理 {0} PID={1}" -f $t.Name, $t.ProcessId)
  taskkill /PID $t.ProcessId /T /F 2>&1 | Out-Null
}
if (-not $alive) { Log '没有匹配到大肥鱼残留进程(可能整栈已停)' }
Start-Sleep -Seconds 3
# 4.幂等一键启动(redis 6380 → server 8081 → NapCat;Hidden 防独立控制台窗口)
& powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File 'D:\code\Git_Local\ChatBot\Vdafeiyu\scripts\start-dafeiyu.ps1'
Log ('拉起结束 exit=' + $LASTEXITCODE)
exit 0
