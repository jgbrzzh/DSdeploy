# 随包公开表情资源

| 名称 | 图片数 | 上游 | 固定提交 |
|---|---:|---|---|
| 大肥鱼表情包 | 138 | https://github.com/shirachino/astrbot-deepseek-meme-pack | 7b9d61b09ce068cac621ff2c520ecab11d35d967 |
| 菲比啾比表情包 | 101 | https://github.com/shirachino/astrbot-Phoebe-meme-pack | ad942f73d5ec5bdb43a84bbe315efa4d0602117f |

两个上游 manifest.json 均声明 CC0，维护者为 shirachino。保留所有原始图片、预览和 manifest；没有从私人备份发布图片。原清单 source.ref 写 v1.0.0，但上游未提供同名可解析标签，所以实际按上述 main 提交锁定，不能把清单版本号当作存在的 Git 标签。

为符合 GitHub 单文件大小限制，原始文件分装成若干独立 ZIP（不是需要手动合并的分卷压缩包）。安装器自动按 manifest.json 的 SHA-256 校验并组合，图片内容没有转码或修改。上游清单带 UTF-8 BOM；导入时仅将运行目录内的清单规范化为无 BOM JSON，以兼容当前插件分类读取器，随包原始清单仍保留。

新部署运行“导入初始配置.cmd”时自动装入并默认同时选择两个库。已有部署使用“导入内置表情库.cmd”；先备份，不覆盖已有同名包及其修改、不改变已有选择规则。在 meme_manager 管理页的默认/人格/会话绑定中可选一个或同时选两个。

这里只存放可公开的上游资源，不保存聊天、登录、API Key、私人附件或个人选择规则。图库目录单独只读挂载到容器，更新图库不需要重新构建 Docker 镜像。
