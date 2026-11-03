"""Check the built atlas's PDF association and preservation against the ZIP baseline.

Run after python3 verify_extract.py. No network or PDF checkout required.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, unquote

root = Path(__file__).resolve().parents[1]
site = root / '_site'
read = lambda name: json.loads((site / 'data' / name).read_text())
index = read('pdf-index.json')
portfolio = read('portfolio-current.json')
assert index['repository'] == 'wang10086-creator/chcnav-patent-pdfs'
assert index['portfolioSha256'] == hashlib.sha256((site / 'data/portfolio-current.json').read_bytes()).hexdigest()
assert set(index['documents']) == {d['id'] for d in portfolio}
assert index['counts']['matched'] == len(portfolio) == 938
assert not any(index['counts'][k] for k in ('missing', 'duplicates', 'unexpected'))
paths = set()
for d in portfolio:
    r = index['documents'][d['id']]
    assert r['applicationNumber'] == d['applicationNumber']
    assert Path(r['path']).name.startswith(d['id'] + '_')
    assert r['path'] not in paths
    paths.add(r['path'])
    assert r['sizeBytes'] > 0 and len(r['sha256']) == 64 and len(r['gitBlobSha']) == 40
    encoded = quote(r['path'], safe='/')
    assert unquote(encoded) == r['path']
baseline = json.loads((root / 'site-manifest.json').read_text())
overrides = json.loads((root / 'site-overrides-manifest.json').read_text())
assert {'atlas.js', 'data/pdf-index.json'} <= set(overrides)
assert set(overrides) & set(baseline) <= {'index.html', 'atlas.js'}, 'Original evidence/data/style replacement is not allowed'
for name, expected in baseline.items():
    if name not in overrides:
        assert hashlib.sha256((site / name).read_bytes()).hexdigest() == expected, name
products = read('product-portraits.json')
routes = read('route-tree.json')
assert len({d['applicationNumber'] for d in portfolio}) == 807
assert len(products['categories']) == 16
assert len(routes['paths']) == 21 and len(routes['subpaths']) == 109
print('PASS: 938 exact-version PDF links; all original data, evidence, images and styles preserved')
