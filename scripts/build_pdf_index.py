"""Match an immutable PDF repository snapshot to the atlas's exact publications.

Usage: python3 scripts/build_pdf_index.py --pdf-repo ../pdf-repository --site ../site
The PDF checkout must be clean and at the commit being indexed.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

PDF_REPOSITORY = 'wang10086-creator/chcnav-patent-pdfs'
ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def build(pdf_repo, site):
    if git(pdf_repo, 'status', '--porcelain').strip():
        raise ValueError('PDF checkout must be clean')
    commit = git(pdf_repo, 'rev-parse', 'HEAD').decode().strip()
    entries = git(pdf_repo, 'ls-tree', '-rz', 'HEAD').decode().split('\0')[:-1]
    portfolio_path = site / 'data/portfolio-current.json'
    portfolio = json.loads(portfolio_path.read_text())
    docs = {d['id']: d for d in portfolio}
    if len(docs) != len(portfolio):
        raise ValueError('Duplicate publication IDs in portfolio')
    records, duplicates, unexpected = {}, [], []
    for entry in entries:
        metadata, name = entry.split('\t', 1)
        mode, kind, blob = metadata.split()
        path = PurePosixPath(name)
        if path.suffix.lower() != '.pdf':
            continue
        if mode != '100644' or kind != 'blob' or path.is_absolute() or '..' in path.parts:
            raise ValueError(f'Unsafe PDF tree entry: {name}')
        match = re.match(r'^(CN\d+[A-Z]\d?)(?:_|\.|\s)', path.name, re.I)
        if not match or match[1].upper() not in docs:
            unexpected.append(name)
            continue
        publication = match[1].upper()
        if publication in records:
            duplicates.append(publication)
            continue
        data = (pdf_repo / name).read_bytes()
        if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]:
            raise ValueError(f'Invalid PDF signature or missing EOF: {name}')
        # Verify the bytes being hashed belong to the exact committed Git blob.
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != blob:
            raise ValueError(f'Uncommitted PDF contents: {name}')
        records[publication] = dict(applicationNumber=docs[publication]['applicationNumber'],
            path=name, gitBlobSha=blob, sha256=hashlib.sha256(data).hexdigest(), sizeBytes=len(data))
    missing = sorted(set(docs) - set(records))
    if missing or duplicates or unexpected:
        raise ValueError(json.dumps(dict(missing=missing, duplicates=duplicates,
            unexpected=unexpected), ensure_ascii=False))
    return dict(schemaVersion=1, repository=PDF_REPOSITORY, commit=commit,
        portfolioSha256=hashlib.sha256(portfolio_path.read_bytes()).hexdigest(),
        matchingRule='Exact full publication ID including kind code; no application-level fallback',
        verification='Git blob bytes, PDF header/EOF and SHA-256; not a legal or full-content review',
        counts=dict(documents=len(docs), matched=len(records), missing=0, duplicates=0,
            unexpected=0, totalBytes=sum(r['sizeBytes'] for r in records.values())),
        documents=dict(sorted(records.items())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf-repo', type=Path, required=True)
    parser.add_argument('--site', type=Path, required=True)
    args = parser.parse_args()
    index = build(args.pdf_repo.resolve(), args.site.resolve())
    dest = ROOT / 'site-overrides/data/pdf-index.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(index['counts'], indent=2))
