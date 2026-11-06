from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import threading,json,sys
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2];out=root/'top-filters-preview';out.mkdir(exist_ok=True)
class Q(SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
s=ThreadingHTTPServer(('127.0.0.1',0),partial(Q,directory=str(root/'pre-top-filters-build' if sys.argv[1]=='before' else Path(__file__).resolve().parents[1]/'_site')));threading.Thread(target=s.serve_forever,daemon=True).start();rows=[]
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for w,h in [(1920,1080),(1440,900),(1366,768),(1280,720),(820,1180),(390,844),(683,384)]:
   p=b.new_page(viewport={'width':w,'height':h});p.goto('http://127.0.0.1:'+str(s.server_port),wait_until='networkidle');p.wait_for_selector('.pm-canvas');p.wait_for_timeout(100)
   def box():return p.locator('.pm-viewport').evaluate('(e)=>({width:e.clientWidth,height:e.clientHeight,top:e.getBoundingClientRect().top,area:e.clientWidth*e.clientHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight})')
   r={'width':w,'height':h,'overview':box()}
   if w in [1440,390]:p.screenshot(path=str(out/(sys.argv[1]+('-desktop.png' if w==1440 else '-mobile.png'))),full_page=True)
   p.locator('#pm-locate').fill('CN110749912A');p.locator('[data-path-result]').first.click();p.locator('#pm-search-results summary').click();p.wait_for_timeout(150);r['detail']=box()
   if w==1440:p.screenshot(path=str(out/(sys.argv[1]+'-detail.png')),full_page=True)
   rows.append(r);p.close()
  b.close()
finally:s.shutdown()
(out/(sys.argv[1]+'-measurements.json')).write_text(json.dumps(rows,indent=2))
print(json.dumps(rows))
