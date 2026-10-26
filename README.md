# QQ 大肥鱼一键部署包

将 AstrBot、NapCat、DeepSeek API、长期记忆与主动陪伴接到 QQ。面向 Windows 用户，提供首次配置和之后的一键启动入口。

**[下载最新版部署包](https://github.com/jgbrzzh/DSdeploy/releases/latest) · [完整操作流程](docs/操作流程.md) · [验证范围](docs/验证记录.md) · [隐私说明](docs/隐私与发布范围.md)**

Windows 10/11（支持 WSL2 的版本），Docker Desktop 的 Linux 容器模式。
组合：NapCat 登录机器人 QQ → AstrBot → DeepSeek 官方 API；LivingMemory 长期记忆 + Proactive Chat 主动陪伴；Ollama + bge-m3 本地记忆向量。
默认模型名 `deepseek-flash`，对应官方当前 V4.1 Flash 接口；支持首次配置时改为其他兼容接口与模型。

## 第一次使用

1. 将整个部署包解压到固定目录，例如 `D:\QQ大肥鱼`。不要直接在压缩包内运行。
2. 没装 Docker Desktop 时，双击 `安装Docker.cmd`。安装器下载到包内，程序安装到 `runtime/DockerDesktop`，WSL 数据盘定向到 `data/docker-desktop`。根据安装器完成 WSL2/虚拟化设置；需要重启时先重启。打开 Docker Desktop，等待引擎运行。
3. 双击 `一键启动.cmd`，输入你的 QQ、机器人小号 QQ、API 地址、模型名、API Key。Key 输入时隐藏，只保存在本机文件中。
4. 脚本下载三个上游镜像，固定摘要，构建含插件依赖的 AstrBot 运行环境，并下载 bge-m3（约 1.2 GB）。自动设置模型、主人权限、OneBot、人格、长期记忆和主动陪伴，并打开两个面板。
5. `private/面板登录信息.txt` 包含 AstrBot 账号/初始密码和 NapCat Token。在 NapCat 面板输入 Token，**扫码登录你刚填的机器人小号**。
6. 用主人 QQ 加机器人为好友并私聊：“你好，大肥鱼”。以 QQ 实际收到回复为验收。只有网页打开、容器运行不算全部成功。

之后直接双击 `一键启动.cmd`。已有配置、人设、聊天记录及登录状态不会被脚本覆盖。
这是首次联网下载的部署器，ZIP 不内置 Docker、QQ、模型权重或第三方镜像；需要可用网络及自备有余额的 API Key。
插件源码和许可证已内置，并记录固定提交与 SHA-256；首次构建需要联网安装其 Python 依赖。依赖受 AstrBot 镜像锁定的要求约束，冲突时会终止构建。
建议电脑至少 8 GB 内存，16 GB 更宽裕；给 Docker 足够内存与磁盘空间。bge-m3 默认使用 CPU，不要求独立显卡。

## 包内入口

| 文件 | 用途 |
|---|---|
| 一键启动.cmd | 首次部署、之后启动并打开面板 |
| 一键停止.cmd | 停止本包服务，保留数据 |
| 查看状态.cmd | 容器状态 |
| 查看日志.cmd | 查看两侧最近日志并持续跟随；Ctrl+C 退出 |
| 环境检查.cmd | 检查文件、Docker、Linux 容器模式和 Compose 配置 |
| 备份数据.cmd | 暂停服务后压缩数据，恢复备份前正在运行的服务 |
| 安装Docker.cmd | 下载并校验官方安装器，定向到包内安装 Docker Desktop |
| 下载镜像包.cmd | 在联网 Docker 电脑导出可带回本包的基础镜像 |

## 文件位置约定

部署器以 `Deploy.ps1` 所在文件夹为根目录，不使用调用者当前目录，也不把项目文件写到桌面或用户文档目录。

- `runtime/downloads`：下载的安装器；`runtime/DockerDesktop`：Docker 程序。
- `runtime/tmp`、`runtime/pip-cache`、`runtime/uv-cache`：脚本临时目录与缓存路径。
- `private/docker-client`：本包 Docker 客户端配置；`data/docker-desktop`：Docker WSL 数据盘，镜像、构建缓存及容器日志保存在其中。
- `data`、`private`、`backups`：业务数据、凭据及备份。

若机器已有其他位置的 Docker，启动器不会自动迁移或重装它；必须先在 Docker Desktop 中把 Disk image location 设为包内 `data/docker-desktop`。未发现包内数据盘时，启动器在拉取镜像前停止。
Docker Desktop/WSL 是 Windows 安装的软件，仍会有注册表、用户设置与系统日志等系统记录；本包不能将这些操作系统记录变成便携文件。此约定约束本包管理的项目文件和大型数据。
首次安装后请固定这个文件夹的位置；Docker 安装位置和数据盘不能只靠移动目录改名迁移。

镜像下载不畅时，可在另一台网络畅通且已运行 Docker 的电脑执行「下载镜像包.cmd」，将生成的 offline 文件夹带回本包。官方链接与手动导出步骤见 `offline/下载说明.md`。插件依赖和本地向量模型仍有首次联网下载步骤。

镜像下载默认使用 DaoCloud 国内入口 `docker.m.daocloud.io`，仅改变本包拉取地址，不修改整台电脑的 Docker 镜像源设置。需要切换时可运行 `powershell -File .\Deploy.ps1 -ImageSource 1ms` 或 `-ImageSource Official`。首次锁定版本后，继续沿用已记录的镜像地址。
如果网络使用 Fake-IP DNS，本包会在首次下载 bge-m3 前检查 Ollama 官方仓库和它返回的 Cloudflare 模型 CDN 域名；仅在解析到非公网地址时，通过 AliDNS HTTPS 查询获得公网 IPv4，并在 `compose.dns.json` 中为本包 Ollama 容器设置 hosts 映射。不改系统 DNS，不关闭 Ollama 的地址校验。

## 管理与扩展

- AstrBot：<http://127.0.0.1:6185>，用户名 `astrbot`，密码由部署器随机生成。
- NapCat：<http://127.0.0.1:6099/webui>，Token 随机生成。
- 反向 WebSocket 已设置为 `ws://astrbot:6199/ws`，双方共享随机连接密钥。不要改成容器内的 `127.0.0.1`。
- 默认只允许主人私聊；群聊未放行。要开启群聊，在 AstrBot 白名单中按面板说明添加群，再使用 @ 或“大肥鱼”唤醒。
- 在 AstrBot 的“人格”中编辑 `dafeiyu`。`bootstrap/persona.txt` 只用于首次初始化。
- 更换模型/Key：在 AstrBot 面板修改并保存。`private/settings.json` 是首次初始化输入，启动器不会将它覆盖回面板。
- 已安装 **LivingMemory 2.7.3**：每 10 轮对话触发总结，支持主动保存/召回；通过本地 bge-m3 进行语义检索。按人格和会话隔离记忆，初始只为主人私聊启用。
- 已安装 **Proactive Chat v1.2.6**：仅给主人私聊主动发消息；常规间隔 120–240 分钟，23:00–08:00（北京时间）免打扰，最多 1 次未回复主动消息。启动后启用 60 分钟自动任务检查；实际发信时间还受随机间隔、QQ 在线与上游调度影响。
- 在 AstrBot 插件配置中可以调整主动间隔、免打扰、会话名单或关闭主动消息。默认关闭群主动消息、TTS、插件独立管理服务器、遥测与更新通知轮询。
- 未加入语音、B 站浏览和手机控制。聊天、总结和主动消息都会消耗你配置的模型 API 额度；向量计算在本机执行，但用于总结的对话和检索到的记忆仍可能发给聊天模型。
- 本包不依赖 DSH；DeepSeek 聊天模型通过 API 调用，不在本机下载其权重。记忆检索用的 bge-m3 则会下载到本机。

## 数据与恢复

`data/astrbot` 保存 AstrBot 配置、聊天数据库、插件源码与记忆/陪伴数据；`data/napcat` 保存连接配置；`data/qq` 保存 QQ 登录状态；`data/ollama` 保存本地记忆模型。
`private` 保存首次配置、构建状态和凭据；`compose.lock.json` 保存三个上游镜像摘要。不要将这些目录、日志或备份上传到公开仓库。

备份保存在 `backups`，保留 `data/astrbot`、`data/napcat`、`data/qq`、`private` 和镜像版本锁的原相对路径；不备份正在使用的 Docker 虚拟磁盘、镜像缓存或可重新下载的 Ollama 模型。
恢复时先停止服务，将上述三个业务数据目录与 `private` 改名留存，将备份解压到部署包根目录，再启动；同名 `compose.lock.json` 也从备份恢复。不要移动或替换 `data/docker-desktop`。
失败的备份保留为 `.partial`，不会伪装为已完成的 ZIP。

启动器不会自动更新版本。需要更新时先备份，再将 `compose.lock.json` 改名留存，重新启动会拉取新镜像并生成新的版本锁。
回退除了恢复旧镜像锁，也应恢复配套数据备份，因为上游升级可能迁移数据库。
同一台机器默认只运行一份本包（固定项目名 `dsdeploy`，固定端口 6185/6099）。

## 排查

- 提示没有 Docker：安装 Docker Desktop 并启动；若安装后仍提示缺失，重新打开启动器。
- 提示 Linux containers：在 Docker Desktop 菜单切换到 Linux 容器。
- 拉取失败：默认已使用 DaoCloud；可用 ImageSource 参数切换为毫秒镜像或原站，或导入本地镜像。不会修改整机的 Docker 镜像源配置。
- 端口占用：先停止占用 6185/6099 的旧部署，不要删除其数据。
- NapCat 已登录但机器人不回答：先确认登录的是填写的小号；检查反向 WS 是否连接成功、URL 和双方 Token 是否一致。再在 AstrBot 面板单独测试模型。
- API 401：Key 或 API 地址错误；余额不足的 429 需要检查余额，不能只按限流处理。
- 主人私聊成功后再放行群和其他用户。QQ 登录/设备验证由 QQ 本身完成。
- 默认没有开放宿主机命令执行，初始人格仅挂载两个记忆工具。第三方插件按需在 AstrBot 中安装。

## 长期记忆和主动陪伴验收

1. 在 AstrBot 插件列表确认 LivingMemory 和 Proactive Chat 加载成功，模型列表中有 `bge_m3_local`。
2. 在 QQ 私聊中发送 `/lmem status`，检查记忆系统状态；告诉大肥鱼一个偏好，并明确要求“请记住”。在 LivingMemory 的插件页面中确认确实出现了记忆。
3. 在 AstrBot 中新建同一 QQ 会话的新对话，再问刚才的偏好，验证不是仅靠旧聊天上下文回答。重启服务后再测一次。
4. 在 Proactive Chat 配置中暂时将间隔调短，选非免打扰时段，在 QQ 中确认实际收到主动消息；之后恢复 120–240 分钟。用插件状态/日志确认未回复上限与静默时段。
5. 本包已完成真实容器构建、插件加载、1024 维向量计算、测试记忆导入与重启后召回、主动调度器初始化和备份验证；**QQ 登录/收发、真实 DeepSeek 对话、对话自动总结及主动消息到达 QQ** 仍需要你的账号与 API Key 完成端到端验收。详见 `docs/验证记录.md`。

## 核对来源

- [AstrBot 官方 Docker 部署](https://docs.astrbot.app/deploy/astrbot/docker.html)
- [AstrBot 源代码](https://github.com/AstrBotDevs/AstrBot)
- [NapCat Docker 官方仓库](https://github.com/NapNeko/NapCat-Docker)
- [DeepSeek 官方 API 入门](https://api-docs.deepseek.com/quick_start/agent_integrations/)
- [LivingMemory 源码与许可](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory)
- [Proactive Chat 源码与许可](https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat)
- [Ollama bge-m3 模型](https://ollama.com/library/bge-m3)
- [B 站相关部署演示](https://www.bilibili.com/video/BV1x2Jq6NEbT/)

实现依据及本地验证边界见 `docs/验证记录.md`。本包包含部署脚本、原创简短人格及未修改的第三方插件源码归档；插件各自的 AGPL-3.0 许可证保存在源码包内，出处见 `vendor/manifest.json`。其他上游程序通过其官方镜像下载，各自许可不变。

本项目自身采用 [AGPL-3.0](LICENSE)，第三方归属见 [NOTICE.md](NOTICE.md)。维护、检查和发布步骤见 [维护与发布](docs/维护与发布.md)。
