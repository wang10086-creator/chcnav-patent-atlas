"""Isolated browser import tests; every fixture is synthetic and local."""
import csv
import io
import json
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright
import openpyxl

ROOT = Path(__file__).resolve().parents[2]
base = 'https://monitor.local/'
profile = dict(id='test-only', name='隔离测试公司', inScopeApplicantNames=['隔离测试公司'], aliases=[],
    relatedApplicantCandidates=[], nameEvidence='仅用于隔离测试', searchRule='精确名称测试')
config = json.loads((ROOT / 'site-overrides/data/monitor-config.json').read_text())
config['profiles'] = [profile, dict(profile, id='empty-profile', name='另一隔离测试公司', inScopeApplicantNames=['另一隔离测试公司'])]
baseline = [dict(id='CN100000001A', applicationNumber='CN202600000001.1', applicants='隔离测试公司', legalStatus='当前法律状态未核验')]
headers = ['公开（公告）号', '申请号', '名称', '申请人', '当前法律状态']
rows = [['CN100000001A', 'CN202600000001.1', '<script>隔离测试</script>', '隔离测试公司', '审中'],
        ['CN100000001B', 'CN202600000001.1', '隔离授权版', '隔离测试公司', '授权'],
        ['CN100000003A', 'CN202600000003.3', '隔离新增申请', '隔离测试公司', '审中']]
html = '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/patent-monitor.css"><main id="app"></main><script src="/patent-monitor-core.js"></script><script src="/monitor-xlsx.js"></script><script src="/patent-monitor.js"></script><script>(async()=>{window.baseline=BASELINE;await PatentMonitor.load(baseline);document.querySelector('#app').innerHTML=PatentMonitor.render();PatentMonitor.bind();window.ready=true;})();</script>'''.replace('BASELINE', json.dumps(baseline, ensure_ascii=False))

with tempfile.TemporaryDirectory(prefix='monitor-isolated-') as temp, sync_playwright() as p:
    temp = Path(temp)
    csv_file = temp / 'isolated.csv'
    with csv_file.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(headers); writer.writerows(rows)
    xlsx = temp / 'isolated.xlsx'
    book = openpyxl.Workbook(); sheet = book.active; sheet.append(headers)
    for row in rows: sheet.append(row)
    book.save(xlsx)
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
    requests = []
    def route(request):
        path = request.request.url.removeprefix(base)
        requests.append(request.request.url)
        if path == 'data/monitor-config.json': request.fulfill(content_type='application/json', body=json.dumps(config, ensure_ascii=False))
        elif path in ['patent-monitor.css', 'patent-monitor-core.js', 'patent-monitor.js', 'monitor-xlsx.js']:
            request.fulfill(content_type='text/css' if path.endswith('.css') else 'application/javascript', body=(ROOT / 'site-overrides' / path).read_text())
        else: request.fulfill(content_type='text/html', body=html)
    context.route('**/*', route)
    page = context.new_page(); errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(base); page.wait_for_function('window.ready')
    page.locator('#monitor-profile').select_option('empty-profile')
    assert '当前对象基线：0' in page.locator('.monitor-status-grid').inner_text()
    page.locator('#monitor-profile').select_option('test-only')
    page.locator('#monitor-export-file').set_input_files(csv_file)
    for selector, value in {'monitor-query': '隔离测试精确检索，非正式数据', 'monitor-time-from': '2026-01-01', 'monitor-time-to': '2026-12-31', 'monitor-executed-at': '2026-11-03T15:00', 'monitor-total': '3', 'monitor-pages-expected': '1', 'monitor-pages-actual': '1'}.items():
        page.locator('#' + selector).fill(value)
    page.locator('#monitor-login').select_option('authenticated'); page.locator('#monitor-complete').check()
    def run():
        page.locator('#monitor-import-form button[type=submit]').click()
        page.wait_for_function("document.querySelector('#monitor-run-message').textContent.includes('已生成')")
    def get_report():
        with page.expect_download() as download: page.locator('#monitor-report-download').click()
        return json.loads(Path(download.value.path()).read_text())
    run(); report = get_report()
    assert report['counts']['firstStatusObservations'] == 3 and report['counts']['newApplicationCount'] == 1
    assert report['counts']['newPublicationVersions'] == 1
    assert page.locator('#monitor-report script').count() == 0
    page.locator('#monitor-reviewed').check()
    with page.expect_download() as download: page.locator('#monitor-snapshot-download').click()
    snapshot_file = temp / 'reviewed.json'; snapshot_file.write_text(Path(download.value.path()).read_text())
    page.locator('#monitor-baseline-file').set_input_files(snapshot_file); run(); report = get_report()
    assert report['runState'] == 'no-difference-in-complete-export'
    page.locator('#monitor-login').select_option('expired'); run(); report = get_report()
    assert report['runState'] == 'exception-review-required'
    page.locator('#monitor-login').select_option('authenticated'); page.locator('#monitor-baseline-file').set_input_files([])
    page.locator('#monitor-export-file').set_input_files(xlsx); run(); report = get_report()
    assert report['counts']['firstStatusObservations'] == 3 and report['metadata']['xlsxInfo']['rowCount'] == 3
    events = temp / 'one-publication-two-events.csv'
    with events.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(headers + ['法律事件', '法律事件日期'])
        writer.writerow(rows[0] + ['隔离事件一', '2026-01-01']); writer.writerow(rows[0] + ['隔离事件二', '2026-02-01'])
    page.locator('#monitor-export-file').set_input_files(events); page.locator('#monitor-total').fill('1')
    page.locator('#monitor-count-basis').select_option('publications'); run(); report = get_report()
    assert report['counts']['anomalies'] == 0 and report['counts']['legalEvents'] == 2
    assert report['metadata']['importedRows'] == 2 and report['metadata']['distinctPublications'] == 1
    assert report['metadata']['resultCountBasis'] == 'publications'
    page.locator('#monitor-count-basis').select_option('rows'); run(); report = get_report()
    assert report['runState'] == 'exception-review-required'
    page.locator('#monitor-total').fill('2'); run(); report = get_report()
    assert report['counts']['anomalies'] == 0 and report['metadata']['resultCountBasis'] == 'rows'
    page.screenshot(path=str(ROOT.parent / 'monitor-preview-desktop.png'), full_page=False)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.monitor-intro').scroll_into_view_if_needed()
    page.screenshot(path=str(ROOT.parent / 'monitor-preview-mobile.png'), full_page=False)
    assert not errors, errors
    assert all(url.startswith(base) for url in requests), requests
    browser.close()
    print('PASS: actual browser CSV/XLSX imports, profile scope, review snapshot, no-change, expired-login, escaped content, desktop/mobile, no external requests or notifications')
