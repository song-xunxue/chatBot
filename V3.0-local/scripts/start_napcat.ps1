# start_napcat.ps1 — 无窗口启动本地 NapCat（本栈 QQ）
# 用法: powershell -NoProfile -ExecutionPolicy Bypass -File start_napcat.ps1
# 说明: 用 WMI Create 启动，完全脱离父进程、不生成可见控制台窗口；
#       单实例判据=6099 监听 或 NapCat 进程存在(2026-10-26 加进程判据+互斥锁,
#       防多入口并发双拉——大肥鱼侧当日双实例事故教训)；日志追加到 runtime\napcat.out.log。
#       注意: 不要强杀 QQ/NapCat 进程（会丢登录态，需要重新扫码）。

$ErrorActionPreference = 'SilentlyContinue'

# 公共件(Get-NapcatProcs 进程判据 / Enter-StackLock 互斥锁)
. (Join-Path 'D:\code\Git_Local\ChatBot' 'scripts\launcher-common.ps1')

$app  = 'D:\code\Git_Local\ChatBot\.local\napcat\app'
$log  = 'C:\Users\26904\.dsh\runtime\napcat.out.log'
$uin  = '1145077465'

# 同栈互斥锁(其它启动器正在跑就退出)
$mtx = Enter-StackLock 'Qingxun'
if (-not $mtx) { Write-Host "[napcat] 其它启动器正在运行,退出(互斥锁)"; exit 0 }

# 已在运行就不重复拉起(6099 监听 或 进程存在——进程在哪怕在等扫码也不算停)
$procs = Get-NapcatProcs (Join-Path $app 'napcat') $uin
if ((Get-NetTCPConnection -LocalPort 6099 -State Listen -ErrorAction SilentlyContinue) -or $procs.Count -gt 0) {
  Write-Host "[napcat] 已在运行（6099 监听或进程存在），跳过"
  try { $mtx.ReleaseMutex() } catch {}
  exit 0
}

$cmd = "cmd.exe /c `"`"$app\napcat.bat`" -q $uin >> `"$log`" 2>&1`""
# 无窗 WMI 启动:ShowWindow=0(2026-10-26 修——不带 startupinfo 的 WMI Create 会弹出可见
# 控制台窗口,17:29 看护拉起的 napcat.bat 宿主 cmd 最小化残留即此坑)
$su = ([wmiclass]'Win32_ProcessStartup').CreateInstance()
$su.ShowWindow = 0
$r = ([wmiclass]'Win32_Process').Create($cmd, $null, $su)
Write-Host "[napcat] 启动 ret=$($r.ReturnValue) pid=$($r.ProcessId)"

# 最多等 90 秒，确认 6099 起来
for ($i = 1; $i -le 30; $i++) {
  Start-Sleep -Seconds 3
  if (Get-NetTCPConnection -LocalPort 6099 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "[napcat] 已就绪（等待 $($i*3)s）"
    exit 0
  }
}
Write-Host "[napcat] 90 秒内未监听，看 $log"
exit 1
