"""Read the deployed public Pages files back from the GitHub runner, without credentials."""
import argparse,hashlib,json,time,urllib.request,urllib.parse
from pathlib import Path

def verify(url,expected_dir,attempts=12,delay=10,fetch=None):
 parsed=urllib.parse.urlparse(url)
 if (parsed.scheme,parsed.netloc,parsed.path.rstrip('/'))!=('https','wang10086-creator.github.io','/chcnav-patent-atlas'):
  raise ValueError('Unexpected deployment URL')
 expected_dir=Path(expected_dir)
 files=['data/manual-updates.json','maintenance.html','manual-editor.js','index.html','atlas.js','upgrade-shell.css','data/incopat-status-snapshot.json']
 expected={name:(expected_dir/name).read_bytes() for name in files}
 def download(address):
  request=urllib.request.Request(address,headers={'Cache-Control':'no-cache','User-Agent':'CHCNAV-release-verification'})
  with urllib.request.urlopen(request,timeout=30) as response:
   if response.status!=200:raise ValueError('Public response is not HTTP 200')
   return response.read()
 fetch=fetch or download
 for attempt in range(attempts):
  try:
   observed={}
   for name,body in expected.items():
    digest=hashlib.sha256(body).hexdigest()
    actual=fetch(url.rstrip('/')+'/'+name+'?release='+digest+'&attempt='+str(attempt))
    if hashlib.sha256(actual).hexdigest()!=digest:raise ValueError('Public content differs: '+name)
    observed[name]={'httpStatus':200,'sha256':digest}
   data=json.loads(expected['data/incopat-status-snapshot.json'])
   result={'result':'pass','url':url,'source':data['source'],'snapshotDate':data['snapshotDate'],'officialVerified':data['officialVerified'],'documents':len(data['records']),'applications':len({r['applicationNumber'] for r in data['records']}),'files':observed,'scope':'Public HTTP content readback; browser interactions tested locally, not in this check'}
   print('PUBLIC_STATUS_READBACK '+json.dumps(result,ensure_ascii=False));return result
  except Exception as error:
   print('Public readback attempt',attempt+1,'failed:',type(error).__name__)
   if attempt+1==attempts:raise
   time.sleep(delay)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--expected-dir',default='_site');args=p.parse_args();verify(args.url,args.expected_dir)
