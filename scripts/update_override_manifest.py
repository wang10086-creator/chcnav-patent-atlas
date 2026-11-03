"""Record reviewed static overrides separately from the immutable ZIP manifest."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
overrides = root / 'site-overrides'
manifest = {p.relative_to(overrides).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(overrides.rglob('*')) if p.is_file()}
(root / 'site-overrides-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Recorded {len(manifest)} reviewed overrides')
