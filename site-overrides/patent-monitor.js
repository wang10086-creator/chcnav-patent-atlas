/* Incopat exports stay in this browser; the public site never receives the file. */
(function(){
 'use strict';
 const SOURCE='https://www-incopat-com-s-6.proxy.itic-sci.com/';
 const state={config:null,docs:[],profileId:'',report:null,history:[],loadError:'',busy:false};
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const array=x=>Array.isArray(x)?x:[];
 const formatDate=x=>x?new Date(x).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+'（北京时间）':'尚无已验收记录';
 async function load(docs){
  state.docs=docs||[];
  try{const response=await fetch('data/monitor-config.json');if(!response.ok)throw Error('config '+response.status);state.config=await response.json();if(!Array.isArray(state.config.profiles)||!state.config.profiles.length||state.config.profiles.some(p=>!p.id||!Array.isArray(p.inScopeApplicantNames)||!p.inScopeApplicantNames.length))throw Error('Invalid monitoring profiles');state.profileId=state.config.profiles[0].id;}
  catch(e){state.loadError='监控配置未能载入，暂不能进行可靠比对。请刷新重试。';}
 }
 const activeProfile=()=>state.config.profiles.find(p=>p.id===state.profileId)||state.config.profiles[0];
 const docsForProfile=profile=>state.docs.filter(d=>String(d.applicants||'').split(/[;；\n]/).some(n=>profile.inScopeApplicantNames.includes(n.trim())));
 const table=(columns,rows)=>`<div class="monitor-table-scroll"><table><thead><tr>${columns.map(([_,name])=>`<th>${esc(name)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,100).map(row=>`<tr>${columns.map(([key])=>`<td>${esc(typeof row[key]==='object'?JSON.stringify(row[key]):row[key])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${rows.length>100?`<p class="monitor-note">页面显示前 100 / ${rows.length} 条；完整记录保留在下载报告中。</p>`:''}`;
 function reportHtml(r){
  if(!r)return '<div class="monitor-empty"><b>尚未导入核查批次</b><p>上传真实导出文件后，结果只在当前浏览器计算。没有文件或覆盖不全，不会显示“无变化”。</p></div>';
  const c=r.counts||{};
  return `<section class="monitor-result" aria-live="polite"><div class="monitor-result-heading"><div><span class="monitor-tag ${r.anomalies?.length?'warning':''}">${esc(r.runStateLabel)}</span><h2>本次比对结果</h2><p>原文件 SHA-256：<code>${esc(r.metadata?.fileSha256||'未能读取')}</code></p></div><button class="button" id="monitor-report-download">下载待核对报告 ↓</button></div><div class="monitor-metrics">${[['导出行',c.importedRows],['去重文献',c.distinctPublications],['首次状态观察',c.firstStatusObservations],['状态文本变化',c.stateChanges],['新增申请',c.newApplicationCount],['既有申请新版本',c.newPublicationVersions],['重复行',c.duplicateRows],['异常',c.anomalies]].map(([label,value])=>`<div><b>${value??0}</b><span>${label}</span></div>`).join('')}</div><p class="monitor-note">来源总数 ${r.metadata?.totalResults??'未记录'}，口径：${r.metadata?.resultCountBasis==='publications'?'完整公开号去重文献数':'原始导出行数'}${r.metadata?.resultCountBasisLegacyDefault?'（旧元数据未指定，兼容采用导出行口径）':''}。仅比较本次导出的覆盖范围。没有出现在导出中的旧记录不会被判为失效、撤回或删除。首次取得的状态与有前后依据的状态变化分别列示。</p>
   ${array(r.anomalies).length?`<details open><summary>执行异常与待复核项（${r.anomalies.length}）</summary>${table([['type','类型'],['publicationNumber','公开号'],['reason','原因']],r.anomalies)}</details>`:''}
   ${array(r.stateChanges).length?`<details open><summary>状态文本变化（${r.stateChanges.length}）</summary>${table([['publicationNumber','公开号'],['before','之前'],['after','此次来源文本'],['evidence','来源／日期／核查时间']],r.stateChanges)}</details>`:''}
   ${array(r.firstStatusObservations).length?`<details><summary>首次取得状态观察（${r.firstStatusObservations.length}，不是已证实的状态变化）</summary>${table([['publicationNumber','公开号'],['before','之前依据'],['after','来源状态文本'],['evidence','来源证据']],r.firstStatusObservations)}</details>`:''}
   ${array(r.legalEvents).length?`<details><summary>法律事件记录（${r.legalEvents.length}）</summary>${table([['publicationNumber','公开号'],['event','事件原文'],['eventDate','事件日期'],['reviewRequired','日期待核对'],['evidence','来源证据']],r.legalEvents)}</details>`:''}
   ${array(r.newPublications).length?`<details open><summary>新增公布文献（${r.newPublications.length}）</summary>${table([['publicationNumber','完整公开号'],['applicationNumber','申请号'],['title','名称'],['kind','新增类型'],['familyId','来源同族标识']],r.newPublications.map(x=>({...x,kind:x.kind==='new-publication-version'?'既有申请的新公布／授权版本':'新申请的公布文献'})))}</details>`:''}
   ${array(r.duplicateRows).length?`<details><summary>已去重的重复导出行（${r.duplicateRows.length}）</summary>${table([['publicationNumber','公开号'],['sourceRows','原文件行号']],r.duplicateRows)}</details>`:''}
   <p class="monitor-note">${esc(r.notice||'比对失败，未改动正式数据。')}</p>${r.anomalies?.length?'':`<div class="monitor-snapshot"><label><input type="checkbox" id="monitor-reviewed"> 我已核对本批来源、覆盖、日期和状态文字，另存为下一次比对的观察基线</label><button class="button" id="monitor-snapshot-download" disabled>另存本地观察基线 ↓</button><small>只下载本地文件，不更新网站，不发送通知；下次可将该文件作为对照快照导入。</small></div>`}</section>`;
 }
 function render(){
  const config=state.config,profile=config?activeProfile():null,source=config?.source,baselineDocs=profile?docsForProfile(profile):[];
  if(state.loadError)return `<section class="patent-monitor"><h1>专利监控</h1><p role="alert">${esc(state.loadError)}</p></section>`;
  if(!config)return '<section class="patent-monitor"><h1>专利监控</h1><p>正在读取监控配置…</p></section>';
  return `<section class="patent-monitor"><header class="monitor-intro"><div><span class="monitor-eyebrow">华测导航（CHCNAV）</span><h1>专利监控</h1><p>按可靠标识核查状态记录与新增公布，先核对，再决定是否更新画像。</p></div><a class="button" href="#products">返回产品画像</a></header><label class="monitor-profile-label">监控对象<select id="monitor-profile">${config.profiles.map(p=>`<option value="${esc(p.id)}" ${p.id===state.profileId?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label><div class="monitor-status-grid"><article class="monitor-status"><span class="monitor-tag warning">云执行端尚未接通</span><h2>自动检索与导出</h2><p>${esc(source.probeDetail)}</p><small>上次连通检查：${esc(formatDate(source.checkedAt))}</small><small>上次成功自动执行：${esc(formatDate(source.lastSuccessfulAutomaticRun??source.lastSuccessfulRunAt))}</small><a href="${SOURCE}" target="_blank" rel="noopener">Incopat 数据来源 ↗</a></article><article class="monitor-status"><span class="monitor-tag">可用 · 手动导入</span><h2>本地核查与比对</h2><p>支持 Incopat CSV／XLSX 导出，文件在浏览器内处理。每批记录检索条件、总数、分页、时间与校验值。</p><small>当前对象基线：${baselineDocs.length} 条文献 / ${new Set(baselineDocs.map(d=>d.applicationNumber)).size} 个申请</small><small>当前基线没有官方法律状态核验；首次观察不会当作已证实的变化。</small></article></div><details class="monitor-scope"><summary>监控范围与执行方式</summary><p><b>默认申请人精确范围：</b>${esc(profile.inScopeApplicantNames.join('；'))}</p><p>${esc(profile.nameEvidence)}</p><p>${esc(profile.searchRule)}</p><p>已核实曾用名：${array(profile.aliases).length?esc(profile.aliases.join('；')):'尚未取得可靠证据，未自动加入别名。'}</p><details><summary>共申请人候选（${array(profile.relatedApplicantCandidates).length}，不自动扩大检索）</summary>${table([['name','文献中记载的完整名称'],['documentCount','共申请文献数']],array(profile.relatedApplicantCandidates))}</details><ol>${config.executionPlan.map(step=>`<li>${esc(step)}</li>`).join('')}</ol><p class="monitor-note">本站为静态页面，无法持续控制云浏览器。本机交互验收情况见上方记录；持续云执行端与定时任务尚未接通，后续结果仍需人工核对。本次原生 XLSX 请先在本地转换为规范 CSV 再导入；网页直接导入尚未兼容。请勿把密码、Cookie、验证码或导出会话交给页面或提交到公开仓库。</p></details>
  <section class="monitor-import"><div class="monitor-section-title"><div><h2>导入真实导出批次</h2><p>保留 Incopat 完整公开号和申请号；状态／事件、申请人等列按原表头识别。</p></div><button class="button" id="monitor-template-download">下载字段模板 ↓</button></div><form id="monitor-import-form"><div class="monitor-form-grid"><label class="monitor-wide">导出文件（CSV UTF-8／GB18030 或 XLSX）<input id="monitor-export-file" type="file" accept=".csv,.tsv,.xlsx" required></label><label class="monitor-wide">上次经人工核对的观察基线（可选 JSON）<input id="monitor-baseline-file" type="file" accept=".json"><small>不选时，以当前对象 ${baselineDocs.length} 条文献为基线，状态字段未官方核验。</small></label><label class="monitor-wide">实际检索条件<input id="monitor-query" placeholder="填写在 Incopat 实际执行的检索式及申请人范围" required></label><label>时间范围起<input id="monitor-time-from" type="date" required></label><label>时间范围止<input id="monitor-time-to" type="date" required></label><label>源检索执行时间<input id="monitor-executed-at" type="datetime-local" required></label><label>来源显示总结果数<input id="monitor-total" type="number" min="0" step="1" required></label><label>来源总数口径<select id="monitor-count-basis"><option value="publications">完整公开号去重文献数</option><option value="rows">原始导出行数</option></select><small>按来源实际口径选择；同一文献多个事件可导出多行，不要改写来源总数。</small></label><label>应下载页数<input id="monitor-pages-expected" type="number" min="1" step="1" required></label><label>已下载页数<input id="monitor-pages-actual" type="number" min="0" step="1" required></label><label>登录与机构授权<select id="monitor-login"><option value="unconfirmed">尚未确认</option><option value="authenticated">导出时已确认有效</option><option value="expired">已失效／导出受阻</option></select></label><label class="monitor-check"><input id="monitor-complete" type="checkbox"> 已核对分页、结果数及全量导出完整</label></div><div class="monitor-actions"><button class="button monitor-primary" type="submit">导入并生成待核对报告</button><span id="monitor-run-message" role="status"></span></div></form></section><div id="monitor-report">${reportHtml(state.report)}</div><section class="monitor-history"><h2>本次浏览会话记录</h2><p class="monitor-note">仅保存在当前浏览器内存，刷新后清空；请下载每批报告保留证据。不会写入正式数据或触发通知。</p><div id="monitor-history-list">${historyHtml()}</div></section></section>`;
 }
 function historyHtml(){return state.history.length?table([['checkedAt','源执行时间'],['label','结果状态'],['fileName','文件'],['sha256','文件 SHA-256']],state.history):'<p class="monitor-empty">尚无导入批次。</p>';}
 function download(value,name,type='application/json'){const blob=new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}
 async function decodeCSV(buffer){let text=new TextDecoder('utf-8',{fatal:false}).decode(buffer);if(text.includes('\uFFFD')){try{text=new TextDecoder('gb18030',{fatal:true}).decode(buffer);}catch{throw Error('CSV 编码无法可靠识别，请从 Incopat 导出 UTF-8 CSV 或使用 XLSX');}}return text;}
 function resultBindings(root){
  root.querySelector('#monitor-report-download')?.addEventListener('click',()=>download(state.report,'incopat-review-'+Date.now()+'.json'));
  const reviewed=root.querySelector('#monitor-reviewed'),button=root.querySelector('#monitor-snapshot-download');
  if(reviewed&&button){reviewed.onchange=()=>button.disabled=!reviewed.checked;button.onclick=()=>{try{download(PatentMonitorCore.makeSnapshot(state.report,reviewed.checked),'incopat-observation-baseline-'+Date.now()+'.json');}catch(e){root.querySelector('#monitor-run-message').textContent=e.message;}};}
 }
 function bind(root=document){
  const form=root.querySelector('#monitor-import-form');if(!form)return;
  const profileControl=root.querySelector('#monitor-profile');if(profileControl)profileControl.onchange=()=>{if(state.busy)return;state.profileId=profileControl.value;state.report=null;const view=root.querySelector('.patent-monitor');view.outerHTML=render();bind(root);};
  root.querySelector('#monitor-template-download').onclick=()=>download('\uFEFF公开（公告）号,申请号,名称,申请人,当前法律状态,法律事件,法律事件日期,公开（公告）日,简单同族ID,证据链接\r\n','incopat-field-template.csv','text/csv;charset=utf-8');
  form.onsubmit=async event=>{
   event.preventDefault();if(state.busy)return;if(!form.reportValidity())return;
   const field=id=>root.querySelector('#'+id),file=field('monitor-export-file').files[0],message=field('monitor-run-message');if(!file)return;
   if(file.size>40*1048576){message.textContent='文件超过浏览器单批 40 MiB 限制；请使用本地 Python 导入命令处理，不要删减导出结果凑容量。';return;}
   state.busy=true;if(profileControl)profileControl.disabled=true;const runProfile=activeProfile(),runDocs=docsForProfile(runProfile);message.textContent='正在本地读取、计算校验值并比对…';
   let metadata={sourceUrl:SOURCE,fileName:file.name};
   try{
    const bytes=await file.arrayBuffer();metadata.fileSha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
    const value=id=>field(id).value,number=id=>Number(value(id));
    metadata={...metadata,searchQuery:value('monitor-query'),timeFrom:value('monitor-time-from'),timeTo:value('monitor-time-to'),executedAt:new Date(value('monitor-executed-at')).toISOString(),totalResults:number('monitor-total'),resultCountBasis:value('monitor-count-basis'),expectedPages:number('monitor-pages-expected'),downloadedPages:number('monitor-pages-actual'),loginStatus:value('monitor-login'),exportComplete:field('monitor-complete').checked};
    let rows;
    if(/\.xlsx$/i.test(file.name)){if(!window.MonitorXlsx)throw Error('XLSX 读取器未载入，请刷新或改用 CSV／Python 导入命令');rows=await MonitorXlsx.read(bytes);metadata.xlsxInfo=rows.xlsxInfo||null;}
    else rows=PatentMonitorCore.parseCSV(await decodeCSV(bytes));
    const previousFile=field('monitor-baseline-file').files[0];let previous=null;
    if(previousFile){if(previousFile.size>40*1048576)throw Error('观察基线过大，请使用本地命令处理');previous=JSON.parse(await previousFile.text());}
    state.report=PatentMonitorCore.compare(rows,runDocs,metadata,runProfile,previous);
   }catch(e){state.report={schemaVersion:1,kind:'incopat-review-report',runState:'import-failed',runStateLabel:'导入失败，未完成核查',metadata,counts:{},anomalies:[{type:'import-failed',reason:String(e.message||e)}],notice:'文件未能完整解析，不能报告“无变化”或“监控成功”。正式专利数据保持不变。'};}
   state.history.unshift({checkedAt:metadata.executedAt||'未完成',label:state.report.runStateLabel,fileName:file.name,sha256:metadata.fileSha256||'未完成'});
   root.querySelector('#monitor-report').innerHTML=reportHtml(state.report);root.querySelector('#monitor-history-list').innerHTML=historyHtml();resultBindings(root);state.busy=false;if(profileControl)profileControl.disabled=false;message.textContent='已生成本地报告，请核对下方状态与异常。';
   root.querySelector('#monitor-report').scrollIntoView({block:'start',behavior:'smooth'});
  };
  resultBindings(root);
 }
 window.PatentMonitor={load,render,bind};
})();
