# 功能：两个启动器共用的底层函数——不弹任何窗口地拉起服务、探活、写日志
# 作者：李文煜
# 日期：2026-10-26
# 变更日志：
#   2026-10-26 首版：Start-Svc 用 Start-Process -WindowStyle Hidden，全程不经过 cmd / vbs / WMI
#   2026-10-26 修：参数改成「一整行字符串」——数组形式不会自动给含空格的路径加引号，
#               曾把 QQ 路径拆成 "C:\Program" + "Files\Tencent\..." 导致 NapCat 起不来
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

function Start-Svc {
    # 无窗口启动一个进程；返回 PID（失败 0）
    # $ArgumentLine 必须是**一整行**参数串，含空格的路径自己带引号。
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string]$ArgumentLine = '',
        [Parameter(Mandatory = $true)][string]$WorkDir,
        [Parameter(Mandatory = $true)][string]$OutLog,
        [Parameter(Mandatory = $true)][string]$ErrLog,
        [hashtable]$EnvVars = @{}
    )
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
