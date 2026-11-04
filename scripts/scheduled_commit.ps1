# 功能:定时 git 提交(2026-11-04 00:05 一次性计划任务 ChatBotScheduledCommit 触发)
# 行为:git add -A → 隐私红线扫描(命中即中止) → commit(不推送;推送永远等用户明示)
# 日志:logs/scheduled-commit.log
# 日期:2026-11-03
$Root = 'D:\code\Git_Local\ChatBot'
Set-Location $Root
$Log = Join-Path $Root 'logs\scheduled-commit.log'
function L([string]$Msg) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Msg
    Write-Host $line
    try { Add-Content -Path $Log -Value $line -Encoding UTF8 } catch {}
}

L '=== 定时提交开始 ==='

# 1.暂存全部改动(backups/logs/.claude/tmp 等已由 .gitignore 挡住)
git add -A 2>&1 | Out-Null

# 2.隐私红线扫描:敏感词表外置 logs/privacy-words.txt(gitignore 内,脚本不含字面量自指)
$WordsFile = Join-Path $Root 'logs\privacy-words.txt'
if (-not (Test-Path $WordsFile)) { L "敏感词表缺失($WordsFile),中止提交"; exit 1 }
$pattern = ((Get-Content $WordsFile -Encoding UTF8 | Where-Object { $_.Trim() }) -join '|')
if (-not $pattern) { L '敏感词表为空,跳过扫描'; exit 1 }
$scan = git grep --cached -l -E $pattern 2>$null
if ($scan) {
    L ("隐私扫描命中,中止提交: " + ($scan -join ','))
    exit 1
}
L '隐私扫描通过'

# 3.提交(不推送)
git commit -m "feat: 面板双主题(浅色Next风格默认+深色切换)+侧栏折叠+悬浮胶囊顶栏+图表主题化;大肥鱼面板源码化(成对移除dream/worldbook,独立build新风格);proactive沉默话题纠偏确认;数据整理脚本data_prune(9-25后已apply);备份体系(daily-backup+ChatBotDailyBackup 02:17+ssh隧道面板公网脚本+napcat观看代理);人设渲染自述化;AI_MEMORY_GUIDE快照" 2>&1 | ForEach-Object { L $_ }
L '=== 定时提交完成(未推送,推送等用户明示) ==='
