# 功能：V3.0-local 栈彻底关闭——禁看护任务 + 杀 NapCat/server/redis 全部进程(桌面「chatbot-关闭器」入口)
# 日期：2026-10-27
# 变更日志：
#   2026-10-27 首版:禁 ChatBotLocalServer/ChatBotLocalWatchdog(否则 2 分钟自动复活)→
#               精确杀本栈 NapCat 链(含 napcat.bat 宿主 cmd)→ 杀 8091 → 杀 6390;
#               配套 start-qingxun.ps1 会重新启用看护
$Root = 'D:\code\Git_Local\ChatBot'
. (Join-Path $Root 'scripts\launcher-common.ps1')

$Log   = Join-Path $Root 'V3.0-local\logs\stop.log'
$NapDir = 'D:\code\Git_Local\ChatBot\.local\napcat\app\napcat'
$QQ     = '1145077465'

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

    # 2.杀本栈 NapCat 链(Get-NapcatProcs 口径 + napcat.bat 宿主 cmd——它不在标准口径内,WMI 拉起的宿主;
    #   cmd 匹配按"命令行同时含 napcat.bat 与本栈 QQ 号",路径用解析后的绝对形式)
    $alive = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -eq 'QQ.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape("-q $QQ")) -or
        ($_.Name -in @('NapCatWinBootMain.exe', 'node.exe') -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($NapDir)) -or
        ($_.Name -eq 'cmd.exe' -and $_.CommandLine -and $_.CommandLine -match 'napcat\.bat' -and $_.CommandLine -match $QQ)
    })
    foreach ($t in $alive) {
        Write-SvcLog $Log 'kill' ("清理 {0} PID={1}" -f $t.Name, $t.ProcessId)
        taskkill /PID $t.ProcessId /T /F 2>&1 | Out-Null
    }
    if (-not $alive) { Write-SvcLog $Log 'kill' '无 NapCat 进程' }

    # 3.按端口杀 server 8091 与 redis 6390
    foreach ($pair in @(@(8091, 'server'), @(6390, 'redis'))) {
        $port, $tag = $pair
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        $killed = $false
        foreach ($c in $conns) {
            $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            if ($p) {
                Write-SvcLog $Log 'kill' ("清理 $tag PID=" + $p.Id)
                taskkill /PID $p.Id /T /F 2>&1 | Out-Null
                $killed = $true
            }
        }
        if (-not $killed) { Write-SvcLog $Log 'kill' "$tag($port) 未在监听" }
    }

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
