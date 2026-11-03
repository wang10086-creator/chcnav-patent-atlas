"""Private temporary XLSX/CSV CLI fixtures; no production data is changed."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import openpyxl

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='incopat-cli-test-') as directory:
    temp = Path(directory)
    baseline = temp / 'baseline.json'; baseline.write_text(json.dumps([dict(id='CN100000001A', applicationNumber='CN202600000001.1', applicants='上海华测导航技术股份有限公司', legalStatus='当前法律状态未核验')]))
    metadata = dict(sourceUrl='https://www-incopat-com-s-6.proxy.itic-sci.com/', searchQuery='ISOLATED TEST ONLY', timeFrom='2026-01-01', timeTo='2026-12-31', executedAt='2026-11-03T07:00:00Z', totalResults=2, expectedPages=1, downloadedPages=1, exportComplete=True, loginStatus='authenticated')
    meta_file = temp / 'metadata.json'; meta_file.write_text(json.dumps(metadata))
    xlsx = temp / 'isolated.xlsx'
    wb = openpyxl.Workbook(); sheet = wb.active
    sheet.append(['公开（公告）号', '申请号', '申请人', '当前法律状态'])
    sheet.append(['CN100000001A', 'CN202600000001.1', '上海华测导航技术股份有限公司', '审中'])
    sheet.append(['CN100000001B', 'CN202600000001.1', '上海华测导航技术股份有限公司', '授权'])
    wb.save(xlsx)
    output = temp / 'review.json'
    command = ['python3', str(ROOT / 'scripts/import_incopat.py'), '--export', str(xlsx), '--metadata', str(meta_file), '--baseline', str(baseline), '--output', str(output)]
    result = subprocess.run(command, capture_output=True, text=True); assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text()); assert report['counts']['stateChanges'] == 0
    assert report['counts']['firstStatusObservations'] == 2 and report['counts']['newPublicationVersions'] == 1
    assert report['metadata']['fileSha256'] == hashlib.sha256(xlsx.read_bytes()).hexdigest()
    metadata['downloadedPages'] = 0; meta_file.write_text(json.dumps(metadata))
    result = subprocess.run(command, capture_output=True, text=True); assert result.returncode == 2
    assert json.loads(output.read_text())['runState'] == 'exception-review-required'
    result = subprocess.run(command[:-1] + [str(ROOT / 'site-overrides/not-allowed.json')], capture_output=True, text=True)
    assert result.returncode != 0 and not (ROOT / 'site-overrides/not-allowed.json').exists()
    wb = openpyxl.Workbook(); sheet = wb.active
    sheet.append(['公开（公告）号', '申请号', '申请人', '当前法律状态', '法律事件', '法律事件日期'])
    for event, date in [('隔离事件一', '2026-01-01'), ('隔离事件二', '2026-02-01')]:
        sheet.append(['CN100000001A', 'CN202600000001.1', '上海华测导航技术股份有限公司', '审中', event, date])
    wb.save(xlsx)
    metadata.update(downloadedPages=1, totalResults=1, resultCountBasis='publications'); meta_file.write_text(json.dumps(metadata))
    result = subprocess.run(command, capture_output=True, text=True); assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text()); assert report['counts']['legalEvents'] == 2 and report['counts']['distinctPublications'] == 1
    assert report['metadata']['importedRows'] == 2 and report['metadata']['totalResults'] == 1
    result = subprocess.run(command + ['--count-basis', 'rows'], capture_output=True, text=True); assert result.returncode == 2
    print('PASS: real local XLSX CLI, checksum, status/version split, completeness, explicit document/row count basis, multi-event preservation, public-output refusal')
