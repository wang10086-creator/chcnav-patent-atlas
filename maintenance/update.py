import argparse,json,hashlib,datetime,subprocess
from pathlib import Path
from update_core import read_input,preview,ZH
ROOT=Path(__file__).resolve().parents[1];LEDGER=ROOT/'site-overrides/data/manual-updates.json'
def prepare(path,mapping=None):
 ledger=json.loads(LEDGER.read_text());base=json.loads((ROOT/'_site/data/portfolio-current.json').read_text());products=json.loads((ROOT/'_site/data/product-portraits.json').read_text());topics=json.loads((ROOT/'_site/data/route-tree.json').read_text())
 result=preview(read_input(path,mapping),base,ledger,{x['id'] for x in products['categories']},{x['id'] for x in topics['subpaths']})
 return {'baseSha256':hashlib.sha256(LEDGER.read_bytes()).hexdigest(),'rows':result}
if __name__=='__main__':
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
 q=sub.add_parser('preview');q.add_argument('input');q.add_argument('--mapping');q.add_argument('--out',required=True)
 q=sub.add_parser('apply');q.add_argument('preview');q.add_argument('--confirm',action='store_true')
 q=sub.add_parser('pr');q.add_argument('--confirm',action='store_true')
 args=p.parse_args()
 if args.cmd=='preview':
  result=prepare(args.input,json.loads(Path(args.mapping).read_text()) if args.mapping else None);Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2));print({k:sum(r['decision']==k for r in result['rows']) for k in ['新增','更新','已存在','冲突','缺失信息']})
 elif args.cmd=='apply':
  if not args.confirm:raise SystemExit('尚未确认：未改动文件。请审阅预览后使用 --confirm')
  if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='main':raise SystemExit('请先创建更新分支，不在main写入')
  proposal=json.loads(Path(args.preview).read_text());assert proposal['baseSha256']==hashlib.sha256(LEDGER.read_bytes()).hexdigest(),'草稿基线已变化，请重新预览'
  # Revalidate hand-edited proposals; never trust a preview decision or fingerprint.
  ledger=json.loads(LEDGER.read_text());base=json.loads((ROOT/'_site/data/portfolio-current.json').read_text());products=json.loads((ROOT/'_site/data/product-portraits.json').read_text());topics=json.loads((ROOT/'_site/data/route-tree.json').read_text())
  assert all('record' in r for r in proposal['rows']),'请先修复冲突/缺失行'
  rows=preview([r['record'] for r in proposal['rows']],base,ledger,{x['id'] for x in products['categories']},{x['id'] for x in topics['subpaths']});assert all(r['decision'] in ['新增','更新','已存在'] for r in rows),rows
  for r in rows:
   if r['decision']!='已存在':ledger['events'].append({'record':r['record'],'fingerprint':r['fingerprint'],'enteredAt':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  LEDGER.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n');subprocess.run(['python3','scripts/update_override_manifest.py'],cwd=ROOT,check=True);print('已生成分支工作区更新，尚未提交或发布。')
 else:
  if not args.confirm:raise SystemExit('请确认公开白名单字段后使用 --confirm；不会提交原Excel或预览')
  branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip();assert branch!='main'
  staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).splitlines();assert set(staged)<={'site-overrides/data/manual-updates.json','site-overrides-manifest.json'},'暂存区包含其他文件，停止以防上传私有原件'
  subprocess.run(['git','add','site-overrides/data/manual-updates.json','site-overrides-manifest.json'],cwd=ROOT,check=True)
  subprocess.run(['git','commit','-m','Append reviewed manual patent updates'],cwd=ROOT,check=True)
  subprocess.run(['git','push','-u','origin',branch],cwd=ROOT,check=True)
  subprocess.run(['gh','pr','create','--draft','--base','main','--title','人工专利数据更新','--body','请审核新增、状态依据、公开字段及自动测试。合并后由 Pages 发布并回读。'],cwd=ROOT,check=True)
