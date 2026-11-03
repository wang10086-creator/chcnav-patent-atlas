"""Build the private manual-monitor workbench, excluding accounts and exports."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'admin-ui/index.html', 'admin-ui/admin.js', 'admin-ui/admin.css',
    'scripts/manual_monitor_admin.py', 'scripts/import_incopat.py',
    'scripts/prepare_incopat_exports.py', 'scripts/incopat_xlsx_native.py',
    'site-overrides/patent-monitor-core.js',
    'site-overrides/data/monitor-config.json',
    '_site/data/portfolio-current.json',
    'MANUAL_MONITOR_ADMIN.md', 'INCOPAT_CONNECTORS.md',
    'NATIVE_INCOPAT_IMPORT.md',
)


def package(output):
    output = Path(output).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('运行包须保存在公开仓库之外')
    payloads = {name: (ROOT / name).read_bytes() for name in FILES}
    manifest = {
        'format': 'chcnav-private-manual-monitor-v1',
        'requires': ['Python 3', 'Node.js (node on PATH)'],
        'productionAdministratorIncluded': False,
        'privateExportsIncluded': False,
        'automaticExecution': False,
        'publishesWebsite': False,
        'baselinePublications': len(json.loads(payloads['_site/data/portfolio-current.json'])),
        'files': [{'path': name, 'bytes': len(data),
                   'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in payloads.items()],
    }
    payloads['package-manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'x', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in payloads.items():
            archive.writestr('chcnav-manual-monitor/' + name, data)
    with ZipFile(output) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(payloads):
            raise ValueError('运行包完整性检查失败')
        for name, data in payloads.items():
            if archive.read('chcnav-manual-monitor/' + name) != data:
                raise ValueError('运行包内容校验失败：' + name)
    return dict(path=str(output), bytes=output.stat().st_size,
                sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                files=len(payloads), baselinePublications=manifest['baselinePublications'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(package(parser.parse_args().output), ensure_ascii=False, indent=2))
