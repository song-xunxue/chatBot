# 功能：桌面「ChatBot启动器」文件夹七件套制作(幂等可重跑,已存在即覆盖刷新)
#   清浔-NapCat / 大肥鱼-NapCat / 清浔-面板 / 大肥鱼-面板 /
#   清浔-NapCat登录 / 大肥鱼-NapCat登录 / 语音合成-TTS
# 约定:NapCat 两个走 powershell -WindowStyle Hidden(完全无窗,已在监听自动跳过);
#       TTS 保留状态窗口(显示模型加载/心跳,关窗口=连 api_v2+frpc 一起停,Job Object 绑定);
#       面板/NapCat登录 为 .url 纯网页快捷方式(WebUI 登录密码统一 114507xX)。
# 作者：李文煜
# 日期：2026-10-26

$ErrorActionPreference = 'Continue'
$desktop = [Environment]::GetFolderPath('Desktop')
$dir = Join-Path $desktop 'ChatBot启动器'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$sh = New-Object -ComObject WScript.Shell

function New-CbShortcut([string]$name, [string]$target, [string]$argLine,
                        [string]$icon = '', [string]$workDir = '', [int]$winStyle = 7) {
    $sc = $sh.CreateShortcut((Join-Path $dir $name))
    $sc.TargetPath = $target
    if ($argLine) { $sc.Arguments = $argLine }
    if ($icon) { $sc.IconLocation = $icon }
    if ($workDir) { $sc.WorkingDirectory = $workDir }
    $sc.WindowStyle = $winStyle
    $sc.Save()
    Write-Host ("  已创建: " + $name)
}

Write-Host "=== ChatBot 启动器五件套 -> $dir ==="

# 1.清浔 NapCat(无窗;6099 已监听自动跳过;WMI 启动脱离父进程常驻)
New-CbShortcut '清浔-NapCat.lnk' 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\code\Git_Local\ChatBot\V3.0-local\scripts\start_napcat.ps1"' `
    -icon 'C:\Program Files\Tencent\QQNT\QQ.exe,0'

# 2.大肥鱼 NapCat(无窗;3000 已监听自动跳过;未连上提示 WebUI 扫码地址)
New-CbShortcut '大肥鱼-NapCat.lnk' 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\code\Git_Local\ChatBot\Vdafeiyu\scripts\start-napcat.ps1"' `
    -icon 'C:\Program Files\Tencent\QQNT\QQ.exe,0'

# 3/4.两栈管理面板 + 5/6.两栈 NapCat WebUI 登录页(.url 纯网页快捷方式)
$panels = @(
    , @('清浔-面板.url', 'http://127.0.0.1:8091')
    , @('大肥鱼-面板.url', 'http://127.0.0.1:8081')
    , @('清浔-NapCat登录.url', 'http://127.0.0.1:6099/webui')
    , @('大肥鱼-NapCat登录.url', 'http://127.0.0.1:6089/webui')
)
foreach ($p in $panels) {
    $content = "[InternetShortcut]`r`nURL=" + $p[1] + "`r`nIconIndex=0"
    [IO.File]::WriteAllText((Join-Path $dir $p[0]), $content)
    Write-Host ("  已创建: " + $p[0])
}

# 5.语音合成 TTS(控制台窗口显示加载状态;关窗口=api_v2+frpc 随 Job Object 一起停止)
New-CbShortcut '语音合成-TTS.lnk' 'D:\code\Git_Local\ChatBot\V3.0\tts-tools\GPT-SoVITS启动器3.0.exe' '' `
    -icon 'D:\code\Git_Local\ChatBot\V3.0\tts-tools\启动器.ico,0' `
    -workDir 'D:\code\Git_Local\ChatBot\V3.0\tts-tools' -winStyle 1

# 6/7.关闭器(2026-10-27 加:禁看护任务+杀该栈全部进程;配套启动器会恢复看护并拉起)
New-CbShortcut '清浔-关闭器.lnk' 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\code\Git_Local\ChatBot\V3.0-local\scripts\stop-qingxun.ps1"' `
    -icon 'C:\Windows\System32\imageres.dll,101'   # 红叉/停用图标(imageres 101=关闭)
New-CbShortcut '大肥鱼-关闭器.lnk' 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\code\Git_Local\ChatBot\Vdafeiyu\scripts\stop-dafeiyu.ps1"' `
    -icon 'C:\Windows\System32\imageres.dll,101'

Write-Host "=== 完成,共 9 件 ==="
Get-ChildItem $dir | ForEach-Object { "  " + $_.Name }
