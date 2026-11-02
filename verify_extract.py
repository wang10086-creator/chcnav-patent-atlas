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
