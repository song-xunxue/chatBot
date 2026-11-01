# 功能:NapCat WS 断线自愈脚本(server onebot.watch 的 napcat_heal_script 调用)
# 流程:优雅关闭本栈 QQ 链(taskkill 无 /F 走 WM_CLOSE,登录态保留) -> 绝不强杀守登录态铁律 ->
#       幂等启动器拉起(快速登录) -> 等待 onebot_connected
# 日期:2026-11-01
# 变更日志:
#   2026-11-01 首版:watch.py 断线自愈配套。背景=大肥鱼 10-27 17:52 WS 断线静默 5 天
#               (QQ 进程活而 NapCat WS 客户端死,外部看护门控误判"待扫码"不动作)。
# 退出码:0=自愈完成且 onebot 已重连 / 2=QQ 优雅关闭失败(不强杀) / 3=启动器失败或锁忙 / 4=跑完但未连上
$Root = 'D:\code\Git_Local\ChatBot'
$Stack    = 'Qingxun'
$NapDir   = 'D:\code\Git_Local\ChatBot\.local\napcat\app\napcat'
$QQ       = '1145077465'
$Port     = 8091
$StartScript = 'D:\code\Git_Local\ChatBot\V3.0-local\scripts\start-qingxun.ps1'
$Log = Join-Path $Root ('logs\heal-' + $Stack + '.log')
. (Join-Path $Root 'scripts\launcher-common.ps1')

$mtx = Enter-StackLock $Stack
if (-not $mtx) { Write-SvcLog $Log 'lock' '其它启动/关闭器正在运行,自愈退出'; exit 3 }
try {
    Write-SvcLog $Log 'HEAL' ('=== ' + $Stack + ' 断线自愈开始 ===')
    # 1.找本栈 QQ 主进程(精确匹配 -q 号,绝不误伤另一栈)
    $procs = Get-NapcatProcs $NapDir $QQ
    $qqMain = @($procs | Where-Object { $_.Name -eq 'QQ.exe' } | Select-Object -First 1)
    if (-not $qqMain) {
        Write-SvcLog $Log 'heal' 'QQ 主进程已不在(崩溃/被外部关闭),跳过优雅关闭直接拉起'
    } else {
        # 2.优雅关闭(taskkill 无 /F = WM_CLOSE,QQNT 正常退出登出,登录态保留)
        Write-SvcLog $Log 'heal' ('优雅关闭 QQ PID=' + $qqMain.ProcessId)
        taskkill /PID $qqMain.ProcessId 2>&1 | Out-Null
        $gone = $false
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 1
            if (-not (Get-Process -Id $qqMain.ProcessId -ErrorAction SilentlyContinue)) { $gone = $true; break }
        }
        if (-not $gone) {
            # 3.铁律:绝不强杀 QQ(丢登录态要重扫码)——优雅失败放弃本轮,等退避重试或人工
            Write-SvcLog $Log 'heal' '优雅关闭 15s 未退出,按铁律不强杀,放弃本轮自愈'
            exit 2
        }
        Write-SvcLog $Log 'heal' 'QQ 已退出,清理 NapCat 链残留(node/NapCatWinBootMain 优雅杀,不阻塞)'
        foreach ($s in (Get-NapcatProcs $NapDir $QQ)) { taskkill /PID $s.ProcessId 2>&1 | Out-Null }
        Start-Sleep -Seconds 3
    }
    # 4.释放互斥锁后再调启动器(启动器自己会拿同名锁;同进程树嵌套拿锁=死锁)
    try { $mtx.ReleaseMutex() } catch {}
    try { $mtx.Dispose() } catch {}
    $mtx = $null
    # 5.幂等启动器(redis/server 在跑自动跳过,NapCat 进程没了重新拉起+快速登录)
    Write-SvcLog $Log 'heal' ('调用启动器: ' + $StartScript)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StartScript
    $rc = $LASTEXITCODE
    Write-SvcLog $Log 'heal' ('启动器退出码: ' + $rc)
    if ($rc -ne 0) { exit 3 }
    # 6.最终自检:onebot_connected
    $ok = Wait-SvcHealth ('http://127.0.0.1:' + $Port + '/health') '"onebot_connected":\s*true' 30
    if ($ok) { Write-SvcLog $Log 'done' '=== 自愈完成:onebot 已重连 ==='; exit 0 }
    Write-SvcLog $Log 'done' '=== 自愈脚本跑完但 onebot 未连上(可能等扫码),交给下轮探测 ==='
    exit 4
} finally {
    if ($mtx) {
        try { $mtx.ReleaseMutex() } catch {}
        try { $mtx.Dispose() } catch {}
    }
}
