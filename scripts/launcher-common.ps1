# 功能：两个启动器共用的底层函数——不弹任何窗口地拉起服务、探活、写日志
# 作者：李文煜
# 日期：2026-10-26
# 变更日志：
#   2026-10-26 首版：Start-Svc 用 Start-Process -WindowStyle Hidden，全程不经过 cmd / vbs / WMI
#   2026-10-26 修：参数改成「一整行字符串」——数组形式不会自动给含空格的路径加引号，
#               曾把 QQ 路径拆成 "C:\Program" + "Files\Tencent\..." 导致 NapCat 起不来
#   2026-10-27 加：Move-SvcLogArchive 启动前日志轮转（Start-Process 重定向每次启动截断覆盖，
#               不轮转则历史一次重启即丢）；Start-Svc 增 -Utf8Stdio（python stdout 重定向
#               默认 GBK 致中文乱码，PYTHONUTF8=1 一刀切）——两栈共用本文件，双栈同步生效
# 说明：
#   · 这台机器 Win11 已移除 VBScript 引擎，任何 .vbs 都会报「没有 VBS 脚本引擎」，别用
#   · 也不要 `cmd /c` 包一层：会留下可见的控制台窗口
#   · Start-Process -WindowStyle Hidden 对控制台程序等价于 SW_HIDE，不会闪窗

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

function Write-SvcLog([string]$LogPath, [string]$Tag, [string]$Msg) {
    $line = '{0}  [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Tag, $Msg
    Write-Host $line
    try {
        $dir = Split-Path -Parent $LogPath
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Add-Content -Path $LogPath -Value $line -Encoding UTF8
    } catch {}
}

function Test-SvcPort([int]$Port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(700)
        $connected = ($ok -and $c.Connected)
        $c.Close()
        return $connected
    } catch { return $false }
}

function Move-SvcLogArchive([string]$Path, [int]$Keep = 8) {
    # 启动前日志轮转(2026-10-27 加,low 项修复):Start-Process -RedirectStandard* 每次启动都
    # 截断覆盖目标文件,不轮转则历史日志一次重启就丢(2026-10-26 晚安事故现场因此取证困难)。
    # 现文件非空 → 改名 <去.log后缀>.<yyyyMMdd-HHmmss>.log 存档;同名时间戳冲突加 -N 后缀;
    # 每个基名只保留最新 $Keep 份(文件名含时间戳,字典序=时间序),更旧的删。
    try {
        if (-not $Path -or -not (Test-Path $Path)) { return }
        if ((Get-Item $Path -ErrorAction SilentlyContinue).Length -le 0) { return }
        $dir = Split-Path -Parent $Path
        $base = [IO.Path]::GetFileNameWithoutExtension($Path)
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $dst = Join-Path $dir ('{0}.{1}.log' -f $base, $stamp)
        $n = 2
        while (Test-Path $dst) {
            $dst = Join-Path $dir ('{0}.{1}-{2}.log' -f $base, $stamp, $n)
            $n++
        }
        Move-Item -Path $Path -Destination $dst -Force
        $olds = Get-ChildItem -Path $dir -Filter "$base.*.log" -File -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -Skip $Keep
        foreach ($f in $olds) { Remove-Item $f.FullName -Force -ErrorAction SilentlyContinue }
    } catch {}
}

function Start-Svc {
    # 无窗口启动一个进程；返回 PID（失败 0）
    # $ArgumentLine 必须是**一整行**参数串，含空格的路径自己带引号。
    # -Utf8Stdio:python 进程 stdout/stderr 重定向到文件时默认走本地 ANSI(GBK)编码,
    #   中文日志必乱码;置 PYTHONUTF8=1 + PYTHONIOENCODING=utf-8 让该进程全线 UTF-8。
    #   传了本开关仍可用 EnvVars 覆盖(调用方显式值优先)。
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string]$ArgumentLine = '',
        [Parameter(Mandatory = $true)][string]$WorkDir,
        [Parameter(Mandatory = $true)][string]$OutLog,
        [Parameter(Mandatory = $true)][string]$ErrLog,
        [hashtable]$EnvVars = @{},
        [switch]$Utf8Stdio
    )
    if ($Utf8Stdio) {
        $merged = @{ PYTHONUTF8 = '1'; PYTHONIOENCODING = 'utf-8' }
        foreach ($k in $EnvVars.Keys) { $merged[$k] = $EnvVars[$k] }
        $EnvVars = $merged
    }
    Move-SvcLogArchive $OutLog
    Move-SvcLogArchive $ErrLog
    $saved = @{}
    foreach ($k in $EnvVars.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$EnvVars[$k], 'Process')
    }
    try {
        $p = Start-Process -FilePath $Exe -ArgumentList $ArgumentLine -WorkingDirectory $WorkDir `
            -WindowStyle Hidden -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -PassThru -ErrorAction Stop
        return $p.Id
    } catch {
        return 0
    } finally {
        foreach ($k in $saved.Keys) {
            [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process')
        }
    }
}

function Wait-SvcPort([int]$Port, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-SvcPort $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return (Test-SvcPort $Port)
}

function Wait-SvcHealth([string]$Url, [string]$Pattern, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $text = (Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 3).Content
            if ($text -match $Pattern) { return $true }
        } catch {}
        Start-Sleep -Seconds 2
    }
    return $false
}

# 2026-10-26 加:NapCat 单实例机制公共件(当日大肥鱼双实例事故——3000 登录后才开,
# 等扫码期间两个启动器并发各拉一个,同号双 QQ 互踢闪窗)

function Get-NapcatProcs([string]$DirLike, [string]$QQ) {
    # 该栈 NapCat 相关进程(精确匹配:QQ.exe 带 -q <QQ号>;NapCatWinBootMain/node 命令行含目录)。
    # 单实例判据用它而不是 3000/6099 端口——HTTP 端口登录后才开,WebUI 端口与登录无关,
    # 都不能完整表达"NapCat 进程在不在";进程在(哪怕在等扫码)就不该再拉
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -eq 'QQ.exe' -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape("-q $QQ")) -or
        ($_.Name -in @('NapCatWinBootMain.exe', 'node.exe') -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($DirLike))
    })
}

function Enter-StackLock([string]$Stack) {
    # 同栈启动器互斥锁(防多入口并发双拉):拿到返回 Mutex 对象(用完须 Release+Dispose),
    # 拿不到(别的启动器正在跑)返回 $null,调用方应直接退出。
    # AbandonedMutexException(持锁进程已死,锁被弃)须视为拿到——否则上次进程异常退出后永远死锁
    $mtx = New-Object System.Threading.Mutex($false, "Global\ChatBot_${Stack}Start")
    $got = $false
    try { $got = $mtx.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $got = $true }
    catch { $got = $false }
    if ($got) { return $mtx }
    try { $mtx.Dispose() } catch {}
    return $null
}
