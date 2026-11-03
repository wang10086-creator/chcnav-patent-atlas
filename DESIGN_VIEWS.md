# 外观设计原页与视图证据

## 当前核查结果

本批 152 件外观文献与既有 PDF 对应索引逐件按完整公开号关联。全部 152 件的 PDF 首页正文均包含对应完整公开号；PDF 字节与原关联清单 SHA-256 一致，无未确认身份、重复或缺失。

- 完整 PDF：552 页；全部保留 180 dpi RGB 页面渲染，其中 248 页明确标注为外观设计图片或照片。
- 封面载明应有 1,639 幅；获得 1,639 个有名称视图并附可追溯分图，保留全部原页。
- 1,631 个标签来自 PDF 图页文字；`CN304194747S` 的 8 个标签在图像中，已依据实际原页作助手视觉复核，并在 `scripts/design_view_label_evidence.json` 固定对应 PDF SHA-256、页码、顺序和名称。此项不是人工核验，也不是 OCR 结果。
- 全部 152 件的命名视图数量与各自封面数量一致。计数一致与整页覆盖不等于完整外观保护范围已经人工或法律核验；人工逐件全视图审核数仍为 0。
- 新增 4,382 个 WEBP 文件（原页、分图及对应缩略图），共 53,983,268 字节。图像清单约 2 MB。既有站点约 84 MB，合计约 141 MB，未删减旧资料，低于 GitHub Pages 当前 1 GB 发布上限。官方依据：[GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)。该服务另有每月 100 GB 软带宽限制，因此只按需加载缩略图和单张放大图。

## 渲染与拆图边界

`scripts/extract_design_views.py` 使用 PyMuPDF 整页渲染，不以 PDF 内嵌图像提取代替整页覆盖。当前图页包含栅格设计图与向量页框，均进入页面渲染。数据中未发现纯矢量设计图页；隔离纯矢量页和纯扫描页夹具已验证同一渲染器可处理，夹具不写入正式数据。

自动分图仅在独立图形矩形与文字标签位置可可靠对应时，按两者联合边界加安全余量从页面渲染，保留设计内容及标签。无法可靠拆分时应保留整页，不用内嵌图像数量代替视图数量，也不伪造名称。每件记录 PDF 来源与校验、实际页数、预期视图数量、命名数量、分图数量、方法和限制；每页含页码、标签、尺寸、文件大小、内容分类及图像校验值。

原页和分图以 WEBP 保存，展示图不替代原 PDF。全尺寸图为 180 dpi 页面渲染，最终准确性仍应回到原 PDF；不通过生成图像补画任何设计内容。

## 页面交互

`DesignViews.load()` 加载核查清单，`render(id)` 生成指定完整公开号的图库，`bind()` 绑定交互。默认显示 6 项缩略图，其余折叠；可切换分图／原页，另展开封面及简要说明。点击后在放大窗口切换上一项／下一项、左右方向键、原尺寸／适合宽度，并可在站内 PDF 阅读器定位同一原文件的实际页码。阅读器按固定来源版本及 SHA-256 核验原文件；网络受限时明确提示并显示同一文件已保存的对应原页。原 PDF 来源和下载入口均保留。

编号未确认的候选文件不会作为该专利的已确认图库显示；索引缺失会显示异常，保留旧图片和 PDF 入口。

## 复现与检查

开发重建需要 PyMuPDF、Pillow，源 PDF checkout 应与关联清单版本一致：

```sh
python3 scripts/extract_design_views.py --pdf-repo ../pdf-repository --site _site
python3 scripts/check_design_views.py --pdf-repo ../pdf-repository --site _site
```

数据带入正式构建后，标准库检查无须 PDF checkout 或第三方图片包：

```sh
python3 scripts/check_design_manifest.py
```

该检查核对完整设计文献集合、页码连续性、视图及图片统计、与 PDF 关联索引的来源 SHA 一致性、每项图片存在性及所有图片 SHA-256。证据输出在 `reports/design-views-audit.csv`、`design-views-summary.json`、`design-views-validation.json` 和 `design-gallery-browser.json`。

未来若遇到正文无编号的扫描首页，提取器可用本地 Tesseract 英文模型尝试确认完整公开号；无法唯一确认时隔离，不能用名称相似度填补。模型、OCR 临时文件及其他下载凭据不进入公开仓库。中文图名在无法可靠识别时保留完整原页待复核。
