# 第三方源码归档

源码 ZIP 来自对应上游固定提交，保留完整源码、上游文档与许可信息，不含本地配置、密钥或运行数据。首两个归档由 git archive 生成，后两个由 GitHub 对应提交的源码包去除顶层目录后重新封装，未改动源码内容。
精确版本、仓库、提交与 SHA-256 见 manifest.json。构建时先校验摘要再解压。

- LivingMemory，作者 lxfight，AGPL-3.0： https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory
- Proactive Chat，作者 DBJD-CR，AGPL-3.0： https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat
- meme_manager，作者 anka，MIT： https://github.com/anka-afk/astrbot_plugin_meme_manager
- 积分签到，作者小星萤，MIT 声明见上游 README： https://github.com/firefiy99/astrbot_plugin_signin

源码未修改。构建时安装各自 requirements.txt，并固定 AstrBot 基础镜像已安装的依赖版本；依赖冲突时停止构建。运行时仅生成用户自己的插件配置文件。
