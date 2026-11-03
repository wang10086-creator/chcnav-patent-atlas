"""Batch completeness checks use isolated native-format XLSX fixtures."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_incopat_exports import ROOT, prepare
import test_native_incopat_xlsx as fixtures


class PrepareNativeBatchesTests(unittest.TestCase):
    setUp = fixtures.NativeIncopatXlsxTests.setUp
    tearDown = fixtures.NativeIncopatXlsxTests.tearDown

    def source_fixture(self, name='batch.xlsx'):
        target = self.temp_dir / name
        fixtures.fixture(target, headers=['序号', '申请人', '公开（公告）号', '申请号',
                                 '公开（公告）日', '当前法律状态', '法律状态', '链接到incoPat'],
                values=['1', '隔离测试申请人', 'CN123456789A', 'CN202410000001.1',
                        '20240101', '授权', fixtures.HISTORY, '到incoPat中查看CN123456789A'])
        return target

    def manifest(self, batches, total=1, query='隔离测试检索'):
        target = self.temp_dir / 'manifest.json'
        target.write_text(json.dumps({'searchQuery': query, 'totalResults': total, 'batches': batches}, ensure_ascii=False), encoding='utf-8')
        return target

    def test_single_complete_batch_is_complete(self):
        source = self.source_fixture()
        before = source.read_bytes()
        audit = prepare(self.manifest([{'path': source.name, 'range': '1-1'}]), self.temp_dir / 'prepared')
        self.assertTrue(audit['exportComplete'])
        self.assertEqual(audit['distinctPublications'], 1)
        self.assertEqual(audit['canonicalRows'], 2)
        self.assertEqual(before, source.read_bytes())

    def test_missing_batch_cannot_be_complete(self):
        source = self.source_fixture()
        audit = prepare(self.manifest([{'path': source.name, 'range': '1-1'}], total=2), self.temp_dir / 'prepared')
        self.assertFalse(audit['exportComplete'])
        self.assertEqual(audit['missingSequenceNumbers'], [2])

    def test_duplicate_ranges_cannot_be_complete(self):
        source = self.source_fixture()
        audit = prepare(self.manifest([{'path': source.name, 'range': '1-1'}, {'path': source.name, 'range': '1-1'}]), self.temp_dir / 'prepared')
        self.assertFalse(audit['exportComplete'])
        self.assertIn('overlapping-ranges', {x['type'] for x in audit['issues']})

    def test_source_query_mismatch_cannot_be_complete(self):
        source = self.source_fixture()
        audit = prepare(self.manifest([{'path': source.name, 'range': '1-1'}], query='不同检索式'), self.temp_dir / 'prepared')
        self.assertFalse(audit['exportComplete'])
        self.assertIn('source-query', {x['type'] for x in audit['issues']})

    def test_reports_cannot_be_written_into_public_source(self):
        source = self.source_fixture()
        with self.assertRaisesRegex(ValueError, '公开仓库之外'):
            prepare(self.manifest([{'path': source.name, 'range': '1-1'}]), ROOT / 'private-export-fixture')


if __name__ == '__main__':
    unittest.main()
