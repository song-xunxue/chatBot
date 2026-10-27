# 功能：大肥鱼 NapCat(QQ 3682822273)独立无窗启动——单实例判据=进程存在(等扫码也算在跑)
# 日期：2026-10-26
# 变更日志：
#   2026-10-26 首版：从 start-dafeiyu.ps1 抽出 NapCat 分支(桌面「ChatBot启动器\大肥鱼-NapCat」入口)
#   2026-10-26 修：单实例判据由 3000 端口改为**进程存在**——3000 登录后才开,等扫码期间
#               重复执行会双开(当日双实例事故成因);并加同栈互斥锁防多启动器并发双拉
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File start-napcat.ps1
# 日志：Vdafeiyu\logs\napcat.out.log / 结果落 Vdafeiyu\logs\stack-watchdog.log

$Root = 'D:\code\Git_Local\ChatBot'
. (Join-Path $Root 'scripts\launcher-common.ps1')

$Log    = Join-Path $Root 'Vdafeiyu\logs\stack-watchdog.log'
$NapDir = 'C:\Users\26904\.dsh\napcat-dafeiyu\app\napcat'
$QQExe  = 'C:\Program Files\Tencent\QQNT\QQ.exe'
$HookDll = Join-Path $NapDir 'NapCatWinBootHook.dll'
$QQ     = '3682822273'

# 0.同栈互斥锁(其它大肥鱼启动器正在跑就退出,防并发双拉)
$mtx = Enter-StackLock 'Dafeiyu'
if (-not $mtx) {
    Write-SvcLog $Log 'napcat' '其它大肥鱼启动器正在运行,本实例退出(互斥锁)'
    exit 0
}
try {
    # 1.单实例判据:NapCat 进程存在即跳过——含"等扫码/登录中"状态(3000 未开不代表没在跑)
    $alive = Get-NapcatProcs $NapDir $QQ
    if ($alive.Count -gt 0) {
        $qqMain = @($alive | Where-Object { $_.Name -eq 'QQ.exe' })
        $extra = $(if ($qqMain.Count -gt 1) { "(警告:检测到 $($qqMain.Count) 个 QQ 主进程,疑似多开)" } else { '' })
        Write-SvcLog $Log 'napcat' ("NapCat 进程已在运行(PID=" + ($alive | Select-Object -First 1).ProcessId + "),跳过 $extra")
        exit 0
    }

    # 2.无进程才拉起(Start-Svc 无窗;envs 为 NapCat 引导所需路径)
    $envs = @{
        NAPCAT_PATCH_PACKAGE = Join-Path $NapDir 'qqnt.json'
        NAPCAT_LOAD_PATH     = Join-Path $NapDir 'loadNapCat.js'
        NAPCAT_INJECT_PATH   = $HookDll
        NAPCAT_LAUNCHER_PATH = Join-Path $NapDir 'NapCatWinBootMain.exe'
        NAPCAT_MAIN_PATH     = Join-Path $NapDir 'napcat.mjs'
    }
    $line = '"{0}" "{1}" {2}' -f $QQExe, $HookDll, $QQ
    $napPid = Start-Svc -Exe (Join-Path $NapDir 'NapCatWinBootMain.exe') -ArgumentLine $line -WorkDir $NapDir `
        -OutLog (Join-Path $Root 'Vdafeiyu\logs\napcat.out.log') -ErrLog (Join-Path $Root 'Vdafeiyu\logs\napcat.err.log') -EnvVars $envs
    Write-SvcLog $Log 'napcat' ("无 NapCat 进程,已拉起 PID={0} arg={1}" -f $napPid, $line)

    # 3.等 3000 监听(最多 60s);未连上多为登录态失效,提示 WebUI 扫码地址
    $ok = Wait-SvcPort 3000 60
    if (-not $ok) {
        $qr = Join-Path $NapDir 'cache\qrcode.png'
        if (Test-Path $qr) { Copy-Item $qr 'C:\Users\26904\.dsh\runtime\大肥鱼_qr_latest.png' -Force }
        Write-SvcLog $Log 'napcat' '60s 未监听:可能登录态失效,浏览器开 http://127.0.0.1:6089/webui 扫码(token 见 napcat-dafeiyu\config\webui.json)'
        exit 2
    }
    Write-SvcLog $Log 'napcat' '已就绪(3000 监听)'
    exit 0
}
finally {
    try { $mtx.ReleaseMutex() } catch {}
    try { $mtx.Dispose() } catch {}
}
