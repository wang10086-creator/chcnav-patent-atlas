# 手动更新：开发交付，尚未上线

当前基线 938 文献 / 807 申请，938 PDF 精确版本链接；原文件及 IncoPat 2026-11-03 快照不覆盖。

## 实际操作

1. 在网站“新增／批量更新”入口进入 maintenance.html，或在详情选择“更新法律状态”“补充／修正 PDF”。这些是公开的本地草稿工具，不授予仓库写入权限。文件只在浏览器解析，不上传。可单条填写或导入 CSV、单表 XLSX、JSON；下载中文模板，自定义表头可用 JSON 映射到英文字段。
2. 操作 kind 为 patent（新增或补充文献）、status（追加状态）、pdf（修正链接）。企业默认 chcnav；新企业须 company 与 companyName。所有新文献须完整含版本公开号及申请号、名称、申请人、来源链接。各法域编号格式不同，当前使用保守格式检查，特殊格式不自动补正。
3. 页面查看预览，勾选最小字段可公开后下载 manual-patent-draft.json。此时仍为“本地草稿”；取消会清空，不改网站。浏览器预览是初筛，以下 Python 复验为权威结果。
4. 在已获授权的本地仓库建立分支并完成初始构建（python3 verify_extract.py）；原始 Excel 和草稿放仓库外，例如 ../private-input/。运行：

   python3 maintenance/update.py preview ../private-input/manual-patent-draft.json --out ../private-input/preview.json

   原生 CSV/XLSX 也可直接替代输入；--mapping 可指定私有 JSON 映射文件。XLSX 忽略错误 A1 维度，扫描真实行；拒绝公式、多非空表及超限内容。日期使用 YYYY-MM-DD 纯文本，不能猜测 Excel 数值日期。

5. 阅读预览，修正冲突/缺失信息。确认后：

   python3 maintenance/update.py apply ../private-input/preview.json --confirm

   仅追加 site-overrides/data/manual-updates.json 并更新校验清单。重新验证输入，阻止过期草稿与 main 直接写入；重复记录不创建，空字段不删除原值。此时仍未发布。

6. 备份移走已有 _site 后重建并运行测试；通过后，可用已正常认证的 Git/gh：

   python3 maintenance/update.py pr --confirm

   仅暂存追加数据与校验清单，若已有其他暂存文件则停止。创建草稿 PR，进入“已提交待审核”。不在网页放 Token，不扩大权限；无 gh/仓库写权限时由已有维护者按相同文件范围提交，不创建新账户。
7. PR 自动执行构建、原始资料保留及数据校验、隔离测试；审核公开字段、编号、状态依据及分类关系。实际核对官方登记后方可选择 official，并填写 evidenceUrl；本站显示为人工声明及依据，未自动将其升级为机器核验事实。审批后才转正式并合并。
8. main 的 Pages 流程发布，随后真实 HTTP 回读页面、脚本及 manual-updates.json 的 SHA；成功的对应运行才是“已发布到网站”。旧草稿页不会自行声称已发布。检查线上目标文献/企业及计数；保存 PR、部署链接供追溯。

## 状态与分类

status 字段需要 normalizedStatus（pending/granted/active/terminated/expired/invalid/unknown）、statusRaw、asOf、sourceUrl、verification（database/manual/official）；事件日期未知可以空。enteredAt 由 apply 实际生成。按地域/具体文献记录，不传播到同族。日期相同而标准状态不同保留冲突；比基线旧的记录不会替代新快照。历史记录均在详情保留，官方地域不从“授权”推断。人工更新日期筛选与企业、地域及状态组合使用。

新增文献先进入对应企业、检索、列表、统计和“待分析资料”产品入口，不编造权利范围。可以填写 productId；要关联 topicId，必须提供 contentForm（method/structure/design）、claimNumbers、claimText、sourceUrl。导图将用户声明的关联纳入计数，详情独立展示原文/文献版本与未分析标记；不把提交的原文伪装成已完成范围分析。产品及子路径编号来自已有 data/product-portraits.json 和 route-tree.json。新企业数据通过追加记录隔离切换；已配置独立目录的企业仍保留原有导航方式。

## PDF 查找及修正

已有 938 份精确版本索引继续保留，不批量重新托管或覆盖。对缺失/新文献可手动执行：

python3 maintenance/find_pdfs.py CN123456789A --source-page https://patents.google.com/patent/CN123456789A/en --out ../private-input/pdf-result.json

不传 source-page 时生成公开专利页面查询地址（不是猜测 PDF 下载地址）。若已有可合法访问的官方页面，优先明确传入；当前自动请求仅允许 Google Patents、其 PDF 存储域及 EPO 公开域，其他官方源需人工查证后补链，未接入受保护接口。

查 robots、实际页面及其 PDF 链接；核对 %PDF 字节，若已安装 pdftotext 则检查第一页页首完整编号与版本。扫描、文本不足保持候选，不声称外观全视图已核验。验证码/登录/访问限制不绕过。不永久保存 PDF 字节。结果 JSON 走同一预览、确认、PR 流程。已有人工 PDF 修正会拒绝自动覆盖；人工可以再追加修正。在线阅读新链接使用新标签页，避免假设跨站允许嵌入。

本环境实际查询受网络限制，未证明能够批量取得任何国家全部PDF。原有图库完整性检查保留；本轮未重新人工通读938份PDF，也不把历史关联清单当作新一轮全文核验。生产记录没有新增测试数据。
