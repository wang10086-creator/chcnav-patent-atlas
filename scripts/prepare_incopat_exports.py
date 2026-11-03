"""Merge native Incopat export batches into a private canonical CSV and audit.

The manifest contains searchQuery, totalResults, and batches [{path, range}].
Paths resolve relative to the manifest. Outputs must stay outside this public
repository. A partial or conflicting export is written with exportComplete=false
and exits 2, so it cannot be mistaken for a successful complete monitoring run.
"""
import argparse
import csv
import json
from pathlib import Path
import re

from incopat_xlsx_native import (APP, PUB, columns, native_xlsx_rows,
                                 read_workbook, record, sha)

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['publicationNumber', 'applicationNumber', 'title', 'applicants',
          'legalStatus', 'legalEvent', 'eventDate', 'publicationDate', 'familyId',
          'evidenceUrl', 'sourceFile', 'sourceFileSha256', 'sourceSheet',
          'sourceExcelRow', 'sourceRecordNumber', 'sourceBatchRange',
          'legalEventDescription', 'sourceEventIndex']


def prepare(manifest_path, output_dir):
    manifest_path, output_dir = Path(manifest_path).resolve(), Path(output_dir).resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        raise ValueError('输出目录必须位于公开仓库之外，不能提交真实导出和证据链接')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    total, query = manifest.get('totalResults'), manifest.get('searchQuery')
    if type(total) is not int or total < 0 or not isinstance(query, str) or not query.strip():
        raise ValueError('清单必须记录有效的实际检索式和来源文献总数')
    batches = manifest.get('batches')
    if not isinstance(batches, list) or not batches:
        raise ValueError('清单缺少真实导出批次')
    rows, raw_records, files, issues, source_sequences, pubs, expected_sequences = [], [], [], [], [], [], []
    for batch in batches:
        source_path = Path(batch['path'])
        if not source_path.is_absolute():
            source_path = manifest_path.parent / source_path
        range_match = re.fullmatch(r'([1-9]\d*)-([1-9]\d*)', str(batch.get('range', '')))
        if not range_match:
            raise ValueError('批次范围必须明确记录为起始序号-结束序号')
        start, end = map(int, range_match.groups())
        if end < start or end > total:
            raise ValueError('批次范围超出本次来源总数或顺序无效')
        expected_sequences.extend(range(start, end + 1))
        book = read_workbook(source_path)
        parsed, info = native_xlsx_rows(source_path)
        main = next(s for s in book['sheets'] if s['name'] == info['worksheet'])
        intro = {}
        for sheet in book['sheets']:
            if sheet['name'] == '下载简介':
                for source_row in sheet['rows']:
                    cells = {re.match('[A-Z]+', k).group(): v['value'] for k, v in source_row['cells'].items()}
                    if cells.get('A'):
                        intro[cells['A']] = cells.get('B', '')
        physical = [r for r in main['rows'][1:] if any(c['value'].strip() for c in r['cells'].values())]
        if intro.get('下载内容') != query:
            issues.append({'type': 'source-query', 'file': source_path.name, 'reason': '原生下载简介检索式与清单不一致或缺失'})
        if intro.get('数据范围') != batch['range']:
            issues.append({'type': 'source-range', 'file': source_path.name, 'reason': '原生下载简介范围与清单不一致或缺失'})
        try:
            intro_count = float(intro.get('数量', ''))
        except ValueError:
            intro_count = -1
        if intro_count != len(physical) or len(physical) != end - start + 1:
            issues.append({'type': 'source-count', 'file': source_path.name, 'reason': '原生数量、物理记录数或范围数量不一致'})
        cols = columns(main)
        for source_row in physical:
            raw = record(source_row, cols)
            pub, app = raw.get('公开（公告）号', ''), raw.get('申请号', '')
            pubs.append(pub)
            if not PUB.fullmatch(pub) or not APP.fullmatch(app):
                issues.append({'type': 'identifier', 'file': source_path.name, 'row': source_row['row'], 'reason': '完整文献号或申请号格式无法确认'})
            try:
                sequence = float(raw.get('序号', ''))
                if not sequence.is_integer() or not start <= sequence <= end:
                    raise ValueError('outside range')
                source_sequences.append(int(sequence))
            except ValueError:
                issues.append({'type': 'source-sequence', 'file': source_path.name, 'row': source_row['row'], 'reason': '原始序号缺失、非整数或不在批次范围内'})
            raw_records.append({'sourceFile': source_path.name, 'sourceFileSha256': book['sha256'],
                                'sourceSheet': main['name'], 'sourceExcelRow': source_row['row'],
                                'sourceBatchRange': batch['range'], 'rawFields': raw,
                                'cells': source_row['cells']})
        for row in parsed:
            rows.append({'publicationNumber': row['公开（公告）号'], 'applicationNumber': row['申请号'],
                         'title': row.get('title', ''), 'applicants': row['申请人'],
                         'legalStatus': row['当前法律状态'], 'legalEvent': row.get('legalEvent', ''),
                         'eventDate': row.get('eventDate', ''), 'publicationDate': row.get('publicationDate', ''),
                         'familyId': row.get('简单同族ID', ''), 'evidenceUrl': row.get('evidenceUrl', ''),
                         'sourceFile': source_path.name, 'sourceFileSha256': book['sha256'],
                         'sourceSheet': main['name'], 'sourceExcelRow': row['sourceExcelRow'],
                         'sourceRecordNumber': row.get('序号', ''), 'sourceBatchRange': batch['range'],
                         'legalEventDescription': row.get('legalEventDescription', ''),
                         'sourceEventIndex': row.get('sourceEventIndex', '')})
        files.append({'path': str(source_path.resolve()), 'sha256': book['sha256'], 'bytes': book['bytes'],
                      'range': batch['range'], 'downloadedAt': batch.get('downloadedAt'),
                      'worksheet': main['name'], 'declaredDimension': main['declaredDimension'],
                      'physicalDataRows': len(physical), 'expandedEventRows': len(parsed),
                      'downloadIntroduction': intro})
    missing = sorted(set(range(1, total + 1)) - set(source_sequences))
    if missing:
        issues.append({'type': 'missing-records', 'reason': '来源序号覆盖不完整', 'missing': missing})
    if len(expected_sequences) != len(set(expected_sequences)):
        issues.append({'type': 'overlapping-ranges', 'reason': '清单批次范围存在重叠'})
    if len(source_sequences) != len(set(source_sequences)):
        issues.append({'type': 'duplicate-sequences', 'reason': '原生记录序号重复'})
    if len(pubs) != len(set(pubs)):
        issues.append({'type': 'duplicate-publications', 'reason': '多个原始记录有相同完整公开号'})
    if len(pubs) != total or len(set(pubs)) != total:
        issues.append({'type': 'total-results', 'reason': '导出记录或唯一文献总数与来源不一致'})
    output_dir.mkdir(parents=True, exist_ok=True)
    canonical = output_dir / 'incopat-canonical.csv'
    with canonical.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    audit = {'adapterVersion': 1, 'searchQuery': query, 'sourceTotalResults': total,
             'sourceCountBasis': 'publications', 'nativeRecords': len(pubs),
             'distinctPublications': len(set(pubs)), 'canonicalRows': len(rows),
             'eventCount': sum(bool(r['legalEvent']) for r in rows),
             'exportComplete': not issues, 'missingSequenceNumbers': missing,
             'issues': issues, 'batches': files, 'canonicalFile': canonical.name,
             'canonicalSha256': sha(canonical.read_bytes()),
             'manifest': manifest, 'sourceManifestSha256': sha(manifest_path.read_bytes()),
             'notice': '仅准备本地待复核资料；未审核法律状态、未修改网站、未发送通知。'}
    for name, value in [('incopat-adaptation-audit.json', audit), ('incopat-original-records.json', raw_records)]:
        (output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        audit = prepare(args.manifest, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: audit[k] for k in ['nativeRecords', 'distinctPublications', 'canonicalRows', 'eventCount', 'exportComplete', 'issues']}, ensure_ascii=True))
    return 0 if audit['exportComplete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
