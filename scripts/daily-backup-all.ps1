# 功能:双栈数据每日备份包装(计划任务 ChatBotDailyBackup 每天凌晨 02:17 调用)
# 流程:清浔(6390+V3.0-local/server/data) → 大肥鱼(6380+Vdafeiyu/server/data),各自保留 14 份
# 日志:backups\backup.log(backup.ps1 内部写);本包装只在两栈都失败时退出码 1
# 日期:2026-11-03
# 变更日志:
#   2026-11-03 首版(用户拍板:备份定时任务凌晨 2 点后开启;2026-10-27 的"不自启动"禁令
#              针对的是栈服务看护,本任务是用户主动要求的数据保护,不拉起任何服务)
$Root = 'D:\code\Git_Local\ChatBot'
$Backup = Join-Path $Root 'scripts\backup.ps1'
$rc1 = 0
$rc2 = 0
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Backup `
    -Stack Qingxun -RedisPort 6390 `
    -DataDir 'D:\code\Git_Local\ChatBot\V3.0-local\server\data' `
    -EnvFile 'D:\code\Git_Local\ChatBot\V3.0-local\.env'
$rc1 = $LASTEXITCODE
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Backup `
    -Stack Dafeiyu -RedisPort 6380 `
    -DataDir 'D:\code\Git_Local\ChatBot\Vdafeiyu\server\data' `
    -EnvFile 'D:\code\Git_Local\ChatBot\Vdafeiyu\.env'
$rc2 = $LASTEXITCODE
if ($rc1 -ne 0 -or $rc2 -ne 0) { exit 1 }
exit 0
