# 功能:单栈数据备份(手动跑,不挂计划任务——用户立规不自启动)——redis 快照 + server/data 打包 + .env 留档
# 用法:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup.ps1 -Stack Qingxun -RedisPort 6390 -DataDir "D:\code\Git_Local\ChatBot\V3.0-local\server\data"
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup.ps1 -Stack Dafeiyu -RedisPort 6380 -DataDir "D:\code\Git_Local\ChatBot\Vdafeiyu\server\data" -EnvFile "D:\code\Git_Local\ChatBot\Vdafeiyu\.env"
# 产出: backups\<Stack>\<YYYYMMDD-HHMMSS>\{dump.rdb, data.zip, env.bak};保留最近 -Keep 份(默认 14)
# 日期: 2026-11-03
# 变更日志:
#   2026-11-03 首版(P0 数据安全:redis 聊天数据+日记/人设文件此前无任何备份)
param(
    [Parameter(Mandatory = $true)][string]$Stack,
    [Parameter(Mandatory = $true)][int]$RedisPort,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [string]$EnvFile = '',
    [int]$Keep = 14
)
$ErrorActionPreference = 'Continue'
$Root = 'D:\code\Git_Local\ChatBot'
. (Join-Path $Root 'scripts\launcher-common.ps1')
$RedisCli = 'C:\Users\26904\.dsh\runtime\redis8\Redis-8.10.2-Windows-x64-msys2\redis-cli.exe'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Dir = Join-Path $Root ("backups\{0}\{1}" -f $Stack, $Stamp)
$Log = Join-Path $Root 'backups\backup.log'
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

Write-SvcLog $Log 'BACKUP' ("=== {0} 备份开始 -> {1} ===" -f $Stack, $Stamp)

# 1.redis 快照(--rdb 让服务端落盘快照并回传文件;redis 未运行则跳过并警告,文件部分继续)
if (Test-SvcPort $RedisPort) {
    & $RedisCli -p $RedisPort --rdb (Join-Path $Dir 'dump.rdb') 2>&1 | Out-Null
    if (Test-Path (Join-Path $Dir 'dump.rdb')) {
        Write-SvcLog $Log 'redis' ("dump.rdb OK ({0} KB)" -f [math]::Round((Get-Item (Join-Path $Dir 'dump.rdb')).Length / 1KB))
    } else {
        Write-SvcLog $Log 'redis' 'dump.rdb 生成失败(--rdb 无返回文件)'
    }
} else {
    Write-SvcLog $Log 'redis' ("redis {0} 未运行,跳过快照(只备文件)" -f $RedisPort)
}

# 2.server/data 打包(日记/人设/表情包等文件资产;diary 的 .tmp 残骸一并进去无害)
if (Test-Path $DataDir) {
    try {
        Compress-Archive -Path (Join-Path $DataDir '*') -DestinationPath (Join-Path $Dir 'data.zip') -Force
        Write-SvcLog $Log 'data' ("data.zip OK ({0} KB)" -f [math]::Round((Get-Item (Join-Path $Dir 'data.zip')).Length / 1KB))
    } catch {
        Write-SvcLog $Log 'data' ("打包失败: {0}" -f $_.Exception.Message)
    }
} else {
    Write-SvcLog $Log 'data' ("DataDir 不存在,跳过: {0}" -f $DataDir)
}

# 3..env 留档(备份目录本地留存不入 git;灾难恢复时密钥不用翻记忆)
if ($EnvFile -and (Test-Path $EnvFile)) {
    Copy-Item $EnvFile (Join-Path $Dir 'env.bak') -Force
    Write-SvcLog $Log 'env' '.env 已留档为 env.bak'
}

# 4.保留策略:只留最近 $Keep 份,超删最旧
$all = Get-ChildItem (Join-Path $Root ("backups\{0}" -f $Stack)) -Directory | Sort-Object Name
if ($all.Count -gt $Keep) {
    foreach ($old in ($all | Select-Object -First ($all.Count - $Keep))) {
        Remove-Item $old.FullName -Recurse -Force
        Write-SvcLog $Log 'retention' ("清理超出保留期的旧备份: {0}" -f $old.Name)
    }
}
Write-SvcLog $Log 'DONE' ("=== {0} 备份完成: {1} ===" -f $Stack, $Dir)
