"""Import a real Incopat CSV/XLSX into a local review report (never publishes).

Needs Python 3, Node.js and openpyxl for XLSX. Keep exports and reports outside
the public repository. See MONITORING.md for metadata and review rules.
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def xlsx_rows(path, sheet_name=None):
    from incopat_xlsx_native import native_xlsx_rows
    native = native_xlsx_rows(path, sheet_name)
    if native is not None:
        return native
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
    if sheet_name:
        if sheet_name not in workbook.sheetnames:
            raise ValueError('指定工作表不存在')
        sheets = [workbook[sheet_name]]
    else:
        sheets = list(workbook)
    tables = []
    for sheet in sheets:
        # Some exporters incorrectly declare A1 even when physical rows exist.
        sheet.reset_dimensions()
        values = list(sheet.iter_rows(values_only=True))
        values = [list(row) for row in values if any(v is not None and str(v).strip() for v in row)]
        if values:
            tables.append((sheet.title, values))
    if len(tables) != 1:
        raise ValueError('XLSX 包含零个或多个非空工作表；请用 --sheet 明确导入工作表，并按该表记录真实覆盖信息')
    title, values = tables[0]
    headers = [str(v).strip() if v is not None else '' for v in values.pop(0)]
    if any(not h for h in headers) or len(set(headers)) != len(headers):
        raise ValueError('XLSX 表头为空或重复')
    if not any(h in headers for h in ('publicationNumber', 'id', '公开（公告）号', '公开(公告)号', '公开公告号', '公开号', '公告号')) or not any(h in headers for h in ('applicationNumber', '申请号', '申请（专利）号', '申请(专利)号')):
        raise ValueError('XLSX 缺少完整公开号或申请号必需表头，不能认定零结果或无变化')
    rows = []
    for row_number, values in enumerate(values, 2):
        values += [None] * (len(headers) - len(values))
        row = {}
        for header, value in zip(headers, values):
            if isinstance(value, str) and value.startswith('='):
                raise ValueError(f'第 {row_number} 行含公式；请导出纯值，不执行公式或外部链接')
            if header in ('申请号', '申请（专利）号', '申请(专利)号', 'applicationNumber') and value is not None and not isinstance(value, str):
                raise ValueError(f'第 {row_number} 行申请号为数值单元格，无法确认精度与前导字符；请从来源导出文本字段')
            row[header] = value.isoformat() if isinstance(value, (datetime.datetime, datetime.date)) else '' if value is None else str(value)
        rows.append(row)
    workbook.close()
    return rows, dict(worksheet=title, worksheetRows=len(rows), explicitlySelected=bool(sheet_name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', dest='export_file', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=ROOT / '_site/data/portfolio-current.json')
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--profile', default='chcnav')
    parser.add_argument('--sheet')
    parser.add_argument('--count-basis', choices=('publications', 'rows'), help='来源总数的真实口径：完整公开号去重文献数，或原始导出行数；覆盖 run.json 同名字段')
    parser.add_argument('--output', type=Path, required=True, help='Private path outside this public repository')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error('导出报告必须保存在公开仓库之外，避免把 Incopat 导出资料误提交')
    data = args.export_file.read_bytes()
    metadata = json.loads(args.metadata.read_text(encoding='utf-8-sig'))
    metadata.update(fileSha256=hashlib.sha256(data).hexdigest(), fileName=args.export_file.name)
    if args.count_basis:
        metadata['resultCountBasis'] = args.count_basis
    payload = dict(metadata=metadata, baseline=json.loads(args.baseline.read_text(encoding='utf-8-sig')), previous=json.loads(args.previous.read_text(encoding='utf-8-sig')) if args.previous else None)
    config = json.loads((ROOT / 'site-overrides/data/monitor-config.json').read_text(encoding='utf-8-sig'))
    payload['profile'] = next((p for p in config['profiles'] if p['id'] == args.profile), None)
    if not payload['profile']:
        parser.error('未知竞争对手 profile；先在配置中添加有证据的精确名称')
    names = set(payload['profile']['inScopeApplicantNames'])
    if not isinstance(payload['baseline'], list):
        parser.error('文献基线必须是 portfolio 数组；观察快照请通过 --previous 提供')
    payload['baseline'] = [d for d in payload['baseline'] if any(n.strip() in names for n in str(d.get('applicants', '')).replace('；', ';').split(';'))]
    try:
        if args.export_file.suffix.lower() == '.xlsx':
            payload['rows'], sheet_info = xlsx_rows(args.export_file, args.sheet)
            metadata['xlsxInfo'] = sheet_info
        elif args.export_file.suffix.lower() in ('.csv', '.tsv'):
            try:
                payload['csvText'] = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                payload['csvText'] = data.decode('gb18030')
        else:
            raise ValueError('只支持 CSV、TSV 或 XLSX，不处理可执行宏或加密文件')
        bridge = "const c=require(process.argv[1]);let s='';process.stdin.setEncoding('utf8');process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{const p=JSON.parse(s),rows=p.rows||c.parseCSV(p.csvText);console.log(JSON.stringify(c.compare(rows,p.baseline,p.metadata,p.profile,p.previous),null,2));});"
        result = subprocess.run(['node', '-e', bridge, str(ROOT / 'site-overrides/patent-monitor-core.js')],
            input=json.dumps(payload, ensure_ascii=False), text=True, encoding='utf-8', capture_output=True, check=False)
        if result.returncode:
            raise ValueError('解析／比对失败：' + result.stderr[-1600:])
        report = json.loads(result.stdout)
    except Exception as error:
        report = dict(schemaVersion=1, kind='incopat-review-report', runState='import-failed',
            runStateLabel='导入失败，未完成核查', metadata=metadata, counts={},
            anomalies=[dict(type='import-failed', reason=str(error))], publicationState='review-only-not-published')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(report=str(output), state=report['runState'], counts=report['counts']), ensure_ascii=False))
    return 2 if report.get('anomalies') else 0


if __name__ == '__main__':
    sys.exit(main())
