# 华测导航专利画像：开发预览与维护

本分支基于现有全量站点开发，未合并生产分支、未触发生产发布。原网站和 PDF 仓库访问方式保持不变。

## 本次实现

- 产品类型仍为主入口，保持产品 → 方法／结构／外观 → 技术路径 → 子路径 → 多件引用专利。路径与子路径按去重申请数排序，展示排序依据，不将数量视为专利重要性或有效性结论。
- 首屏增加所选产品、具体产品／系列及官网图片与来源提示；研发速览优先展示技术方向，知识产权核对层展开每件专利独立的权项组合、关系、限制、版本、状态与原文。
- 外观 PDF 按完整公开号和文献版本核对内部编号，逐页渲染，保留封面、说明、图页与所有其他实际页面。能够可靠定位的视图另提供带标号裁图，不能自动分离时保留原页。
- 外观页面显示按需加载的缩略图，可放大、切换、原尺寸查看并链接 PDF 对应页。页面覆盖、自动标签核对、助手视觉复核、人工逐图复核与法律范围分析分别标明，不能互相替代。
- 新增「专利监控」页面，真实支持 CSV／XLSX 导入、本地 SHA-256、状态观察和变化、新申请和同申请新文献版本比对，结果先下载供人工核对。不会向服务器上传导入文件或直接改写正式数据。

## 当前限制

Incopat 指定入口在当前云端浏览器环境被 HTTPS 代理以 403 拒绝，浏览器记录 `ERR_TUNNEL_CONNECTION_FAILED`。尚未到达登录页，登录、机构授权、验证码、检索、分页和导出均未验收。当前没有可安全接管的交互式授权浏览器，也没有已接通的可靠定时执行端。页面明确显示「云执行端尚未接通」，没有模拟运行结果。

后续自动执行应复用用户已有、具备安全接管能力的云电脑：先由用户在其安全登录界面完成授权，再验收检索和完整导出；凭据只能保存在该执行端的私有存储，不能进入公开仓库。未取得上述能力前，使用手动导入流程。详细字段、流程、测试和后续执行验收见 `MONITORING.md`。

新增视图仅补充证据，不自动升级既有摘要解读为完整外观权利范围结论，不确认当前法律有效性或官网产品实施关系。

## 数据保护与构建

原五 ZIP、原始 SHA-256 清单、全部原始数据、807 件申请分析、944 张旧图及其证据链接保持字节不变；原页面脚本仍可从 ZIP 追溯。新增 HTML／JS 展示层和新图片单独登记在 `site-overrides/` 与 `site-overrides-manifest.json`。938 份 PDF 的对应清单和来源 commit 保持不变。

`verify_extract.py` 先完整校验原始基线，再应用经校验的静态覆盖。重复构建需要先将旧 `_site/` 移到独立备份目录，脚本不会覆盖已有构建目录。

```sh
python3 scripts/update_override_manifest.py
python3 verify_extract.py
python3 scripts/check_pdf_links.py
python3 scripts/check_preservation_upgrade.py --pdf-repo ../pdf-repository --json-output ../preservation-after.json
python3 scripts/check_design_views.py --site _site --pdf-repo ../pdf-repository
node --check _site/atlas.js
python3 -m http.server 8001 --bind 127.0.0.1 --directory _site
```

开发阶段的 PDF 渲染与深度图像验证使用 PyMuPDF、Pillow 和完整 PDF checkout；已有图片的静态构建与部署校验只使用 Python 标准库，不要求生产构建下载全部 PDF 或安装图像工具。

当前 GitHub Actions 仅在 main push 或手动触发时部署。未经用户确认，不推送 main、合并或手动触发该工作流。

## 统计、核验与容量

核对口径见 `reports/` 中的设计逐件 CSV、视图汇总及验证记录，以及工作区中的原资料保护和整体验证记录。原始外观摘要图 152 张保留，新增原页／裁图不与它们混计为「原有全视图」。缩略图文件数、原页图文件数、裁图数和 PDF 中列明的视图数分别统计。

官方 Pages 发布站点上限为 1 GB，月流量有 100 GB 软限额；本次用完整构建产物实际字节数评估，PDF 仍由原 PDF 仓库提供，不重复复制进画像站。依据：[GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)。

## 预览

完整预览包保留实际全量站点，不是样例。解压后运行包内 `preview.py`，在本机打开其打印的 localhost 地址；不要直接双击 index.html，浏览器的 file 协议不能可靠读取 JSON。预览中的原 PDF／外部证据入口仍指向现有在线来源。
