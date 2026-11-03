"""Coverage schemas use private, generated native-export fixtures only."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_incopat_exports import ROOT, prepare
import test_native_incopat_xlsx as fixtures


class ManualCoverageCliTests(unittest.TestCase):
    setUp = fixtures.NativeIncopatXlsxTests.setUp
    tearDown = fixtures.NativeIncopatXlsxTests.tearDown

    def prepared(self, **extra):
        source = self.temp_dir / 'fixture.xlsx'
        fixtures.fixture(source, headers=['序号', *fixtures.HEADERS], values=['1', *fixtures.VALUES])
        manifest = self.temp_dir / 'manifest.json'
        manifest.write_text(json.dumps(dict(searchQuery='隔离测试检索', totalResults=1,
            batches=[dict(path=source.name, range='1-1')], **extra)), encoding='utf-8')
        output = self.temp_dir / 'prepared'
        return prepare(manifest, output), output

    def test_prepare_records_result_pages_and_batches_as_distinct_units(self):
        audit, _ = self.prepared(resultPageCount=1, resultPageSize=20, expectedExportBatches=1)
        self.assertTrue(audit['exportComplete'])
        self.assertEqual(audit['resultPageCount'], 1)
        self.assertEqual(audit['downloadedExportBatches'], 1)
        self.assertEqual(audit['nativeRecords'], 1)
        self.assertEqual(audit['canonicalRows'], 2)

    def test_unrecorded_list_page_count_remains_unknown(self):
        audit, _ = self.prepared()
        self.assertTrue(audit['exportComplete'])
        self.assertIsNone(audit['resultPageCount'])
        self.assertIsNone(audit['expectedExportBatches'])

    def test_declared_missing_batch_is_not_complete(self):
        audit, _ = self.prepared(expectedExportBatches=2)
        self.assertFalse(audit['exportComplete'])
        self.assertIn('export-batch-count', {i['type'] for i in audit['issues']})

    def test_wrong_list_page_count_is_not_complete(self):
        audit, _ = self.prepared(resultPageCount=10, resultPageSize=20)
        self.assertFalse(audit['exportComplete'])
        self.assertIn('result-page-count', {i['type'] for i in audit['issues']})

    def test_cli_imports_verified_native_audit_and_preserves_original_row_evidence(self):
        audit, output = self.prepared(resultPageCount=1, resultPageSize=20, expectedExportBatches=1)
        metadata = self.temp_dir / 'run.json'
        metadata.write_text(json.dumps(dict(
            sourceUrl='https://www-incopat-com-s-6.proxy.itic-sci.com/',
            searchQuery='隔离测试检索', timeFrom='2024-01-01', timeTo='2026-11-03',
            executedAt='2026-11-03T17:08:19+08:00', totalResults=1,
            exportComplete=True, loginStatus='authenticated')), encoding='utf-8')
        baseline = self.temp_dir / 'baseline.json'
        baseline.write_text(json.dumps([dict(id='CN123456789A', applicationNumber='CN202410000001.1',
            applicants='上海华测导航技术股份有限公司', legalStatus='当前法律状态未核验')]), encoding='utf-8')
        review = self.temp_dir / 'review.json'
        command = [sys.executable, str(ROOT / 'scripts/import_incopat.py'),
            '--export', str(output / 'incopat-canonical.csv'), '--metadata', str(metadata),
            '--baseline', str(baseline), '--export-audit', str(output / 'incopat-adaptation-audit.json'),
            '--output', str(review)]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(review.read_text(encoding='utf-8'))
        self.assertEqual(report['counts']['firstStatusObservations'], 1)
        self.assertEqual(report['counts']['legalEvents'], 2)
        self.assertEqual(report['coverage']['resultPageCount'], 1)
        self.assertEqual(report['coverage']['downloadedExportBatches'], 1)
        self.assertFalse(report['coverage']['allResultPagesVisited'])
        self.assertEqual(report['legalEvents'][0]['evidence']['originalSource']['fileSha256'], audit['batches'][0]['sha256'])
        self.assertEqual(report['legalEvents'][0]['evidence']['originalSource']['excelRow'], '2')
        result = subprocess.run(command + ['--expected-export-batches', '2'], capture_output=True,
                                text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(review.read_text(encoding='utf-8'))['runState'], 'exception-review-required')


if __name__ == '__main__':
    unittest.main()
