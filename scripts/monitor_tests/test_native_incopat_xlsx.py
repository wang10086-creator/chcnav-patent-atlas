"""Fixtures reproduce native exports' incorrect dimensions and hyperlink storage."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from xml.sax.saxutils import escape
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_incopat import xlsx_rows

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
HEADERS = ['标题 (中文)', '申请人', '公开（公告）号', '申请号',
           '公开（公告）日', '当前法律状态', '法律状态', '链接到incoPat']
HISTORY = ('#法律状态公告日：20240101;\n法律状态：公开;\n描述信息：公开;\n\n'
           '#法律状态公告日：20250102;\n法律状态：授权;\n描述信息：授权;\n\n')
VALUES = ['隔离测试专利', '隔离测试申请人', 'CN123456789A', 'CN202410000001.1',
          '20240101', '授权', HISTORY, '到incoPat中查看CN123456789A']
URL = 'https://www.incopat.com/detail/init2?formerQuery=isolated-fixture&local=zh'


def sheet_xml(rows, hyperlink=False, formula=False):
    body = []
    for n, row in enumerate(rows, 1):
        cells = []
        for i, value in enumerate(row):
            ref = chr(65 + i) + str(n)
            f = '<f>1+1</f>' if formula and n == 2 and i == 0 else ''
            cells.append(f'<c r="{ref}" t="inlineStr">{f}<is><t>{escape(value)}</t></is></c>')
        body.append(f'<row r="{n}">' + ''.join(cells) + '</row>')
    links = '<hyperlinks><hyperlink ref="H2" r:id="rId1"/></hyperlinks>' if hyperlink else ''
    return (f'<worksheet xmlns="{S}" xmlns:r="{R}"><dimension ref="A1"/>'
            '<sheetData>' + ''.join(body) + '</sheetData>' + links + '</worksheet>')


def fixture(path, headers=HEADERS, values=VALUES, extra=False, formula=False):
    names = ['下载的著录项1', '下载简介'] + (['未确认数据'] if extra else [])
    sheets = ''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(names, 1))
    rels = ''.join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml" Type="{R}/worksheet"/>' for i in range(1, len(names) + 1))
    with ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{S}" xmlns:r="{R}"><workbookPr date1904="false"/><sheets>{sheets}</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{P}">{rels}</Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml([headers, values], hyperlink=True, formula=formula))
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels', f'<Relationships xmlns="{P}"><Relationship Id="rId1" Type="{R}/hyperlink" Target="{escape(URL)}" TargetMode="External"/></Relationships>')
        z.writestr('xl/worksheets/sheet2.xml', sheet_xml([['下载内容', '隔离测试检索'], ['数据范围', '1-1'], ['数量', '1']]))
        if extra:
            z.writestr('xl/worksheets/sheet3.xml', sheet_xml([['未知列'], ['未知数据']]))


class NativeIncopatXlsxTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(os.environ.get('CODEX_TEST_TMPDIR', tempfile.gettempdir())).resolve()
        self.temp_dir = self.temp_root / ('incopat-fixture-' + uuid.uuid4().hex)
        self.temp_dir.mkdir()
        self.path = self.temp_dir / 'fixture.xlsx'

    def tearDown(self):
        if self.temp_dir.resolve().parent != self.temp_root:
            raise ValueError('Unexpected fixture cleanup path')
        shutil.rmtree(self.temp_dir)

    def test_physical_rows_hyperlink_intro_and_event_dates(self):
        fixture(self.path)
        original = self.path.read_bytes()
        rows, info = xlsx_rows(self.path)
        self.assertEqual(info['declaredDimension'], 'A1')
        self.assertEqual(info['worksheetRows'], 1)
        self.assertEqual(info['expandedEventRows'], 2)
        self.assertTrue(info['ignoredIntroductionSheet'])
        self.assertEqual([r['eventDate'] for r in rows], ['2024-01-01', '2025-01-02'])
        self.assertEqual([r['legalEvent'] for r in rows], ['公开', '授权'])
        self.assertEqual(rows[0]['title'], '隔离测试专利')
        self.assertEqual(rows[0]['当前法律状态'], '授权')
        self.assertEqual(rows[0]['evidenceUrl'], URL)
        self.assertEqual(rows[0]['sourceExcelRow'], 2)
        self.assertEqual(rows[0]['publicationDate'], '2024-01-01')
        self.assertEqual(original, self.path.read_bytes())

    def test_explicit_introduction_is_not_a_patent_table(self):
        fixture(self.path)
        with self.assertRaisesRegex(ValueError, '必需表头'):
            xlsx_rows(self.path, '下载简介')

    def test_missing_identifier_header_is_rejected(self):
        fixture(self.path, headers=['缺失申请号' if h == '申请号' else h for h in HEADERS])
        with self.assertRaisesRegex(ValueError, '必需表头'):
            xlsx_rows(self.path)

    def test_unknown_populated_sheet_requires_selection(self):
        fixture(self.path, extra=True)
        with self.assertRaisesRegex(ValueError, '未确认'):
            xlsx_rows(self.path)
        rows, info = xlsx_rows(self.path, '下载的著录项1')
        self.assertEqual(len(rows), 2)
        self.assertTrue(info['explicitlySelected'])

    def test_formulas_are_not_evaluated(self):
        fixture(self.path, formula=True)
        with self.assertRaisesRegex(ValueError, 'formula'):
            xlsx_rows(self.path)

    def test_incomplete_legal_history_is_rejected(self):
        values = [*VALUES]
        values[6] = '#法律状态公告日：20250102;\n法律状态：授权;'
        fixture(self.path, values=values)
        with self.assertRaisesRegex(ValueError, 'lacks event or description'):
            xlsx_rows(self.path)

    def test_cli_bridge_preserves_chinese_across_every_byte_boundary(self):
        # Exercise the actual CLI bridge with a stream that splits every UTF-8
        # multibyte character, reproducing the real Windows pipe corruption.
        importer = Path(__file__).resolve().parents[1] / 'import_incopat.py'
        tree = ast.parse(importer.read_text(encoding='utf-8'))
        bridge = next(ast.literal_eval(n.value) for n in ast.walk(tree)
                      if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'bridge' for t in n.targets))
        applicant = '隔离测试申请人股份有限公司'
        payload = {'rows': [{'publicationNumber': 'CN123456789A',
                             'applicationNumber': 'CN202410000001.1',
                             'applicants': applicant, 'legalStatus': '授权',
                             'legalEvent': '授权', 'eventDate': '2025-01-02'}],
                   'baseline': [{'id': 'CN123456789A', 'applicationNumber': 'CN202410000001.1'}],
                   'metadata': {'searchQuery': '隔离检索', 'timeFrom': '2024-01-01',
                                'timeTo': '2026-11-03', 'executedAt': '2026-11-03T17:00:00+08:00',
                                'totalResults': 1, 'resultCountBasis': 'publications',
                                'expectedPages': 1, 'downloadedPages': 1, 'exportComplete': True,
                                'loginStatus': 'authenticated', 'fileSha256': '0' * 64,
                                'sourceUrl': 'https://www-incopat-com-s-6.proxy.itic-sci.com/'},
                   'profile': {'id': 'fixture', 'name': '隔离测试', 'inScopeApplicantNames': [applicant]}}
        data_path = self.temp_dir / 'transport.json'
        data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        prefix = ("const {Readable}=require('stream');"
                  "const bytes=require('fs').readFileSync(process.argv[2]);"
                  "Object.defineProperty(process,'stdin',{value:Readable.from("
                  "Array.from(bytes,b=>Buffer.from([b]))) });")
        core = Path(__file__).resolve().parents[2] / 'site-overrides/patent-monitor-core.js'
        completed = subprocess.run(['node', '-e', prefix + bridge, str(core), str(data_path)],
                                   text=True, encoding='utf-8', capture_output=True, check=True)
        result = json.loads(completed.stdout)
        self.assertEqual(result['counts']['anomalies'], 0)
        self.assertEqual(result['observations'][0]['applicants'], [applicant])
        self.assertNotIn('\ufffd', completed.stdout)


if __name__ == '__main__':
    unittest.main()
