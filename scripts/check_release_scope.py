"""Prevent unrelated monitoring or administrator features entering this release."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    'atlas.js', 'index.html', 'reader-upgrade.css', 'upgrade-shell.css',
    'design-views.js', 'design-views.css', 'data/design-views.json',
    'data/design-views-audit.csv', 'data/pdf-index.json',
    'pdf-viewer.html', 'pdf-viewer.js', 'pdf-viewer.css',
}
PREFIXES = ('assets/design-views/', 'vendor/pdfjs/')


def check():
    manifest = json.loads((ROOT / 'site-overrides-manifest.json').read_text())
    assert all(name in ALLOWED or name.startswith(PREFIXES) for name in manifest), 'Unrelated override in release'
    forbidden = ['data/monitor-config.json', 'monitor-xlsx.js', 'patent-monitor-core.js',
                 'patent-monitor.css', 'patent-monitor.js', 'admin-ui/index.html']
    for folder in ['site-overrides', '_site']:
        assert all(not (ROOT / folder / name).exists() for name in forbidden), 'Monitoring artifact in static site'
        html = (ROOT / folder / 'index.html').read_text()
        script = (ROOT / folder / 'atlas.js').read_text()
        assert all(word not in html for word in ['#monitor', 'patent-monitor', 'monitor-xlsx', '专利监控', '127.0.0.1:8765'])
        assert all(word not in script for word in ['PatentMonitor', "view==='monitor'", 'MonitorXlsx'])
    assert not (ROOT / 'admin-ui').exists(), 'Administrator UI not authorized for this release'
    print(f'PASS: {len(manifest)} gallery/route/PDF-reader overrides only; no monitoring controls or administrator UI')


if __name__ == '__main__':
    check()
