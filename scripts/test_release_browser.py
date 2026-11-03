"""Read-only release UI checks for the design gallery and product path reader.

Default local checks distinguish the saved committed-PDF test route from live
network access. Use --live-only for an online check with no request interception.
No authentication, data uploads, notification, or publication is performed.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import traceback
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = 'CN308935268S'
RAW_PATTERN = 'https://raw.githubusercontent.com/wang10086-creator/chcnav-patent-pdfs/**'


def ready(page):
    page.wait_for_function("typeof currentReady !== 'undefined' && currentReady && pdfIndex?.counts?.matched===938 && window.DesignViews?.getState().loaded", timeout=30000)


def overflow(page):
    return page.evaluate('document.documentElement.scrollWidth > innerWidth')


def monitor_absent(page):
    return page.evaluate("""() => ({
      noNavigation: !document.querySelector('a[href="#monitor"],a[href*="127.0.0.1:8765"],#monitor-admin-workbench'),
      noGlobals: !window.PatentMonitor && !window.MonitorXlsx,
      noScripts: ![...document.scripts].some(s=>/patent-monitor|monitor-xlsx|manual_monitor_admin/.test(s.src)),
      noControls: !document.querySelector('#manual-import-form,#login-form,#monitor-files,#approve-button'),
      noMonitorTitle: ![...document.querySelectorAll('h1,h2,h3')].some(h=>/专利监控|管理员工作台/.test(h.textContent))
    })""")


def path_checks(page, screenshots):
    result = page.evaluate("""() => {
      const before={reader:{...reader},filter:{...currentFilter},query:currentQuery};
      const checks=[], problems=[], productIds=new Set();
      for(const product of primaryData.categories){
        productIds.add(product.id);
        currentFilter.product=product.id;currentFilter.form='';currentQuery='';resetReader(product.id);
        const forms=readerModel(currentFiltered()).available;
        for(const form of forms){
          reader.form=form;reader.topic='';const m=readerModel(currentFiltered());
          if(m.product?.id!==product.id){problems.push('wrong product '+product.id);continue;}
          if(new Set(m.paths.map(p=>p.path.id)).size!==m.paths.length)problems.push('duplicate path '+product.id+form);
          if(new Set(m.topics.map(t=>t[0])).size!==m.topics.length)problems.push('duplicate topic '+product.id+form);
          if(m.paths.some((p,i)=>i&&m.paths[i-1].count<p.count))problems.push('path order '+product.id+form);
          if(m.paths.some(p=>p.children.some((c,i)=>i&&readerApplicationCount(p.children[i-1][1])<readerApplicationCount(c[1]))))problems.push('topic order '+product.id+form);
          currentRender();
          if(document.querySelectorAll('.reader-detail').length!==1)problems.push('detail count '+product.id+form);
          if(document.querySelectorAll('.route-branch[open]').length>1)problems.push('expanded paths '+product.id+form);
          checks.push({product:product.id,form,paths:m.paths.length,subpaths:m.topics.length});
        }
      }
      currentFilter=before.filter;currentQuery=before.query;reader=before.reader;currentRender();
      return {productCount:productIds.size,checks,problems};
    }""")
    assert result['productCount'] == 16, result
    assert not result['problems'], result['problems']
    assert page.locator('.reader-product-hero').count() == 1
    assert page.locator('.reader-references').get_attribute('open') is None
    page.locator('[data-reader-audience="ip"]').click()
    assert page.locator('.reader-references').get_attribute('open') is not None
    page.locator('.reader-evidence').first.locator('summary').click()
    assert page.locator('.reader-evidence[open]').count() == 1
    assert page.locator('.reader-reference [data-pdf-publication]').first.locator('a').count() == 2
    branch = page.locator('.route-branch').last
    if branch.get_attribute('open') is None:
        branch.locator('summary').click()
    page.wait_for_function("document.querySelectorAll('.route-branch[open]').length===1")
    assert page.locator('.route-branch[open]').count() == 1
    branch.locator('[data-reader-topic]').last.click()
    assert page.locator('.reader-detail').count() == 1
    page.evaluate('window.scrollTo(0,0)')
    page.wait_for_function('scrollY===0')
    page.screenshot(path=str(screenshots / 'release-paths-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('[data-reader-audience="rd"]').click()
    page.locator('#reader-directory-toggle').click()
    assert page.locator('.reader-workspace.show-directory').count() == 1
    branch = page.locator('.route-branch').last
    if branch.get_attribute('open') is None:
        branch.locator('summary').click()
    branch.locator('[data-reader-topic]').last.click()
    assert page.locator('.reader-workspace.show-directory').count() == 0
    assert not overflow(page)
    page.evaluate('window.scrollTo(0,0)')
    page.wait_for_function('scrollY===0')
    page.screenshot(path=str(screenshots / 'release-paths-mobile.png'), full_page=True)
    page.locator('#current-q').fill('CN104697526A')
    page.wait_for_function("document.querySelector('.reader-product-facts b')?.textContent==='1'")
    page.locator('#current-clear').click()
    assert page.locator('#current-q').input_value() == ''
    result.update(desktop=True,mobile390NoOverflow=True,rdIpToggle=True,independentEvidence=True,
                  oneExpandedPath=True,singleDetail=True,search=True,mobileDirectorySwitch=True)
    return result


def gallery_checks(page, base, screenshots):
    page.set_viewport_size({'width':1440,'height':1000})
    page.goto(base + '#patent/' + PUBLICATION, wait_until='networkidle')
    ready(page)
    gallery = page.locator('.design-views[data-dv-id="'+PUBLICATION+'"]')
    assert gallery.count() == 1
    assert gallery.locator('.dv-card:visible').count() <= 6
    assert gallery.locator('img:not([loading="lazy"])').count() == 0
    assert gallery.locator('.dv-more').get_attribute('open') is None
    gallery.locator('.dv-card:visible').first.click()
    page.wait_for_selector('#design-viewer[open]')
    page.wait_for_function("document.querySelector('#dv-viewer-image').naturalWidth>0")
    first_image = page.locator('#dv-viewer-image').get_attribute('src')
    first_link = page.locator('#dv-page-pdf').get_attribute('href')
    query = parse_qs(urlsplit(first_link).query)
    assert query['id'] == [PUBLICATION] and int(query['page'][0]) >= 2
    assert page.locator('#dv-source-pdf').get_attribute('href').startswith('https://github.com/wang10086-creator/chcnav-patent-pdfs/blob/')
    page.locator('[data-dv-next]').click()
    assert page.locator('#dv-viewer-image').get_attribute('src') != first_image
    page.keyboard.press('ArrowLeft')
    assert page.locator('#dv-viewer-image').get_attribute('src') == first_image
    page.locator('[data-dv-zoom]').click()
    assert page.locator('[data-dv-zoom]').get_attribute('aria-pressed') == 'true'
    page.locator('[data-dv-zoom]').click()
    page.screenshot(path=str(screenshots / 'release-gallery-desktop.png'))
    page.keyboard.press('Escape')
    gallery.locator('[data-dv-mode="pages"]').click()
    assert gallery.locator('.dv-card').count() == 4
    assert gallery.locator('.dv-card:visible').count() == 2
    gallery.locator('.dv-support > summary').click()
    assert gallery.locator('.dv-card:visible').count() == 4
    gallery.locator('.dv-card:visible').first.click()
    page.wait_for_function("document.querySelector('#dv-viewer-image').naturalWidth>0")
    assert '整页' in page.locator('#dv-viewer-title').inner_text() or 'PDF 第' in page.locator('#dv-viewer-title').inner_text() or '图' in page.locator('#dv-viewer-title').inner_text()
    page.set_viewport_size({'width':390,'height':844})
    assert not overflow(page)
    page.screenshot(path=str(screenshots / 'release-gallery-mobile.png'))
    page.locator('[data-dv-close]').click()
    assert not overflow(page)
    return dict(publication=PUBLICATION,multiPage=True,lazyThumbnails=True,defaultCompact=True,
                magnify=True,nextPreviousAndKeyboard=True,originalSizeToggle=True,
                sourceVersionLink=True,pdfPageLink=first_link,wholeDrawingPagesAndSupport=True,
                mobile390NoOverflow=True)


def pdf_checks(browser, base, pdf_repo, live_only, screenshots):
    results = {}
    if not live_only:
        index=json.loads((ROOT/'site-overrides/data/pdf-index.json').read_text())
        record=index['documents'][PUBLICATION]
        body=(pdf_repo/record['path']).read_bytes()
        assert hashlib.sha256(body).hexdigest() == record['sha256']
        ctx=browser.new_context(viewport={'width':1280,'height':900})
        ctx.route(RAW_PATTERN,lambda r:r.fulfill(status=200,body=body,content_type='application/pdf',headers={'Access-Control-Allow-Origin':'*'}))
        page=ctx.new_page()
        page.goto(base+'pdf-viewer.html?id='+PUBLICATION+'&page=3',wait_until='networkidle')
        page.wait_for_function("document.querySelector('#pv-status').textContent.includes('SHA-256 校验通过')",timeout=30000)
        assert '第 3 / 4 页' in page.locator('#pv-status').inner_text()
        assert page.locator('#pv-canvas').is_visible()
        page.locator('#pv-next').click()
        page.wait_for_function("document.querySelector('#pv-status').textContent.includes('第 4 / 4 页') && document.querySelector('#pv-status').textContent.includes('SHA-256 校验通过')")
        page.set_viewport_size({'width':390,'height':844})
        assert not overflow(page)
        page.screenshot(path=str(screenshots/'release-pdf-isolated-mobile.png'),full_page=True)
        results['isolatedCommittedPdf']={'sha256Matched':True,'page3Then4':True,'canvasRendered':True,'mobileNoOverflow':True,'networkIntercepted':True}
        ctx.close()
        ctx=browser.new_context(viewport={'width':390,'height':844})
        ctx.route(RAW_PATTERN,lambda r:r.abort('failed'))
        page=ctx.new_page();page.goto(base+'pdf-viewer.html?id='+PUBLICATION+'&page=3',wait_until='networkidle')
        page.wait_for_selector('#pv-fallback:visible')
        page.wait_for_function("document.querySelector('#pv-fallback').naturalWidth>0")
        assert 'page-003.webp' in page.locator('#pv-fallback').get_attribute('src')
        assert '原页渲染图' in page.locator('#pv-message').inner_text()
        assert not overflow(page)
        results['isolatedNetworkFailure']={'exactSavedPage':True,'explicitFailureNotice':True,'mobileNoOverflow':True,'networkIntercepted':True}
        ctx.close()
    ctx=browser.new_context(viewport={'width':1280,'height':900})
    page=ctx.new_page();page.goto(base+'pdf-viewer.html?id='+PUBLICATION+'&page=3',wait_until='domcontentloaded')
    page.wait_for_function("['SHA-256 校验通过','已保存的原页渲染图','未能显示'].some(x=>document.querySelector('#pv-status').textContent.includes(x))",timeout=55000)
    results['actualNetwork']={'status':page.locator('#pv-status').inner_text(),
                              'message':page.locator('#pv-message').inner_text(),
                              'canvasVisible':page.locator('#pv-canvas').is_visible(),
                              'fallbackVisible':page.locator('#pv-fallback').is_visible(),
                              'networkIntercepted':False}
    ctx.close()
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True)
    p.add_argument('--pdf-repo',type=Path,default=ROOT.parent/'pdf-repository')
    p.add_argument('--output',type=Path,default=ROOT/'reports/release-browser-validation.json')
    p.add_argument('--screenshots',type=Path,default=ROOT.parent/'release-validation')
    p.add_argument('--live-only',action='store_true')
    args=p.parse_args();base=args.base_url.rstrip('/')+'/'
    args.screenshots.mkdir(parents=True,exist_ok=True)
    report={'baseUrl':base,'checkedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
            'mode':'live-only-no-interception' if args.live_only else 'local-and-separated-pdf-fixtures',
            'status':'running','mutatingNetworkRequests':[],'pageErrors':[]}
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':1000})
            page=context.new_page();page.set_default_timeout(15000)
            page.on('pageerror',lambda e:report['pageErrors'].append(str(e)))
            page.on('request',lambda r:report['mutatingNetworkRequests'].append({'method':r.method,'url':r.url}) if r.method not in ('GET','HEAD','OPTIONS') else None)
            response=page.goto(base,wait_until='networkidle',timeout=30000)
            report['mainHttpStatus']=response.status if response else None
            assert response and response.status==200, 'Website did not return HTTP 200'
            ready(page)
            report['monitorIsolation']=monitor_absent(page)
            assert all(report['monitorIsolation'].values()),report['monitorIsolation']
            report['paths']=path_checks(page,args.screenshots)
            report['gallery']=gallery_checks(page,base,args.screenshots)
            page.goto(base+'#monitor',wait_until='networkidle');ready(page)
            report['monitorHashIsolation']=monitor_absent(page)
            assert all(report['monitorHashIsolation'].values()),report['monitorHashIsolation']
            forbidden=['patent-monitor.js','patent-monitor.css','patent-monitor-core.js','monitor-xlsx.js','data/monitor-config.json','admin-ui/index.html','scripts/manual_monitor_admin.py']
            report['unpublishedPaths']={name:context.request.get(base+name).status for name in forbidden}
            assert all(status==404 for status in report['unpublishedPaths'].values()),report['unpublishedPaths']
            assert not report['pageErrors'],report['pageErrors']
            assert not report['mutatingNetworkRequests'],report['mutatingNetworkRequests']
            context.close()
            report['pdf']=pdf_checks(browser,base,args.pdf_repo,args.live_only,args.screenshots)
            browser.close()
        report['status']='pass'
    except Exception as error:
        report['status']='unverified' if args.live_only and 'paths' not in report else 'fail'
        report['error']=type(error).__name__ + ': ' + str(error)
        report['failureTraceback']=traceback.format_exc()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'output':str(args.output),
                      'products':report.get('paths',{}).get('productCount'),
                      'productFormChecks':len(report.get('paths',{}).get('checks',[])),
                      'pageErrors':report['pageErrors'],'error':report.get('error')},ensure_ascii=False))
    return 0 if report['status']=='pass' else 2


if __name__=='__main__':
    sys.exit(main())
