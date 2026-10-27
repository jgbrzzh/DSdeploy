# Per-directory identity; never discovers or changes another deployment.
function Initialize-Instance {
    $path = Join-Path $Root 'private/instance.json'
    if (-not (Test-Path -LiteralPath $path)) {
        if ((Test-Path -LiteralPath (Join-Path $Root 'data/astrbot/cmd_config.json')) -and -not ($Action -eq 'ConfigureInstance' -and $AdoptData)) {
            throw '检测到旧部署数据。请保留旧目录，将新版解压到新目录。已备份并复制的数据可用 -Action ConfigureInstance -AdoptData 为副本建立新实例。'
        }
        $normalized = [IO.Path]::GetFullPath($Root).TrimEnd('\','/').ToLowerInvariant()
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $digest = $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalized)) } finally { $hasher.Dispose() }
        $id = ([BitConverter]::ToString($digest)).Replace('-','').ToLowerInvariant().Substring(0,10)
        $astrPort = if ($AstrBotPort) { $AstrBotPort } else { 20000 + ([BitConverter]::ToUInt16($digest,0) % 9000) }
        $napPort = if ($NapCatPort) { $NapCatPort } else { 30000 + ([BitConverter]::ToUInt16($digest,2) % 9000) }
        $busyPorts = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | ForEach-Object { $_.Port })
        if (-not $AstrBotPort) { while ($astrPort -in $busyPorts) { $astrPort = 20000 + (($astrPort - 20000 + 1) % 9000) } }
        if (-not $NapCatPort) { while ($napPort -in $busyPorts) { $napPort = 30000 + (($napPort - 30000 + 1) % 9000) } }
        if ($astrPort -eq $napPort -or $astrPort -lt 1024 -or $napPort -lt 1024) { throw '面板端口必须不同，且为 1024 到 65535。' }
        $mode = if ($Action -eq 'InstallDocker') { 'local' } else { 'shared' }
        $newInstance = [ordered]@{schema_version=1; root=$normalized; project=('dsdeploy-'+$id); image=('dsdeploy-astrbot-'+$id+':local'); astrbot_port=$astrPort; napcat_port=$napPort; docker_mode=$mode}
        Write-Utf8 $path ($newInstance | ConvertTo-Json)
    }
    $script:Instance = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $currentRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\','/').ToLowerInvariant()
    if ($script:Instance.root -ne $currentRoot) { throw '实例设置属于另一个目录。新实例请只解压程序包，不复制 private/instance.json。迁移副本请先将该文件改名保留，再创建新实例。' }
    if ($script:Instance.project -notmatch '^dsdeploy-[a-f0-9]{10}$' -or $script:Instance.image -ne ('dsdeploy-astrbot-'+$script:Instance.project.Substring(9)+':local')) { throw '实例名称或镜像标签无效。' }
    foreach ($port in @($script:Instance.astrbot_port,$script:Instance.napcat_port)) {
        if ($port -lt 1024 -or $port -gt 65535) { throw '实例面板端口无效。' }
    }
    if ($script:Instance.astrbot_port -eq $script:Instance.napcat_port) { throw '实例面板端口不能相同。' }
    foreach ($relative in @('data','data/astrbot','data/napcat','data/qq','data/ollama','private','backups')) {
        $target = Join-Path $Root $relative
        if (Test-Path -LiteralPath $target) {
            $item = Get-Item -LiteralPath $target -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '隔离业务目录不能是链接。' }
        }
    }
    $env:DSDEPLOY_PROJECT = $script:Instance.project
    $env:DSDEPLOY_ASTRBOT_IMAGE = $script:Instance.image
    $env:DSDEPLOY_ASTRBOT_PORT = [string]$script:Instance.astrbot_port
    $env:DSDEPLOY_NAPCAT_PORT = [string]$script:Instance.napcat_port
    $addressText = "实例：$($script:Instance.project)`r`nAstrBot: http://127.0.0.1:$($script:Instance.astrbot_port)`r`nNapCat: http://127.0.0.1:$($script:Instance.napcat_port)/webui`r`n本目录独立保存配置、数据与备份；仅管理此实例的容器。"
    Write-Utf8 (Join-Path $Root 'private/本实例面板地址.txt') $addressText
}
