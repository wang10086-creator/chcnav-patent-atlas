# 外观图库与技术路径界面发布

本次仅发布已开发的外观设计图库和产品技术路径界面，以及图库定位原文所需的站内 PDF 阅读器。基于生产提交 `78917e7cd579eba335fc703b7f1e0c93ee954e25` 独立制作，不合并包含其他功能的整条开发分支。

## 上线范围

- 152 件外观文献按完整公开号、原 PDF 的 SHA-256 及固定来源版本关联，保留全部 552 页原页渲染，新增 1,639 幅命名视图和按需加载的缩略图。
- 外观图库支持放大、前后切换、原页及简要说明查看，并可在站内 PDF 阅读器定位对应页；原始 PDF 阅读／下载及证据链接保留。
- 继续以产品类型为主入口，产品内按方法／结构／外观、技术路径、子路径、引用专利浏览。桌面显示路径树与单一子路径详情；手机切换目录／详情。研发速览与知识产权核对可切换，路径按可核验的去重申请关联数量排序。
- 本次静态覆盖仅允许图库、路径阅读界面及其 PDF 阅读依赖。监控配置、导入器、监控脚本、管理页面、导航入口及初始化代码均未带入发布候选。原监控开发分支保持保留。

## 原资料与核验口径

938 份公开文本、807 件申请及分析、16 个主产品类型、21 条路径、109 个子路径、944 张旧图片和 938 条原 PDF 关联全部保留。五个原始 ZIP、原始 SHA 清单、数据、图片、样式和证据文件不被覆盖；仅现有 HTML／JS 展示层允许调整。

原页覆盖和视图计数一致不等于已完成全部外观保护范围的人工或法律核验；页面保留原有待核提示。PDF 阅读器核验源字节 SHA，读取原 PDF 受限时明确显示同一源文件预存的对应页，不将回退图片声称为在线 PDF 渲染成功。

## 构建、维护与发布

```text
python3 scripts/update_override_manifest.py
python3 verify_extract.py
python3 scripts/check_preservation_upgrade.py --pdf-repo ../pdf-repository --json-output reports/preservation-validation.json
python3 scripts/check_design_views.py --site _site --pdf-repo ../pdf-repository
python3 -m http.server 8013 --bind 127.0.0.1 --directory _site
```

重复构建前请将旧 `_site` 移到独立备份目录。静态构建及部署只需 Python 标准库；深度 PDF 验证另需 PyMuPDF、Pillow，浏览器测试另需 Playwright 和 Chromium。测试脚本与实际验证记录见 `scripts/test_release_browser.py` 和 `reports/`。

沿用原 GitHub Pages 工作流：main push 后校验解包、上传 `_site` 并部署。工作流配置不变。部署运行成功与实际公网浏览器验证分别记录；若当前云网络拒绝访问 github.io，将明确记录线上功能尚未实测。
