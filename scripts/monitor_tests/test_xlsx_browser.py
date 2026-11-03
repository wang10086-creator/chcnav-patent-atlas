"""Isolated browser XLSX tests; fixtures live only in a temporary directory."""
from datetime import date
from io import BytesIO
from pathlib import Path
import tempfile
import zipfile
import xml.etree.ElementTree as ET
import json

import openpyxl
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HEADERS = ['公开（公告）号', '申请号', '标题', '当前法律状态', '法律事件日期']
MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def workbook(rows, extra=None):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = 'Incopat 导出'
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    if extra is not None:
        second = book.create_sheet('其他数据')
        for row in extra:
            second.append(row)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def transform(data, shared=False, compression=zipfile.ZIP_DEFLATED, mutate=None):
    with zipfile.ZipFile(BytesIO(data)) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    if shared:
        tree = ET.fromstring(contents['xl/worksheets/sheet1.xml'])
        strings = []
        for cell in tree.iter('{'+MAIN_NS+'}c'):
            if cell.get('t') == 'inlineStr':
                text = ''.join(t.text or '' for t in cell.iter('{'+MAIN_NS+'}t'))
                strings.append(text)
                for child in list(cell):
                    cell.remove(child)
                cell.set('t', 's')
                ET.SubElement(cell, '{'+MAIN_NS+'}v').text = str(len(strings)-1)
        contents['xl/worksheets/sheet1.xml'] = ET.tostring(tree, encoding='utf-8')
        root = ET.Element('{'+MAIN_NS+'}sst')
        for value in strings:
            ET.SubElement(ET.SubElement(root, '{'+MAIN_NS+'}si'), '{'+MAIN_NS+'}t').text = value
        contents['xl/sharedStrings.xml'] = ET.tostring(root, encoding='utf-8')
    if mutate:
        mutate(contents)
    result = BytesIO()
    with zipfile.ZipFile(result, 'w', compression=compression) as dest:
        for name, content in contents.items():
            dest.writestr(name, content)
    return result.getvalue()


def remove_required_header(contents):
    tree = ET.fromstring(contents['xl/worksheets/sheet1.xml'])
    for text in tree.iter('{'+MAIN_NS+'}t'):
        if text.text == '申请号':
            text.text = '任意列'
    contents['xl/worksheets/sheet1.xml'] = ET.tostring(tree, encoding='utf-8')


def main():
    base = workbook([['CN123456789A', 'CN202611234567.8', None, '审中', date(2026, 11, 3)]])
    scenarios = {
        'inline-deflate': (base, True),
        'shared-deflate': (transform(base, shared=True), True),
        'stored-zip': (transform(base, compression=zipfile.ZIP_STORED), True),
        'empty-extra-sheet': (workbook([['CN123456789A', 'CN202611234567.8', None, '审中', date(2026, 11, 3)]], []), True),
        'multiple-data-sheets': (workbook([['CN123456789A', 'CN202611234567.8', '', '审中', '']], [['不应忽略的数据']]), False),
        'numeric-application': (workbook([['CN123456789A', 202611234567, '', '审中', '']]), False),
        'formula': (workbook([['CN123456789A', 'CN202611234567.8', '=1+1', '审中', '']]), False),
        'broken-zip': (base[:-40], False),
        'macro-workbook': (transform(base, mutate=lambda c: c.update({'xl/vbaProject.bin': b'not executed'})), False),
        'external-xml-entity': (transform(base, mutate=lambda c: c.update({'xl/worksheets/sheet1.xml': b'<!DOCTYPE x [<!ENTITY e SYSTEM "https://example.test/">]><x/>'})), False),
        'headers-only-complete': (workbook([]), True),
        'headers-missing-required': (transform(workbook([]), mutate=remove_required_header), False),
    }
    with tempfile.TemporaryDirectory(prefix='monitor-xlsx-test-') as temp, sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        page.set_content('<input type="file" id="file">')
        page.add_script_tag(path=str(ROOT/'site-overrides/monitor-xlsx.js'))
        network = []
        page.on('request', lambda req: network.append(req.url))
        results = {}
        for name, (data, accepted) in scenarios.items():
            fixture = Path(temp)/(name+'.xlsx')
            fixture.write_bytes(data)
            page.locator('#file').set_input_files(str(fixture))
            result = page.evaluate('''async () => {
              try {
                const bytes=await document.querySelector('#file').files[0].arrayBuffer();
                const rows=await MonitorXlsx.read(bytes);
                return {ok:true,rows,info:rows.xlsxInfo};
              } catch(e) {return {ok:false,message:e.message};}
            }''')
            assert result['ok'] == accepted, (name, result)
            if accepted and name != 'headers-only-complete':
                row = result['rows'][0]
                assert row['公开（公告）号'] == 'CN123456789A', (name, row)
                assert row['申请号'] == 'CN202611234567.8', (name, row)
                assert row['标题'] == '', (name, row)
                assert row['法律事件日期'] == '2026-11-03', (name, row)
                assert result['info']['rowCount'] == 1
            elif accepted:
                assert result['rows'] == [] and result['info']['rowCount'] == 0
            results[name] = 'PASS' if accepted else result['message']
        assert not network, network
        browser.close()
    print(json.dumps({'cases': len(results), 'networkRequests': 0, 'results': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
