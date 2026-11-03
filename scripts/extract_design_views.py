"""Render every page of design PDFs; add conservative caption-bound view crops.

python3 scripts/extract_design_views.py --pdf-repo ../pdf-repository --site _site
The original pages are always retained. Caption counts and rendered page coverage
are recorded separately; neither is asserted to be a legal scope verification.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DPI = 180


def write_render(page, path, clip=None):
    pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72, DPI / 72), clip=clip,
                          colorspace=fitz.csRGB, alpha=False)
    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'WEBP', quality=86, method=3)
    thumb = image.copy()
    thumb.thumbnail((320, 380), Image.Resampling.LANCZOS)
    thumb_path = path.with_name(path.stem + '-thumb.webp')
    thumb.save(thumb_path, 'WEBP', quality=78, method=4)
    return dict(width=pix.width, height=pix.height, bytes=path.stat().st_size,
                thumbnailBytes=thumb_path.stat().st_size)


def ocr_identity(page):
    """Only use OCR to corroborate a full publication identifier, never a guess."""
    with tempfile.TemporaryDirectory(prefix='chcnav-design-ocr-') as temp:
        path = Path(temp) / 'cover.png'
        page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).save(path)
        result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng', '--psm', '11'],
                                capture_output=True, timeout=60, check=False)
        return re.sub(r'\s+', '', result.stdout.decode(errors='replace'))


def caption_lines(page):
    out = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            label = ''.join(s['text'] for s in line['spans']).strip()
            label = re.sub(r'\s+', '', label)
            rect = fitz.Rect(line['bbox'])
            if ('图' in label and len(label) <= 60 and '外观设计' not in label
                    and '图片或照片' not in label and rect.y0 > 55
                    and rect.y1 < page.rect.height - 65):
                out.append((label, rect))
    return sorted(out, key=lambda x: (round(x[1].x0 / 140), x[1].y0))


def process_document(args):
    doc, record, pdf_root, output_root, source_commit = args
    pdf_path = Path(pdf_root) / record['path']
    data = pdf_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError(f"PDF differs from association index: {doc['id']}")
    pdf = fitz.open(stream=data, filetype='pdf')
    first_text = re.sub(r'\s+', '', pdf[0].get_text())
    ids = sorted(set(re.findall(r'CN\d{9}S', first_text)))
    status = 'verified-text' if ids == [doc['id']] else 'unconfirmed'
    identity_method = 'Full publication ID in first-page PDF text'
    if status == 'unconfirmed':
        try:
            ocr = ocr_identity(pdf[0])
            ocr_ids = sorted(set(re.findall(r'CN\d{9}S', ocr)))
            if ocr_ids == [doc['id']]:
                ids, status = ocr_ids, 'verified-ocr'
                identity_method = 'Full publication ID corroborated by first-page OCR'
        except (OSError, subprocess.SubprocessError) as error:
            identity_method += '; OCR unavailable: ' + type(error).__name__
    expected = re.search(r'图片或照片\s*(\d+)\s*幅', pdf[0].get_text())
    expected_count = int(expected[1]) if expected else None
    out_dir = Path(output_root) / 'assets/design-views' / doc['id']
    base = 'assets/design-views/' + doc['id']
    limitations = []
    if status == 'unconfirmed':
        limitations.append('PDF 正文／OCR 未能唯一确认完整公开号；仅保留隔离核查记录，不展示图库。')
    pages, recognized, split_count = [], 0, 0
    visual_evidence = json.loads((ROOT / 'scripts/design_view_label_evidence.json').read_text())['records'].get(doc['id'])
    visually_reviewed = 0
    for page in pdf:
        number = page.number + 1
        text = page.get_text()
        normalized = re.sub(r'\s+', '', text)
        kind = ('cover' if number == 1 else 'drawing' if '外观设计图片或照片' in normalized
                else 'description' if '简要说明' in normalized else 'unknown')
        stem = f'page-{number:03}'
        metadata = write_render(page, out_dir / (stem + '.webp'))
        captions = caption_lines(page) if kind == 'drawing' else []
        recognized += len(captions)
        images = [fitz.Rect(info['bbox']) for info in page.get_image_info()
                  if info['bbox'][3] > 60 and info['bbox'][1] < page.rect.height - 70]
        used, views = set(), []
        visual_labels = []
        if not captions and kind == 'drawing' and visual_evidence and visual_evidence['pageNumber'] == number:
            assert visual_evidence['pdfSha256'] == record['sha256'], 'Visual label evidence belongs to another PDF'
            assert len(images) == visual_evidence['expectedRasterImageCount'] == len(visual_evidence['labels'])
            for index, (label, rect) in enumerate(zip(visual_evidence['labels'], images)):
                clip = fitz.Rect(rect.x0 - 8, rect.y0 - 8, rect.x1 + 8, rect.y1 + 8) & page.rect
                name = f'page-{number:03}-view-{index + 1:02}'
                view_metadata = write_render(page, out_dir / (name + '.webp'), clip)
                views.append(dict(label=label, image=base + '/' + name + '.webp',
                                  thumbnail=base + '/' + name + '-thumb.webp',
                                  method='page-render-visually-reviewed-raster-label',
                                  clipPoints=[round(x, 3) for x in clip], **view_metadata))
            visual_labels = visual_evidence['labels']
            recognized += len(visual_labels)
            visually_reviewed += len(visual_labels)
        for index, (label, label_rect) in enumerate(captions):
            candidates = []
            cx = (label_rect.x0 + label_rect.x1) / 2
            for image_index, rect in enumerate(images):
                gap = label_rect.y0 - rect.y1
                if image_index not in used and -2 <= gap <= 35 and rect.x0 - 24 <= cx <= rect.x1 + 24:
                    candidates.append((abs(gap) + abs(cx - (rect.x0 + rect.x1) / 2) / 5, image_index, rect))
            if not candidates:
                continue
            _, image_index, rect = min(candidates, key=lambda x: x[0])
            # Ambiguous overlapping image rectangles are left to the complete page.
            if any(rect.intersects(other) and other != rect and (rect & other).get_area() > rect.get_area() * .15
                   for other in images):
                continue
            clip = rect | label_rect
            clip = fitz.Rect(clip.x0 - 8, clip.y0 - 8, clip.x1 + 8, clip.y1 + 8) & page.rect
            name = f'page-{number:03}-view-{index + 1:02}'
            view_metadata = write_render(page, out_dir / (name + '.webp'), clip)
            views.append(dict(label=label, image=base + '/' + name + '.webp',
                              thumbnail=base + '/' + name + '-thumb.webp',
                              method='page-render-safe-caption-crop',
                              clipPoints=[round(x, 3) for x in clip], **view_metadata))
            used.add(image_index)
        split_count += len(views)
        pages.append(dict(pageNumber=number, pageKind=kind, image=base + '/' + stem + '.webp',
                          thumbnail=base + '/' + stem + '-thumb.webp', method='full-page-render',
                          dpi=DPI, textAvailable=bool(text.strip()), labels=visual_labels or [x[0] for x in captions],
                          labelMethod='visual-original-page-review' if visual_labels else 'pdf-text' if captions else 'unavailable',
                          rasterImageCount=len(images), vectorPrimitiveCount=len(page.get_drawings()),
                          views=views, **metadata))
    counts_match = expected_count is not None and expected_count == recognized
    if not counts_match:
        limitations.append('封面应有视图数与可提取图页标签数未完成一致性确认；全部原页仍保留。')
    if split_count < recognized:
        limitations.append('部分视图未可靠自动拆分，保留完整图页，不据此减少视图覆盖。')
    limitations.append('页渲染和标签校验不代表已完成逐视图人工核验或法律保护范围判断。')
    encoded_path = '/'.join(__import__('urllib.parse', fromlist=['quote']).quote(x, safe='') for x in record['path'].split('/'))
    repo = 'wang10086-creator/chcnav-patent-pdfs'
    result = dict(id=doc['id'], title=doc['title'], applicationNumber=doc['applicationNumber'],
                  status='page-render-complete' if status != 'unconfirmed' else 'identity-unconfirmed',
                  identity=dict(status=status, method=identity_method, observedPublicationIds=ids,
                                applicationNumberPresent=doc['applicationNumber'].removeprefix('CN') in first_text),
                  pdf=dict(path=record['path'], commit=source_commit, sha256=record['sha256'],
                           pageCount=len(pdf), viewUrl=f'https://github.com/{repo}/blob/{source_commit}/{encoded_path}',
                           downloadUrl=f'https://raw.githubusercontent.com/{repo}/{source_commit}/{encoded_path}'),
                  expectedViewCount=expected_count, recognizedViewCount=recognized,
                  renderedPageCount=len(pages), viewImageCount=split_count,
                  visuallyReviewedLabels=visually_reviewed,
                  viewVerificationStatus='caption-count-matches-cover' if counts_match else 'count-needs-review',
                  coverageNote='完整 PDF 每页渲染保留；可确认的图页标签单列，可靠拆分时附分视图。',
                  limitations=limitations, pages=pages)
    pdf.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf-repo', type=Path, required=True)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    portfolio = json.loads((args.site / 'data/portfolio-current.json').read_text())
    designs = [doc for doc in portfolio if doc['patentType'] == '外观设计']
    index = json.loads((ROOT / 'site-overrides/data/pdf-index.json').read_text())
    if args.limit:
        designs = designs[:args.limit]
    output = ROOT / 'site-overrides'
    jobs = [(doc, index['documents'][doc['id']], str(args.pdf_repo.resolve()), str(output), index['commit']) for doc in designs]
    records = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, record in enumerate(pool.map(process_document, jobs)):
            records[record['id']] = record
            if (i + 1) % 10 == 0 or i + 1 == len(jobs):
                print(f'Rendered {i + 1}/{len(jobs)} design PDFs', flush=True)
    for record in records.values():
        for page in record['pages']:
            page['contentClassification'] = (
                'raster-and-vector' if page['rasterImageCount'] and page['vectorPrimitiveCount'] else
                'raster' if page['rasterImageCount'] else
                'vector-or-text' if page['vectorPrimitiveCount'] or page['textAvailable'] else 'unknown')
            for item in [page] + page['views']:
                item['sha256'] = hashlib.sha256((output / item['image']).read_bytes()).hexdigest()
                item['thumbnailSha256'] = hashlib.sha256((output / item['thumbnail']).read_bytes()).hexdigest()
    assets = [p for p in (output / 'assets/design-views').rglob('*') if p.is_file()]
    summary = dict(designDocuments=len(records), identityVerified=sum(r['identity']['status'] != 'unconfirmed' for r in records.values()),
                   identityUnconfirmed=sum(r['identity']['status'] == 'unconfirmed' for r in records.values()),
                   pdfPages=sum(r['pdf']['pageCount'] for r in records.values()),
                   renderedPages=sum(r['renderedPageCount'] for r in records.values()),
                   drawingPages=sum(p['pageKind'] == 'drawing' for r in records.values() for p in r['pages']),
                   expectedViews=sum(r['expectedViewCount'] or 0 for r in records.values()),
                   expectedCountKnownDocuments=sum(r['expectedViewCount'] is not None for r in records.values()),
                   recognizedViewLabels=sum(r['recognizedViewCount'] for r in records.values()),
                   pdfTextViewLabels=sum(r['recognizedViewCount'] - r['visuallyReviewedLabels'] for r in records.values()),
                   visuallyReviewedViewLabels=sum(r['visuallyReviewedLabels'] for r in records.values()),
                   splitViewImages=sum(r['viewImageCount'] for r in records.values()),
                   viewCountsAgreeDocuments=sum(r['viewVerificationStatus'] == 'caption-count-matches-cover' for r in records.values()),
                   assetFiles=len(assets), assetBytes=sum(p.stat().st_size for p in assets),
                   completeManualViewReviews=0)
    manifest = dict(schemaVersion=1, generatedAt=datetime.now(timezone.utc).isoformat(),
                    sourcePdfCommit=index['commit'], renderer=f'PyMuPDF {fitz.VersionBind}', dpi=DPI,
                    originalSingleAbstractImagesPreserved=True,
                    countingPolicy='PDF pages, extracted captions, safe view crops and manual view verification are separate counts.',
                    summary=summary, documents=dict(sorted(records.items())))
    dest = output / 'data/design-views.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    report = ROOT / 'reports/design-views-audit.csv'
    report.parent.mkdir(exist_ok=True)
    with report.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['publicationId', 'applicationNumber', 'identityStatus', 'pdfPath', 'pdfSha256', 'pdfPages',
                         'renderedPages', 'expectedViews', 'recognizedCaptions', 'splitViewImages', 'method', 'limitations'])
        for r in records.values():
            writer.writerow([r['id'], r['applicationNumber'], r['identity']['status'], r['pdf']['path'], r['pdf']['sha256'],
                             r['pdf']['pageCount'], r['renderedPageCount'], r['expectedViewCount'], r['recognizedViewCount'],
                             r['viewImageCount'], 'all-page-render + conservative-caption-bounded-crops', '；'.join(r['limitations'])])
    (ROOT / 'reports/design-views-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
