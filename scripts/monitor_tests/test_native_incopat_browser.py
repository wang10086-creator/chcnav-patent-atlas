"""Isolated native-Incopat XLSX browser regression.

Fixtures reproduce the observed export structure; no private real export is
included or represented as having been tested here. No network beyond the
temporary loopback page is allowed by the harness.
"""
from contextlib import contextmanager
from datetime import date
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
HEADERS = ['序号', '标题 (中文)', '申请人', '公开（公告）号', '申请号',
           '公开（公告）日', '当前法律状态', '法律状态', '链接到incoPat',
           '专利有效性', '简单同族ID']
HISTORY = ('#法律状态公告日：20240101;\n法律状态：公开;\n描述信息：公布;\n\n'
           '#法律状态公告日：20250102;\n法律状态：授权;\n描述信息：授权记录;\n\n')
VALUES = ['1', '隔离测试专利', '隔离测试申请人', 'CN123456789A',
          'CN202410000001.1', '20240101', '授权', HISTORY,
          '到incoPat中查看', '有效', 'isolated-family']
URL = 'https://www.incopat.com/detail/init2?formerQuery=isolated-fixture&local=zh'
QUERY = '申请人=隔离测试申请人（精确）'


def sheet_xml(rows, *, hyperlink=False, formula=False, numeric_date=None,
              numeric_app=False, shared=None):
    output = []
    for number, row in enumerate(rows, 1):
        cells = []
        for column, value in enumerate(row):
            ref = chr(65 + column) + str(number)
            if number > 1 and ((numeric_date is not None and column == 5) or
                               (numeric_app and column == 4)):
                content = str(numeric_date if column == 5 else 202410000001)
                cells.append(f'<c r="{ref}" t="n"><v>{content}</v></c>')
                continue
            if shared is not None:
                shared.append(str(value))
                content = f'<v>{len(shared) - 1}</v>'
                kind = 's'
            else:
                content = '<is><t>' + escape(str(value)) + '</t></is>'
                kind = 'inlineStr'
            f = '<f>1+1</f>' if formula and number == 2 and column == 1 else ''
            cells.append(f'<c r="{ref}" t="{kind}">{f}{content}</c>')
        output.append(f'<row r="{number}">' + ''.join(cells) + '</row>')
    links = '<hyperlinks><hyperlink ref="I2" r:id="link1"/></hyperlinks>' if hyperlink else ''
    return (f'<worksheet xmlns="{NS}" xmlns:r="{REL}"><dimension ref="A1"/>'
            '<sheetData>' + ''.join(output) + '</sheetData>' + links + '</worksheet>')


def fixture(*, headers=None, values=None, extra=False, formula=False,
            shared_strings=False, numeric_date=None, numeric_app=False,
            date1904=False, source_range='1-1', source_count='1', sequence='1',
            no_intro=False, bad_intro=False, hyperlink=URL, compression=ZIP_DEFLATED,
            intro_formula=False, main_name='下载的著录项1'):
    headers = list(headers or HEADERS)
    values = list(values or VALUES)
    values[0] = sequence
    names = [main_name] + ([] if no_intro else ['下载简介']) + (['未确认数据'] if extra else [])
    sheets = ''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
                     for i, name in enumerate(names, 1))
    rels = ''.join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml" Type="{REL}/worksheet"/>'
                   for i in range(1, len(names) + 1))
    shared = [] if shared_strings else None
    first = sheet_xml([headers, values], hyperlink=True, formula=formula,
                      numeric_date=numeric_date, numeric_app=numeric_app, shared=shared)
    stream = BytesIO()
    with ZipFile(stream, 'w', compression=compression) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="{REL}"><workbookPr date1904="{str(date1904).lower()}"/><sheets>{sheets}</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{PKG}">{rels}</Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', first)
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels', f'<Relationships xmlns="{PKG}"><Relationship Id="link1" Type="{REL}/hyperlink" Target="{escape(hyperlink)}" TargetMode="External"/></Relationships>')
        if not no_intro:
            intro = ([['公开（公告）号', '申请号'], ['CN123456789A', 'CN202410000001.1']]
                     if bad_intro else [['下载内容', QUERY], ['数据范围', source_range], ['数量', source_count]])
            z.writestr('xl/worksheets/sheet2.xml', sheet_xml(intro, formula=intro_formula, shared=shared))
        if extra:
            z.writestr(f'xl/worksheets/sheet{len(names)}.xml', sheet_xml([['未知列'], ['未知数据']], shared=shared))
        if shared is not None:
            z.writestr('xl/sharedStrings.xml', f'<sst xmlns="{NS}">' + ''.join('<si><t>' + escape(s) + '</t></si>' for s in shared) + '</sst>')
    return stream.getvalue()


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class NativeBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='incopat-native-browser-')
        cls.folder = Path(cls.temp.name)
        (cls.folder / 'index.html').write_text('<!doctype html><input type="file" id="file">')
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=cls.temp.name))
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.p = sync_playwright().start()
        cls.browser = cls.p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        cls.page = cls.browser.new_page()
        cls.page.goto(f'http://127.0.0.1:{cls.server.server_port}/')
        cls.page.add_script_tag(path=str(ROOT / 'site-overrides/monitor-xlsx.js'))
        cls.network = []
        cls.page.on('request', lambda req: cls.network.append(req.url))
        cls.cases = []

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()
        if cls.network:
            raise AssertionError('Parser emitted unexpected network requests: ' + str(cls.network))

    def read(self, data):
        path = self.folder / 'fixture.xlsx'
        path.write_bytes(data)
        self.page.locator('#file').set_input_files(str(path))
        result = self.page.evaluate('''async () => {
          try {
            const bytes = await document.querySelector('#file').files[0].arrayBuffer();
            const rows = await MonitorXlsx.read(bytes);
            return {ok:true, rows, info:rows.xlsxInfo};
          } catch(e) { return {ok:false, message:e.message}; }
        }''')
        self.assertEqual(data, path.read_bytes())
        self.cases.append(self.id())
        return result

    def test_native_dimension_intro_hyperlink_history_audit(self):
        data = fixture()
        result = self.read(data)
        self.assertTrue(result['ok'], result)
        info = result['info']
        self.assertEqual(info['declaredDimension'], 'A1')
        self.assertTrue(info['physicalXmlRowsUsed'])
        self.assertTrue(info['ignoredIntroductionSheet'])
        self.assertEqual(info['physicalDataRows'], 1)
        self.assertEqual(info['expandedEventRows'], 2)
        self.assertEqual(info['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(info['sourceRange'], '1-1')
        self.assertEqual(info['sourceSearchQuery'], QUERY)
        self.assertEqual(info['sourceSequences'], [1])
        self.assertEqual(info['issues'], [])
        self.assertTrue(info['sourceCoverageVerified'])
        self.assertEqual([r['eventDate'] for r in result['rows']], ['2024-01-01', '2025-01-02'])
        self.assertEqual([r['legalEvent'] for r in result['rows']], ['公开', '授权'])
        self.assertTrue(all(r['evidenceUrl'] == URL for r in result['rows']))
        self.assertTrue(all(r['sourceExcelRow'] == 2 for r in result['rows']))
        self.assertEqual(result['rows'][0]['title'], '隔离测试专利')
        self.assertEqual(info['rawRecords'][0]['rawFields']['法律状态'], HISTORY)
        self.assertNotIn('法律状态', result['rows'][0])
        self.assertEqual(info['rawRecords'][0]['cells']['链接到incoPat']['hyperlink'], URL)

    def test_native_shared_strings_and_stored_zip(self):
        result = self.read(fixture(shared_strings=True, compression=ZIP_STORED))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['rows'][0]['title'], '隔离测试专利')
        self.assertEqual(result['info']['issues'], [])

    def test_native_whitespace_headers(self):
        headers = [h.replace('申请号', '申 请号').replace('公开（公告）号', '公开 （公告）号') for h in HEADERS]
        result = self.read(fixture(headers=headers))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['rows'][0]['applicationNumber'], 'CN202410000001.1')

    def test_native_excel_numeric_date_1900(self):
        result = self.read(fixture(numeric_date=45292))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['rows'][0]['publicationDate'], '2024-01-01')

    def test_native_excel_numeric_date_1904(self):
        serial = (date(2024, 1, 1) - date(1904, 1, 1)).days
        result = self.read(fixture(numeric_date=serial, date1904=True))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['rows'][0]['publicationDate'], '2024-01-01')

    def test_validity_is_not_current_legal_status(self):
        values = list(VALUES)
        values[6] = '未核验'
        result = self.read(fixture(values=values))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['rows'][0]['legalStatus'], '未核验')
        self.assertEqual(result['info']['rawRecords'][0]['rawFields']['专利有效性'], '有效')

    def test_missing_intro_is_audited_incomplete(self):
        result = self.read(fixture(no_intro=True))
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['info']['sourceCoverageVerified'])
        self.assertIn('introduction-missing', [i['type'] for i in result['info']['issues']])

    def test_count_and_range_mismatch_are_not_complete(self):
        result = self.read(fixture(source_range='1-2', source_count='2'))
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['info']['sourceCoverageVerified'])
        self.assertIn('source-count', [i['type'] for i in result['info']['issues']])
        self.assertIn('source-range-count', [i['type'] for i in result['info']['issues']])

    def test_numeric_app_is_rejected(self):
        result = self.read(fixture(numeric_app=True))
        self.assertFalse(result['ok'])
        self.assertIn('编号列为数值', result['message'])

    def test_unknown_extra_sheet_is_not_ignored(self):
        result = self.read(fixture(extra=True))
        self.assertFalse(result['ok'])
        self.assertIn('未确认', result['message'])

    def test_spoofed_introduction_is_not_ignored(self):
        result = self.read(fixture(bad_intro=True))
        self.assertFalse(result['ok'])
        self.assertIn('下载简介缺少已知来源键', result['message'])

    def test_formula_is_rejected(self):
        result = self.read(fixture(formula=True))
        self.assertFalse(result['ok'])
        self.assertIn('公式单元格', result['message'])

    def test_formula_like_native_text_is_rejected(self):
        values = list(VALUES)
        values[1] = '=HYPERLINK("https://fixture.invalid", "x")'
        result = self.read(fixture(values=values))
        self.assertFalse(result['ok'])
        self.assertIn('公式样式文本', result['message'])

    def test_javascript_hyperlink_is_rejected(self):
        result = self.read(fixture(hyperlink='javascript:alert(1)'))
        self.assertFalse(result['ok'])
        self.assertIn('HTTP 来源地址', result['message'])

    def test_missing_legal_description_rejects_all_rows(self):
        values = list(VALUES)
        values[7] = '#法律状态公告日：20250102;\n法律状态：授权;'
        result = self.read(fixture(values=values))
        self.assertFalse(result['ok'])
        self.assertIn('缺少事件或描述信息', result['message'])

    def test_renamed_history_table_is_not_silently_generic(self):
        result = self.read(fixture(no_intro=True, main_name='Sheet1'))
        self.assertFalse(result['ok'])
        self.assertIn('不能静默略过历史拆分', result['message'])

    def test_invalid_legal_date_is_rejected(self):
        values = list(VALUES)
        values[7] = HISTORY.replace('20240101', '20240230')
        result = self.read(fixture(values=values))
        self.assertFalse(result['ok'])
        self.assertIn('无效公告日期', result['message'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
