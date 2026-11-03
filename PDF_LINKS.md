# 专利原文与画像关联

画像库：`wang10086-creator/chcnav-patent-atlas`；原文件库：`wang10086-creator/chcnav-patent-pdfs`。

## 对应规则与用户入口

`site-overrides/data/pdf-index.json` 是两库的对应清单，以完整公开号为键，记录申请号、原文件相对路径、源仓库 commit、Git blob SHA、SHA-256 和字节大小。严格区分 A/B/U/S 文献，不按申请号回退，不自动把授权版当作公开版。

技术路径引用、全部文献列表、专利详情提供“阅读 PDF”和“下载 PDF”。阅读指向 GitHub 文件预览，下载指向原始文件；中文文件名分段编码。两者均固定到清单中的 commit，源库后来改名或更新不会悄悄替换已有证据。原来的文献来源、摘要、权利要求文本、图片和分析继续保留。

PDF 取得不等于正文已经逐页核验，也不改变既有法律状态与外观视图核验口径。索引加载失败只显示提示，已有画像仍可浏览；未匹配版本不会错误借用同申请其他版本。

## 2026-11-03 关联核验

- PDF 来源 commit：`f14c181a8665bd58a335201f7c1fd92cd10867a0`。
- 938 份文件，683,731,328 字节；对应 938 条文献、807 个申请，缺失／重复／多余均为 0。
- 全量文件通过已提交 Git 字节、PDF 头尾标识及 SHA-256 检查。首页可提取文字的 736 份包含对应公开号；202 份首页无可提取文字，按文件名公开号匹配，未进行 OCR 或逐页正文核验。
- Chromium 检查全部 938 条详情生成的 PDF 阅读与下载链接，验证 A/B 版本分离；桌面列表和详情抽屉、390px 手机 A/B/U/S 详情正常，无横向溢出、无页面脚本错误。
- PDF 索引 404、格式不完整、未知文献与申请元信息不一致的情况均未产生错误 PDF 链接；已有画像继续可用。
- 抽样实际访问 GitHub 文件页面及原始 PDF 地址成功。此结果不代表用户当前网络条件或 GitHub 预览服务在所有设备上的可用性。

## 发布构建

原始五 ZIP 与 `site-manifest.json` 保持不变。`verify_extract.py` 先验证全部 989 个基线文件，再逐项验证并应用 `site-overrides-manifest.json` 中登记的静态文件，并执行 PDF 对应与原始数据保留检查。现有 Pages workflow 仍使用该构建脚本；发布目录为 `_site/`。源码和清单保存在仓库中，无须重新上传数百 MB 的 PDF 或重打原 ZIP。

本地构建及检查：

```sh
python3 verify_extract.py
python3 scripts/check_pdf_links.py
node --check _site/atlas.js
python3 -m http.server 8000 --bind 127.0.0.1 --directory _site
```

`verify_extract.py` 要求 `_site/` 不存在，重复构建时请先确认并移走旧构建目录。

## 更新 PDF 批次

在独立目录取得原文件库的目标 commit，并检出该批 PDF，确保工作区干净。在画像库执行：

```sh
python3 scripts/build_pdf_index.py --pdf-repo ../pdf-repository --site _site
python3 scripts/update_override_manifest.py
```

生成器核对全量公开号、重复与缺失、PDF 头/尾标识、Git 已提交字节、SHA-256。出现任何未匹配或重复即停止，不生成部分成功的索引。该检查不能代替逐页正文、权利要求版本或法律核验。更新后审阅对应清单差异，再重新构建检查并通过 PR 发布。
