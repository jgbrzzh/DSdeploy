# DS API 联网搜索与网页正文读取

本版使用 AstrBot 原生 DeepSeek Search API，搜索和 Fetch 直接访问官方服务，不安装另一套搜索插件，也不开启宿主机代码执行。

## 首次配置

“导入初始配置.cmd”使用官方 api.deepseek.com 聊天接口时，会将该官方 Key 同时填入独立的搜索 Key 列表，开启网页搜索和来源链接。AstrBot 的两处配置彼此独立；以后在面板改聊天 Key，不代表搜索 Key 自动同步。

如果聊天使用第三方兼容地址，会另询问 DeepSeek 官方搜索 Key，不把第三方 Key 自动发往 DeepSeek。留空则暂不开搜索，之后在 AstrBot 当前配置文件的 AI → 能力 → 网页搜索中选择 DeepSeek Search API、填写官方 Key 并保存。

## 已有独立实例

运行“配置DS联网搜索.cmd”。先备份本实例，保留已有 DeepSeek 搜索 Key；没有搜索 Key 时，优先采用当前生效模型的官方 DeepSeek Key，最后才参考首次提供的独立搜索 Key。不改聊天模型、QQ、人格或其他实例，不重下镜像。

原 v1.0 目录无需运行此入口；要保留它不动，请只在新版目录配置。

配置对应：web_search=true，websearch_provider=deepseek，websearch_deepseek_key=[本机官方Key]，web_search_link=true。公开包不含真实 Key。

## 试聊验收

- “请先搜索 AstrBot 的最新版本，再回答并附上来源链接。”
- “请阅读这个页面并总结安装步骤：https://docs.astrbot.app/deploy/astrbot/docker.html”

要在日志或对话工具记录中看到 web_search_deepseek / deepseek_fetch_web_page 及实际返回结果，再判断成功；不能只听角色说“我搜过了”。模型自行决定是否调用工具，不要求每句联网。

搜索和网页正文读取单独按官方规则计费，也受账号余额、频率和目标网站访问限制影响。402/429 请分别检查余额和限速；有结果而正文读取失败时先换公开免登录网页。

## 依据与验证边界

- [AstrBot DeepSeek 搜索官方说明](https://docs.astrbot.app/use/websearch/deepseek.html)：可复用同一个官方 Key，但需填写独立搜索配置；支持 Search 与 Fetch。
- [DeepSeek Search API 文档](https://api-docs.deepseek.com/zh-cn/guides/search/)：以官方当前服务规则为准。
- 固定 AstrBot 源码的 core/tools/web_search_tools.py 使用 https://api.deepseek.com/v1/tools/search 和 /v1/tools/fetch；本包只生成其现有配置。

配置回归覆盖开启搜索、使用当前官方 Key、保留身份及拒绝第三方 Key 自动复用。没有使用私人备份 Key 发起请求，也没有付费 API 的真实联网搜索验收。无需将原始私人备份导入新实例。
