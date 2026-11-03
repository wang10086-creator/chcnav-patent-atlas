"""Read native Incopat XLSX physical rows and hyperlinks without trusting dimensions."""
import datetime as dt
import hashlib
from pathlib import Path
import posixpath
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
PUB = re.compile(r'^CN\d{9}[ABUS]\d?$')
APP = re.compile(r'^CN\d{8,13}(?:\.[0-9X])?$')
MAIN_REQUIRED = {'公开（公告）号', '申请号', '申请人', '当前法律状态'}



def sha(data):
    return hashlib.sha256(data).hexdigest()


def text(el):
    return ''.join(el.itertext()) if el is not None else ''


def safe_xml(data):
    # NUL removal also detects ASCII markup encoded as UTF-16 or UTF-32.
    probe = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
        raise ValueError('XLSX XML contains a forbidden DTD or entity declaration')
    return ET.fromstring(data)


def relationships(z, path):
    parent, name = posixpath.split(path)
    relpath = posixpath.join(parent, '_rels', name + '.rels')
    if relpath not in z.namelist():
        return {}
    return {r.attrib['Id']: r.attrib for r in safe_xml(z.read(relpath))}


def resolve(base, target):
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), target)).lstrip('/')


def read_workbook(path):
    data = path.read_bytes()
    sheets = []
    with ZipFile(path) as z:
        wb = safe_xml(z.read('xl/workbook.xml'))
        wb_rels = relationships(z, 'xl/workbook.xml')
        prop = wb.find('s:workbookPr', NS)
        epoch = dt.datetime(1904, 1, 1) if prop is not None and prop.attrib.get('date1904') in ('1', 'true') else dt.datetime(1899, 12, 30)
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [text(si) for si in safe_xml(z.read('xl/sharedStrings.xml'))]
        for s in wb.find('s:sheets', NS):
            spath = resolve('xl/workbook.xml', wb_rels[s.attrib[RID]]['Target'])
            root = safe_xml(z.read(spath))
            rels = relationships(z, spath)
            links = {}
            for link in root.findall('s:hyperlinks/s:hyperlink', NS):
                relation = rels.get(link.attrib.get(RID), {})
                if relation.get('Type', '').endswith('/hyperlink'):
                    links[link.attrib['ref']] = relation.get('Target', '')
            rows = []
            for row in root.findall('s:sheetData/s:row', NS):
                cells = {}
                for c in row.findall('s:c', NS):
                    if c.find('s:f', NS) is not None:
                        raise ValueError(f'{path.name} {s.attrib["name"]}!{c.attrib["r"]} contains a formula; not executed')
                    typ = c.attrib.get('t', 'n')
                    value = text(c.find('s:is', NS)) if typ == 'inlineStr' else text(c.find('s:v', NS))
                    if typ == 's':
                        value = strings[int(value)]
                    cells[c.attrib['r']] = {'value': value, 'type': typ,
                                          'style': c.attrib.get('s'),
                                          'hyperlink': links.get(c.attrib['r'], '')}
                rows.append({'row': int(row.attrib['r']), 'cells': cells})
            sheets.append({'name': s.attrib['name'], 'xmlPath': spath,
                           'declaredDimension': root.find('s:dimension', NS).attrib.get('ref') if root.find('s:dimension', NS) is not None else None,
                           'rows': rows})
    return {'path': str(path.resolve()), 'sha256': sha(data), 'bytes': len(data),
            'epoch': epoch, 'sheets': sheets}


def column(ref):
    return re.match('[A-Z]+', ref).group()


def columns(sheet):
    if not sheet['rows']:
        return {}
    return {column(ref): c['value'].strip() for ref, c in sheet['rows'][0]['cells'].items()}


def record(row, cols):
    return {cols[column(ref)]: c['value'] for ref, c in row['cells'].items() if column(ref) in cols}


def date_value(value, cell, epoch):
    if not value:
        return ''
    if cell.get('type') == 'n':
        return (epoch + dt.timedelta(days=float(value))).date().isoformat()
    if re.fullmatch(r'\d{8}', value):
        return dt.datetime.strptime(value, '%Y%m%d').date().isoformat()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}(?: 00:00:00)?', value):
        return dt.date.fromisoformat(value[:10]).isoformat()
    raise ValueError(f'Unrecognized date value {value!r}')


def legal_history(raw):
    if not raw.strip():
        return []
    marker = re.compile(r'#法律状态公告日[：:]\s*(\d{8})[;；]')
    matches = list(marker.finditer(raw))
    if not matches or raw[:matches[0].start()].strip():
        raise ValueError('Legal history does not follow observed dated Incopat format')
    events = []
    for i, m in enumerate(matches):
        chunk = raw[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(raw)]
        event = re.search(r'^\s*法律状态[：:]\s*([^\n]*?)[;；]\s*(?:\n|$)', chunk)
        desc = re.search(r'(?:^|\n)\s*描述信息[：:]\s*(.*?)\s*$', chunk, re.S)
        if not event or not desc:
            raise ValueError('Dated legal history block lacks event or description')
        events.append({'event': event.group(1),
                       'eventDate': dt.datetime.strptime(m.group(1), '%Y%m%d').date().isoformat(),
                       'description': desc.group(1), 'sourceBlock': raw[m.start():matches[i + 1].start() if i + 1 < len(matches) else len(raw)]})
    return events


def native_xlsx_rows(path, sheet_name=None):
    """Return (rows, info) for native exports, or None for generic spreadsheets.

    Native workbooks may incorrectly declare every sheet's dimensions as A1.
    XML physical rows preserve records and hyperlinks, and avoid evaluating any
    formulas. Only a known download-introduction sheet is automatically skipped.
    """
    workbook = read_workbook(Path(path))
    populated = [s for s in workbook['sheets'] if s['rows']]
    native = [s for s in populated if re.fullmatch(r'下载的著录项\d*', s['name'])]
    if not native:
        return None
    if sheet_name:
        selected = [s for s in populated if s['name'] == sheet_name]
        if not selected:
            raise ValueError('指定工作表不存在')
        tables = selected
    else:
        tables = native
        extra = [s for s in populated if s not in native and s['name'] != '下载简介']
        if extra:
            raise ValueError('XLSX 包含未确认的数据工作表；请用 --sheet 明确选择')
    if len(tables) != 1:
        raise ValueError('XLSX 存在多个著录项工作表；请用 --sheet 明确选择并记录该表覆盖范围')
    table = tables[0]
    cols = columns(table)
    if not MAIN_REQUIRED.issubset(set(cols.values())):
        raise ValueError('原生 Incopat XLSX 缺少完整公开号、申请号、申请人或当前法律状态必需表头')
    if any(not h for h in cols.values()) or len(set(cols.values())) != len(cols):
        raise ValueError('XLSX 表头为空或重复')
    result = []
    physical_rows = 0
    for row in table['rows'][1:]:
        if not any(c['value'].strip() for c in row['cells'].values()):
            continue
        physical_rows += 1
        raw = record(row, cols)
        by_header = {cols[column(k)]: v for k, v in row['cells'].items() if column(k) in cols}
        app_cell = by_header.get('申请号', {})
        if app_cell.get('type') not in ('s', 'inlineStr', 'str'):
            raise ValueError(f'第 {row["row"]} 行申请号为数值单元格，不能确认精度')
        if any(v.lstrip().startswith('=') for v in raw.values()):
            raise ValueError(f'第 {row["row"]} 行含公式样式文本；请提供纯值')
        common = {**raw, 'title': raw.get('标题 (中文)', raw.get('标题(中文)', '')),
                  'evidenceUrl': by_header.get('链接到incoPat', {}).get('hyperlink', ''),
                  'publicationDate': date_value(raw.get('公开（公告）日', ''), by_header.get('公开（公告）日', {}), workbook['epoch']),
                  'sourceExcelRow': row['row'], 'sourceSheet': table['name']}
        events = legal_history(raw.get('法律状态', ''))
        for index, event in enumerate(events or [{}], 1):
            result.append({**common, 'legalEvent': event.get('event', raw.get('法律事件', '')),
                           'eventDate': event.get('eventDate', ''),
                           'legalEventDescription': event.get('description', ''),
                           'sourceEventIndex': index if events else ''})
    return result, {'worksheet': table['name'], 'worksheetRows': physical_rows,
                    'expandedEventRows': len(result), 'explicitlySelected': bool(sheet_name),
                    'nativeFormat': True, 'declaredDimension': table['declaredDimension'],
                    'physicalXmlRowsUsed': True,
                    'ignoredIntroductionSheet': any(s['name'] == '下载简介' for s in populated)}


