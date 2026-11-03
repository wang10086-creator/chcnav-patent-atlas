"""Public configuration never exposes monitoring writes or trusts frontend roles.

Uses the recorded public summary and local assets only. No export, authentication,
admin API call or production update occurs during this browser test.
"""
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'site-overrides'
config = json.loads((source / 'data/monitor-config.json').read_text())
portfolio_path = ROOT / '_site/data/portfolio-current.json'
original_bytes = portfolio_path.read_bytes()
portfolio = json.loads(original_bytes)
base = 'https://monitor-public.local/'
html = '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;padding:24px;background:#f5f7fa;color:#23374b;font-family:Arial,sans-serif}*{box-sizing:border-box}a{color:#136b88}.button{padding:10px 13px;text-decoration:none;border:1px solid #ccd7e1;border-radius:7px}@media(max-width:700px){body{padding:14px}}</style>
<link rel="stylesheet" href="/patent-monitor.css"><main id="app"></main><script src="/patent-monitor.js"></script>
<script>(async()=>{const docs=await fetch('/data/portfolio-current.json').then(r=>r.json());await PatentMonitor.load(docs);document.querySelector('#app').innerHTML=PatentMonitor.render();PatentMonitor.bind();window.ready=true;})();</script>'''

assert config['manualMonitoring'] == dict(mode='manual', publicReadOnly=True,
    adminWorkbenchUrl='http://127.0.0.1:8765/', requiresAdministrator=True,
    automaticEnabled=False)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                args=['--no-sandbox'])
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    requests, errors = [], []
    served_config = json.loads(json.dumps(config))

    def route(request):
        requests.append(dict(url=request.request.url, method=request.request.method))
        path = request.request.url.removeprefix(base).split('?', 1)[0]
        if path == 'data/monitor-config.json':
            request.fulfill(content_type='application/json', body=json.dumps(served_config, ensure_ascii=False))
        elif path == 'data/portfolio-current.json':
            request.fulfill(content_type='application/json', body=original_bytes)
        elif path in ('patent-monitor.js', 'patent-monitor.css'):
            request.fulfill(content_type='text/css' if path.endswith('.css') else 'application/javascript',
                            body=(source / path).read_text())
        else:
            request.fulfill(content_type='text/html', body=html)

    context.route('**/*', route)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))

    def assert_readonly():
        page.wait_for_function('window.ready')
        assert page.locator('[data-monitor-access="public-readonly"]').count() == 1
        assert page.locator('input[type=file],input[type=password],form').count() == 0
        assert page.locator('#monitor-reviewed,#monitor-snapshot-download,#monitor-report-download').count() == 0
        assert '手动核查工作台' in page.locator('.patent-monitor').inner_text()
        assert '首次观察' in page.locator('.patent-monitor').inner_text()
        assert page.locator('#monitor-admin-workbench').get_attribute('href') == 'http://127.0.0.1:8765/'
        assert page.locator('#monitor-admin-workbench').get_attribute('rel') == 'noopener noreferrer'

    page.goto(base)
    assert_readonly()
    timestamp = page.locator('[data-monitor-executed-at]').get_attribute('data-monitor-executed-at')
    timestamp_text = page.locator('[data-monitor-executed-at]').inner_text()
    assert timestamp == config['source']['interactiveValidation']['sourceExecutedAt']
    assert '938' in page.locator('.monitor-public-metrics').inner_text()
    assert '2,333' in page.locator('.monitor-public-metrics').inner_text() or '2333' in page.locator('.monitor-public-metrics').inner_text()
    page.screenshot(path=str(ROOT.parent / 'manual-monitor-public-desktop.png'))
    page.evaluate('''() => {
      localStorage.setItem('admin','true');localStorage.setItem('isAdmin','true');
      localStorage.setItem('role','administrator');localStorage.setItem('monitorAdmin','true');
      sessionStorage.setItem('admin','true');
    }''')
    page.goto(base + '?admin=true&role=administrator')
    assert_readonly()
    assert page.locator('[data-monitor-executed-at]').get_attribute('data-monitor-executed-at') == timestamp
    assert page.locator('[data-monitor-executed-at]').inner_text() == timestamp_text
    page.reload()
    assert_readonly()
    assert page.locator('[data-monitor-executed-at]').inner_text() == timestamp_text
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(ROOT.parent / 'manual-monitor-public-mobile.png'))
    # A malformed public URL cannot redirect an administrator to an external host.
    served_config['manualMonitoring']['adminWorkbenchUrl'] = 'https://untrusted.invalid/collect'
    page.reload();page.wait_for_function('window.ready')
    assert page.locator('#monitor-admin-workbench').count() == 0
    assert '地址尚未正确配置' in page.locator('.patent-monitor').inner_text()
    served_config['profiles'] = []
    page.reload();page.wait_for_function('window.ready')
    assert page.locator('[role=alert]').count() == 1
    assert page.locator('input[type=file],input[type=password],form').count() == 0
    assert not errors, errors
    assert all(r['url'].startswith(base) and r['method'] == 'GET' for r in requests), requests
    browser.close()

assert portfolio_path.read_bytes() == original_bytes
report = dict(publicReadOnly=True, administrativeControlsExposed=False,
    frontendRoleSpoofingIgnored=True, actualExecutionTimePreserved=timestamp,
    refreshDoesNotCreateExecution=True, invalidExternalWorkbenchRejected=True,
    malformedConfigHasNoAdministrativeControls=True,
    ordinaryVisitorNetworkWrites=0, pageErrors=errors, mobileOverflow=False,
    baselineDocuments=len(portfolio), originalPortfolioSha256=hashlib.sha256(original_bytes).hexdigest(),
    originalPortfolioUnchanged=True,
    authorityBoundary='Actual import, review and persistence authorization is enforced by the separate private admin service, not frontend visibility.')
(ROOT / 'reports/manual-monitor-public-validation.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print('PASS: actual public configuration is read-only, frontend role spoofing has no effect, source time stable, no network writes or data changes')
