"""Private input -> public allowlisted append-only updates. No credentials or implicit publishing."""
import csv,json,re,hashlib,datetime,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
FIELDS={'kind','company','companyName','publicationId','applicationNumber','title','applicants','filingDate','pubDate','patentType','jurisdiction','abstract','sourceUrl','pdfUrl','statusRaw','normalizedStatus','eventDate','asOf','verification','evidenceUrl','productId','topicId','claimNumbers','claimText','contentForm','pdfStatus','pdfCheckedAt','pdfReason'}
ZH=dict(zip(['操作','企业标识','企业名称','公开号','申请号','名称','申请人','申请日','公开日','专利类型','地域','摘要','来源链接','PDF链接','状态原文','标准状态','事件日期','数据截至日期','核验方式','核验依据','产品编号','子路径编号','权项编号','权利要求原文'],['kind','company','companyName','publicationId','applicationNumber','title','applicants','filingDate','pubDate','patentType','jurisdiction','abstract','sourceUrl','pdfUrl','statusRaw','normalizedStatus','eventDate','asOf','verification','evidenceUrl','productId','topicId','claimNumbers','claimText']))
ZH['内容分类']='contentForm'
def pub(value):
 v=re.sub(r'[\s-]','',str(value)).upper()
 if not re.fullmatch(r'(CN|US|EP|WO|JP|KR|GB|DE|FR|AU|CA)\d{5,14}[A-Z]\d?',v):raise ValueError('公开号须含国家及文献版本，如 CN123456789A；不自动猜版本')
 return v

def safe_url(v):
 from urllib.parse import urlsplit
 if not v:return ''
 u=urlsplit(v)
 if u.scheme!='https' or not u.hostname or u.username or u.password:raise ValueError('链接必须为不含凭据的 HTTPS 地址')
 if any(x in v.lower() for x in ['libfile_','oai-library:','oaiusercontent.com','/api/library/']):raise ValueError('不能公开私有文件引用')
 if re.search(r'(token|signature|password|api_key|sig)=',u.query,re.I):raise ValueError('不能公开带凭据或签名的链接')
 return v

def read_input(path,mapping=None):
 p=Path(path)
 if p.suffix.lower()=='.json':rows=json.loads(p.read_text());rows=rows.get('rows',rows) if isinstance(rows,dict) else rows
 elif p.suffix.lower()=='.csv':rows=list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
 elif p.suffix.lower()=='.xlsx':
  ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
  with zipfile.ZipFile(p) as z:
   if sum(x.file_size for x in z.infolist())>30_000_000:raise ValueError('XLSX 解压超过30MB')
   def xml(n):
    b=z.read(n)
    if b'<!DOCTYPE' in b.upper() or b'<!ENTITY' in b.upper():raise ValueError('不允许XML实体')
    return ET.fromstring(b)
   strings=[''.join(x.itertext()) for x in xml('xl/sharedStrings.xml')] if 'xl/sharedStrings.xml' in z.namelist() else []
   tables=[]
   for n in z.namelist():
    if not re.fullmatch('xl/worksheets/sheet[0-9]+.xml',n):continue
    table=[]
    for row in xml(n).findall('.//s:sheetData/s:row',ns):
     cells={}
     for c in row.findall('s:c',ns):
      if c.find('s:f',ns) is not None:raise ValueError('不执行公式，请导出纯值')
      col=re.match('[A-Z]+',c.attrib['r'])[0];idx=0
      for ch in col:idx=idx*26+ord(ch)-64
      node=c.find('s:v',ns);val=node.text if node is not None else ''
      if c.attrib.get('t')=='s':val=strings[int(val)]
      elif c.attrib.get('t')=='inlineStr':val=''.join(c.find('s:is',ns).itertext())
      cells[idx-1]=val or ''
     if cells:table.append([cells.get(i,'') for i in range(max(cells)+1)])
    if table:tables.append(table)
   if len(tables)!=1:raise ValueError('请使用模板单表，禁止猜测多表含义')
   t=tables[0];rows=[dict(zip(t[0],r)) for r in t[1:]]
 else:raise ValueError('支持 JSON/CSV/XLSX')
 aliases={**ZH,**(mapping or {})};return [{aliases.get(k,k):str(v).strip() for k,v in r.items() if v is not None and str(v).strip()} for r in rows]

def preview(rows,base,ledger,products,topics):
 existing={d['id']:d for d in base};companies={d['id']:'chcnav' for d in base}
 for event in ledger['events']:
  r=event['record']
  if r['kind']=='patent':existing[r['publicationId']]={**existing.get(r['publicationId'],{}),**r};companies[r['publicationId']]=r['company']
 known={e['fingerprint'] for e in ledger['events']};out=[]
 for raw in rows:
  try:
   r={k:v for k,v in raw.items() if k in FIELDS and v};r['kind']=r.get('kind','patent');r['company']=r.get('company','chcnav');r['publicationId']=pub(r.get('publicationId',''));r['jurisdiction']=r.get('jurisdiction',r['publicationId'][:2]).upper()
   if r['kind'] not in ['patent','status','pdf']:raise ValueError('操作须为 patent/status/pdf')
   if not re.fullmatch('[a-z][a-z0-9-]{1,40}',r['company']):raise ValueError('企业标识格式错误')
   if r['jurisdiction']!=r['publicationId'][:2]:raise ValueError('地域与文献编号冲突')
   for key in ['sourceUrl','pdfUrl','evidenceUrl']:
    if key in r:r[key]=safe_url(r[key])
   for key in ['filingDate','pubDate','eventDate','asOf']:
    if key in r:datetime.date.fromisoformat(r[key])
   old=existing.get(r['publicationId'])
   if old and companies[r['publicationId']]!=r['company']:raise ValueError('文献已属于其他企业，须单独核对')
   oldapp=(old or {}).get('applicationNumber')
   if oldapp and r.get('applicationNumber',oldapp)!=oldapp:raise ValueError('同公开号申请号冲突')
   r['applicationNumber']=r.get('applicationNumber',oldapp or '')
   if not re.fullmatch(r'[A-Z]{2}[A-Z0-9./-]{5,30}',r['applicationNumber']):raise ValueError('缺失或无效申请号；不猜填')
   if r.get('contentForm') and r['contentForm'] not in ['method','structure','design']:raise ValueError('内容分类须 method/structure/design')
   if any(companies.get(k,'chcnav')!=r['company'] and v.get('applicationNumber')==r['applicationNumber'] for k,v in existing.items()):raise ValueError('申请关联跨企业冲突，须先核对')
   if r['kind']=='patent':
    if not old and not all(r.get(k) for k in ['title','applicants','sourceUrl']):raise ValueError('缺失新增必需的名称、申请人及来源')
    if r['company']!='chcnav' and not r.get('companyName'):raise ValueError('新企业需名称')
    if r.get('productId') and r['productId'] not in products:raise ValueError('未知产品编号')
    if r.get('topicId') and (r['topicId'] not in topics or not all(r.get(k) for k in ['claimNumbers','claimText','sourceUrl','productId','contentForm'])):raise ValueError('子路径关联须有真实权项编号、原文、来源及产品')
   else:
    if not old:raise ValueError('请先新增此文献，再更新状态或PDF')
   if r['kind']=='status':
    if not all(r.get(k) for k in ['statusRaw','normalizedStatus','asOf','sourceUrl','verification']):raise ValueError('缺少状态、截至日期、来源或核验方式')
    if r['normalizedStatus'] not in ['pending','granted','active','terminated','expired','invalid','unknown']:raise ValueError('标准状态不受支持')
    if r['verification'] not in ['database','manual','official']:raise ValueError('核验方式须 database/manual/official')
    if r['verification']=='official' and not r.get('evidenceUrl'):raise ValueError('官方核验必须提供对应登记依据，并在PR人工核对')
   if r.get('pdfStatus') and r['pdfStatus'] not in ['已核验 PDF','找到候选，待核验','仅有来源页面','访问受限','未找到','链接失效']:raise ValueError('PDF检查状态无效')
   if r['kind']=='pdf' and not (r.get('pdfUrl') or (r.get('pdfStatus') and r.get('sourceUrl'))):raise ValueError('缺少 PDF 链接，人工填写不自动等于已核验')
   canonical=json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'));fingerprint=hashlib.sha256(canonical.encode()).hexdigest()
   decision='已存在' if fingerprint in known else ('更新' if old else '新增');known.add(fingerprint)
   if r['kind']=='patent':existing[r['publicationId']]={**(old or {}),**r};companies[r['publicationId']]=r['company']
   out.append({'decision':decision,'record':r,'fingerprint':fingerprint,'excludedFields':sorted(set(raw)-FIELDS)})
  except (ValueError,TypeError) as e:out.append({'decision':'缺失信息' if '缺' in str(e) else '冲突','error':str(e)})
 return out
