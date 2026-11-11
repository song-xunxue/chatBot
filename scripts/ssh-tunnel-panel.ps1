# 功能:面板公网访问 SSH 反向隧道守护(手机移动数据访问家里面板)
# 架构:本机(全部服务) --SSH隧道--> 云端43.140.219.99 nginx(只转发) --> 手机
# 链路:手机 -> 云端8091/8081(nginx,安全组已放行8091;8081需控制台补) -> 云端127.0.0.1:18091/18081(隧道)
#       -> 家里8091(6390 面板)/8081(大肥鱼面板)
# 行为:循环守护,SSH 断线 5 秒后自动重连;云端只转发不跑任何 bot 服务
# 用法:powershell -File scripts\ssh-tunnel-panel.ps1  (常驻;手动跑或挂计划任务均可)
# 日志:D:\code\Git_Local\ChatBot\logs\ssh-tunnel.log
# 日期:2026-11-03
$Key = 'D:\code\Git_Local\ChatBot\.claude\ubuntu.pem'
$Remote = 'ubuntu@43.140.219.99'
$Log = 'D:\code\Git_Local\ChatBot\logs\ssh-tunnel.log'

function Write-TLog([string]$Msg) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Msg
    Write-Host $line
    try { Add-Content -Path $Log -Value $line -Encoding UTF8 } catch {}
}

Write-TLog '=== 面板公网隧道守护启动 ==='
while ($true) {
    Write-TLog '建立 SSH 反向隧道(18091<-8091, 18081<-8081)...'
    & ssh -i $Key -N `
        -R '127.0.0.1:18091:127.0.0.1:8091' `
        -R '127.0.0.1:18081:127.0.0.1:8081' `
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
        -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new `
        -o ConnectTimeout=15 `
        $Remote 2>&1 | Out-Null
    $code = $LASTEXITCODE
    Write-TLog ("SSH 退出 code={0},5 秒后重连" -f $code)
    Start-Sleep -Seconds 5
}
