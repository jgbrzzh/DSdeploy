# Windows PowerShell 5.1. Never executes a script from the source directory.
function Get-MigrationValue($Object, [string]$Name, $Default = $null) {
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name) { return $Object.$Name }
    return $Default
}
function Set-MigrationValue($Object, [string]$Name, $Value) {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force
}
function Get-MigrationPath([string]$Path) {
    # Docker Desktop renders bind paths using either Windows or Linux host notation.
    $pathText = $Path.Replace('\','/')
    if ($pathText -match '^/(?:run/desktop/mnt/host|host_mnt|mnt)/([a-zA-Z])/(.*)$') { $pathText = $Matches[1] + ':/' + $Matches[2] }
    return [IO.Path]::GetFullPath($pathText).TrimEnd('\','/').ToLowerInvariant()
}
function Assert-MigrationPath([string]$Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "迁移不接受链接目录或文件：$cursor" }
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}
function Copy-MigrationTree([string]$Source, [string]$Destination, [string]$Relative, $Manifest) {
    Assert-MigrationPath $Source
    $item = Get-Item -LiteralPath $Source -Force
    if ($item.PSIsContainer) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
        foreach ($child in Get-ChildItem -LiteralPath $Source -Force) {
            Copy-MigrationTree $child.FullName (Join-Path $Destination $child.Name) ($Relative + '/' + $child.Name) $Manifest
        }
    } else {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        $hash = Get-Sha256 $Source
        if ($hash -ne (Get-Sha256 $Destination)) { throw "文件复制校验失败：$Relative" }
        $Manifest.Add([pscustomobject]@{path=$Relative; bytes=$item.Length; sha256=$hash})
    }
}
function Get-MigrationDockerJson([string[]]$Arguments) {
    $probe = Get-DockerProbe $Arguments
    if ($probe.ExitCode -ne 0) { throw '无法读取旧部署的 Docker 配置或镜像，请确认旧部署使用的 Docker 引擎已启动。' }
    return (($probe.Output -join [Environment]::NewLine) | ConvertFrom-Json)
}
function Save-MigrationState($State) {
    $content = $State | ConvertTo-Json -Depth 30
    foreach ($path in @((Join-Path $State.transaction 'state.json'),(Join-Path $Root 'migration.json'))) {
        Assert-MigrationPath $path
        $temporary = $path + '.pending'
        Assert-MigrationPath $temporary
        Write-Utf8 $temporary $content
        if (Test-Path -LiteralPath $path) {
            Assert-MigrationPath ($path+'.previous')
            [IO.File]::Replace($temporary,$path,($path+'.previous'))
        }
        else { [IO.File]::Move($temporary,$path) }
    }
}
function Get-MigrationFiles { return @('data','private','compose.lock.json','compose.dns.json','compose.napcat-dns.json','compose.migrated.json') }
function Restore-MigrationSource($State) {
    foreach ($container in @($State.containers)) {
        $policy = [string]$container.restart
        if ($policy -eq 'on-failure' -and $container.retries -gt 0) { $policy += ':' + $container.retries }
        Invoke-Docker @('update',('--restart='+$policy),$container.id)
    }
    foreach ($container in @($State.containers)) {
        if ($container.running) { Invoke-Docker @('start',$container.id) }
    }
}
function Undo-DeploymentMigration {
    $receipt = Join-Path $Root 'migration.json'
    if (-not (Test-Path -LiteralPath $receipt)) { throw '本目录没有可回退的迁移记录。' }
    Assert-MigrationPath $receipt
    $state = Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.status -eq 'rolled-back') { Write-Host '迁移已经回退。'; return }
    $allowedBackup = (Get-MigrationPath (Join-Path $Root 'backups')) + '\'
    if ((Get-MigrationPath $state.target) -ne (Get-MigrationPath $Root) -or -not (Get-MigrationPath $state.transaction).StartsWith($allowedBackup)) { throw '迁移记录不属于本目录。' }
    Assert-MigrationPath $state.transaction
    $env:DOCKER_CONFIG = Join-Path $state.source 'private/docker-client'
    $oldDocker = Join-Path $state.source 'runtime/DockerDesktop/resources/bin'
    if (Test-Path -LiteralPath $oldDocker) { $env:PATH += ';' + $oldDocker }
    Require-Docker
    if ($state.committed) {
        # Stop by the destination's unique label, even if its Compose file is damaged.
        $newIds = Get-DockerProbe @('ps','--all','--quiet','--filter',('label=com.docker.compose.project='+$state.project))
        if ($newIds.ExitCode -ne 0) { throw '无法检查新版容器，暂不恢复旧版，避免重复登录。' }
        foreach ($id in @($newIds.Output | Where-Object { $_ })) {
            $newContainer = @(Get-MigrationDockerJson @('inspect',$id))[0]
            $workingDirectory = Get-MigrationValue $newContainer.Config.Labels 'com.docker.compose.project.working_dir' ''
            if (-not $workingDirectory -or (Get-MigrationPath $workingDirectory) -ne (Get-MigrationPath $Root)) { throw '新版项目名称被其他目录使用，停止回退，避免误停其他容器。' }
            Invoke-Docker @('update','--restart=no',$id)
            Invoke-Docker @('stop','--time','60',$id)
        }
        $retained = Join-Path $state.transaction 'new-version-retained'
        New-Item -ItemType Directory -Path $retained -Force | Out-Null
        foreach ($relative in Get-MigrationFiles) {
            $current = Join-Path $Root $relative
            $saved = Join-Path $state.transaction ('target-before/' + $relative)
            $retainedPath = Join-Path $retained $relative
            Assert-MigrationPath $current
            Assert-MigrationPath $saved
            if (Test-Path -LiteralPath $saved) {
                if (Test-Path -LiteralPath $current) {
                    if (Test-Path -LiteralPath $retainedPath) { throw '回退记录存在冲突，请保留目录并检查，避免覆盖。' }
                    Move-Item -LiteralPath $current -Destination $retainedPath
                }
                Move-Item -LiteralPath $saved -Destination $current
            } elseif ($relative -in @($state.installed) -and -not (Test-Path -LiteralPath $retainedPath)) {
                if (Test-Path -LiteralPath $current) { Move-Item -LiteralPath $current -Destination $retainedPath }
            }
        }
        if ($state.target_image) { Invoke-Docker @('tag',$state.target_image,$state.image) }
    }
    Restore-MigrationSource $state
    $state.status = 'rolled-back'
    Save-MigrationState $state
    Write-Host '已回退迁移，并恢复旧版原来的运行状态。新版副本仍保存在迁移备份中。' -ForegroundColor Green
}
function Invoke-DeploymentMigration([string]$SourceDirectory) {
    if (-not $SourceDirectory) { $SourceDirectory = Read-Host '请粘贴旧版部署包所在文件夹（可直接拖入文件夹）' }
    $SourceDirectory = [IO.Path]::GetFullPath($SourceDirectory.Trim().Trim('"')).TrimEnd('\','/')
    Assert-MigrationPath $Root
    Assert-MigrationPath $SourceDirectory
    $sourcePath = Get-MigrationPath $SourceDirectory
    $targetPath = Get-MigrationPath $Root
    if ($sourcePath -eq $targetPath -or $sourcePath.StartsWith($targetPath+'\') -or $targetPath.StartsWith($sourcePath+'\')) { throw '旧版和新版必须是互不包含的两个目录，不能原地迁移。' }
    if (Test-Path -LiteralPath (Join-Path $Root 'migration.json')) { throw '本目录已有迁移记录。请使用已迁移的实例；如要重新迁移，请将新版解压到另一个空目录。' }
    foreach ($relative in @('compose.yaml','data/astrbot/cmd_config.json','data/napcat/webui.json','private/settings.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $SourceDirectory $relative) -PathType Leaf)) { throw "旧版目录缺少 $relative，请选择完整的部署包目录。" }
    }
    foreach ($relative in @('data/astrbot','data/napcat','data/qq','data/docker-desktop')) {
        $path = Join-Path $Root $relative
        if ((Test-Path -LiteralPath $path) -and @(Get-ChildItem -LiteralPath $path -Force).Count) { throw '新版目录已有业务数据或 Docker 数据盘。请将新版解压到另一个空目录后迁移，不会覆盖已有机器人。' }
    }
    $sourceInstance = Join-Path $SourceDirectory 'private/instance.json'
    $oldProject = 'dsdeploy'
    $oldImage = 'dsdeploy-astrbot:local'
    $sourceVariables = @{}
    foreach ($name in @('DSDEPLOY_PROJECT','DSDEPLOY_ASTRBOT_IMAGE','DSDEPLOY_ASTRBOT_PORT','DSDEPLOY_NAPCAT_PORT')) { $sourceVariables[$name] = [Environment]::GetEnvironmentVariable($name) }
    if (Test-Path -LiteralPath $sourceInstance) {
        $oldInstance = Get-Content -LiteralPath $sourceInstance -Raw -Encoding UTF8 | ConvertFrom-Json
        if ((Get-MigrationPath $oldInstance.root) -ne $sourcePath -or $oldInstance.project -notmatch '^dsdeploy-[a-f0-9]{10}$') { throw '旧实例身份与所选目录不一致，请选择原来正常运行的目录。' }
        $oldProject = $oldInstance.project
        $oldImage = $oldInstance.image
        $env:DSDEPLOY_ASTRBOT_PORT = [string]$oldInstance.astrbot_port
        $env:DSDEPLOY_NAPCAT_PORT = [string]$oldInstance.napcat_port
    } else {
        $env:DSDEPLOY_ASTRBOT_PORT = $null
        $env:DSDEPLOY_NAPCAT_PORT = $null
    }
    $env:DSDEPLOY_PROJECT = $oldProject
    $env:DSDEPLOY_ASTRBOT_IMAGE = $oldImage
    $env:DOCKER_CONFIG = Join-Path $SourceDirectory 'private/docker-client'
    $oldDocker = Join-Path $SourceDirectory 'runtime/DockerDesktop/resources/bin'
    if (Test-Path -LiteralPath $oldDocker) { $env:PATH += ';' + $oldDocker }
    try {
        Require-Docker
        $sourceBase = if (Test-Path -LiteralPath (Join-Path $SourceDirectory 'compose.migrated.json')) { 'compose.migrated.json' } else { 'compose.yaml' }
        $sourceCompose = @('compose','--project-name',$oldProject,'--project-directory',$SourceDirectory,'-f',(Join-Path $SourceDirectory $sourceBase))
        foreach ($extra in @('compose.lock.json','compose.dns.json','compose.napcat-dns.json')) {
            $path = Join-Path $SourceDirectory $extra
            if (Test-Path -LiteralPath $path) { Assert-MigrationPath $path; $sourceCompose += @('-f',$path) }
        }
        $config = Get-MigrationDockerJson ($sourceCompose + @('config','--format','json'))
        $sourceConfigJson = $config | ConvertTo-Json -Depth 60
    } finally {
        foreach ($name in $sourceVariables.Keys) { [Environment]::SetEnvironmentVariable($name,$sourceVariables[$name]) }
    }
    $services = @($config.services.PSObject.Properties.Name)
    if (@($services | Sort-Object) -join ',' -ne 'astrbot,napcat,ollama') { throw '检测到额外或缺失的 Compose 服务，无法保证所有外部数据完整迁移，已停止。' }
    if (Get-MigrationValue $config 'volumes') { throw '检测到自定义 Docker 数据卷；本入口不会静默遗漏外部卷。' }
    if ((Get-MigrationValue $config 'configs') -or (Get-MigrationValue $config 'secrets')) { throw '检测到自定义 Compose configs/secrets，需要单独核对外部文件，已停止。' }
    $sourceVersion = if (Test-Path -LiteralPath (Join-Path $SourceDirectory 'VERSION')) { (Get-Content -LiteralPath (Join-Path $SourceDirectory 'VERSION') -Raw -Encoding UTF8).Trim() } else { '1.0-compatible-layout' }
    $containers = [Collections.Generic.List[object]]::new()
    $sourceIds = Get-DockerProbe @('ps','--all','--quiet','--filter',('label=com.docker.compose.project='+$oldProject))
    if ($sourceIds.ExitCode -ne 0) { throw '无法枚举旧版容器。' }
    $serviceImages = @{}
    foreach ($id in @($sourceIds.Output | Where-Object { $_ })) {
        $container = @(Get-MigrationDockerJson @('inspect',$id))[0]
        $labels = $container.Config.Labels
        $working = Get-MigrationValue $labels 'com.docker.compose.project.working_dir' ''
        if (-not $working -or (Get-MigrationPath $working) -ne $sourcePath) { throw '同名旧项目实际属于另一个目录，已停止，避免误停其他机器人。' }
        $service = Get-MigrationValue $labels 'com.docker.compose.service'
        if ($service -notin $services -or $serviceImages.ContainsKey($service)) { throw '旧项目存在额外容器或同服务多副本，请先核对部署。' }
        foreach ($port in @(Get-MigrationValue $config.services.$service 'ports' @())) {
            $bindings = @(Get-MigrationValue $container.HostConfig.PortBindings ($port.target.ToString()+'/'+$port.protocol) @())
            if (-not @($bindings | Where-Object { $_.HostPort -eq [string]$port.published -and $_.HostIp -eq $port.host_ip }).Count) { throw '旧容器实际端口与旧配置不一致，无法保证原地址不变，已停止。' }
        }
        foreach ($mount in @($container.Mounts)) {
            if ($mount.Type -eq 'bind' -and @('/AstrBot/data','/app/napcat/config','/app/.config/QQ','/root/.ollama') -contains $mount.Destination) {
                $expected = @{ '/AstrBot/data'='data/astrbot'; '/app/napcat/config'='data/napcat'; '/app/.config/QQ'='data/qq'; '/root/.ollama'='data/ollama' }[$mount.Destination]
                if ((Get-MigrationPath $mount.Source) -ne (Get-MigrationPath (Join-Path $SourceDirectory $expected))) { throw '旧容器的业务挂载不属于所选目录，已停止。' }
            }
        }
        $serviceImages[$service] = $container.Image
        $containers.Add([pscustomobject]@{id=$id;service=$service;running=[bool]$container.State.Running;restart=$container.HostConfig.RestartPolicy.Name;retries=$container.HostConfig.RestartPolicy.MaximumRetryCount})
    }
    foreach ($service in $services) {
        $svc = $config.services.$service
        if (Get-MigrationValue $svc 'container_name') { throw '旧配置设置了固定容器名，无法安全并存旧容器，已停止。' }
        if (-not $serviceImages.ContainsKey($service)) {
            $image = @(Get-MigrationDockerJson @('image','inspect',$svc.image))[0]
            $serviceImages[$service] = $image.Id
        }
        # Resolve immutable IDs before any interruption; no latest pulls or plugin initialization.
        $null = Get-MigrationDockerJson @('image','inspect',$serviceImages[$service])
        foreach ($volume in @($svc.volumes)) {
            if ($volume.type -ne 'bind') { throw '旧配置含命名卷或临时卷，不能保证复制完整，已停止。' }
            $bindPath = Get-MigrationPath $volume.source
            if (-not $bindPath.StartsWith($sourcePath+'\')) { throw '旧配置包含部署目录外的挂载，不能保证复制完整，已停止。' }
            $relative = $bindPath.Substring($sourcePath.Length+1)
            if ($relative -notmatch '^(data|private)(\\|$)' -and $relative -notin @('bootstrap','meme-packs')) { throw "检测到自定义挂载 $relative，请先将其归入 data 后再迁移。" }
            Assert-MigrationPath $volume.source
            $volume.source = Join-Path $Root $relative
        }
        if (Get-MigrationValue $svc 'build') { $svc.build.context = $Root }
    }
    $astrPort = @($config.services.astrbot.ports | Where-Object { $_.target -eq 6185 })
    $napPort = @($config.services.napcat.ports | Where-Object { $_.target -eq 6099 })
    if ($astrPort.Count -ne 1 -or $napPort.Count -ne 1) { throw '旧版面板端口结构不受支持，已停止，避免迁移后地址改变。' }
    # Target identity is new; user-facing ports and every business byte are inherited.
    Initialize-Instance
    $targetIds = Get-DockerProbe @('ps','--all','--quiet','--filter',('label=com.docker.compose.project='+$script:Instance.project))
    if ($targetIds.ExitCode -ne 0 -or @($targetIds.Output | Where-Object { $_ }).Count) { throw '新版目录已有容器，请解压到另一个空目录再迁移。' }
    $script:Instance.astrbot_port = [int]$astrPort[0].published
    $script:Instance.napcat_port = [int]$napPort[0].published
    $script:Instance.docker_mode = 'shared'
    Set-MigrationValue $script:Instance 'docker_bin' (Split-Path -Parent (Get-Command docker).Source)
    $newIdentity = $script:Instance | ConvertTo-Json -Depth 10
    Set-MigrationValue $config 'name' $script:Instance.project
    $networks = Get-MigrationValue $config 'networks'
    if ($networks) {
        foreach ($network in $networks.PSObject.Properties) {
            if (Get-MigrationValue $network.Value 'external' $false) { throw '旧配置使用外部共享网络，需要单独确认，已停止。' }
            Set-MigrationValue $network.Value 'name' ($script:Instance.project+'_'+$network.Name)
        }
    }
    foreach ($service in $services) { $config.services.$service.image = $serviceImages[$service] }
    $config.services.astrbot.image = $script:Instance.image
    $transaction = Join-Path $Root ('backups/migration-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    Assert-MigrationPath $transaction
    New-Item -ItemType Directory -Path $transaction -Force | Out-Null
    $state = [pscustomobject]@{schema=1;status='preparing';source=$SourceDirectory;target=$Root;source_version=$sourceVersion;transaction=$transaction;project=$script:Instance.project;image=$script:Instance.image;target_image='';committed=$false;containers=@($containers.ToArray());moved=@();installed=@();created=(Get-Date -Format o)}
    $priorImage = Get-DockerProbe @('image','inspect',$script:Instance.image,'--format','{{.Id}}')
    if ($priorImage.ExitCode -eq 0) { $state.target_image = [string]$priorImage.Output }
    Save-MigrationState $state
    try {
        Write-Host ('正在迁移旧版 ' + $sourceVersion + '；旧目录保留，配置和记忆不套用新版默认值。') -ForegroundColor Cyan
        # Stop ALL source services, including originally stopped ones; verify none remain running.
        foreach ($container in $state.containers) { Invoke-Docker @('stop','--time','60',$container.id) }
        foreach ($container in $state.containers) {
            $stopped = @(Get-MigrationDockerJson @('inspect',$container.id))[0]
            if ($stopped.State.Running) { throw '旧容器仍在写入数据，未开始复制。' }
        }
        $manifest = [Collections.Generic.List[object]]::new()
        $snapshot = Join-Path $transaction 'source-snapshot'
        foreach ($relative in @('data','private')) {
            New-Item -ItemType Directory -Path (Join-Path $snapshot $relative) -Force | Out-Null
            foreach ($child in Get-ChildItem -LiteralPath (Join-Path $SourceDirectory $relative) -Force) {
                if ($relative -eq 'data' -and $child.Name -eq 'docker-desktop') { continue }
                Copy-MigrationTree $child.FullName (Join-Path $snapshot ($relative+'/'+$child.Name)) ($relative+'/'+$child.Name) $manifest
            }
        }
        Write-Utf8 (Join-Path $transaction 'files.json') (ConvertTo-Json -InputObject @($manifest.ToArray()) -Depth 5)
        Write-Utf8 (Join-Path $transaction 'source-compose.json') $sourceConfigJson
        $before = Join-Path $transaction 'target-before'
        New-Item -ItemType Directory -Path $before -Force | Out-Null
        $state.status = 'switching'
        $state.committed = $true
        Save-MigrationState $state
        foreach ($relative in Get-MigrationFiles) {
            $current = Join-Path $Root $relative
            Assert-MigrationPath $current
            if (Test-Path -LiteralPath $current) {
                # Journal the intent before the move; rollback checks actual existence.
                $state.moved += $relative
                Save-MigrationState $state
                Move-Item -LiteralPath $current -Destination (Join-Path $before $relative)
            }
        }
        foreach ($relative in @('data','private')) {
            $state.installed += $relative
            Save-MigrationState $state
            $copied = [Collections.Generic.List[object]]::new()
            Copy-MigrationTree (Join-Path $snapshot $relative) (Join-Path $Root $relative) $relative $copied
        }
        Write-Utf8 (Join-Path $Root 'private/instance.json') $newIdentity
        $buildState = Join-Path $Root 'private/build-state.json'
        if (Test-Path -LiteralPath $buildState) { Remove-Item -LiteralPath $buildState }
        foreach ($relative in @('compose.migrated.json','compose.lock.json')) { $state.installed += $relative }
        Save-MigrationState $state
        # config output is already interpolated; escape literal dollars before
        # Compose reads it again (credentials and Windows folder names may use $).
        Write-Utf8 (Join-Path $Root 'compose.migrated.json') (($config | ConvertTo-Json -Depth 60).Replace('$','$$'))
        Write-Utf8 (Join-Path $Root 'compose.lock.json') (@{services=@{astrbot=@{image=$script:Instance.image};napcat=@{image=$serviceImages.napcat};ollama=@{image=$serviceImages.ollama}}} | ConvertTo-Json -Depth 6)
        Invoke-Docker @('tag',$serviceImages.astrbot,$script:Instance.image)
        Write-Utf8 $buildState (@{signature=(Get-BuildSignature);origin='migrated-runtime';source_version=$sourceVersion;image_id=$serviceImages.astrbot} | ConvertTo-Json -Depth 5)
        Initialize-Instance
        # The old restart policy is disabled only during cutover; rollback restores it.
        foreach ($container in $state.containers) { Invoke-Docker @('update','--restart=no',$container.id) }
        Invoke-Compose @('config','--quiet')
        Invoke-Compose @('up','-d','--no-build','--pull','never')
        if (-not (Wait-Ollama)) { throw '新版本地向量服务未就绪。' }
        $astrReady = Wait-Panel $script:Instance.astrbot_port
        $napReady = Wait-Panel $script:Instance.napcat_port '/webui'
        if (-not $astrReady -or -not $napReady) { throw '新版面板未就绪，开始回退。' }
        $state.status = 'complete'
        Save-MigrationState $state
        Write-Host '迁移完成。面板地址和登录配置沿用旧版，旧版已停止并关闭容器自动重启。' -ForegroundColor Green
        Write-Host ('完整副本、逐文件校验清单和回退记录：' + $transaction)
        Write-Host '请用原 QQ 检查聊天与旧记忆。QQ 是否保留登录由腾讯决定；如提示扫码，请重新扫码。'
    } catch {
        $failure = $_.Exception.Message
        Write-Host '迁移未完成，正在恢复旧版……' -ForegroundColor Yellow
        try { Undo-DeploymentMigration } catch { Write-Warning ('自动回退未完成：' + $_.Exception.Message + '。请保留所有目录，使用“回退版本迁移.cmd”。') }
        throw $failure
    }
}
