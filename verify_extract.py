import hashlib,json,pathlib,stat,zipfile
root=pathlib.Path('_site'); root.mkdir(exist_ok=False)
manifest=json.loads(pathlib.Path('site-manifest.json').read_text())
assert len(manifest)==989
seen=set()
for n in range(1,6):
 with zipfile.ZipFile(f'site-part-{n:02}.zip') as archive:
  for info in archive.infolist():
   p=pathlib.PurePosixPath(info.filename)
   assert not p.is_absolute() and '..' not in p.parts and '\\' not in info.filename
   assert not stat.S_ISLNK(info.external_attr >>16)
   assert not info.is_dir() and info.filename not in seen
   assert p.suffix.lower() not in {'.xlsx','.xls','.zip'}
   assert info.filename in manifest
   data=archive.read(info)
   assert hashlib.sha256(data).hexdigest()==manifest[info.filename],info.filename
   dst=root.joinpath(*p.parts); dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(data)
   seen.add(info.filename)
assert seen==set(manifest)
assert (root/'index.html').is_file() and (root/'.nojekyll').is_file()
print(f'Validated {len(seen)} static files, SHA-256 matched; source v19 2f88ed4a688eb0c9b5bf028c35fb520a6c1db2d9')

# Preserve and verify the original public artifact before applying reviewed edits.
override_root=pathlib.Path('site-overrides')
overrides=json.loads(pathlib.Path('site-overrides-manifest.json').read_text())
actual={p.relative_to(override_root).as_posix() for p in override_root.rglob('*') if p.is_file()}
assert actual==set(overrides), 'Override inventory differs from manifest'
for name,digest in overrides.items():
 p=pathlib.PurePosixPath(name)
 assert not p.is_absolute() and '..' not in p.parts and '\\' not in name
 assert p.suffix.lower() in {'.html','.js','.mjs','.css','.json','.csv','.webp','.png','.jpg','.jpeg','.svg','.wasm','.bcmap','.ttf','.pfb','.icc','.woff','.woff2','.txt'},name
 src=override_root.joinpath(*p.parts)
 assert not src.is_symlink() and not any(parent.is_symlink() for parent in src.parents)
 data=src.read_bytes()
 assert hashlib.sha256(data).hexdigest()==digest,name
 dst=root.joinpath(*p.parts); dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(data)
print(f'Applied {len(overrides)} reviewed static overrides, SHA-256 matched')
import runpy
for checker in ('scripts/check_pdf_links.py','scripts/check_design_manifest.py','scripts/check_preservation_upgrade.py'):
 if pathlib.Path(checker).is_file():
  try:
   runpy.run_path(checker,run_name='__main__')
  except SystemExit as result:
   if result.code not in (None,0):
    raise
