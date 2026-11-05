"""Opt-in public-source lookup. Never constructs a PDF URL; extracts it from an actual page."""
import argparse,json,re,urllib.request,urllib.parse,urllib.robotparser,subprocess,tempfile,datetime
from html.parser import HTMLParser
from update_core import pub
ALLOWED={'patents.google.com','patentimages.storage.googleapis.com','data.epo.org','www.epo.org'}
class Links(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='meta' and a.get('name')=='citation_pdf_url':self.urls.append(a.get('content',''))
  if tag=='a' and '.pdf' in a.get('href','').lower():self.urls.append(a['href'])
class Guard(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if urllib.parse.urlsplit(newurl).hostname not in ALLOWED:raise ValueError('跳转来源不在允许名单')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def get(url):
 if urllib.parse.urlsplit(url).hostname not in ALLOWED:raise ValueError('未授权自动访问此来源，请人工核对')
 with urllib.request.build_opener(Guard).open(urllib.request.Request(url,headers={'User-Agent':'PatentAtlasManualCheck/1.0'}),timeout=20) as r:
  b=r.read(12_000_001)
  if len(b)>12_000_000:raise ValueError('文件超过12MB检查上限')
  return b

def check(identifier,page):
 result={'publicationId':pub(identifier),'sourceUrl':page,'checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pdfStatus':'未找到','reason':''}
 try:
  parsed=urllib.parse.urlsplit(page);robots=parsed.scheme+'://'+parsed.netloc+'/robots.txt';rp=urllib.robotparser.RobotFileParser();rp.parse(get(robots).decode(errors='replace').splitlines())
  if not rp.can_fetch('PatentAtlasManualCheck',page):raise ValueError('来源 robots 禁止自动访问')
  html=get(page).decode(errors='replace')
  if re.search(r'captcha|access denied|verify you are human',html,re.I):raise ValueError('验证码或访问限制，停止此来源')
  parser=Links();parser.feed(html)
  result['pdfStatus']='仅有来源页面'
  if not parser.urls:return result
  url=urllib.parse.urljoin(page,parser.urls[0]);result['pdfUrl']=url
  pdf=get(url)
  if not pdf.startswith(b'%PDF-'):result.update(pdfStatus='链接失效',reason='返回内容不是PDF');return result
  result.update(pdfStatus='找到候选，待核验',reason='已确认PDF字节，尚未确认目标文献版本或全部页面')
  with tempfile.TemporaryDirectory() as d:
   from pathlib import Path
   f=Path(d)/'document.pdf';f.write_bytes(pdf)
   try:
    text=subprocess.check_output(['pdftotext','-f','1','-l','1',str(f),'-'],timeout=30).decode(errors='replace');flat=re.sub(r'\s','',text).upper()[:200]
    match=re.search(r'(?:CN|US|EP|WO|JP|KR|GB|DE|FR|AU|CA)\d{5,14}[A-Z]\d?',flat)
    if match and match.group()==result['publicationId']:result.update(pdfStatus='已核验 PDF',reason='PDF第一页页首文本匹配完整公开号及文献版本；扫描或图纸完整性仍需人工核对')
   except (OSError,subprocess.SubprocessError):pass
 except Exception as e:result.update(pdfStatus='访问受限',reason=type(e).__name__+': '+str(e)[:160])
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('publication');p.add_argument('--source-page');p.add_argument('--out',required=True);a=p.parse_args();r=check(a.publication,a.source_page or 'https://patents.google.com/patent/'+pub(a.publication)+'/en');from pathlib import Path;root=Path(__file__).resolve().parents[1];ledger=json.loads((root/'site-overrides/data/manual-updates.json').read_text());known=json.loads((root/'_site/data/portfolio-current.json').read_text());known += [dict(e['record'],id=e['record']['publicationId']) for e in ledger['events'] if e['record']['kind']=='patent'];doc=next(d for d in known if d['id']==r['publicationId']);assert not any(e['record']['kind']=='pdf' and e['record']['publicationId']==r['publicationId'] for e in ledger['events']),'已有人工PDF记录，自动检查不得覆盖；请人工修正';row={'kind':'pdf','company':doc.get('company','chcnav'),'applicationNumber':doc['applicationNumber'],'publicationId':r['publicationId'],'jurisdiction':r['publicationId'][:2],'sourceUrl':r['sourceUrl'],'pdfStatus':r['pdfStatus'],'pdfCheckedAt':r['checkedAt'],'pdfReason':r['reason']};row.update({'pdfUrl':r['pdfUrl']} if r.get('pdfUrl') else {});open(a.out,'w').write(json.dumps({'rows':[row]},ensure_ascii=False,indent=2));print(r['pdfStatus'])
