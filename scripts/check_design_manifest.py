"""Standard-library-only deployment check for design view evidence.

No PDF checkout, OCR engine, image package or browser is required.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / '_site'


def check():
    manifest = json.loads((SITE / 'data/design-views.json').read_text())
    portfolio = json.loads((SITE / 'data/portfolio-current.json').read_text())
    pdf_index = json.loads((SITE / 'data/pdf-index.json').read_text())
    designs = {d['id']: d for d in portfolio if d['patentType'] == '外观设计'}
    assert manifest['schemaVersion'] == 1
    assert set(manifest['documents']) == set(designs)
    assert manifest['sourcePdfCommit'] == pdf_index['commit']
    totals = dict(pdfPages=0, renderedPages=0, drawingPages=0, expectedViews=0,
                  expectedCountKnownDocuments=0, recognizedViewLabels=0, splitViewImages=0,
                  identityVerified=0, identityUnconfirmed=0, viewCountsAgreeDocuments=0,
                  pdfTextViewLabels=0, visuallyReviewedViewLabels=0)
    assets = set()
    for publication, record in manifest['documents'].items():
        assert record['id'] == publication and record['applicationNumber'] == designs[publication]['applicationNumber']
        assert record['pdf']['sha256'] == pdf_index['documents'][publication]['sha256']
        assert record['pdf']['path'] == pdf_index['documents'][publication]['path']
        verified = record['identity']['status'] in ('verified-text', 'verified-ocr')
        assert verified, f'Unconfirmed identity must not silently enter the verified gallery: {publication}'
        assert record['identity']['observedPublicationIds'] == [publication]
        totals['identityVerified'] += verified
        totals['identityUnconfirmed'] += not verified
        pages = record['pages']
        assert record['renderedPageCount'] == record['pdf']['pageCount'] == len(pages)
        assert [p['pageNumber'] for p in pages] == list(range(1, len(pages) + 1))
        totals['pdfPages'] += record['pdf']['pageCount']
        totals['renderedPages'] += len(pages)
        totals['drawingPages'] += sum(p['pageKind'] == 'drawing' for p in pages)
        named = sum(len(p['labels']) for p in pages)
        crops = sum(len(p['views']) for p in pages)
        assert record['recognizedViewCount'] == named
        assert record['viewImageCount'] == crops
        assert all(len(p['views']) <= len(p['labels']) for p in pages)
        totals['recognizedViewLabels'] += named
        totals['splitViewImages'] += crops
        visual = record.get('visuallyReviewedLabels', 0)
        totals['visuallyReviewedViewLabels'] += visual
        totals['pdfTextViewLabels'] += named - visual
        expected = record['expectedViewCount']
        if expected is not None:
            assert isinstance(expected, int) and expected >= 0
            totals['expectedViews'] += expected
            totals['expectedCountKnownDocuments'] += 1
        agrees = expected is not None and expected == named
        assert (record['viewVerificationStatus'] == 'caption-count-matches-cover') == agrees
        totals['viewCountsAgreeDocuments'] += agrees
        if not agrees:
            assert record['limitations'], 'An uncertain view count must retain an explanation'
        for page in pages:
            assert page['method'] == 'full-page-render' and page['dpi'] >= 150
            assert page['width'] > 0 and page['height'] > 0
            for item in [page] + page['views']:
                for key, digest_key in [('image', 'sha256'), ('thumbnail', 'thumbnailSha256')]:
                    name = item[key]
                    path = PurePosixPath(name)
                    assert name.startswith(f'assets/design-views/{publication}/')
                    assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
                    file = SITE.joinpath(*path.parts)
                    data = file.read_bytes()
                    assert data[:4] == b'RIFF' and data[8:12] == b'WEBP', name
                    assert hashlib.sha256(data).hexdigest() == item[digest_key], name
                    assets.add(name)
    summary = manifest['summary']
    assert summary['designDocuments'] == len(designs)
    for key, value in totals.items():
        assert summary[key] == value, (key, summary[key], value)
    assert summary['assetFiles'] == len(assets)
    assert summary['assetBytes'] == sum((SITE / name).stat().st_size for name in assets)
    assert summary['completeManualViewReviews'] == 0, 'Automated processing cannot claim human verification'
    print(f"PASS: design manifest {len(designs)} publications, {totals['renderedPages']} complete pages, "
          f"{totals['recognizedViewLabels']} named views, {len(assets)} verified WEBP assets")


if __name__ == '__main__':
    check()
