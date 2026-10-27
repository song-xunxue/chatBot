# 功能：大肥鱼栈彻底关闭——禁看护任务 + 杀 NapCat/server/redis 全部进程(桌面「大肥鱼-关闭器」入口)
# 日期：2026-10-27
# 变更日志：
#   2026-10-27 首版:禁 DafeiyuStackWatchdog/NapCat-Watchdog(否则 2-5 分钟自动复活)→
#               精确杀大肥鱼 NapCat 链 → 杀 8081 → 杀 6380;配套 start-dafeiyu.ps1 会重新启用看护
# 注意：6380 若是早前在终端前台跑的那只 redis,杀掉后窗口留空(已隐藏无感);下次启动由
#       watch-stack 无窗拉起,顺带完成迁移
$Root = 'D:\code\Git_Local\ChatBot'
. (Join-Path $Root 'scripts\launcher-common.ps1')

$Log   = Join-Path $Root 'Vdafeiyu\logs\stop.log'
$NapDir = 'C:\Users\26904\.dsh\napcat-dafeiyu\app\napcat'
$QQ     = '3682822273'

$mtx = Enter-StackLock 'Dafeiyu'
if (-not $mtx) { Write-SvcLog $Log 'lock' '其它大肥鱼启动/关闭器正在运行,本实例退出'; exit 0 }
try {
    Write-SvcLog $Log 'STOP' '=== 大肥鱼 彻底关闭 ==='

    # 1.禁并停看护任务(关闭的核心:不禁用的话 2-5 分钟内全部复活)
    foreach ($task in @('DafeiyuStackWatchdog', 'NapCat-Watchdog')) {
        try {
            Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
            Disable-ScheduledTask -TaskName $task -ErrorAction Stop | Out-Null
            Write-SvcLog $Log 'task' "已禁用看护任务: $task"
        } catch { Write-SvcLog $Log 'task' "禁用 $task 失败(可能不存在): $($_.Exception.Message)" }
    }

    # 2.杀大肥鱼 NapCat 链(精确匹配:QQ 带 -q 号 / NapCatWinBootMain·node 含目录;taskkill /T 连子进程)
    $alive = Get-NapcatProcs $NapDir $QQ
    foreach ($t in $alive) {
        Write-SvcLog $Log 'kill' ("清理 {0} PID={1}" -f $t.Name, $t.ProcessId)
        taskkill /PID $t.ProcessId /T /F 2>&1 | Out-Null
    }
    if (-not $alive) { Write-SvcLog $Log 'kill' '无 NapCat 进程' }

    # 3.按端口杀 server 8081 与 redis 6380(监听者即目标,不误伤)
    foreach ($pair in @(@(8081, 'server'), @(6380, 'redis'))) {
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
    if (Test-SvcPort 8081) { $left += '8081' }
    if (Test-SvcPort 6380) { $left += '6380' }
    if ((Get-NapcatProcs $NapDir $QQ).Count) { $left += 'NapCat' }
    if ($left.Count) {
        Write-SvcLog $Log 'done' ("关闭后仍有残留: " + ($left -join ','))
    } else {
        Write-SvcLog $Log 'done' '=== 大肥鱼 已全部停止(看护已禁用,双击启动器恢复) ==='
    }
} finally {
    try { $mtx.ReleaseMutex() } catch {}
    try { $mtx.Dispose() } catch {}
}
