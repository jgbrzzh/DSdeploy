# 第三方源码归档

两个 ZIP 由对应上游固定提交执行 `git archive` 得到，保留完整源码与 LICENSE，不含任何本地配置、密钥或运行数据。
精确版本、仓库、提交与 SHA-256 见 manifest.json。构建时先校验摘要再解压。

- LivingMemory，作者 lxfight，AGPL-3.0： https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory
- Proactive Chat，作者 DBJD-CR，AGPL-3.0： https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat

源码未修改。构建时安装各自 requirements.txt，并固定 AstrBot 基础镜像已安装的依赖版本；依赖冲突时停止构建。运行时仅生成用户自己的插件配置文件。
