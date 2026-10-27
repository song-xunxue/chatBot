# 功能：V3.0-local（QQ 1145077465）全栈一键启动——Redis 6390 → server 8091 → NapCat，全程不弹任何窗口
# 日期：2026-10-26
# 变更日志：
#   2026-10-26 首版：Start-Process -WindowStyle Hidden（不经 cmd / vbs / WMI）；幂等；可选 TTS
#   2026-10-26 修：参数改成一整行、路径显式加引号（QQ 路径含空格被拆开过）
# 用法：
#   双击桌面「chatbot 启动器」，可重复执行。要带语音就加 -WithTts。
# 日志：
#   D:\code\Git_Local\ChatBot\V3.0-local\logs\launcher.out.log

param([switch]$WithTts)

$Root = 'D:\code\Git_Local\ChatBot'
. (Join-Path $Root 'scripts\launcher-common.ps1')

$LogPath  = 'D:\code\Git_Local\ChatBot\V3.0-local\logs\launcher.out.log'
$RedisExe = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-server.exe'
$RedisCli = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-cli.exe'
$RedisDir = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2'   # 本栈专用，别和大肥鱼混
$Python   = 'C:\Users\26904\anaconda3\envs\mychat\python.exe'
$ServerPy = 'D:\code\Git_Local\ChatBot\V3.0-local\server\scripts\local_dev.py'
$ServerWd = 'D:\code\Git_Local\ChatBot\V3.0-local\server'
$NapDir   = 'D:\code\Git_Local\ChatBot\.local\napcat\app\napcat'
$QQExe    = 'C:\Program Files\Tencent\QQNT\QQ.exe'
$HookDll  = Join-Path $NapDir 'NapCatWinBootHook.dll'
$QQ       = '1145077465'
$TtsScript = 'D:\code\Git_Local\ChatBot\V3.0-local\scripts\tts_local.ps1'

Write-SvcLog $LogPath 'START' '=== V3.0-local 一键启动 ==='

# 0.同栈互斥锁(2026-10-26 加:防多个启动器并发双拉 NapCat——大肥鱼侧当日双实例事故教训)
$mtx = Enter-StackLock 'Qingxun'
if (-not $mtx) {
    Write-SvcLog $LogPath 'lock' '其它启动器正在运行,本实例退出(互斥锁)'
    exit 0
}
try {

# 0.5 恢复看护任务(2026-10-27 加:关闭器 stop-qingxun.ps1 会禁用它们,启动时配套恢复)
foreach ($task in @('ChatBotLocalServer', 'ChatBotLocalWatchdog')) {
    try { Enable-ScheduledTask -TaskName $task -ErrorAction Stop | Out-Null } catch {}
}

# 1.Redis 6390
if (Test-SvcPort 6390) {
    Write-SvcLog $LogPath 'redis' '6390 已在监听，跳过'
} else {
    $line = '--port 6390 --appendonly yes --dir "{0}" --logfile "{0}\redis-6390.log"' -f $RedisDir
    $pid1 = Start-Svc -Exe $RedisExe -ArgumentLine $line -WorkDir $RedisDir `
        -OutLog (Join-Path $RedisDir 'stdout-6390.log') -ErrLog (Join-Path $RedisDir 'stderr-6390.log')
    Write-SvcLog $LogPath 'redis' "启动 redis-server PID=$pid1"
    [void](Wait-SvcPort 6390 20)
}
$pong = ''
for ($i = 0; $i -lt 15; $i++) {
    $pong = (& $RedisCli -p 6390 ping 2>$null) -join ''
    if ($pong -match 'PONG') { break }
    Start-Sleep -Seconds 1
}
Write-SvcLog $LogPath 'redis' ("PING: {0}" -f ($(if ($pong -match 'PONG') { 'PONG 就绪' } else { '未通，停止后续启动' })))
if ($pong -notmatch 'PONG') { exit 1 }

# 2.server 8091
if (Test-SvcPort 8091) {
    Write-SvcLog $LogPath 'server' '8091 已在监听，跳过'
} else {
    $line = '"{0}" --port 8091 --token 114507xX' -f $ServerPy
    $pid2 = Start-Svc -Exe $Python -ArgumentLine $line -WorkDir $ServerWd -Utf8Stdio `
        -OutLog (Join-Path $Root 'V3.0-local\logs\server.out.log') -ErrLog (Join-Path $Root 'V3.0-local\logs\server.err.log')
    Write-SvcLog $LogPath 'server' "启动 server PID=$pid2"
    [void](Wait-SvcPort 8091 30)
}

# 3.NapCat（本栈 QQ）
# 注意：6099 是 NapCat 的 WebUI 端口，QQ 没登录时它也会在听——不能当成"已就绪"。
# 只有 8091 health 里 onebot_connected=true 才算真的连上。
# 2026-10-26 修(单实例机制):onebot 未连时先看**进程**——进程在(登录中/等扫码)就不清不拉
# 只等待(旧版无条件清残留再拉,服务未起时会陷入"每轮杀 NapCat"循环);进程真死才清残留重拉。
$alreadyOnline = $false
try {
    $hv = (Invoke-WebRequest 'http://127.0.0.1:8091/health' -UseBasicParsing -TimeoutSec 3).Content
    $alreadyOnline = $hv -match '"onebot_connected":\s*true'
} catch {}
$napAlive = Get-NapcatProcs $NapDir $QQ
if ($alreadyOnline) {
    Write-SvcLog $LogPath 'napcat' 'onebot 已连接，跳过'
} elseif ($napAlive.Count -gt 0) {
    $qqMain = @($napAlive | Where-Object { $_.Name -eq 'QQ.exe' })
    $extra = $(if ($qqMain.Count -gt 1) { "(警告:检测到 $($qqMain.Count) 个 QQ 主进程,疑似多开,建议清理)" } else { '' })
    Write-SvcLog $LogPath 'napcat' ("NapCat 进程在运行但 onebot 未连(登录中/等扫码),不清不拉只等待 $extra")
} else {
    if (Test-SvcPort 6099) {
        Write-SvcLog $LogPath 'napcat' '6099 在听但 onebot 未连（残留核），先清掉'
        $stale = Get-CimInstance Win32_Process | Where-Object {
            ($_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($NapDir)) -or
            ($_.Name -eq 'QQ.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape("-q $QQ")) -or
            ($_.Name -eq 'NapCatWinBootMain.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($NapDir))
        }
        foreach ($s in $stale) { taskkill /PID $s.ProcessId /T /F 2>&1 | Out-Null }
        Start-Sleep -Seconds 3
    }
    $envs = @{
        NAPCAT_PATCH_PACKAGE = Join-Path $NapDir 'qqnt.json'
        NAPCAT_LOAD_PATH     = Join-Path $NapDir 'loadNapCat.js'
        NAPCAT_INJECT_PATH   = $HookDll
        NAPCAT_LAUNCHER_PATH = Join-Path $NapDir 'NapCatWinBootMain.exe'
        NAPCAT_MAIN_PATH     = Join-Path $NapDir 'napcat.mjs'
    }
    $line = '"{0}" "{1}" {2}' -f $QQExe, $HookDll, $QQ
    $pid3 = Start-Svc -Exe (Join-Path $NapDir 'NapCatWinBootMain.exe') -ArgumentLine $line -WorkDir $NapDir `
        -OutLog (Join-Path $Root 'V3.0-local\logs\napcat.out.log') -ErrLog (Join-Path $Root 'V3.0-local\logs\napcat.err.log') -EnvVars $envs
    Write-SvcLog $LogPath 'napcat' "启动 NapCat PID=$pid3 arg=$line"
    [void](Wait-SvcPort 6099 60)
}

# 4.可选 TTS
if ($WithTts) {
    if (Test-SvcPort 9880) {
        Write-SvcLog $LogPath 'tts' '9880 已在监听，跳过'
    } elseif (Test-Path $TtsScript) {
        $pline = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $TtsScript
        $pid4 = Start-Svc -Exe 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentLine $pline `
            -WorkDir (Split-Path $TtsScript) -OutLog (Join-Path $Root 'V3.0-local\logs\tts.out.log') -ErrLog (Join-Path $Root 'V3.0-local\logs\tts.err.log')
        Write-SvcLog $LogPath 'tts' "启动 TTS PID=$pid4"
    }
} else {
    Write-SvcLog $LogPath 'tts' '未指定 -WithTts，跳过 9880'
}

# 5.等 onebot 连上
$online = Wait-SvcHealth 'http://127.0.0.1:8091/health' '"onebot_connected":\s*true' 90
Write-SvcLog $LogPath 'done' ("onebot_connected=true：{0}" -f $online)
if (-not $online) {
    $qr = Join-Path $NapDir 'cache\qrcode.png'
    if (Test-Path $qr) {
        Copy-Item $qr 'C:\Users\26904\.dsh\runtime\清浔_qr_latest.png' -Force
        Write-SvcLog $LogPath 'napcat' '未连上，二维码已复制到 .dsh\runtime\清浔_qr_latest.png'
    }
    exit 2
}
Write-SvcLog $LogPath 'done' '=== V3.0-local 全部就绪 ==='
exit 0
}
finally {
    try { $mtx.ReleaseMutex() } catch {}
    try { $mtx.Dispose() } catch {}
}
