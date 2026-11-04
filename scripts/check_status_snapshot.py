"""Validate only the authorized public status projection; never reads private workbooks."""
import json,hashlib
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[1]
EXPECTED_SHA='faccd8054418d12a100ae992ee775f3bd46a414c3690b8150295698d4256dfbf'
FIELDS={'publicationId','applicationNumber','statusRaw','validityRaw','jurisdiction'}
def check():
 p=ROOT/'site-overrides/data/incopat-status-snapshot.json';data=p.read_bytes();s=json.loads(data)
 assert hashlib.sha256(data).hexdigest()==EXPECTED_SHA
 assert set(s)=={'schemaVersion','source','snapshotDate','officialVerified','verificationLabel','records'}
 assert s['source']=='IncoPat' and s['snapshotDate']=='2026-11-03' and s['officialVerified'] is False
 assert s['verificationLabel']=='第三方数据库快照，未官方核验'
 records=s['records'];assert len(records)==938
 baseline=json.loads((ROOT/'_site/data/portfolio-current.json').read_text());byid={d['id']:d['applicationNumber'] for d in baseline}
 assert len({r['publicationId'] for r in records})==938 and {r['publicationId']:r['applicationNumber'] for r in records}==byid
 apps=defaultdict(set)
 for r in records:
  assert set(r)==FIELDS and r['jurisdiction']=='CN'
  assert all(isinstance(v,str) and v.strip() and len(v)<80 for v in r.values())
  apps[r['applicationNumber']].add((r['statusRaw'],r['validityRaw'],r['jurisdiction']))
 assert len(apps)==807 and all(len(v)==1 for v in apps.values())
 doc_states=dict(Counter(r['statusRaw'] for r in records));doc_valid=dict(Counter(r['validityRaw'] for r in records))
 app_states=dict(Counter(next(iter(v))[0] for v in apps.values()));app_valid=dict(Counter(next(iter(v))[1] for v in apps.values()))
 assert doc_valid=={'有效':491,'失效':340,'审中':107} and app_valid=={'有效':360,'失效':340,'审中':107}
 assert doc_states=={'授权':491,'未缴年费':112,'驳回':213,'实质审查':104,'撤回':6,'全部无效':3,'期限届满':4,'公开':3,'避重放弃':2}
 assert not any(x in data.decode() for x in ['libfile_','oaiusercontent','http','/workspace','权利人','法律状态历史','password','token'])
 assert (ROOT/'_site/data/incopat-status-snapshot.json').read_bytes()==data
 assert not list((ROOT/'_site').rglob('*.xlsx'))
 result={'documents':938,'applications':807,'documentStatus':doc_states,'applicationStatus':app_states,'documentValidity':doc_valid,'applicationValidity':app_valid,'matching':'exact publication and application','applicationConflicts':0,'publicFieldWhitelist':'pass','mappingSha256':EXPECTED_SHA,'officialVerified':False}
 print(json.dumps(result,ensure_ascii=False));return result
if __name__=='__main__':check()
