# 功能：大肥鱼栈看护——Redis 6380 / 服务 8081 缺哪个补哪个（NapCat 3000 归计划任务
#       NapCat-Watchdog 管，职责不重叠不打架）
# 日期：2026-10-26
# 变更日志：
#   2026-10-26 首版：仿 V3.0-local watch_stack.ps1 模式；redis 必须 PING 通才拉服务（防整进程退
#               FAKEREDIS 丢数据）；复用 scripts/launcher-common.ps1 的无窗启动（不经 cmd/vbs）
# 由计划任务 DafeiyuStackWatchdog 每 2 分钟调用，全程无窗

$Root = 'D:\code\Git_Local\ChatBot'
. (Join-Path $Root 'scripts\launcher-common.ps1')

$Log      = Join-Path $Root 'Vdafeiyu\logs\stack-watchdog.log'
$RedisExe = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-server.exe'
$RedisCli = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-cli.exe'
$RedisDir = Join-Path $Root 'Vdafeiyu\.data\redis'
$Python   = 'C:\Users\26904\anaconda3\envs\mychat\python.exe'
$ServerPy = Join-Path $Root 'Vdafeiyu\server\scripts\local_dev.py'
$ServerWd = Join-Path $Root 'Vdafeiyu\server'

# 1) Redis 6380（数据目录固定在 Vdafeiyu\.data\redis，绝不指向 redis8 安装目录）
if (-not (Test-SvcPort 6380)) {
    $line = '--port 6380 --appendonly yes --dir "{0}"' -f $RedisDir
    $redisPid = Start-Svc -Exe $RedisExe -ArgumentLine $line -WorkDir $RedisDir `
        -OutLog (Join-Path $RedisDir 'stdout.log') -ErrLog (Join-Path $RedisDir 'stderr.log')
    Write-SvcLog $Log 'redis' ("6380 不在监听,已拉起 PID={0}" -f $redisPid)
    [void](Wait-SvcPort 6380 15)
}

# 2) 服务 8081：redis PING 通才拉（铁律：服务先于 redis 启动会整进程退 FAKEREDIS 且不回切）
if (-not (Test-SvcPort 8081)) {
    $pong = (& $RedisCli -p 6380 ping 2>$null) -join ''
    if ($pong -notmatch 'PONG') {
        Write-SvcLog $Log 'server' 'redis 未 PING 通,本轮跳过服务拉起(下轮重试)'
        exit 0
    }
    $line = '"{0}" --port 8081 --token 114507xX --no-seed' -f $ServerPy
    $svcPid = Start-Svc -Exe $Python -ArgumentLine $line -WorkDir $ServerWd -Utf8Stdio `
        -OutLog (Join-Path $Root 'Vdafeiyu\logs\server.out.log') -ErrLog (Join-Path $Root 'Vdafeiyu\logs\server.err.log')
    Write-SvcLog $Log 'server' ("8081 不在监听,redis 就绪后拉起 PID={0}" -f $svcPid)
}
