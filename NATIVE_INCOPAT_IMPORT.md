# 原生 Incopat 分批导出与本地比对

原始 XLSX、真实执行清单、完整证据 URL 和报告应保存在公开仓库之外。脚本不会上传文件、更新网站或发送通知。

## 准备规范 CSV

在 Incopat 原生导出窗口记录完整申请人检索式、国家/文献版本、日期范围、未合并的结果总数和导出限制。保存全部不重叠的批次，例如每批 100 条的 `1-100` 至末批；不得用扩大申请人范围的测试文件代替正式范围。

在私有目录保存清单，文件路径相对清单解析：

```json
{
  "searchQuery": "填写来源实际执行的完整检索式",
  "totalResults": 938,
  "batches": [
    {"path": "batch-001-100.xlsx", "range": "1-100", "downloadedAt": "填写实际带时区下载时间"},
    {"path": "batch-101-200.xlsx", "range": "101-200", "downloadedAt": "填写实际带时区下载时间"}
  ]
}
```

上例只展示前两批的写法，并非完整导出。必须按真实文件补全全部批次。

```text
python scripts/prepare_incopat_exports.py --manifest /private/batches.json --output /private/prepared
```

`prepare_incopat_exports.py` 与 `import_incopat.py` 共用 `incopat_xlsx_native.py` 的解析逻辑。它读取物理 XML 行，处理原生导出的错误 `A1` 范围声明、下载简介、标题空格、Excel 日期和超链接关系。完整历史状态仅按明确公告日期拆分，不用“专利有效性”推断当前法律状态。

输出包括规范 CSV、逐原始记录和单元格审计、每文件 SHA-256、原始行号、序号、下载简介及完整性审计。缺批、重复/重叠范围、简介检索式不一致、来源数量不一致或完整公开号重复时，审计为 `exportComplete=false`，命令退出码为 2，不能认定监控成功。无法解析的必需列、编号单元格或历史状态结构也会拒绝处理，不补造数据。

一次文献可能有多个历史事件行。来源总数口径须选 `publications`；例如 938 条原始文献拆为 2333 个事件行时，来源总数仍是 938。

## 比对和复核

先确认审计 `exportComplete=true` 且 `issues` 为空，再准备真实执行元数据：`searchQuery`、`timeFrom`、`timeTo`、带时区的 `executedAt`、`totalResults`、`resultCountBasis=publications`、`expectedPages`、`downloadedPages`、`exportComplete=true`、`loginStatus=authenticated` 和指定 `sourceUrl`。分页数字必须注明单位：原生导出范围批次与检索列表页面是不同口径；保留原始清单及每批哈希，不通过改总数消除不完整。

```text
python scripts/import_incopat.py --export /private/prepared/incopat-canonical.csv --metadata /private/run.json --baseline _site/data/portfolio-current.json --count-basis publications --output /private/review.json
```

首次真实运行省略 `--previous`，结果为首次状态观察并待人工复核，不能称已证实的状态变化。只有真实审核通过后才能另存已审核观察基线；不要通过程序代替人工勾选审核。

## 网站与管理员导入的边界

新浏览器读取器已适配错误 A1 范围、明确下载简介、多表校验、中文空格表头、超链接关系和带日期历史；未知多表或来源冲突仍会拒绝或记录异常。这些新增解析能力已用隔离夹具测试，未宣称已在当前工作区对基线对话的私有十批真实文件完成网页验收。

公开站点现在只读，导入与审核通过私有管理员工作台完成。原生批次由服务端再次读取与核验，规范 CSV 须保留配套来源适配审计。完整流程见 [MANUAL_MONITOR_ADMIN.md](MANUAL_MONITOR_ADMIN.md)。

覆盖 schema 2 明确记录 resultPageCount、resultPageSize、expectedExportBatches、downloadedExportBatches 与原文件范围、校验值。47 个检索列表页和 10 个导出批次分别保存；旧 expectedPages/downloadedPages 仅作为历史兼容，不代表已逐页浏览全部列表。

## 回归验证

```text
python -m unittest discover -s scripts/monitor_tests -p "test_*incopat*.py" -v
```

隔离 fixture 覆盖错误范围、简介多表、超链接、日期、历史事件、必需列/公式拒绝、缺批、重复范围、来源式不一致、仓库内输出拒绝和 UTF-8 中文跨数据块传输。Windows 沙箱可设置 `CODEX_TEST_TMPDIR` 为工作区可写临时目录。
