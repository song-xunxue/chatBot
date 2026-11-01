# 功能：V3.0-local 栈彻底关闭——禁看护任务 + 杀 NapCat/server/redis 全部进程(桌面「chatbot-关闭器」入口)
# 日期：2026-10-27
# 变更日志：
#   2026-10-27 首版:禁 ChatBotLocalServer/ChatBotLocalWatchdog(否则 2 分钟自动复活)→
#               精确杀本栈 NapCat 链(含 napcat.bat 宿主 cmd)→ 杀 8091 → 杀 6390;
#               配套 start-qingxun.ps1 会重新启用看护
#   2026-11-01 改:①QQ 主进程先优雅关闭(taskkill 无 /F 走 WM_CLOSE 登录态保留)12s 仍活
#               才强杀兜底(node/宿主等辅助进程不持登录态,仍直接强杀);②redis 改先
#               shutdown save 优雅落盘再兜底强杀(防丢未快照数据);③start 脚本已按
#               用户立规(两栈不自启动)删除 Enable 看护段,本脚本禁用行为保持不变
$Root = 'D:\code\Git_Local\ChatBot'
. (Join-Path $Root 'scripts\launcher-common.ps1')

$Log   = Join-Path $Root 'V3.0-local\logs\stop.log'
$NapDir = 'D:\code\Git_Local\ChatBot\.local\napcat\app\napcat'
$QQ     = '1145077465'
$RedisCli = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-cli.exe'

$mtx = Enter-StackLock 'Qingxun'
if (-not $mtx) { Write-SvcLog $Log 'lock' '其它本栈启动/关闭器正在运行,本实例退出'; exit 0 }
try {
    Write-SvcLog $Log 'STOP' '=== V3.0-local 彻底关闭 ==='

    # 1.禁并停看护/服务任务
    foreach ($task in @('ChatBotLocalServer', 'ChatBotLocalWatchdog')) {
        try {
            Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
            Disable-ScheduledTask -TaskName $task -ErrorAction Stop | Out-Null
            Write-SvcLog $Log 'task' "已禁用任务: $task"
        } catch { Write-SvcLog $Log 'task' "禁用 $task 失败: $($_.Exception.Message)" }
    }

    # 2.停本栈 NapCat 链(Get-NapcatProcs 口径 + napcat.bat 宿主 cmd——它不在标准口径内,WMI 拉起的宿主;
    #   cmd 匹配按"命令行同时含 napcat.bat 与本栈 QQ号",路径用解析后的绝对形式)
    # 2026-11-01 改:QQ 主进程先优雅(taskkill 无 /F=WM_CLOSE,登录态保留)12s 仍活才强杀兜底;
    #               node/宿主等辅助进程不持登录态,维持直接强杀
    $alive = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -eq 'QQ.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape("-q $QQ")) -or
        ($_.Name -in @('NapCatWinBootMain.exe', 'node.exe') -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($NapDir)) -or
        ($_.Name -eq 'cmd.exe' -and $_.CommandLine -and $_.CommandLine -match 'napcat\.bat' -and $_.CommandLine -match $QQ)
    })
    $qqProcs  = @($alive | Where-Object { $_.Name -eq 'QQ.exe' })
    $auxProcs = @($alive | Where-Object { $_.Name -ne 'QQ.exe' })
    foreach ($t in $auxProcs) {
        Write-SvcLog $Log 'kill' ("清理辅助进程 {0} PID={1}" -f $t.Name, $t.ProcessId)
        taskkill /PID $t.ProcessId /T /F 2>&1 | Out-Null
    }
    foreach ($t in $qqProcs) {
        Write-SvcLog $Log 'kill' ("优雅关闭 QQ PID={0}(等 12s,登录态保留)" -f $t.ProcessId)
        taskkill /PID $t.ProcessId 2>&1 | Out-Null
    }
    foreach ($t in $qqProcs) {
        if (Get-Process -Id $t.ProcessId -ErrorAction SilentlyContinue) {
            Write-SvcLog $Log 'kill' ("QQ 优雅未退出,强杀兜底 PID={0}" -f $t.ProcessId)
            taskkill /PID $t.ProcessId /T /F 2>&1 | Out-Null
        }
    }
    if (-not $alive) { Write-SvcLog $Log 'kill' '无 NapCat 进程' }
    Start-Sleep -Seconds 2

    # 3.停 server 8091 与 redis 6390(2026-11-01 改:redis 先 shutdown save 优雅落盘,失败再强杀兜底)
    $conns = Get-NetTCPConnection -LocalPort 8091 -State Listen -ErrorAction SilentlyContinue
    $killed = $false
    foreach ($c in $conns) {
        $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($p) {
            Write-SvcLog $Log 'kill' ("清理 server PID=" + $p.Id)
            taskkill /PID $p.Id /T /F 2>&1 | Out-Null
            $killed = $true
        }
    }
    if (-not $killed) { Write-SvcLog $Log 'kill' "server(8091) 未在监听" }

    & $RedisCli -p 6390 shutdown save 2>&1 | Out-Null
    Write-SvcLog $Log 'kill' 'redis 已发 shutdown save(优雅落盘)'
    Start-Sleep -Seconds 3
    $conns = Get-NetTCPConnection -LocalPort 6390 -State Listen -ErrorAction SilentlyContinue
    $killed = $false
    foreach ($c in $conns) {
        $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($p) {
            Write-SvcLog $Log 'kill' ("redis 未响应优雅关闭,强杀兜底 PID=" + $p.Id)
            taskkill /PID $p.Id /T /F 2>&1 | Out-Null
            $killed = $true
        }
    }
    if (-not $killed) { Write-SvcLog $Log 'kill' "redis(6390) 已优雅停止或未在监听" }

    Start-Sleep -Seconds 5
    $left = @()
    if (Test-SvcPort 8091) { $left += '8091' }
    if (Test-SvcPort 6390) { $left += '6390' }
    if ($alive.Count) { $left += 'NapCat' }
    if ($left.Count) {
        Write-SvcLog $Log 'done' ("关闭后仍有残留: " + ($left -join ','))
    } else {
        Write-SvcLog $Log 'done' '=== V3.0-local 已全部停止(看护已禁用,双击启动器恢复) ==='
    }
} finally {
    try { $mtx.ReleaseMutex() } catch {}
    try { $mtx.Dispose() } catch {}
}
