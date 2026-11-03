/* Local-only Incopat comparison. No network, writes, notifications or status inference. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.PatentMonitorCore=api;})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const aliases={
  publicationNumber:['publicationNumber','id','公开（公告）号','公开(公告)号','公开公告号','公开号','公告号'],
  applicationNumber:['applicationNumber','申请号','申请（专利）号','申请(专利)号'],
  title:['title','标题','名称','发明名称','专利名称'],
  applicants:['applicants','申请人','申请（专利权）人','申请(专利权)人'],
  legalStatus:['legalStatus','当前法律状态','法律状态'],
  legalEvent:['legalEvent','法律事件','法律状态事件'],
  eventDate:['eventDate','法律事件日期','法律状态公告日'],
  publicationDate:['publicationDate','公开（公告）日','公开(公告)日','公开日','公告日'],
  familyId:['familyId','简单同族ID','同族ID','同族号'],
  evidenceUrl:['evidenceUrl','证据链接','来源链接'],
  sourceFile:['sourceFile'],sourceFileSha256:['sourceFileSha256'],
  sourceSheet:['sourceSheet'],sourceExcelRow:['sourceExcelRow'],
  sourceRecordNumber:['sourceRecordNumber','序号'],sourceBatchRange:['sourceBatchRange'],
  sourceEventIndex:['sourceEventIndex'],legalEventDescription:['legalEventDescription']
 };
 const clean=x=>String(x??'').trim();
 const publication=x=>clean(x).toUpperCase().replace(/[\s\u3000-]/g,'');
 const application=x=>clean(x).toUpperCase().replace(/[\s\u3000]/g,'');
 const knownStatus=x=>!!clean(x)&&!/(未核验|待核验|未知|未确认|待确认|不明|不详|未提供|不可用|见详情|需复核|unknown|unverified|uncertain)/i.test(x)&&!/^(其他|其它|N\/?A|NULL|NAN|-+)$/i.test(clean(x));
 const calendarDate=x=>/^\d{4}-\d{2}-\d{2}$/.test(x||'')&&!Number.isNaN(Date.parse(x))&&new Date(x).toISOString().slice(0,10)===x;
 function parseCSV(text){
  text=String(text).replace(/^\uFEFF/,'');
  const first=text.split(/\r?\n/)[0]||'', delimiter=first.includes('\t')&&!first.includes(',')?'\t':',';
  const rows=[];let row=[],cell='',quoted=false;
  for(let i=0;i<text.length;i++){
   const c=text[i];
   if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else if(quoted||cell==='')quoted=!quoted;else throw Error('CSV 引号位置不合法');}
   else if(c===delimiter&&!quoted){row.push(cell);cell='';}
   else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v.trim()))rows.push(row);row=[];cell='';}
   else cell+=c;
  }
  if(quoted)throw Error('CSV 引号未闭合，可能下载不完整');
  row.push(cell);if(row.some(v=>v.trim()))rows.push(row);
  if(!rows.length)throw Error('文件为空');
  const headers=rows.shift().map(clean);
  if(headers.some(x=>!x)||new Set(headers).size!==headers.length)throw Error('CSV 表头为空或重复');
  if(!aliases.publicationNumber.some(k=>headers.includes(k))||!aliases.applicationNumber.some(k=>headers.includes(k)))throw Error('缺少完整公开号或申请号列；请保留 Incopat 原始表头或使用支持的字段名');
  return rows.map((values,i)=>{if(values.length!==headers.length)throw Error(`第 ${i+2} 行列数不完整`);return Object.fromEntries(headers.map((h,n)=>[h,values[n]]));});
 }
 function normalize(row){
  const out={};for(const [key,names] of Object.entries(aliases)){out[key]='';for(const name of names)if(row[name]!==undefined&&clean(row[name])){out[key]=clean(row[name]);break;}}
  out.publicationNumber=publication(out.publicationNumber);out.applicationNumber=application(out.applicationNumber);
  out.applicants=out.applicants.split(/[;；\n]/).map(clean).filter(Boolean);
  return out;
 }
 const fileHash=x=>/^[a-f0-9]{64}$/i.test(x||'');
 const zonedTime=x=>/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(x||'')&&calendarDate(String(x||'').slice(0,10))&&!Number.isNaN(Date.parse(x));
 function validateCoverage(m,rowCount,distinctPublicationCount=null){
  const errors=[],warnings=[];
  const audit=m.exportAudit;
  const current=m.coverageSchemaVersion===2||['resultPageCount','expectedExportBatches','downloadedExportBatches','exportBatches','exportAudit'].some(k=>Object.prototype.hasOwnProperty.call(m,k));
  const req=(ok,msg)=>{if(!ok)errors.push(msg);};
  if(!current){
   req(m.coverageSchemaVersion===undefined||m.coverageSchemaVersion===1,'覆盖记录版本不受支持');
   req(Number.isInteger(m.expectedPages)&&m.expectedPages>0&&m.downloadedPages===m.expectedPages,'分页覆盖不完整或未记录');
   return {schemaVersion:1,mode:'legacy-unspecified-page-count',
    resultPageCount:null,expectedExportBatches:null,downloadedExportBatches:null,
    legacyPageCounts:{expected:m.expectedPages??null,downloaded:m.downloadedPages??null},
    allResultPagesVisited:false,exportBatches:[],complete:errors.length===0,errors,
    warnings:['旧 expectedPages/downloadedPages 未明确列表页或导出批次；仅保留原值，不认定全部检索列表页已逐页浏览。']};
  }
  req(m.coverageSchemaVersion===undefined||m.coverageSchemaVersion===2,'覆盖记录版本不受支持');
  if(m.expectedPages!==undefined||m.downloadedPages!==undefined)warnings.push('旧分页字段仅随原始元数据保留；本次按明确的列表页数和导出批次分别验收。');
  req(Number.isInteger(m.resultPageCount)&&m.resultPageCount>=(m.totalResults===0?0:1),'缺少有效的检索列表总页数 resultPageCount（不能用导出批次数代替）');
  if(m.resultPageSize!==undefined){
   req(Number.isInteger(m.resultPageSize)&&m.resultPageSize>0,'检索列表每页条数无效');
   if(Number.isInteger(m.totalResults)&&m.totalResults>0&&Number.isInteger(m.resultPageSize)&&m.resultPageSize>0)req(m.resultPageCount===Math.ceil(m.totalResults/m.resultPageSize),'检索列表页数、每页条数与来源文献总数不一致');
  }
  req(Number.isInteger(m.expectedExportBatches)&&m.expectedExportBatches>=(m.totalResults===0?0:1),'缺少有效的应导出批次数 expectedExportBatches');
  req(Number.isInteger(m.downloadedExportBatches)&&m.downloadedExportBatches===m.expectedExportBatches,'已下载导出批次数与应导出批次数不一致');
  let batches=m.exportBatches;
  if(batches===undefined&&audit&&typeof audit==='object')batches=audit.batches;
  req(Array.isArray(batches),'缺少逐批范围、检索式和文件校验值清单');
  batches=Array.isArray(batches)?batches:[];
  req(batches.length===m.downloadedExportBatches,'逐批文件清单数量与已下载批次数不一致');
  const hashes=new Set(),ranges=[],normalized=[];
  for(let i=0;i<batches.length;i++){
   const b=batches[i]||{},label=`第 ${i+1} 批`;
   const match=/^([1-9]\d*)\s*-\s*([1-9]\d*)$/.exec(clean(b.range||b.sourceRange));
   const start=match?Number(match[1]):null,end=match?Number(match[2]):null;
   req(!!match&&Number.isSafeInteger(start)&&Number.isSafeInteger(end)&&start<=end&&end<=m.totalResults,label+'的来源序号范围缺失、无效或超过总结果数');
   const hash=clean(b.sha256||b.sourceFileSha256).toLowerCase();
   req(fileHash(hash),label+'缺少真实原文件 SHA-256');
   if(hash&&hashes.has(hash))errors.push(label+'重复使用同一原文件，不能计为独立完整批次');
   hashes.add(hash);
   const count=b.recordCount??b.physicalDataRows??b.sourceCount;
   req(Number.isInteger(count)&&count>=0&&!!match&&count===end-start+1,label+'的原始文献记录数与批次范围不一致（不能使用展开后的法律事件行数）');
   const query=clean(b.searchQuery||b.sourceSearchQuery||b.downloadIntroduction?.['下载内容']);
   req(!!query&&query===clean(m.searchQuery),label+'的来源检索式缺失或与本次检索式不一致');
   if(b.downloadedAt!==undefined&&b.downloadedAt!==null)req(zonedTime(b.downloadedAt),label+'的下载时间缺少有效时区或日期');
   if(b.issues!==undefined)req(Array.isArray(b.issues)&&b.issues.length===0,label+'的原文件适配审计存在异常');
   if(match&&Number.isSafeInteger(start)&&Number.isSafeInteger(end))ranges.push({start,end});
   normalized.push({range:match?`${start}-${end}`:clean(b.range||b.sourceRange),sha256:hash,
    recordCount:count??null,searchQuery:query,fileName:clean(b.fileName||b.sourceFile||(typeof b.path==='string'?b.path.split(/[\\/]/).at(-1):'')),downloadedAt:b.downloadedAt||null});
  }
  let next=1;
  for(const range of ranges.sort((a,b)=>a.start-b.start||a.end-b.end)){
   if(range.start<next)errors.push('导出批次范围存在重叠或重复');
   else if(range.start>next)errors.push(`导出批次范围缺失来源序号 ${next}-${range.start-1}`);
   next=Math.max(next,range.end+1);
  }
  req(next===m.totalResults+1,'导出批次范围未连续覆盖来源全部文献（不能据此显示无变化）');
  const physicalRecords=normalized.reduce((n,b)=>n+(Number.isInteger(b.recordCount)?b.recordCount:0),0);
  req(physicalRecords===distinctPublicationCount,'逐批原始文献数与导入完整公开号去重数不一致');
  if(audit!==undefined){
   req(!!audit&&typeof audit==='object'&&!Array.isArray(audit),'导出适配审计结构无效');
   if(audit&&typeof audit==='object'){
    req(audit.exportComplete===true&&Array.isArray(audit.issues)&&audit.issues.length===0,'导出适配审计未确认完整或仍含异常');
    req(clean(audit.searchQuery)===clean(m.searchQuery),'导出适配审计的检索式与本次检索式不一致');
    req(audit.sourceTotalResults===m.totalResults&&audit.distinctPublications===distinctPublicationCount&&audit.nativeRecords===physicalRecords,'导出适配审计的来源总数／唯一文献数／原始文献数不一致');
    req(audit.canonicalRows===rowCount,'导出适配审计的展开行数与实际导入行数不一致');
    if(audit.canonicalSha256!==undefined)req(fileHash(audit.canonicalSha256)&&audit.canonicalSha256.toLowerCase()===clean(m.fileSha256).toLowerCase(),'规范 CSV 字节校验值与适配审计不一致');
    if(audit.sourceManifestSha256!==undefined)req(fileHash(audit.sourceManifestSha256),'原始批次清单校验值无效');
    if(audit.missingSequenceNumbers!==undefined)req(Array.isArray(audit.missingSequenceNumbers)&&audit.missingSequenceNumbers.length===0,'适配审计仍有未下载的原始文献序号');
    req(Array.isArray(audit.batches),'导出适配审计缺少原始批次文件清单');
    if(Array.isArray(audit.batches)){
     const signature=value=>{const b=value&&typeof value==='object'?value:{};return `${clean(b.range||b.sourceRange).replace(/\s/g,'')}|${clean(b.sha256||b.sourceFileSha256).toLowerCase()}`;};
     req(audit.batches.length===normalized.length&&new Set(audit.batches.map(signature)).size===normalized.length&&audit.batches.every(b=>normalized.some(n=>signature(n)===signature(b))),'显式批次清单与导出适配审计的范围／文件校验值不一致');
    }
   }
  }
  const sampled=Array.isArray(m.sampledResultPages)?m.sampledResultPages:[];
  const visited=Array.isArray(m.visitedResultPages)?m.visitedResultPages:[];
  req(m.sampledResultPages===undefined||Array.isArray(m.sampledResultPages),'检索列表抽查页记录必须是数组');
  req(m.visitedResultPages===undefined||Array.isArray(m.visitedResultPages),'已浏览列表页记录必须是数组');
  req(sampled.every(p=>Number.isInteger(typeof p==='object'?p?.page:p)&&(typeof p==='object'?p.page:p)>=1&&(typeof p==='object'?p.page:p)<=m.resultPageCount),'检索列表抽查页码无效');
  req(visited.every(p=>Number.isInteger(p)&&p>=1&&p<=m.resultPageCount)&&new Set(visited).size===visited.length,'已浏览列表页记录含无效或重复页码');
  return {schemaVersion:2,mode:'explicit-result-pages-and-export-batches',resultPageCount:m.resultPageCount??null,
   resultPageSize:m.resultPageSize??null,sampledResultPages:sampled,visitedResultPages:visited,
   allResultPagesVisited:Number.isInteger(m.resultPageCount)&&m.resultPageCount>0&&new Set(visited).size===m.resultPageCount,
   expectedExportBatches:m.expectedExportBatches??null,downloadedExportBatches:m.downloadedExportBatches??null,
   sourcePublications:distinctPublicationCount,physicalSourceRecords:physicalRecords,expandedImportRows:rowCount,
   exportBatches:normalized,adaptationAuditSupplied:audit!==undefined,complete:errors.length===0,errors,warnings};
 }
 function validateMetadata(m,rowCount,distinctPublicationCount=null){
  const errors=[];const req=(ok,msg)=>{if(!ok)errors.push(msg);};
  req(typeof m.searchQuery==='string'&&!!clean(m.searchQuery),'缺少实际检索条件');
  req(calendarDate(m.timeFrom)&&calendarDate(m.timeTo)&&m.timeFrom<=m.timeTo,'检索时间范围缺失或无效');
  req(/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(m.executedAt||'')&&calendarDate(String(m.executedAt||'').slice(0,10))&&!Number.isNaN(Date.parse(m.executedAt)),'缺少含时区的有效执行时间');
  req(Number.isInteger(m.totalResults)&&m.totalResults>=0,'缺少结果总数');
  const basis=m.resultCountBasis||'rows';
  req(basis==='publications'||basis==='rows','来源总数口径无效，应为 publications（完整公开号）或 rows（导出行）');
  const covered=basis==='publications'?distinctPublicationCount:rowCount;
  req(Number.isInteger(covered)&&m.totalResults===covered,basis==='publications'?'按完整公开号去重的导出文献数与来源总数不一致（不能认定覆盖完整）':'原始导出行数与来源总数不一致（不能认定覆盖完整）');
  errors.push(...validateCoverage(m,rowCount,distinctPublicationCount).errors);
  if(m.xlsxInfo?.issues!==undefined)req(Array.isArray(m.xlsxInfo.issues)&&m.xlsxInfo.issues.length===0,'原生 XLSX 适配仍有异常，不能认定完整导出');
  if(m.xlsxInfo?.nativeFormat){
   const info=m.xlsxInfo;
   if(info.sourceSearchQuery!==undefined)req(clean(info.sourceSearchQuery)===clean(m.searchQuery),'原生 XLSX 下载简介检索式与执行记录不一致');
   if(info.sourceFileSha256!==undefined)req(fileHash(info.sourceFileSha256)&&info.sourceFileSha256.toLowerCase()===clean(m.fileSha256).toLowerCase(),'原生 XLSX 字节校验值与执行记录不一致');
  }
  req(m.exportComplete===true,'未确认全部结果导出');
  req(m.loginStatus==='authenticated','登录／机构授权未确认或已失效');
  req(/^[a-f0-9]{64}$/i.test(m.fileSha256||''),'缺少导出文件 SHA-256');
  if(m.exportAuditSha256!==undefined)req(fileHash(m.exportAuditSha256),'导出适配审计文件 SHA-256 无效');
  req(m.sourceUrl==='https://www-incopat-com-s-6.proxy.itic-sci.com/','数据来源未确认为指定 Incopat 入口');
  return errors;
 }
 function compare(rawRows,baselineDocs,metadata,profile,previousSnapshot=null){
  const normalizedRows=rawRows.map(normalize);
  const distinctPublicationCount=new Set(normalizedRows.map(r=>r.publicationNumber).filter(id=>/^CN\d{9}[ABUS]\d?$/.test(id))).size;
  const coverage=validateCoverage(metadata,rawRows.length,distinctPublicationCount);
  const anomalies=validateMetadata(metadata,rawRows.length,distinctPublicationCount).map(reason=>({type:'run-metadata',reason}));
  const baselineById=new Map(baselineDocs.map(d=>[publication(d.id||d.publicationNumber),d]));
  const baselineApps=new Set(baselineDocs.map(d=>application(d.applicationNumber)));
  const previous=new Map();
  if(previousSnapshot){
   if(previousSnapshot.kind!=='incopat-observation-baseline'||previousSnapshot.reviewed!==true||previousSnapshot.source!==metadata.sourceUrl||previousSnapshot.profile?.id!==profile?.id||!Array.isArray(previousSnapshot.observations))anomalies.push({type:'previous-snapshot',reason:'对照快照不是同来源、同竞争对手且经过人工核对的观察基线'});
   else for(const d of previousSnapshot.observations){
    const id=publication(d.publicationNumber);if(previous.has(id))anomalies.push({type:'previous-snapshot',publicationNumber:id,reason:'对照快照含重复公开号'});
    previous.set(id,d);baselineApps.add(application(d.applicationNumber));
   }
  }
  const names=new Set(profile?.inScopeApplicantNames||[]),byId=new Map(),eventRows=new Map(),duplicateRows=[],conflicts=[];
  for(let i=0;i<rawRows.length;i++){
   const row={...normalizedRows[i],sourceRow:i+2};
   if(row.sourceFileSha256&&!fileHash(row.sourceFileSha256))anomalies.push({type:'source-provenance',row:i+2,reason:'原始来源文件校验值格式无效'});
   if(coverage.schemaVersion===2&&(row.sourceFileSha256||row.sourceBatchRange)&&!coverage.exportBatches.some(b=>b.sha256===row.sourceFileSha256.toLowerCase()&&b.range===row.sourceBatchRange.replace(/\s/g,'')))anomalies.push({type:'source-provenance',row:i+2,reason:'原始记录的文件校验值／批次范围未出现在已核对的批次清单中'});
   if(!/^CN\d{9}[ABUS]\d?$/.test(row.publicationNumber)||!/^CN\d{8,13}(?:\.[0-9X])?$/.test(row.applicationNumber)){
    anomalies.push({type:'identifier',row:i+2,reason:'公开号／申请号格式未能可靠识别，未自动匹配',publicationNumber:row.publicationNumber,applicationNumber:row.applicationNumber});continue;
   }
   const existing=byId.get(row.publicationNumber);
   if(existing){
    const sameIdentity=existing.applicationNumber===row.applicationNumber&&existing.legalStatus===row.legalStatus&&JSON.stringify(existing.applicants)===JSON.stringify(row.applicants);
    const sameEvent=eventRows.get(row.publicationNumber).some(x=>x.legalEvent===row.legalEvent&&x.eventDate===row.eventDate);
    if(sameIdentity&&sameEvent)duplicateRows.push({publicationNumber:row.publicationNumber,sourceRows:[existing.sourceRow,row.sourceRow]});
    else if(sameIdentity)eventRows.get(row.publicationNumber).push(row);
    else conflicts.push({publicationNumber:row.publicationNumber,reason:'同公开号的申请号／当前状态／申请人存在冲突，待人工复核',rows:[existing,row]});
    continue;
   }
   byId.set(row.publicationNumber,row);
   eventRows.set(row.publicationNumber,[row]);
  }
  const conflicted=new Set(conflicts.map(c=>c.publicationNumber));
  const stateChanges=[],firstStatusObservations=[],legalEvents=[],newPublications=[],outOfScope=[],observations=[];
  for(const [id,row] of byId){
   if(conflicted.has(id))continue;
   const existing=baselineById.get(id),prior=previous.get(id);
   if(!knownStatus(row.legalStatus))anomalies.push({type:'status-unconfirmed',publicationNumber:id,reason:'当前法律状态缺失或含义尚未确认，不能据此认定状态无变化'});
   if((existing&&application(existing.applicationNumber)!==row.applicationNumber)||(prior&&application(prior.applicationNumber)!==row.applicationNumber)){
    conflicts.push({publicationNumber:id,reason:'导出申请号与既有公开号对应的申请号不一致，未匹配',rows:[row]});continue;
   }
   const knownApplication=baselineApps.has(row.applicationNumber);
   if(!existing&&!prior&&!knownApplication&&!row.applicants.some(n=>names.has(n))){outOfScope.push({publicationNumber:id,reason:'新增申请人未命中精确范围；名称相似或同族不足以自动纳入',applicants:row.applicants});continue;}
   const oldStatus=prior?.legalStatus||(existing?.legalStatusVerified===true?existing.legalStatus:'');
   const originalSource=r=>({fileName:r.sourceFile||'',fileSha256:r.sourceFileSha256||'',sheet:r.sourceSheet||'',excelRow:r.sourceExcelRow||'',recordNumber:r.sourceRecordNumber||'',batchRange:r.sourceBatchRange||'',eventIndex:r.sourceEventIndex||''});
   const evidence={source:'Incopat 用户手动导出',sourceUrl:metadata.sourceUrl,evidenceUrl:/^https:\/\//i.test(row.evidenceUrl)?row.evidenceUrl:'',checkedAt:metadata.executedAt,eventDate:row.eventDate,sourceRow:row.sourceRow,exportFileSha256:metadata.fileSha256,exportFileName:metadata.fileName||'',originalSource:originalSource(row)};
   if(knownStatus(row.legalStatus)){
    if(knownStatus(oldStatus)&&oldStatus!==row.legalStatus)stateChanges.push({publicationNumber:id,applicationNumber:row.applicationNumber,before:oldStatus,after:row.legalStatus,meaning:'来源文本变化，状态含义待人工核对，不据此自动判定有效或失效',evidence});
    else if(!knownStatus(oldStatus))firstStatusObservations.push({publicationNumber:id,applicationNumber:row.applicationNumber,before:'尚无可信的同来源状态基线',after:row.legalStatus,evidence});
   }
   const events=eventRows.get(id).filter(x=>x.legalEvent);
   const oldEvents=prior?.legalEvents||(prior?.legalEvent?[{event:prior.legalEvent,eventDate:prior.eventDate,checkedAt:prior.checkedAt,evidence:prior.evidence}]:[]);
   const currentEvents=[];
   for(const e of events){
    const eventEvidence={...evidence,eventDate:e.eventDate,sourceRow:e.sourceRow,evidenceUrl:/^https:\/\//i.test(e.evidenceUrl)?e.evidenceUrl:'',originalSource:originalSource(e)};
    currentEvents.push({event:e.legalEvent,eventDate:e.eventDate,checkedAt:metadata.executedAt,evidence:eventEvidence});
    if(!oldEvents.some(old=>old.event===e.legalEvent&&old.eventDate===e.eventDate))legalEvents.push({publicationNumber:id,applicationNumber:row.applicationNumber,event:e.legalEvent,eventDate:e.eventDate||null,reviewRequired:!calendarDate(e.eventDate),evidence:eventEvidence});
   }
   if(!existing&&!prior)newPublications.push({publicationNumber:id,applicationNumber:row.applicationNumber,title:row.title,kind:knownApplication?'new-publication-version':'new-application-publication',familyId:row.familyId||null,familyNote:row.familyId?'同族信息仅供参考，仍按申请号及版本区分':'',evidence});
   const eventHistoryMap=new Map();
   for(const event of [...oldEvents,...currentEvents]){
    const key=event.event+'\0'+event.eventDate,old=eventHistoryMap.get(key);
    const evidenceHistory=[...new Map([...(old?.evidenceHistory||[old?.evidence].filter(Boolean)),...(event.evidenceHistory||[event.evidence].filter(Boolean))].map(e=>[JSON.stringify(e),e])).values()];
    eventHistoryMap.set(key,{...event,firstCheckedAt:old?.firstCheckedAt||old?.checkedAt||event.firstCheckedAt||event.checkedAt,evidenceHistory});
   }
   const historicalEvents=[...eventHistoryMap.values()];
   const oldStatuses=prior?.statusHistory||(prior?[{legalStatus:prior.legalStatus,checkedAt:prior.checkedAt,evidence:prior.evidence}]:[]);
   const statusHistory=[...new Map([...oldStatuses,{legalStatus:row.legalStatus,checkedAt:metadata.executedAt,evidence}].map(s=>[s.legalStatus+'\0'+s.checkedAt+'\0'+s.evidence?.exportFileSha256,s])).values()];
   observations.push({...row,legalEvents:historicalEvents,statusHistory,source:'Incopat 用户手动导出',checkedAt:metadata.executedAt,evidence});
  }
  anomalies.push(...conflicts.map(c=>({type:'data-conflict',...c})),...outOfScope.map(c=>({type:'outside-scope',...c})));
  const newApplicationIds=[...new Set(newPublications.filter(x=>x.kind==='new-application-publication').map(x=>x.applicationNumber))];
  const candidateCount=stateChanges.length+firstStatusObservations.length+legalEvents.length+newPublications.length;
  const runState=anomalies.length?'exception-review-required':candidateCount?'review-required':'no-difference-in-complete-export';
  return {schemaVersion:1,kind:'incopat-review-report',runState,runStateLabel:anomalies.length?'执行异常／覆盖或数据待复核':candidateCount?'已比对，待人工核对':'完整导出范围内未发现差异',
   metadata:{...metadata,resultCountBasis:metadata.resultCountBasis||'rows',resultCountBasisLegacyDefault:!metadata.resultCountBasis,importedRows:rawRows.length,distinctPublications:distinctPublicationCount,comparisonScope:'只对本次完整导出覆盖范围作比较，不将未导出的既有文献推断为撤回、失效或删除'},
   coverage,profile:{id:profile?.id,name:profile?.name,inScopeApplicantNames:[...names]},
   counts:{baselineDocuments:baselineDocs.length,importedRows:rawRows.length,distinctPublications:distinctPublicationCount,duplicateRows:duplicateRows.length,stateChanges:stateChanges.length,firstStatusObservations:firstStatusObservations.length,legalEvents:legalEvents.length,newApplicationCount:newApplicationIds.length,newPublicationVersions:newPublications.filter(x=>x.kind==='new-publication-version').length,anomalies:anomalies.length},
   stateChanges,firstStatusObservations,legalEvents,newPublications,newApplicationIds,duplicateRows,anomalies,observations,
   snapshotObservations:[...new Map([...previous.values(),...observations].map(o=>[publication(o.publicationNumber),o])).values()],
   publicationState:'review-only-not-published',notice:'比较结果仅供人工核对；未修改网站数据，未触发通知。法律状态文本不等同官方有效性判断。'};
 }
 function makeSnapshot(report,reviewed){
  if(reviewed!==true||report.anomalies.length)throw Error('仅完整且无异常、经人工核对的结果可另存观察基线');
  return {schemaVersion:1,kind:'incopat-observation-baseline',reviewed:true,source:report.metadata.sourceUrl,checkedAt:report.metadata.executedAt,fileSha256:report.metadata.fileSha256,profile:report.profile,coverageNote:'保留本次未覆盖的此前观察，各条 checkedAt 为实际核查时间，不能视作本次全量刷新。',observations:report.snapshotObservations||report.observations};
 }
 return {parseCSV,normalize,validateCoverage,validateMetadata,compare,makeSnapshot};
});
