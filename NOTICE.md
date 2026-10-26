# 许可、来源与归属

DSdeploy 是部署脚本、配置生成器及操作文档的集合，不是 AstrBot、NapCat、DeepSeek 或下列插件的官方产品。大肥鱼人格为本项目提供的简短角色提示词，不包含第三方画师的角色图片或语音素材。

本项目自身源码以 GNU AGPL v3 发布，见 [LICENSE](LICENSE)。第三方项目各自保留原作者、来源和许可证；本仓库的许可不代替这些许可。

| 组件 | 作者/维护方 | 用法与来源 |
|---|---|---|
| AstrBot | AstrBot Team | 从 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的容器镜像构建运行环境 |
| NapCat | NapNeko 等贡献者 | 使用 [NapCat-Docker](https://github.com/NapNeko/NapCat-Docker) 镜像，QQ 登录由上游完成 |
| Ollama | Ollama 贡献者 | 使用 [Ollama](https://github.com/ollama/ollama) 镜像运行向量模型 |
| BGE-M3 | BAAI 等模型作者 | 通过 [Ollama 模型库](https://ollama.com/library/bge-m3) 下载，保留模型自身许可 |
| LivingMemory | lxfight 与贡献者 | 未修改的 AGPL-3.0 源码归档，见 vendor/manifest.json 及归档内 LICENSE |
| Proactive Chat | DBJD-CR 与贡献者 | 未修改的 AGPL-3.0 源码归档，见 vendor/manifest.json 及归档内 LICENSE |

vendor 中的 ZIP 由上游固定提交执行 `git archive` 得到，包含对应版本的完整源码、上游说明与许可证，不含本项目使用者的配置或运行数据。精确版本、提交和 SHA-256 记录在 [vendor/manifest.json](vendor/manifest.json)。用户可直接解压检查源码。

Docker、QQ、聊天模型和第三方镜像不会打包进小体积部署 ZIP。它们由用户在实际部署时下载或自行导入，适用各自的条款和许可。
