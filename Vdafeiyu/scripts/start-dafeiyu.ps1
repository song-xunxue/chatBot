# 功能：大肥鱼（QQ 3682822273）全栈一键启动——Redis 6380 → server 8081 → NapCat，全程不弹任何窗口
# 日期：2026-10-26
# 变更日志：
#   2026-10-26 首版：Start-Process -WindowStyle Hidden（不经 cmd / vbs / WMI）；幂等；防 fakeredis
#   2026-10-26 修：参数改成一整行、路径显式加引号（QQ 路径含空格被拆开过）
# 用法：
#   双击桌面「大肥鱼 启动器」，可重复执行。
# 日志：
#   D:\code\Git_Local\ChatBot\Vdafeiyu\logs\launcher.out.log

param()

$Root = 'D:\code\Git_Local\ChatBot'
. (Join-Path $Root 'scripts\launcher-common.ps1')

$LogPath  = 'D:\code\Git_Local\ChatBot\Vdafeiyu\logs\launcher.out.log'
$RedisExe = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-server.exe'
$RedisCli = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-cli.exe'
$RedisDir = 'D:\code\Git_Local\ChatBot\Vdafeiyu\.data\redis'      # 本体自己的数据目录，绝不能指向 redis8 安装目录
$Python   = 'C:\Users\26904\anaconda3\envs\mychat\python.exe'
$ServerPy = 'D:\code\Git_Local\ChatBot\Vdafeiyu\server\scripts\local_dev.py'
$ServerWd = 'D:\code\Git_Local\ChatBot\Vdafeiyu\server'
$NapDir   = 'C:\Users\26904\.dsh\napcat-dafeiyu\app\napcat'
$QQExe    = 'C:\Program Files\Tencent\QQNT\QQ.exe'
$HookDll  = Join-Path $NapDir 'NapCatWinBootHook.dll'
$QQ       = '3682822273'

Write-SvcLog $LogPath 'START' '=== 大肥鱼 一键启动 ==='

# 0.同栈互斥锁(2026-10-26 加:防多个启动器并发双拉 NapCat——当日双实例事故成因)
$mtx = Enter-StackLock 'Dafeiyu'
if (-not $mtx) {
    Write-SvcLog $LogPath 'lock' '其它大肥鱼启动器正在运行,本实例退出(互斥锁)'
    exit 0
}
try {

# 0.5 恢复看护任务(2026-10-27 加:关闭器 stop-dafeiyu.ps1 会禁用它们,启动时配套恢复)
foreach ($task in @('DafeiyuStackWatchdog', 'NapCat-Watchdog')) {
    try { Enable-ScheduledTask -TaskName $task -ErrorAction Stop | Out-Null } catch {}
}

# 1.Redis 6380
if (Test-SvcPort 6380) {
    Write-SvcLog $LogPath 'redis' '6380 已在监听，跳过'
} else {
    $line = '--port 6380 --appendonly yes --dir "{0}" --logfile "{0}\redis.log"' -f $RedisDir
    $pid1 = Start-Svc -Exe $RedisExe -ArgumentLine $line -WorkDir $RedisDir `
        -OutLog (Join-Path $RedisDir 'stdout.log') -ErrLog (Join-Path $RedisDir 'stderr.log')
    Write-SvcLog $LogPath 'redis' "启动 redis-server PID=$pid1"
    [void](Wait-SvcPort 6380 20)
}

# server 必须在 Redis 真 PING 通之后才起，否则 local_dev 会静默退化成 fakeredis 丢数据
$pong = ''
for ($i = 0; $i -lt 15; $i++) {
    $pong = (& $RedisCli -p 6380 ping 2>$null) -join ''
    if ($pong -match 'PONG') { break }
    Start-Sleep -Seconds 1
}
Write-SvcLog $LogPath 'redis' ("PING: {0}" -f ($(if ($pong -match 'PONG') { 'PONG 就绪' } else { '未通，停止后续启动' })))
if ($pong -notmatch 'PONG') { exit 1 }

# 2.server 8081
if (Test-SvcPort 8081) {
    Write-SvcLog $LogPath 'server' '8081 已在监听，跳过'
} else {
    $line = '"{0}" --port 8081 --token 114507xX --no-seed' -f $ServerPy
    $pid2 = Start-Svc -Exe $Python -ArgumentLine $line -WorkDir $ServerWd -Utf8Stdio `
        -OutLog (Join-Path $Root 'Vdafeiyu\logs\server.out.log') -ErrLog (Join-Path $Root 'Vdafeiyu\logs\server.err.log')
    Write-SvcLog $LogPath 'server' "启动 server PID=$pid2"
    [void](Wait-SvcPort 8081 30)
}

# 3.NapCat（大肥鱼 QQ）——单实例判据=进程存在(2026-10-26 修:3000 登录后才开,
#   等扫码期间 3000 不在≠没在跑,只看端口会在等扫码时把第二个实例拉起来,同号双 QQ 互踢)
$alive = Get-NapcatProcs $NapDir $QQ
if ($alive.Count -gt 0) {
    $qqMain = @($alive | Where-Object { $_.Name -eq 'QQ.exe' })
    $extra = $(if ($qqMain.Count -gt 1) { "(警告:检测到 $($qqMain.Count) 个 QQ 主进程,疑似多开,建议清理)" } else { '' })
    Write-SvcLog $LogPath 'napcat' ("NapCat 进程已在运行(PID=" + ($alive | Select-Object -First 1).ProcessId + "),跳过 $extra")
} elseif (Test-SvcPort 3000) {
    Write-SvcLog $LogPath 'napcat' '3000 已在监听，跳过'
} else {
    $envs = @{
        NAPCAT_PATCH_PACKAGE = Join-Path $NapDir 'qqnt.json'
        NAPCAT_LOAD_PATH     = Join-Path $NapDir 'loadNapCat.js'
        NAPCAT_INJECT_PATH   = $HookDll
        NAPCAT_LAUNCHER_PATH = Join-Path $NapDir 'NapCatWinBootMain.exe'
        NAPCAT_MAIN_PATH     = Join-Path $NapDir 'napcat.mjs'
    }
    $line = '"{0}" "{1}" {2}' -f $QQExe, $HookDll, $QQ
    $pid3 = Start-Svc -Exe (Join-Path $NapDir 'NapCatWinBootMain.exe') -ArgumentLine $line -WorkDir $NapDir `
        -OutLog (Join-Path $Root 'Vdafeiyu\logs\napcat.out.log') -ErrLog (Join-Path $Root 'Vdafeiyu\logs\napcat.err.log') -EnvVars $envs
    Write-SvcLog $LogPath 'napcat' "启动 NapCat PID=$pid3 arg=$line"
    [void](Wait-SvcPort 3000 60)
}

# 4.等 onebot 连上
$online = Wait-SvcHealth 'http://127.0.0.1:8081/health' '"onebot_connected":\s*true' 90
Write-SvcLog $LogPath 'done' ("onebot_connected=true：{0}" -f $online)
if (-not $online) {
    $qr = Join-Path $NapDir 'cache\qrcode.png'
    if (Test-Path $qr) {
        Copy-Item $qr 'C:\Users\26904\.dsh\runtime\大肥鱼_qr_latest.png' -Force
        Write-SvcLog $LogPath 'napcat' '未连上，二维码已复制到 .dsh\runtime\大肥鱼_qr_latest.png'
    }
    exit 2
}
Write-SvcLog $LogPath 'done' '=== 大肥鱼 全部就绪 ==='
exit 0
}
finally {
    try { $mtx.ReleaseMutex() } catch {}
    try { $mtx.Dispose() } catch {}
}
