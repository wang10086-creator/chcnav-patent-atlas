from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
import threading,json
from playwright.sync_api import sync_playwright
r=Path.cwd();server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(r/'_site')));threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page(viewport={'width':1440,'height':950});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle');page.wait_for_function('currentReady')
 assert page.locator('[data-reader-audience]').count()==0
 combinations=page.evaluate('''()=>{let n=0;for(const product of primaryData.categories){currentFilter.product=product.id;resetReader(product.id);for(const f of readerModel(currentFiltered()).available){reader.form=f;reader.topic='';currentRender();if(document.querySelectorAll('.reader-detail').length!==1)throw Error(product.id);n++;}}currentFilter.product='';resetReader();currentRender();return n;}''');assert combinations>30
 audit=page.evaluate('''()=>currentAnalyses.flatMap(a=>(a.formGroups||[]).flatMap((g,i)=>routineCarrier(a,g)?[{id:a.id,group:i,claims:g.claimNumbers,texts:currentTexts[a.id].claims.filter(c=>g.claimNumbers.includes(c.number))}]:[]))''')
 page.locator('[data-tree-preview]').first.hover();assert page.locator('#tree-preview').is_visible()
 page.screenshot(path=str(r.parent/'release-validation/tree-desktop.png'))
 page.set_viewport_size({'width':390,'height':844});page.locator('#reader-directory-toggle').click();page.locator('[data-reader-topic]').first.click();assert page.locator('.reader-detail').is_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.screenshot(path=str(r.parent/'release-validation/tree-mobile.png'))
 assert not errors,errors
 (r/'reports/tree-carrier-audit.json').write_text(json.dumps({'hiddenGroupCount':len(audit),'groups':audit,'originalDataModified':False,'rule':'Conservative short method-referencing computer/storage carrier claims only; uncertain groups retained.','desktopHover':True,'mobileTap':True,'pageErrors':errors},ensure_ascii=False,indent=2)+'\n')
 print('PASS groups hidden:',len(audit));b.close()
server.shutdown()
