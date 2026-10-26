<#
V3.0 一键本地启动脚本(Windows PowerShell 5.1 兼容,不使用 PS7 专属语法):
前置检查(python/Ollama/qwen3:8b/前端产物) -> Ollama 离线时自动拉起 serve -> 新控制台窗口启动
server/scripts/local_dev.py -> 轮询 /health 就绪后打印访问地址与鉴权信息。
注意: 本文件必须以 UTF-8 带 BOM 保存(PS5.1 对无 BOM 文件按 ANSI 解析,中文注释/输出会全部乱码)。

作者: 李文煜
日期: 2026-10-25

2026-10-25
变更说明:
    1. 初版: 参数化(Port/Token/NoSeed/Python/SkipOllama) + Ollama 探活与离线拉起 + 模型/前端产物检查
       + 新窗口启动服务 + /health 轮询(最多 60s) + 地址/token 来源/REST 鉴权提示汇总打印
#>

param(
    # 服务监听端口(透传 local_dev.py --port,默认与 V3.0 线上同款 8091)
    [int]$Port = 8091,
    # 面板/REST 鉴权 token;留空则按 环境变量 ACCESS_TOKEN > V3.0/.env > 默认值 依次解析(与 local_dev.py 内部一致)
    [string]$Token = "",
    # 跳过种子数据(透传 local_dev.py --no-seed)
    [switch]$NoSeed,
    # python.exe 完整路径(conda 不在 PATH 中须用完整路径调用,默认 mychat 环境的解释器)
    [string]$Python = "C:/Users/26904/anaconda3/envs/mychat/python.exe",
    # 跳过 Ollama 探活/拉起与模型检查(不用本地模型时)
    [switch]$SkipOllama
)

# Invoke-WebRequest 的进度条渲染会明显拖慢短超时探活请求,统一关闭
$ProgressPreference = 'SilentlyContinue'

# ---------- 路径推导(相对脚本自身定位,不写死绝对路径) ----------
# 本脚本位于 V3.0/scripts/ 下,上一级即 V3.0 根目录
$V3Root       = Split-Path -Parent $PSScriptRoot
$ServerScript = Join-Path $V3Root "server/scripts/local_dev.py"
$DistIndex    = Join-Path $V3Root "dashboard/dist/index.html"
$EnvFile      = Join-Path $V3Root ".env"

# ---------- 本机环境常量 ----------
$OllamaExe     = "D:\ollama\ollama.exe"      # Ollama 可执行文件(安装在 D 盘)
$OllamaModels  = "D:\ollama\models"          # 模型存储目录(起 serve 前必须用环境变量 OLLAMA_MODELS 指向它)
$OllamaBaseUrl = "http://127.0.0.1:11434"    # Ollama HTTP API 地址
$ModelName     = "qwen3:8b"                  # V3.0 默认本地模型

function Write-Section([string]$Title) {
    # 章节标题打印
    Write-Host ""
    Write-Host ("=" * 60)
    Write-Host $Title
    Write-Host ("=" * 60)
}

function Test-HttpOk([string]$Url) {
    # HTTP GET 探活: 返回 200 视为在线;任何异常(拒绝连接/超时/非 200)一律返回 $false
    # -UseBasicParsing 避免 PS5.1 调 IE 引擎解析响应(未初始化浏览器的机器上会失败)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

Write-Section "V3.0 一键本地启动 (端口 $Port)"

# ---------- 1. 前置检查: python 解释器 ----------
if (-not (Test-Path $Python)) {
    Write-Host "[错误] 未找到 python 解释器: $Python" -ForegroundColor Red
    Write-Host "        请用 -Python 参数指定 python.exe 完整路径(conda 环境须完整路径调用)"
    exit 1
}
Write-Host "[OK] python    : $Python"

# ---------- 2. 前置检查: 服务启动脚本 ----------
if (-not (Test-Path $ServerScript)) {
    Write-Host "[错误] 未找到服务启动脚本: $ServerScript" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] 服务脚本  : $ServerScript"

# ---------- 3. Ollama 探活/离线拉起 + 默认模型检查 ----------
$ollamaOnline = $false
if ($SkipOllama) {
    Write-Host "[跳过] 已指定 -SkipOllama,不检查 Ollama"
} else {
    if (Test-HttpOk "$OllamaBaseUrl/api/version") {
        # 已在线分支(最常见): 直接复用,绝不杀/重启正在跑的 Ollama
        $ollamaOnline = $true
        Write-Host "[OK] Ollama    : 已在线 $OllamaBaseUrl"
    } elseif (-not (Test-Path $OllamaExe)) {
        Write-Host "[警告] Ollama 离线且未找到可执行文件: $OllamaExe" -ForegroundColor Yellow
        Write-Host "        跳过 Ollama 拉起,继续启动服务(用到本地模型的功能将不可用)"
    } else {
        # 离线且 exe 存在: 先设模型目录再拉起 serve
        # Start-Process 子进程继承本会话环境变量,因此此处设置 $env:OLLAMA_MODELS 对新起的 serve 生效
        # 窗口形态选 Minimized: 保留一个独立控制台窗口方便看 serve 日志/需要时手动关闭,
        # 且不抢占当前终端焦点;不用 Hidden —— 完全隐藏的后台进程出问题时既看不到日志也不好结束
        $env:OLLAMA_MODELS = $OllamaModels
        Write-Host "[INFO] Ollama 离线,正在拉起: $OllamaExe serve (OLLAMA_MODELS=$OllamaModels)"
        Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Minimized
        # 轮询 /api/version 最多约 30s(15 次 x 2s)
        for ($i = 1; $i -le 15; $i++) {
            Start-Sleep -Seconds 2
            if (Test-HttpOk "$OllamaBaseUrl/api/version") { $ollamaOnline = $true; break }
            Write-Host "        等待 Ollama 启动... ($i/15)"
        }
        if ($ollamaOnline) {
            Write-Host "[OK] Ollama    : 已拉起 $OllamaBaseUrl"
        } else {
            Write-Host "[警告] Ollama 30s 内未就绪,继续启动服务(本地模型功能可能不可用)" -ForegroundColor Yellow
        }
    }

    if ($ollamaOnline) {
        # GET /api/tags 检查默认模型是否已拉取(缺失只警告不自动拉,大模型下载耗时应由用户主动决定)
        try {
            $tags = Invoke-RestMethod -Uri "$OllamaBaseUrl/api/tags" -TimeoutSec 5
            # models[].name 形如 "qwen3:8b",用通配符匹配以兼容可能的 tag 后缀
            $hit = @($tags.models | Where-Object { $_.name -like "$ModelName*" })
            if ($hit.Count -gt 0) {
                Write-Host "[OK] 模型      : $ModelName 已就绪"
            } else {
                Write-Host "[警告] Ollama 在线但未找到模型 $ModelName" -ForegroundColor Yellow
                Write-Host "        请手动执行: ollama pull $ModelName (脚本不自动拉取)"
            }
        } catch {
            Write-Host "[警告] 查询 Ollama 模型列表失败: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

# ---------- 4. 前置检查: 前端构建产物 ----------
# 缺失只警告不退出: 面板不可用但 REST API 照常;需要面板时先在 V3.0/dashboard 下 npm run build
if (Test-Path $DistIndex) {
    Write-Host "[OK] 前端产物  : $DistIndex"
} else {
    Write-Host "[警告] 未找到前端产物: $DistIndex" -ForegroundColor Yellow
    Write-Host "        面板将不可用,REST API 照常;需要面板请先在 V3.0/dashboard 执行 npm run build"
}

# ---------- 5. token 解析(优先级与 local_dev.py 的 token_info 一致) ----------
$ResolvedToken = ""
$TokenSource   = ""
if ($Token -ne "") {
    $ResolvedToken = $Token
    $TokenSource   = "脚本参数 -Token"
} elseif (-not [string]::IsNullOrEmpty($env:ACCESS_TOKEN)) {
    $ResolvedToken = $env:ACCESS_TOKEN
    $TokenSource   = "环境变量 ACCESS_TOKEN"
} elseif (Test-Path $EnvFile) {
    # 逐行找首个 ACCESS_TOKEN= 行(锚定行首,不会误匹配 XX_ACCESS_TOKEN 之类)
    $line = Get-Content -Path $EnvFile | Where-Object { $_ -match '^\s*ACCESS_TOKEN\s*=' } | Select-Object -First 1
    if ($null -ne $line) {
        # 取等号右侧,去首尾空白与包裹引号([char]34 双引号 / [char]39 单引号)
        $ResolvedToken = ($line -split '=', 2)[1].Trim().Trim([char]34).Trim([char]39)
        $TokenSource   = "V3.0/.env"
    }
}
if ($ResolvedToken -eq "") {
    $ResolvedToken = "change-me-please"
    $TokenSource   = "代码默认值"
}
Write-Host "[INFO] ACCESS_TOKEN 来源: $TokenSource"

# ---------- 6. 启动 server(新控制台窗口) ----------
if (Test-HttpOk "http://127.0.0.1:$Port/health") {
    Write-Host "[警告] 端口 $Port 已有服务在响应 /health,可能已有实例在运行" -ForegroundColor Yellow
    Write-Host "        新开的窗口可能因端口被占用而直接退出,请确认是否需要先停掉旧实例"
}

# 用 -f 格式化避免反引号转义引号的易错写法;路径含空格也安全
$serverArgs = '"{0}" --port {1}' -f $ServerScript, $Port
if ($NoSeed) { $serverArgs += ' --no-seed' }
# 显式传 --token(值与上面解析结果一致),确保服务实际生效的 token 与本脚本打印的完全相同
$serverArgs += ' --token "{0}"' -f $ResolvedToken

Write-Host "[INFO] 新窗口启动服务: $Python $serverArgs"
# 控制台程序经 Start-Process 启动会自动开独立控制台窗口,服务日志在那个窗口里看
Start-Process -FilePath $Python -ArgumentList $serverArgs -WorkingDirectory $V3Root

# ---------- 7. 健康检查轮询(最多 60s,2s 间隔) ----------
$healthUrl = "http://127.0.0.1:$Port/health"
Write-Host "[INFO] 等待服务就绪: GET $healthUrl (最多 60s)"
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 2
    if (Test-HttpOk $healthUrl) { $ready = $true; break }
    Write-Host "        等待中... ($i/30)"
}

# ---------- 8. 就绪汇总 ----------
if ($ready) {
    # 自探测局域网 IPv4: 排除回环 127.* 与链路本地 169.254.*(后者不可用于局域网访问),多块网卡取第一个
    $lanIp = $null
    try {
        $lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
            Select-Object -First 1).IPAddress
    } catch { }

    Write-Section "启动成功"
    Write-Host "  本机访问    : http://127.0.0.1:$Port"
    if ($lanIp) {
        Write-Host "  局域网访问  : http://${lanIp}:$Port"
    } else {
        Write-Host "  局域网访问  : 未能自动探测本机 IPv4,请用 ipconfig 自查后替换地址中的主机名"
    }
    Write-Host "  ACCESS_TOKEN: $ResolvedToken  (来源: $TokenSource)"
    Write-Host "  REST 鉴权   : 请求头携带 X-Access-Token: $ResolvedToken"
    Write-Host "  说明        : NapCat 不由本脚本启动,需单独运行"
} else {
    Write-Host ""
    Write-Host "[错误] 服务 $healthUrl 在 60s 内未就绪" -ForegroundColor Red
    Write-Host "        请切换到上一步新开的服务窗口查看日志排查"
    exit 1
}
