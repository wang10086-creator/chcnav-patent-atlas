"""Validate complete design-PDF page coverage and gallery resource integrity.

python3 scripts/check_design_views.py --site _site --pdf-repo ../pdf-repository
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile

import fitz
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT / '_site')
    parser.add_argument('--pdf-repo', type=Path, required=True)
    args = parser.parse_args()
    generated = ROOT / 'site-overrides'
    manifest = json.loads((generated / 'data/design-views.json').read_text())
    portfolio = json.loads((args.site / 'data/portfolio-current.json').read_text())
    designs = {d['id'] for d in portfolio if d['patentType'] == '外观设计'}
    assert set(manifest['documents']) == designs
    index = json.loads((generated / 'data/pdf-index.json').read_text())
    page_count, crop_count, known_expected, named_views = 0, 0, 0, 0
    image_files = set()
    for publication, record in manifest['documents'].items():
        assert record['identity']['status'] in ('verified-text', 'verified-ocr')
        assert record['identity']['observedPublicationIds'] == [publication]
        pdf_record = index['documents'][publication]
        assert record['pdf']['path'] == pdf_record['path']
        assert record['pdf']['sha256'] == pdf_record['sha256']
        data = (args.pdf_repo / pdf_record['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == pdf_record['sha256']
        pdf = fitz.open(stream=data, filetype='pdf')
        assert record['pdf']['pageCount'] == record['renderedPageCount'] == len(record['pages']) == len(pdf)
        assert [p['pageNumber'] for p in record['pages']] == list(range(1, len(pdf) + 1))
        page_count += len(pdf)
        if record['expectedViewCount'] is not None:
            known_expected += record['expectedViewCount']
        named_views += record['recognizedViewCount']
        for page in record['pages']:
            assert page['method'] == 'full-page-render'
            assert page['width'] >= 1400 and page['height'] >= 2000
            assert len(page['views']) <= len(page['labels'])
            for item in [page] + page['views']:
                for field in ('image', 'thumbnail'):
                    path = generated / item[field]
                    assert path.is_file(), path
                    with Image.open(path) as image:
                        image.verify()
                    image_files.add(item[field])
                if 'clipPoints' in item:
                    clip = fitz.Rect(item['clipPoints'])
                    assert not clip.is_empty and clip.x0 >= -0.01 and clip.y0 >= -0.01 and clip.x1 <= pdf[page['pageNumber'] - 1].rect.width + .01 and clip.y1 <= pdf[page['pageNumber'] - 1].rect.height + .01
                    crop_count += 1
        pdf.close()
    assert manifest['summary']['renderedPages'] == page_count
    assert manifest['summary']['splitViewImages'] == crop_count
    assert manifest['summary']['expectedViews'] == known_expected
    assert manifest['summary']['recognizedViewLabels'] == named_views
    assert manifest['summary']['completeManualViewReviews'] == 0
    # This corpus contains raster design drawings and vector page elements. An
    # isolated vector/scanned-page fixture ensures the renderer does not rely on
    # embedded-image extraction, without inserting fixtures into real data.
    spec = importlib.util.spec_from_file_location('design_extract', ROOT / 'scripts/extract_design_views.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='chcnav-design-render-test-') as temp:
        pdf = fitz.open()
        vector = pdf.new_page(width=595, height=842)
        vector.draw_rect(fitz.Rect(20, 20, 570, 820), color=(1, 0, 0), width=4)
        vector.draw_line(fitz.Point(30, 810), fitz.Point(560, 40), color=(0, 0, 1), width=3)
        vector.insert_text((30, 60), 'ISOLATED VECTOR PAGE', fontsize=22)
        meta = module.write_render(vector, Path(temp) / 'vector.webp')
        assert meta['width'] == 1488 and meta['height'] == 2105
        with Image.open(Path(temp) / 'vector.webp') as image:
            assert ImageStat.Stat(image.convert('L')).extrema[0][0] < 100
        scan_image = vector.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes('png')
        scanned = pdf.new_page(width=595, height=842)
        scanned.insert_image(scanned.rect, stream=scan_image)
        assert not scanned.get_text().strip()
        module.write_render(scanned, Path(temp) / 'scanned.webp')
        assert (Path(temp) / 'scanned.webp').stat().st_size > 1000
        assert (Path(temp) / 'vector-thumb.webp').is_file()
        assert (Path(temp) / 'scanned-thumb.webp').is_file()
        pdf.close()
    report = dict(designDocuments=len(designs), pdfPages=page_count, renderedPages=page_count,
                  expectedViews=known_expected, recognizedViewLabels=named_views,
                  safeViewCrops=crop_count, checkedImages=len(image_files),
                  exactVersionSourcesVerified=True, pageSequenceComplete=True,
                  syntheticVectorRender=True, syntheticScannedRender=True,
                  syntheticFixturesPublished=False, manualFullViewReviews=0)
    (ROOT / 'reports/design-views-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
