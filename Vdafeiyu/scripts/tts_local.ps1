# tts_local.ps1 — 本地 GPT-SoVITS 语音服务按需启停
#
# 用途：4060 8GB 显存要同时养 qwen3:8b(约5.3G) 和 SoVITS(约1.6G)，平时可以不占着；
#       要发语音再起，用完停掉。V3.0 的 TTS_PROVIDER=gptsovits 指向 http://127.0.0.1:9880。
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File V3.0\scripts\tts_local.ps1 start
#   ... stop     停掉（释放显存）
#   ... status   看端口/显存
# 首次启动约 60-90s（要加载 BERT/HuBERT/GPT/SoVITS 四份权重）。

param(
  [Parameter(Position = 0)][ValidateSet('start', 'stop', 'status')][string]$Action = 'status',
  [int]$Port = 9880,
  [string]$GsvRoot = 'E:\GPT-SoVITS'
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$py = Join-Path $GsvRoot 'runtime\python.exe'
$api = Join-Path $GsvRoot 'api_v2.py'
$cfg = 'GPT_SoVITS/configs/tts_infer.yaml'
$log = 'C:\Users\26904\.dsh\runtime\gptsovits.log'
$err = 'C:\Users\26904\.dsh\runtime\gptsovits.err'

function Test-Port {
  param([int]$p)
  return [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

function Show-Vram {
  $m = nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>$null
  if ($m) { Write-Host "[tts_local] GPU: $m" }
}

switch ($Action) {
  'start' {
    if (Test-Port $Port) { Write-Host "[tts_local] 已在运行: http://127.0.0.1:$Port（无需重复启动）"; break }
    if (-not (Test-Path $py)) { throw "找不到 GPT-SoVITS 运行时: $py" }
    if (-not (Test-Path $api)) { throw "找不到 api_v2.py: $api" }
    New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
    Write-Host "[tts_local] 启动 GPT-SoVITS（首次约 60-90s，日志: $log）"
    # 工作目录必须是 GPT-SoVITS 根：api_v2 用相对路径找 config/weights
    Start-Process -FilePath $py -ArgumentList $api, '-a', '127.0.0.1', '-p', "$Port", '-c', $cfg `
      -WorkingDirectory $GsvRoot -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Hidden
    for ($i = 1; $i -le 60; $i++) {
      Start-Sleep -Seconds 2
      if (Test-Port $Port) { Write-Host "[tts_local] 就绪: http://127.0.0.1:$Port（等待 $($i*2)s）"; Show-Vram; break }
      if ($i -eq 60) { Write-Host "[tts_local] 60 次探测仍未监听，看 $err"; }
    }
  }
  'stop' {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -like '*api_v2.py*' }
    if (-not $procs) { Write-Host "[tts_local] 没有在跑的 GPT-SoVITS"; break }
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host "[tts_local] 已停止 PID $($p.ProcessId)" }
    Start-Sleep -Seconds 2
    Show-Vram
  }
  'status' {
    if (Test-Port $Port) { Write-Host "[tts_local] 运行中: http://127.0.0.1:$Port" } else { Write-Host "[tts_local] 未运行" }
    Show-Vram
  }
}
