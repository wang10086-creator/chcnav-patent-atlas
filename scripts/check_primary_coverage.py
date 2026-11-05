"""Audit primary product association and distinguish full-library totals from filtered counts."""
from pathlib import Path
from collections import Counter
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def audit(docs,model,analyses):
 categories=model['categories'];mappings=model['mappings'];apps={d['applicationNumber'] for d in docs};ids={c['id'] for c in categories}
 counts=Counter(m['applicationNumber'] for m in mappings)
 issues={
  'duplicatePublications':[k for k,n in Counter(d['id'] for d in docs).items() if n>1],
  'duplicateCategoryIds':[k for k,n in Counter(c['id'] for c in categories).items() if n>1],
  'duplicateApplicationMappings':[k for k,n in counts.items() if n>1],
  'unmappedApplications':sorted(apps-set(counts)),
  'extraApplicationMappings':sorted(set(counts)-apps),
  'unknownCategoryMappings':[m['applicationNumber'] for m in mappings if m['primaryProductId'] not in ids],
  'analysisApplicationMismatch':sorted(apps^{a['applicationNumber'] for a in analyses}),
 }
 mapping={m['applicationNumber']:m['primaryProductId'] for m in mappings}
 totals=[]
 for c in categories:
  rows=[d for d in docs if mapping.get(d['applicationNumber'])==c['id']]
  totals.append({'id':c['id'],'name':c['name'],'applications':len({d['applicationNumber'] for d in rows}),'documents':len(rows)})
 return {'status':'fail' if any(issues.values()) else 'pass','documents':len(docs),'applications':len(apps),'categories':totals,'emptyFullLibraryCategories':[c['id'] for c in totals if not c['documents']],'issues':issues,'summedCategoryApplications':sum(c['applications'] for c in totals),'summedCategoryDocuments':sum(c['documents'] for c in totals)}
def run():
 folder=ROOT/'_site/data';docs=json.loads((folder/'portfolio-current.json').read_text());model=json.loads((folder/'product-portraits.json').read_text());analyses=json.loads((folder/'full-analysis.json').read_text())['records'];snapshot=json.loads((folder/'incopat-status-snapshot.json').read_text())
 result=audit(docs,model,analyses);assert result['status']=='pass',result
 assert result['summedCategoryApplications']==result['applications']
 assert result['summedCategoryDocuments']==result['documents']
 matched={r['publicationId'] for r in snapshot['records'] if r['statusRaw']=='公开'}
 limited=audit([d for d in docs if d['id'] in matched],model,analyses)
 result['reproduction']={'filter':{'sourceStatusRaw':'公开'},'documents':len(matched),'applications':len({d['applicationNumber'] for d in docs if d['id'] in matched}),'categoryCounts':limited['categories'],'zeroCategoryCount':len(limited['emptyFullLibraryCategories']),'interpretation':'This reproduces the screenshot totals, but the screenshot does not establish the actual active filters.'}
 result['sourceSha256']={f:hashlib.sha256((folder/f).read_bytes()).hexdigest() for f in ['portfolio-current.json','product-portraits.json','full-analysis.json','route-tree.json','incopat-status-snapshot.json']}
 # Isolated negative checks prove missing and duplicate links are not explained away as empty filters.
 test=json.loads(json.dumps(model));test['mappings'].pop();assert audit(docs,test,analyses)['issues']['unmappedApplications']
 test=json.loads(json.dumps(model));test['mappings'].append(test['mappings'][0]);assert audit(docs,test,analyses)['issues']['duplicateApplicationMappings']
 test=json.loads(json.dumps(model));test['mappings'][0]['primaryProductId']='missing-fixture';assert audit(docs,test,analyses)['issues']['unknownCategoryMappings']
 result['negativeAuditCases']='missing, duplicate and unknown category mappings detected in isolated copies'
 (ROOT/'reports/primary-coverage-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ['status','documents','applications','emptyFullLibraryCategories','issues']},ensure_ascii=False))
if __name__=='__main__':run()
