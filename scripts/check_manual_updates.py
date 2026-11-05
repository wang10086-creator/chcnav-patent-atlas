import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'maintenance'))
from update_core import preview,FIELDS
ledger=json.loads((ROOT/'site-overrides/data/manual-updates.json').read_text());assert set(ledger)=={'schemaVersion','events'} and ledger['schemaVersion']==1
base=json.loads((ROOT/'_site/data/portfolio-current.json').read_text());products=json.loads((ROOT/'_site/data/product-portraits.json').read_text());topics=json.loads((ROOT/'_site/data/route-tree.json').read_text())
prior={'events':[]}
for e in ledger['events']:
 import datetime
 datetime.datetime.fromisoformat(e['enteredAt'])
 assert set(e)=={'record','fingerprint','enteredAt'} and set(e['record'])<=FIELDS
 result=preview([e['record']],base,prior,{x['id'] for x in products['categories']},{x['id'] for x in topics['subpaths']})[0]
 assert result['decision'] in ['新增','更新'] and result['fingerprint']==e['fingerprint'],result
 prior['events'].append(e)
print('PASS: manual append ledger',len(ledger['events']))

import os,subprocess
if os.environ.get('GITHUB_BASE_REF'):
 previous=json.loads(subprocess.check_output(['git','show','origin/'+os.environ['GITHUB_BASE_REF']+':site-overrides/data/manual-updates.json'],text=True)) if subprocess.run(['git','cat-file','-e','origin/'+os.environ['GITHUB_BASE_REF']+':site-overrides/data/manual-updates.json'],capture_output=True).returncode==0 else {'events':[]}
 assert ledger['events'][:len(previous['events'])]==previous['events'],'历史更新记录不得删除或改写'
