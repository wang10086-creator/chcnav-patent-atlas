"""Read-only preservation audit for the full patent-atlas upgrade.

The v19 ZIP artifact remains an immutable reference. Existing data, evidence,
styles and images must retain their hashes; only the HTML/JS presentation may
change. Added files are allowed. Run after verify_extract.py, optionally checking
the complete PDF checkout with --pdf-repo ../pdf-repository.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PDF_INDEX_SHA256 = '0eeff63ad27356e9cf8f61e86778a92029793c314e47a878cc5bea8ef76b3434'
PDF_SOURCE_COMMIT = 'f14c181a8665bd58a335201f7c1fd92cd10867a0'
DISPLAY_CHANGES = {'index.html', 'atlas.js'}
IMAGE_SUFFIXES = {'.webp', '.png', '.jpg', '.jpeg', '.gif', '.svg'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def audit_design_evidence(site, docs, index, failures):
    path = site / 'data/design-views.json'
    if not path.is_file():
        return {'status': 'not-installed'}
    manifest = json.loads(path.read_text())
    records = manifest.get('documents', {})
    designs = {d['id']: d for d in docs if d['patentType'] == '外观设计'}
    if set(records) != set(designs):
        failures.append('design evidence inventory differs from the 152 design publications')
    if manifest.get('sourcePdfCommit') != PDF_SOURCE_COMMIT:
        failures.append('design evidence source PDF commit differs from protected PDF index')
    assets = {}
    actual = dict(designDocuments=len(records), identityVerified=0, identityUnconfirmed=0,
                  pdfPages=0, renderedPages=0, drawingPages=0, expectedViews=0,
                  expectedCountKnownDocuments=0, recognizedViewLabels=0,
                  splitViewImages=0, viewCountsAgreeDocuments=0)

    def asset(name, expected_size):
        if not isinstance(name, str) or not name.startswith('assets/design-views/') or any(
                p in {'', '.', '..'} for p in name.split('/')) or '\\' in name:
            failures.append(f'invalid design evidence resource path: {name}')
            return
        file = site / name
        if not file.is_file():
            failures.append(f'design evidence resource missing: {name}')
        else:
            size = file.stat().st_size
            if size != expected_size:
                failures.append(f'design evidence size differs from manifest: {name}')
            with file.open('rb') as handle:
                signature = handle.read(12)
            if signature[:4] != b'RIFF' or signature[8:12] != b'WEBP':
                failures.append(f'design evidence is not a WebP image: {name}')
            assets[name] = size

    for publication, record in records.items():
        source = index['documents'].get(publication)
        if not source or record.get('id') != publication or record.get('applicationNumber') != designs.get(publication, {}).get('applicationNumber'):
            failures.append(f'design publication identity differs from portfolio: {publication}')
            continue
        pdf = record.get('pdf', {})
        if (pdf.get('path'), pdf.get('sha256'), pdf.get('commit')) != (
                source['path'], source['sha256'], PDF_SOURCE_COMMIT):
            failures.append(f'design evidence PDF source differs from protected index: {publication}')
        encoded_path = quote(source['path'], safe='/')
        expected_view = f'https://github.com/{index["repository"]}/blob/{PDF_SOURCE_COMMIT}/{encoded_path}'
        expected_download = f'https://raw.githubusercontent.com/{index["repository"]}/{PDF_SOURCE_COMMIT}/{encoded_path}'
        if pdf.get('viewUrl') != expected_view or pdf.get('downloadUrl') != expected_download:
            failures.append(f'design gallery PDF links differ from protected source: {publication}')
        verified = record.get('identity', {}).get('status') in {'verified-text', 'verified-ocr'}
        actual['identityVerified' if verified else 'identityUnconfirmed'] += 1
        page_count = pdf.get('pageCount', 0)
        pages = record.get('pages', [])
        if [p.get('pageNumber') for p in pages] != list(range(1, page_count + 1)):
            failures.append(f'design PDF page coverage not contiguous or complete: {publication}')
        if record.get('renderedPageCount') != len(pages):
            failures.append(f'design rendered-page count inconsistent: {publication}')
        actual['pdfPages'] += page_count
        actual['renderedPages'] += len(pages)
        expected_views = record.get('expectedViewCount')
        if isinstance(expected_views, int):
            actual['expectedCountKnownDocuments'] += 1
            actual['expectedViews'] += expected_views
        page_views, page_labels = 0, 0
        for page in pages:
            if page.get('method') != 'full-page-render':
                failures.append(f'design source page was not fully rendered: {publication}/{page.get("pageNumber")}')
            asset(page.get('image'), page.get('bytes'))
            asset(page.get('thumbnail'), page.get('thumbnailBytes'))
            if page.get('pageKind') not in {'cover', 'description'}:
                actual['drawingPages'] += 1
            page_labels += len(page.get('labels', []))
            for view in page.get('views', []):
                asset(view.get('image'), view.get('bytes'))
                asset(view.get('thumbnail'), view.get('thumbnailBytes'))
                page_views += 1
        if record.get('viewImageCount') != page_views or record.get('recognizedViewCount') != page_labels:
            failures.append(f'design labels or split-view count inconsistent: {publication}')
        actual['recognizedViewLabels'] += page_labels
        actual['splitViewImages'] += page_views
        if isinstance(expected_views, int) and expected_views == page_labels:
            actual['viewCountsAgreeDocuments'] += 1
    actual['assetFiles'] = len(assets)
    actual['assetBytes'] = sum(assets.values())
    for key, value in actual.items():
        if manifest.get('summary', {}).get(key) != value:
            failures.append(f'design summary differs from underlying records: {key}')
    actual['reportedCompleteManualViewReviews'] = manifest.get('summary', {}).get('completeManualViewReviews')
    actual['countingNote'] = ('PDF page coverage, cover-stated view count, extracted labels, and split images '
                              'are separate measures; no automatic assertion of a completed manual design-scope review.')
    return actual


def audit(site, pdf_repo=None):
    failures = []
    manifest = json.loads((ROOT / 'site-manifest.json').read_text())
    originals = {}
    for number in range(1, 6):
        with zipfile.ZipFile(ROOT / f'site-part-{number:02}.zip') as archive:
            for entry in archive.infolist():
                if entry.filename in originals:
                    failures.append(f'duplicate original artifact entry: {entry.filename}')
                data = archive.read(entry)
                originals[entry.filename] = data
                if sha(data) != manifest.get(entry.filename):
                    failures.append(f'original ZIP hash changed: {entry.filename}')
    if set(originals) != set(manifest):
        failures.append('original ZIP inventory differs from immutable manifest')
    preserved = 0
    for name, digest in manifest.items():
        path = site / name
        if not path.is_file():
            failures.append(f'original file missing: {name}')
        elif name not in DISPLAY_CHANGES:
            if sha(path.read_bytes()) != digest:
                failures.append(f'original protected file changed: {name}')
            else:
                preserved += 1
    index_path = site / 'data/pdf-index.json'
    if not index_path.is_file() or sha(index_path.read_bytes()) != PDF_INDEX_SHA256:
        failures.append('938-PDF association index changed or disappeared')

    def read(name):
        return json.loads((site / 'data' / name).read_text())

    docs = read('portfolio-current.json')
    index = read('pdf-index.json')
    products = read('product-portraits.json')
    routes = read('route-tree.json')
    analysis = read('full-analysis.json')
    ids = {d['id'] for d in docs}
    apps = {d['applicationNumber'] for d in docs}
    expected = {'documents': 938, 'applications': 807, 'designDocuments': 152,
                'analyses': 807, 'primaryProducts': 16, 'paths': 21, 'subpaths': 109}
    counts = dict(documents=len(docs), applications=len(apps),
                  designDocuments=sum(d['patentType'] == '外观设计' for d in docs),
                  analyses=len(analysis['records']), primaryProducts=len(products['categories']),
                  paths=len(routes['paths']), subpaths=len(routes['subpaths']))
    for key, count in expected.items():
        if counts[key] != count:
            failures.append(f'baseline count changed: {key}: {counts[key]} != {count}')
    if ids != set(index['documents']) or len(ids) != len(docs):
        failures.append('PDF/publication inventory or uniqueness changed')
    if index.get('commit') != PDF_SOURCE_COMMIT:
        failures.append('PDF source snapshot changed')
    by_app = {}
    for mapping in products['mappings']:
        by_app.setdefault(mapping['applicationNumber'], set()).add(mapping['primaryProductId'])
    if set(by_app) != apps or any(len(v) != 1 for v in by_app.values()):
        failures.append('each application must retain exactly one primary product')
    original_images = sum(Path(name).suffix.lower() in IMAGE_SUFFIXES for name in manifest)
    local_refs, external_refs = set(), set()
    for name, data in originals.items():
        if name.endswith('.json'):
            try:
                strings = walk_strings(json.loads(data))
                for value in strings:
                    if value.startswith(('assets/', './assets/')):
                        local_refs.add(value)
                    elif re.match(r'^https?://', value):
                        external_refs.add(value)
            except (ValueError, UnicodeDecodeError):
                failures.append(f'original JSON unreadable: {name}')
    missing_original_refs = sorted(ref for ref in local_refs
        if not (site / ref.split('#', 1)[0].split('?', 1)[0]).is_file())
    if missing_original_refs:
        failures.append('original referenced assets missing: ' + ', '.join(missing_original_refs))
    original_designs = [d for d in docs if d['patentType'] == '外观设计']
    design_abstracts = sum(bool(d.get('abstractImage')) and
                          (site / d['abstractImage']).is_file() for d in original_designs)
    checked_pdfs = 0
    if pdf_repo:
        for publication, record in index['documents'].items():
            path = pdf_repo / record['path']
            if not path.is_file():
                failures.append(f'original PDF missing: {publication}')
                continue
            data = path.read_bytes()
            if len(data) != record['sizeBytes'] or sha(data) != record['sha256']:
                failures.append(f'original PDF bytes changed: {publication}')
            else:
                checked_pdfs += 1
    design_evidence = audit_design_evidence(site, docs, index, failures)
    site_bytes = sum(p.stat().st_size for p in site.rglob('*') if p.is_file())
    if site_bytes > 1_000_000_000:
        failures.append('published static site exceeds conservative 1 GB capacity budget')
    return dict(status='pass' if not failures else 'fail', counts=counts,
                originalArtifactFiles=len(manifest), immutableFilesPreserved=preserved,
                originalImages=original_images, originalDesignAbstractImages=design_abstracts,
                originalCompleteDesignViewSets=0, originalLocalAssetReferences=len(local_refs),
                missingOriginalLocalReferences=missing_original_refs,
                originalExternalEvidenceReferences=len(external_refs),
                originalExternalEvidenceReferenceSetSha256=sha('\n'.join(sorted(external_refs)).encode()),
                pdfAssociations=len(index['documents']), checkedPdfBytes=checked_pdfs,
                designEvidence=design_evidence, staticSiteBytes=site_bytes,
                capacityBudgetBytes=1_000_000_000,
                originalPresentationRetainedInZip=sorted(DISPLAY_CHANGES), failures=failures)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT / '_site')
    parser.add_argument('--pdf-repo', type=Path)
    parser.add_argument('--json-output', type=Path)
    args = parser.parse_args()
    report = audit(args.site.resolve(), args.pdf_repo.resolve() if args.pdf_repo else None)
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.json_output:
        args.json_output.write_text(output)
    print(output, end='')
    raise SystemExit(0 if report['status'] == 'pass' else 1)
