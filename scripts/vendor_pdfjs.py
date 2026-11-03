"""Vendor a pinned Mozilla PDF.js npm distribution for the static PDF reader.

Only the parser, worker, CMaps, fonts, Wasm decoders/profiles and licenses are
included. Maps, the generic viewer, renderer bundle and legacy builds are omitted.
"""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import tarfile
import urllib.request

VERSION = '6.5.438'
URL = f'https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-{VERSION}.tgz'
SHA256 = '7461aefcd27c4ef0dd76f9ca5760f09466eb6b3f934432670c12132e7b3d6faa'
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'site-overrides/vendor/pdfjs'


def selected(name):
    return name in {'build/pdf.mjs', 'build/pdf.worker.mjs', 'LICENSE', 'package.json'} or name.startswith(
        ('cmaps/', 'standard_fonts/', 'wasm/', 'iccs/'))


def vendor(data):
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Official npm distribution SHA-256 mismatch')
    if DEST.exists():
        raise FileExistsError('Vendor destination exists; review/remove separately before rebuilding')
    DEST.mkdir(parents=True)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'package':
                raise ValueError('Unsafe npm archive entry')
            name = PurePosixPath(*path.parts[1:]).as_posix()
            if not selected(name) or member.isdir():
                continue
            if not member.isfile():
                raise ValueError('Non-regular selected npm archive entry')
            content = archive.extractfile(member).read()
            upstream_name = name
            # Preserve license contents while giving static hosting an explicit type.
            if PurePosixPath(name).name.startswith('LICENSE') and not PurePosixPath(name).suffix:
                name += '.txt'
            target = DEST / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            files[name] = {'upstreamPath': upstream_name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
    total = sum(f['bytes'] for f in files.values())
    if total >= 20 * 1024 * 1024:
        raise ValueError('Vendored static dependencies exceed 20 MiB budget')
    notice = {
        'package': 'pdfjs-dist', 'version': VERSION, 'license': 'Apache-2.0',
        'sourceRepository': 'https://github.com/mozilla/pdf.js',
        'npmTarball': URL, 'npmTarballSha256': SHA256,
        'officialDocs': [
            'https://mozilla.github.io/pdf.js/examples/',
            'https://mozilla.github.io/pdf.js/api/draft/module-pdfjsLib.html'],
        'selection': 'Modern parser and worker; all CMaps, standard fonts, Wasm decoders, ICC profiles and their licenses. Extensionless license files are renamed with .txt and upstream paths recorded; contents unchanged. No generic viewer, renderer bundle, source maps or legacy build.',
        'files': files, 'totalBytes': total,
    }
    (DEST / 'SOURCE.json').write_text(json.dumps(notice, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'version': VERSION, 'files': len(files), 'bytes': total}, indent=2))


if __name__ == '__main__':
    with urllib.request.urlopen(URL, timeout=60) as response:
        vendor(response.read())
