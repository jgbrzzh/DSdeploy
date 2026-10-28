[CmdletBinding()]
param(
    [ValidateSet('Start','Stop','Status','Logs','Backup','InstallDocker','Check','ExportImages','UpgradeCompanion','ImportMemes','PrepareImages','UpdateImages','InitializeConfig','InstallMemePacks','ConfigureInstance','ConfigureSearch','FixNapCatDns','RestoreNapCatDns','Migrate','RollbackMigration')]
    [string]$Action = 'Start',
    [switch]$NoBrowser,
    [ValidateRange(0,65535)][int]$AstrBotPort = 0,
    [ValidateRange(0,65535)][int]$NapCatPort = 0,
    [switch]$AdoptData,
    [string]$SourceDirectory = '',
    [ValidateSet('DaoCloud','1ms','Official')]
    [string]$ImageSource = 'DaoCloud'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root
foreach ($isolationPath in @($Root, (Join-Path $Root 'private'), (Join-Path $Root 'data'))) {
    if ((Test-Path -LiteralPath $isolationPath) -and ((Get-Item -LiteralPath $isolationPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw '实例根目录、private 和 data 不能是指向另一目录的链接。'
    }
}
$env:TEMP = Join-Path $Root 'runtime/tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $Root 'runtime/pip-cache'
$env:UV_CACHE_DIR = Join-Path $Root 'runtime/uv-cache'
$env:DOCKER_CONFIG = Join-Path $Root 'private/docker-client'
foreach ($directory in @($env:TEMP, $env:DOCKER_CONFIG)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}
$Utf8 = New-Object System.Text.UTF8Encoding($false)
function Write-Utf8([string]$Path, [string]$Content) {
    [IO.File]::WriteAllText($Path, $Content, $Utf8)
}
. (Join-Path $Root 'bootstrap/instance.ps1')
function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','') }
    finally { $stream.Dispose(); $hasher.Dispose() }
}
function Get-BackupFiles([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "备份遇到链接，请先检查：$Path" }
    if ($item.PSIsContainer) {
        foreach ($child in Get-ChildItem -LiteralPath $Path -Force) { Get-BackupFiles $child.FullName }
    } else { return $item.FullName }
}
function Write-DataBackup([string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $partial = $Destination + '.partial'
    $archive = [IO.Compression.ZipFile]::Open($partial, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($relative in @('data/astrbot','data/napcat','data/qq','private','compose.yaml','compose.lock.json','compose.dns.json','compose.napcat-dns.json','compose.migrated.json','migration.json')) {
            $source = Join-Path $Root $relative
            if (-not (Test-Path -LiteralPath $source)) { continue }
            foreach ($file in Get-BackupFiles $source) {
                $entry = $file.Substring($Root.TrimEnd('\','/').Length + 1).Replace('\','/')
                if ($entry -eq 'private/meme-import.zip') { continue }
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file, $entry, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
            }
        }
    } finally { $archive.Dispose() }
    Move-Item -LiteralPath $partial -Destination $Destination
}
function Invoke-Docker([string[]]$DockerArgs) {
    # Windows PowerShell 5.1 can turn ordinary CLI progress on stderr into a
    # terminating NativeCommandError. Judge CLI success by its exit code.
    $ErrorActionPreference = 'Continue'
    & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) { throw "Docker 执行失败（$LASTEXITCODE）。请查看上方提示。" }
}
function Get-DockerProbe([string[]]$DockerArgs) {
    $ErrorActionPreference = 'Continue'
    $output = & docker @DockerArgs 2>$null
    return @{ExitCode=$LASTEXITCODE; Output=$output}
}
function Invoke-DockerDownload([string[]]$DockerArgs) {
    for ($attempt=1; $attempt -le 3; $attempt++) {
        try { Invoke-Docker -DockerArgs $DockerArgs; return }
        catch {
            if ($attempt -eq 3) { throw }
            Write-Host "下载连接中断，5 秒后重试（$attempt/3）。已下载内容会复用。"
            Start-Sleep -Seconds 5
        }
    }
}
function Get-ImageReference([string]$Canonical) {
    switch ($ImageSource) {
        'DaoCloud' { 'docker.m.daocloud.io/' + $Canonical }
        '1ms' { 'docker.1ms.run/' + $Canonical }
        'Official' { $Canonical }
    }
}
function Pull-DeploymentImage([string]$Canonical) {
    $reference = Get-ImageReference $Canonical
    Write-Host "镜像下载地址：$reference"
    Invoke-DockerDownload -DockerArgs @('pull',$reference)
    if ($reference -ne $Canonical) { Invoke-Docker -DockerArgs @('tag',$reference,$Canonical) }
}
function Get-ComposeArgs {
    $baseFile = if (Test-Path -LiteralPath (Join-Path $Root 'compose.migrated.json')) { 'compose.migrated.json' } else { 'compose.yaml' }
    $result = @('compose', '--project-name', $script:Instance.project, '--project-directory', $Root, '-f', (Join-Path $Root $baseFile))
    if (Test-Path -LiteralPath (Join-Path $Root 'compose.lock.json')) {
        $result += @('-f', (Join-Path $Root 'compose.lock.json'))
    }
    if (Test-Path -LiteralPath (Join-Path $Root 'compose.dns.json')) {
        $result += @('-f', (Join-Path $Root 'compose.dns.json'))
    }
    if (Test-Path -LiteralPath (Join-Path $Root 'compose.napcat-dns.json')) {
        $result += @('-f', (Join-Path $Root 'compose.napcat-dns.json'))
    }
    return $result
}
function Invoke-Compose([string[]]$ComposeArgs) {
    Invoke-Docker -DockerArgs ((Get-ComposeArgs) + $ComposeArgs)
}
function Set-NapCatDns([bool]$Restore = $false) {
    $override = Join-Path $Root 'compose.napcat-dns.json'
    $baseline = Join-Path $Root 'private/napcat-dns-original.json'
    foreach ($path in @($override, $baseline)) {
        if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "DNS 配置或备份不能是链接：$path"
        }
    }
    $container = Get-DockerProbe ((Get-ComposeArgs) + @('ps','--all','--quiet','napcat'))
    if ($container.ExitCode -ne 0 -or -not $container.Output) {
        throw '未找到本目录的 NapCat 容器。请先完成部署并启动，再运行 DNS 修复。'
    }
    $existed = Test-Path -LiteralPath $override
    $previous = if ($existed) { [Convert]::ToBase64String([IO.File]::ReadAllBytes($override)) } else { '' }
    if ($Restore) {
        if (-not (Test-Path -LiteralPath $baseline)) { throw '没有 DNS 修复前的备份，无需恢复。' }
        $original = Get-Content -LiteralPath $baseline -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($original.existed -isnot [bool]) { throw 'DNS 备份格式无效。' }
        $originalBytes = if ($original.existed) { [Convert]::FromBase64String($original.content) } else { $null }
    } elseif (-not (Test-Path -LiteralPath $baseline)) {
        Write-Utf8 $baseline (@{existed=[bool]$existed; content=$previous} | ConvertTo-Json)
    }
    try {
        if ($Restore) {
            if ($original.existed) { [IO.File]::WriteAllBytes($override, [byte[]]$originalBytes) }
            elseif (Test-Path -LiteralPath $override) { Remove-Item -LiteralPath $override }
        } else {
            Write-Utf8 $override (@{services=@{napcat=@{dns=@('223.5.5.5','119.29.29.29')}}} | ConvertTo-Json -Depth 5)
        }
        Invoke-Compose @('config','--quiet')
        Write-Host '正在重新创建本实例的 NapCat 容器，QQ 会短暂断开……'
        Invoke-Compose @('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','napcat')
    } catch {
        $failure = $_.Exception.Message
        if ($existed) { [IO.File]::WriteAllBytes($override, [Convert]::FromBase64String($previous)) }
        elseif (Test-Path -LiteralPath $override) { Remove-Item -LiteralPath $override }
        Write-Host '操作失败，配置文件已回退；正在尝试用原配置恢复 NapCat。' -ForegroundColor Yellow
        try { Invoke-Compose @('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','napcat') }
        catch { Write-Warning '原配置已保留，但容器未恢复。请检查 Docker 状态后重新启动。' }
        throw $failure
    }
    if ($Restore) {
        Remove-Item -LiteralPath $baseline
        Write-Host '已恢复修复前的 DNS 配置。' -ForegroundColor Green
    } else {
        Write-Host 'NapCat DNS 已设为 223.5.5.5、119.29.29.29；以后启动仍会生效。' -ForegroundColor Green
        Write-Host '需要撤销时，双击“恢复NapCat DNS.cmd”。'
    }
    Write-Host ('请打开 http://127.0.0.1:' + $script:Instance.napcat_port + '/webui 检查二维码和 QQ 登录。DNS 配置成功不代表登录已恢复。')
}
function Require-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        $identityPath = Join-Path $Root 'private/instance.json'
        if (Test-Path -LiteralPath $identityPath) {
            $dockerIdentity = Get-Content -LiteralPath $identityPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($dockerIdentity.PSObject.Properties.Name -contains 'docker_bin') {
                if (Test-Path -LiteralPath (Join-Path $dockerIdentity.docker_bin 'docker.exe')) { $env:PATH += ';' + $dockerIdentity.docker_bin }
            }
        }
        foreach ($dockerBin in @((Join-Path $Root 'runtime/DockerDesktop/resources/bin'), (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'))) {
            if (Test-Path -LiteralPath (Join-Path $dockerBin 'docker.exe')) { $env:PATH += ";$dockerBin"; break }
        }
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw '未安装 Docker Desktop。请双击“安装Docker.cmd”，安装完成并启动 Docker Desktop 后重试。'
    }
    $engine = Get-DockerProbe @('info','--format','{{.OSType}}')
    if ($engine.ExitCode -ne 0) { throw 'Docker 引擎尚未就绪。请启动 Docker Desktop，等显示运行中后重试。' }
    if ($engine.Output -ne 'linux') { throw '请在 Docker Desktop 中切换到 Linux containers。' }
    Invoke-Docker -DockerArgs @('compose','version','--short')
}
function Require-LocalDisk {
    if ($script:Instance.docker_mode -eq 'shared') { return }
    $diskRoot = Join-Path $Root 'data/docker-desktop'
    $localDisks = @(Get-ChildItem -LiteralPath $diskRoot -Filter '*.vhdx' -File -Recurse -ErrorAction SilentlyContinue)
    if ($localDisks.Count -eq 0) {
        throw "未确认 Docker 数据盘位于包内。请在 Docker Desktop 的 Resources / Advanced 中将 Disk image location 设为 $diskRoot，应用后重试。当前不会在外部磁盘位置创建本包镜像。"
    }
}
function New-Token {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()
}
function Read-Default([string]$Prompt, [string]$Default) {
    $value = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value.Trim()
}
function Initialize-Settings {
    $private = Join-Path $Root 'private'
    $settingsPath = Join-Path $private 'settings.json'
    if (Test-Path -LiteralPath $settingsPath) { return }
    Write-Host '首次配置：信息仅保存在本机 private 和 data 目录。' -ForegroundColor Cyan
    $owner = Read-Host '你的 QQ 号（用于首轮私聊测试）'
    if ($owner -notmatch '^\d{5,12}$') { throw 'QQ 号应为 5 到 12 位数字。' }
    $bot = Read-Host '机器人小号 QQ 号（扫码登录时请选择这个号）'
    if ($bot -notmatch '^\d{5,12}$' -or $bot -eq $owner) { throw '请填写与主人 QQ 不同的机器人小号。' }
    $groupText = Read-Host '允许群聊的群号（可选，逗号分隔；直接回车只启用主人私聊）'
    $groups = @($groupText -split '[,，;；\s]+' | Where-Object { $_ } | Select-Object -Unique)
    foreach ($group in $groups) { if ($group -notmatch '^\d{5,12}$') { throw '群号应为 5 到 12 位数字。' } }
    $base = Read-Default '模型 API 地址' 'https://api.deepseek.com/v1'
    $uri = $null
    if (-not [Uri]::TryCreate($base, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'https' -or $uri.UserInfo) {
        throw 'API 地址需要是有效的 HTTPS 地址。'
    }
    $model = Read-Default '模型名称（官方 V4.1 Flash 使用 deepseek-flash）' 'deepseek-flash'
    $secureKey = Read-Host 'API Key（输入时隐藏）' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    if ([string]::IsNullOrWhiteSpace($key)) { throw 'API Key 不能为空。' }
    $searchKey = $key.Trim()
    if ($uri.Host -ne 'api.deepseek.com') {
        $searchSecret = Read-Host 'DeepSeek 官方搜索 Key（与第三方模型 Key 不同；可留空稍后在面板填写）' -AsSecureString
        $searchPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($searchSecret)
        try { $searchKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($searchPointer).Trim() }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($searchPointer) }
    }
    $settings = [ordered]@{
        owner_qq=$owner; bot_qq=$bot; group_ids=$groups; api_base=$base.TrimEnd('/'); model=$model
        api_key=$key.Trim(); search_api_key=$searchKey; onebot_token=(New-Token); napcat_token=(New-Token)
        dashboard_password=('Whale!' + (New-Token).Substring(0,20)); jwt_secret=(New-Token)
    }
    New-Item -ItemType Directory -Force -Path $private | Out-Null
    Write-Utf8 $settingsPath ($settings | ConvertTo-Json -Depth 10)
    Write-Utf8 (Join-Path $private '面板登录信息.txt') @"
AstrBot: http://127.0.0.1:$($script:Instance.astrbot_port)
用户名: astrbot
初始密码: $($settings.dashboard_password)
NapCat: http://127.0.0.1:$($script:Instance.napcat_port)/webui
Token: $($settings.napcat_token)
这些是首次初始化时的凭据；以后在面板修改的密码以面板为准。
请勿将 private、data 或 backups 目录分享给他人。
"@
    $key = $null
}
function Initialize-NapCat($settings) {
    $dir = Join-Path $Root 'data/napcat'
    $client = [ordered]@{
        enable=$true; name='astrbot'; url='ws://astrbot:6199/ws'
        reportSelfMessage=$false; messagePostFormat='array'; token=$settings.onebot_token
        debug=$false; heartInterval=30000; reconnectInterval=5000
    }
    $config = @{network=@{
        httpServers=@(); httpSseServers=@(); httpClients=@(); websocketServers=@()
        websocketClients=@($client); plugins=@()
    }; musicSignUrl=''; enableLocalFile2Url=$false; parseMultMsg=$false}
    foreach ($name in @('onebot11.json', "onebot11_$($settings.bot_qq).json")) {
        $path = Join-Path $dir $name
        if (-not (Test-Path -LiteralPath $path)) { Write-Utf8 $path ($config | ConvertTo-Json -Depth 15) }
    }
    $webui = Join-Path $dir 'webui.json'
    if (-not (Test-Path -LiteralPath $webui)) {
        Write-Utf8 $webui (@{host='0.0.0.0'; port=6099; prefix=''; token=$settings.napcat_token; loginRate=3} | ConvertTo-Json)
    }
}
function Lock-Images {
    $services = @{}
    foreach ($item in @(@('astrbot','soulter/astrbot:latest'), @('napcat','mlikiowa/napcat-docker:latest'), @('ollama','ollama/ollama:latest'))) {
        $raw = & docker image inspect $item[1] --format '{{json .RepoDigests}}'
        if ($LASTEXITCODE -ne 0) { throw '镜像检查失败。' }
        $parsedDigests = ConvertFrom-Json -InputObject ($raw -join [Environment]::NewLine)
        $digests = @($parsedDigests | ForEach-Object { [string]$_ })
        $reference = $item[1]
        $preferredPrefix = (Get-ImageReference $item[1]).Replace(':latest','') + '@sha256:'
        $preferred = @($digests | Where-Object { $_ -and $_.StartsWith($preferredPrefix) })
        if ($preferred.Count -ge 1) { $reference = [string]$preferred[0] }
        elseif ($digests.Count -ge 1 -and $digests[0] -match '@sha256:') { $reference = [string]$digests[0] }
        else {
            # docker save/load on some engines preserves tags but drops RepoDigests.
            # Keep the local tag and forbid automatic pulls for runtime services.
            Write-Host "本地导入镜像未保留仓库摘要，使用本地标签：$reference"
        }
        if ($item[0] -eq 'astrbot') {
            $services['astrbot'] = @{build=@{args=@{ASTRBOT_BASE=$reference}}}
        } else { $services[$item[0]] = @{image=$reference; pull_policy='never'} }
    }
    Write-Utf8 (Join-Path $Root 'compose.lock.json') (@{services=$services} | ConvertTo-Json -Depth 5)
}
function Wait-Panel([int]$Port, [string]$PanelPath = '/') {
    for ($i=0; $i -lt 60; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port$PanelPath" -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}
function Wait-Ollama {
    for ($i=0; $i -lt 30; $i++) {
        $probe = Get-DockerProbe ((Get-ComposeArgs) + @('exec','-T','ollama','ollama','list'))
        if ($probe.ExitCode -eq 0) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}
function Get-BuildSignature {
    $buildFiles = @('Dockerfile','bootstrap/install_plugins.py','vendor/manifest.json','vendor/livingmemory.zip','vendor/proactive_chat.zip','vendor/meme_manager.zip','vendor/signin.zip','compose.lock.json')
    $signature = ($buildFiles | ForEach-Object { Get-Sha256 (Join-Path $Root $_) }) -join ':'
    return $signature
}
function Require-PreparedImages {
    Require-LocalDisk
    $state = Join-Path $Root 'private/build-state.json'
    if (-not (Test-Path -LiteralPath (Join-Path $Root 'compose.lock.json')) -or -not (Test-Path -LiteralPath $state)) {
        throw '请先运行“下载准备镜像.cmd”，此操作不会导入机器人配置。'
    }
    $saved = Get-Content -LiteralPath $state -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($saved.signature -ne (Get-BuildSignature)) { throw '程序或插件依赖已更新，请先运行“下载准备镜像.cmd”重新准备运行环境。' }
    foreach ($image in @($script:Instance.image)) {
        $probe = Get-DockerProbe @('image','inspect',$image,'--format','{{.Id}}')
        if ($probe.ExitCode -ne 0) { throw '运行镜像缺失，请运行“下载准备镜像.cmd”。' }
    }
}
function Prepare-Images([bool]$Refresh = $false) {
    Require-LocalDisk
    Invoke-Compose @('config','--quiet')
    if ($Refresh -or -not (Test-Path -LiteralPath (Join-Path $Root 'compose.lock.json'))) {
        $localArchive = Join-Path $Root 'offline/images.tar'
        $importedImages = $false
        if (-not $Refresh -and (Test-Path -LiteralPath $localArchive)) {
            $checksumPath = $localArchive + '.sha256'
            if (Test-Path -LiteralPath $checksumPath) {
                $expectedHash = ((Get-Content -LiteralPath $checksumPath -Raw -Encoding UTF8).Trim() -split '\s+')[0]
                if ((Get-Sha256 $localArchive) -ne $expectedHash) { throw '本地镜像包 SHA-256 不匹配。' }
            }
            Write-Host '导入包内 offline/images.tar…'
            Invoke-Docker -DockerArgs @('load','--input',$localArchive)
            $importedImages = $true
        }
        Write-Host '首次下载 AstrBot、NapCat 和 Ollama，耗时取决于网络…'
        foreach ($image in @('soulter/astrbot:latest','mlikiowa/napcat-docker:latest','ollama/ollama:latest')) {
            if ($importedImages) {
                $imageProbe = Get-DockerProbe @('image','inspect',$image,'--format','{{.Id}}')
                if ($imageProbe.ExitCode -eq 0) { continue }
            }
            Pull-DeploymentImage $image
        }
        $oldLock = Join-Path $Root 'compose.lock.json'
        if (Test-Path -LiteralPath $oldLock) {
            $lockBackups = Join-Path $Root 'backups'
            New-Item -ItemType Directory -Force -Path $lockBackups | Out-Null
            Copy-Item -LiteralPath $oldLock -Destination (Join-Path $lockBackups ('镜像锁-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json'))
        }
        Lock-Images
    }
    $signature = Get-BuildSignature
    $buildState = Join-Path $Root 'private/build-state.json'
    $imageExists = & docker image ls -q $script:Instance.image
    if ($LASTEXITCODE -ne 0) { throw '检查本地运行镜像失败。' }
    $needsBuild = $true
    if ((Test-Path -LiteralPath $buildState) -and $imageExists) {
        $oldState = Get-Content -LiteralPath $buildState -Raw -Encoding UTF8 | ConvertFrom-Json
        $needsBuild = $oldState.signature -ne $signature
    }
    if ($needsBuild) {
        Write-Host '正在准备长期记忆和主动陪伴插件依赖…'
        Invoke-Compose @('build','astrbot')
        Write-Utf8 $buildState (@{signature=$signature} | ConvertTo-Json)
    }
    $probe = Get-DockerProbe ((Get-ComposeArgs) + @('ps','--status','running','--services'))
    if ($probe.ExitCode -ne 0) { throw '无法读取本包运行状态。' }
    $ollamaWasRunning = @($probe.Output) -contains 'ollama'
    try {
        Invoke-Compose @('up','-d','ollama')
        # Check the service before pulling; exec may race the server startup.
        if (-not (Wait-Ollama)) { throw '本地记忆向量服务未就绪，请检查日志。' }
        $modelProbe = Get-DockerProbe ((Get-ComposeArgs) + @('exec','-T','ollama','ollama','show','bge-m3'))
        if ($modelProbe.ExitCode -ne 0) {
            $dnsOutput = @(Invoke-Compose @('run','--rm','--no-deps','--entrypoint','python','astrbot','/bootstrap/prepare_ollama_dns.py'))
            $dnsJson = ($dnsOutput -join [Environment]::NewLine).Trim()
            if ($dnsJson -and $dnsJson -ne '{}') {
                $dnsObject = ConvertFrom-Json -InputObject $dnsJson
                if ($dnsObject.PSObject.Properties.Name -contains 'services') {
                    Write-Utf8 (Join-Path $Root 'compose.dns.json') $dnsJson
                    Write-Host '检测到模型 CDN 的 Fake-IP 解析，已为本包 Ollama 容器设置真实公网解析。'
                    Invoke-Compose @('up','-d','ollama')
                    if (-not (Wait-Ollama)) { throw '更新解析后记忆向量服务尚未就绪。' }
                }
            }
            Write-Host '首次下载本地记忆模型 bge-m3（约 1.2 GB）…'
            Invoke-DockerDownload -DockerArgs ((Get-ComposeArgs) + @('exec','-T','ollama','ollama','pull','bge-m3'))
        }
    } finally {
        if (-not $ollamaWasRunning) { Invoke-Compose @('stop','ollama') }
    }
    Write-Host '镜像、插件依赖和 bge-m3 已准备好。没有导入或升级机器人配置。'
}
function Initialize-Configuration {
    Require-PreparedImages
    Initialize-Settings
    $settings = Get-Content -LiteralPath (Join-Path $Root 'private/settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($dir in @('data/astrbot','data/napcat','data/qq')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Root $dir) | Out-Null
    }
    Initialize-NapCat $settings
    if (Test-Path -LiteralPath (Join-Path $Root 'data/astrbot/cmd_config.json')) {
        Invoke-CompanionMaintenance 'bootstrap.py'
    } else {
        Invoke-Compose @('run','--rm','--no-deps','--pull','never','--entrypoint','python','astrbot','/bootstrap/bootstrap.py')
    }
    Write-Host '初始配置导入完成；已有配置会保留。需要迁移表达设置时，请单独运行“升级陪伴配置.cmd”。'
}
function Invoke-CompanionMaintenance([string]$Entry) {
    Require-PreparedImages
    if (-not (Test-Path -LiteralPath (Join-Path $Root 'data/astrbot/cmd_config.json'))) {
        throw '请先运行“导入初始配置.cmd”。'
    }
    $probe = Get-DockerProbe ((Get-ComposeArgs) + @('ps','--status','running','--services'))
    if ($probe.ExitCode -ne 0) { throw '无法读取本包运行状态。' }
    $running = @($probe.Output | Where-Object { $_ -in @('astrbot','napcat','ollama') })
    $backupDirectory = Join-Path $Root 'backups'
    New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
    $destination = Join-Path $backupDirectory ('陪伴升级前-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.zip')
    Invoke-Compose @('stop')
    try {
        Write-DataBackup $destination
        Write-Host "已先备份到：$destination"
        Invoke-Compose @('run','--rm','--no-deps','--pull','never','--entrypoint','python','astrbot',('/bootstrap/'+$Entry))
    } finally {
        if ($running.Count -gt 0) { Invoke-Compose (@('up','-d','--no-build','--pull','never','--no-deps') + $running) }
    }
}
try {
    if ($Action -in @('Migrate','RollbackMigration')) {
        . (Join-Path $Root 'bootstrap/migrate.ps1')
        $migrationLockPath = Join-Path $Root 'runtime/migration.lock'
        Assert-MigrationPath $migrationLockPath
        try { $migrationLock = [IO.File]::Open($migrationLockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
        catch { throw '这个目录已有迁移或回退在运行，请等当前窗口完成后再操作。' }
        try {
            if ($Action -eq 'Migrate') { Invoke-DeploymentMigration $SourceDirectory }
            else { Undo-DeploymentMigration }
        } finally { $migrationLock.Dispose() }
        exit 0
    }
    if ($Action -notin @('Check','Status','Logs','Stop') -and (Test-Path -LiteralPath (Join-Path $Root 'migration.json'))) {
        $migrationState = Get-Content -LiteralPath (Join-Path $Root 'migration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($migrationState.status -ne 'complete' -and $migrationState.status -ne 'rolled-back') { throw '上次迁移尚未完成。请先双击“回退版本迁移.cmd”，不要直接启动。' }
    }
    Initialize-Instance
    if ($Action -eq 'ConfigureInstance') {
        Get-Content -LiteralPath (Join-Path $Root 'private/本实例面板地址.txt') -Encoding UTF8
        exit 0
    }
    if ($Action -eq 'InstallDocker') {
        $installDirectory = Join-Path $Root 'runtime/DockerDesktop'
        if (Test-Path -LiteralPath (Join-Path $installDirectory 'Docker Desktop.exe')) {
            Start-Process -FilePath (Join-Path $installDirectory 'Docker Desktop.exe') -WindowStyle Hidden
            Write-Host '包内 Docker Desktop 已存在，已请求启动。'
            exit 0
        }
        if ((Get-Command docker -ErrorAction SilentlyContinue) -or (Test-Path -LiteralPath (Join-Path $env:ProgramFiles 'Docker/Docker/resources/bin/docker.exe'))) {
            $script:Instance.docker_mode = 'shared'
            Write-Utf8 (Join-Path $Root 'private/instance.json') ($script:Instance | ConvertTo-Json)
            Write-Host '复用现有 Docker 引擎，不重装、不迁移旧数据盘。请直接运行“下载准备镜像.cmd”。'
            exit 0
        }
        $script:Instance.docker_mode = 'local'
        Write-Utf8 (Join-Path $Root 'private/instance.json') ($script:Instance | ConvertTo-Json)
        $downloadDirectory = Join-Path $Root 'runtime/downloads'
        New-Item -ItemType Directory -Force -Path $downloadDirectory | Out-Null
        $architecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
        $installer = Join-Path $downloadDirectory 'DockerDesktopInstaller.exe'
        if (-not (Test-Path -LiteralPath $installer)) {
            Write-Host '下载官方 Docker 安装器到包内 runtime/downloads…'
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri "https://desktop.docker.com/win/main/$architecture/Docker%20Desktop%20Installer.exe" -OutFile ($installer+'.part')
            Move-Item -LiteralPath ($installer+'.part') -Destination $installer -Force
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Docker') {
            throw 'Docker 安装器签名未通过验证，请检查下载文件。'
        }
        $diskDirectory = Join-Path $Root 'data/docker-desktop'
        New-Item -ItemType Directory -Force -Path $diskDirectory | Out-Null
        $arguments = 'install --accept-license --backend=wsl-2 --no-windows-containers --installation-dir="{0}" --wsl-default-data-root="{1}"' -f $installDirectory, $diskDirectory
        $process = Start-Process -FilePath $installer -ArgumentList $arguments -Verb RunAs -Wait -PassThru -WindowStyle Hidden
        if ($process.ExitCode -notin @(0,3010)) { throw "Docker 安装未完成（$($process.ExitCode)），请按安装器提示处理。" }
        if (Test-Path -LiteralPath (Join-Path $installDirectory 'Docker Desktop.exe')) {
            Start-Process -FilePath (Join-Path $installDirectory 'Docker Desktop.exe') -WindowStyle Hidden
        }
        Write-Host '请启动 Docker Desktop，完成首次设置；如提示重启请先重启，再双击一键启动。'
        exit 0
    }
    if ($Action -eq 'Check') {
        Write-Host '检查部署包结构…'
        foreach ($file in @('compose.yaml','Dockerfile','bootstrap/bootstrap.py','bootstrap/persona.txt','bootstrap/companion_profile.json','meme-packs/manifest.json','vendor/manifest.json','vendor/livingmemory.zip','vendor/proactive_chat.zip','vendor/meme_manager.zip','vendor/signin.zip')) {
            if (-not (Test-Path -LiteralPath (Join-Path $Root $file))) { throw "缺少文件：$file" }
        }
        Require-Docker
        Invoke-Compose @('config','--quiet')
        Write-Host '结构、Docker 引擎与 Compose 配置检查通过。'
        exit 0
    }
    Require-Docker
    if ($Action -eq 'ExportImages') {
        $offlineDirectory = Join-Path $Root 'offline'
        New-Item -ItemType Directory -Force -Path $offlineDirectory | Out-Null
        $images = @('soulter/astrbot:latest','mlikiowa/napcat-docker:latest','ollama/ollama:latest')
        foreach ($image in $images) { Pull-DeploymentImage $image }
        $destination = Join-Path $offlineDirectory 'images.tar'
        $partial = $destination + '.partial'
        Invoke-Docker -DockerArgs (@('save','--output',$partial) + $images)
        Move-Item -LiteralPath $partial -Destination $destination -Force
        Write-Utf8 ($destination+'.sha256') ((Get-Sha256 $destination).ToLowerInvariant() + '  images.tar')
        Write-Host "镜像已导出：$destination。把 offline 整个目录放入目标部署包后启动。"
        exit 0
    }
    switch ($Action) {
        'PrepareImages' { Prepare-Images }
        'UpdateImages' { Prepare-Images $true }
        'InitializeConfig' { Initialize-Configuration }
        'Start' {
            Require-PreparedImages
            foreach ($file in @('private/settings.json','data/astrbot/cmd_config.json','data/napcat/webui.json')) {
                if (-not (Test-Path -LiteralPath (Join-Path $Root $file))) { throw '请先运行“导入初始配置.cmd”。' }
            }
            Invoke-Compose @('up','-d','--no-build','--pull','never','ollama')
            if (-not (Wait-Ollama)) { throw '本地记忆向量服务未就绪，请查看日志。' }
            $modelProbe = Get-DockerProbe ((Get-ComposeArgs) + @('exec','-T','ollama','ollama','show','bge-m3'))
            if ($modelProbe.ExitCode -ne 0) { throw 'bge-m3 尚未准备好，请运行“下载准备镜像.cmd”。' }
            Invoke-Compose @('up','-d','--no-build','--pull','never')
            $astrReady = Wait-Panel $script:Instance.astrbot_port
            $napReady = Wait-Panel $script:Instance.napcat_port '/webui'
            if (-not $astrReady -or -not $napReady) { throw '部分面板尚未就绪，请用“查看日志.cmd”检查；服务及数据已保留。' }
            Write-Host '两个管理面板已就绪。请在 NapCat 扫码登录，之后用主人 QQ 私聊机器人测试。' -ForegroundColor Green
            Write-Host '面板账号和 Token 位于 private/面板登录信息.txt。此检查不代表 QQ 收发消息已验收。'
            if (-not $NoBrowser) {
                Start-Process (Join-Path $Root 'private/面板登录信息.txt')
                Start-Process ('http://127.0.0.1:'+$script:Instance.napcat_port+'/webui')
                Start-Process ('http://127.0.0.1:'+$script:Instance.astrbot_port)
            }
        }
        'Stop' { Invoke-Compose @('stop'); Write-Host '服务已停止，聊天记录和登录状态保留。' }
        'Status' { Invoke-Compose @('ps'); Write-Host 'QQ 在线与反向连接状态请查看 NapCat 面板；模型状态请在 AstrBot 测试。' }
        'Logs' { Invoke-Compose @('logs','--tail','150','-f') }
        'InstallMemePacks' { Invoke-CompanionMaintenance 'install_meme_packs.py' }
        'ConfigureSearch' { Invoke-CompanionMaintenance 'deepseek_search.py' }
        'FixNapCatDns' { Set-NapCatDns }
        'RestoreNapCatDns' { Set-NapCatDns $true }
        'UpgradeCompanion' { Invoke-CompanionMaintenance 'upgrade_companion.py' }
        'ImportMemes' {
            $inputArchive = Read-Host '请输入你自己的 AstrBot 备份 ZIP 完整路径（只导入表情图片）'
            $inputArchive = $inputArchive.Trim().Trim('"')
            if (-not (Test-Path -LiteralPath $inputArchive -PathType Leaf) -or [IO.Path]::GetExtension($inputArchive) -ne '.zip') {
                throw '没有找到有效的 ZIP 文件。'
            }
            $privateDirectory = Join-Path $Root 'private'
            New-Item -ItemType Directory -Force -Path $privateDirectory | Out-Null
            Copy-Item -LiteralPath $inputArchive -Destination (Join-Path $privateDirectory 'meme-import.zip') -Force
            Invoke-CompanionMaintenance 'import_meme_library.py'
        }
        'Backup' {
            $running = @(& docker @((Get-ComposeArgs) + @('ps','--status','running','--services')))
            if ($LASTEXITCODE -ne 0) { throw '读取运行状态失败。' }
            $backupDir = Join-Path $Root 'backups'
            New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
            $destination = Join-Path $backupDir ('大肥鱼-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.zip')
            Invoke-Compose @('stop')
            try {
                Write-DataBackup $destination
                Write-Host "备份已保存：$destination（含密钥和 QQ 登录信息，请妥善保存）"
            } finally {
                $running = @($running | Where-Object { $_ -in @('astrbot','napcat','ollama') })
                if ($running.Count -gt 0) { Invoke-Compose (@('start') + $running) }
            }
        }
    }
    exit 0
} catch {
    Write-Host ("未完成：" + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
