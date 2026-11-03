/* Isolated metadata and synthetic patent identifiers, never production imports. */
'use strict';
const assert=require('node:assert/strict');
const core=require('../../site-overrides/patent-monitor-core.js');
const query='ISOLATED ONLY exact applicant';
const profile={id:'isolated-coverage',name:'隔离测试',inScopeApplicantNames:['隔离测试申请人']};
const batches=Array.from({length:10},(_,i)=>({range:`${i*100+1}-${Math.min((i+1)*100,938)}`,
  sha256:(i+1).toString(16).padStart(64,'0'),physicalDataRows:Math.min(100,938-i*100),
  downloadedAt:'2026-11-03T17:08:19+08:00',downloadIntroduction:{'下载内容':query},
  path:`/isolated-private-fixture/batch-${i+1}.xlsx`}));
const baseline=[],rows=[];
for(let i=1;i<=938;i++){
  const id=`CN${200000000+i}A`,applicationNumber=`CN2026${String(i).padStart(8,'0')}.1`;
  baseline.push({id,applicationNumber,legalStatus:'当前法律状态未核验'});
  const batch=batches[Math.floor((i-1)/100)];
  for(let e=1;e<=(i<=457?3:2);e++)rows.push({publicationNumber:id,applicationNumber,
    title:'隔离夹具，不是真实专利',applicants:'隔离测试申请人',legalStatus:'审中',
    legalEvent:`隔离事件${e}`,eventDate:`2024-0${e}-01`,
    sourceFile:`batch-${Math.floor((i-1)/100)+1}.xlsx`,sourceFileSha256:batch.sha256,
    sourceSheet:'专利数据',sourceExcelRow:String((i-1)%100+2),sourceRecordNumber:String(i),
    sourceBatchRange:batch.range,sourceEventIndex:String(e)});
}
assert.equal(rows.length,2333);
const metadata={sourceUrl:'https://www-incopat-com-s-6.proxy.itic-sci.com/',searchQuery:query,
  timeFrom:'2024-01-01',timeTo:'2026-11-03',executedAt:'2026-11-03T17:08:19+08:00',
  totalResults:938,resultCountBasis:'publications',fileSha256:'a'.repeat(64),fileName:'isolated.csv',
  exportComplete:true,loginStatus:'authenticated',coverageSchemaVersion:2,
  resultPageCount:47,resultPageSize:20,expectedExportBatches:10,downloadedExportBatches:10,
  sampledResultPages:[{page:2,firstResult:21,lastResult:40},{page:47,firstResult:921,lastResult:938}],
  exportAudit:{adapterVersion:2,searchQuery:query,sourceTotalResults:938,distinctPublications:938,
    nativeRecords:938,canonicalRows:2333,canonicalSha256:'a'.repeat(64),sourceManifestSha256:'b'.repeat(64),
    exportComplete:true,issues:[],missingSequenceNumbers:[],batches}};
const clone=x=>JSON.parse(JSON.stringify(x));
function compare(change=()=>{},inputRows=rows){const m=clone(metadata);change(m);return core.compare(inputRows,baseline,m,profile);}
let report=compare();
assert.equal(report.counts.anomalies,0);assert.equal(report.counts.firstStatusObservations,938);
assert.equal(report.counts.stateChanges,0);assert.equal(report.counts.legalEvents,2333);
assert.equal(report.coverage.resultPageCount,47);assert.equal(report.coverage.downloadedExportBatches,10);
assert.equal(report.coverage.allResultPagesVisited,false,'full export must not assert 47 list pages were visited');
assert.equal(report.coverage.sampledResultPages.length,2);
assert.equal(report.coverage.physicalSourceRecords,938);
assert.equal(report.coverage.expandedImportRows,2333);
assert.equal(report.legalEvents.at(-1).evidence.originalSource.batchRange,'901-938');
assert.equal(report.legalEvents.at(-1).evidence.originalSource.fileSha256,batches[9].sha256);
assert.equal(report.legalEvents.at(-1).evidence.originalSource.excelRow,'39');
const snapshot=core.makeSnapshot(report,true);
assert.equal(compare(()=>{},rows).runState,'review-required');
assert.equal(core.compare(rows,baseline,metadata,profile,snapshot).runState,'no-difference-in-complete-export');
const invalidCases=[
  ['missing batch',m=>{m.exportAudit.batches.pop();m.downloadedExportBatches=9;}],
  ['overlap',m=>{m.exportAudit.batches[1].range='1-100';}],
  ['missing hash',m=>{delete m.exportAudit.batches[0].sha256;}],
  ['duplicate file',m=>{m.exportAudit.batches[1].sha256=m.exportAudit.batches[0].sha256;}],
  ['wrong query',m=>{m.exportAudit.batches[0].downloadIntroduction['下载内容']='different';}],
  ['CSV hash mismatch',m=>{m.exportAudit.canonicalSha256='c'.repeat(64);}],
  ['event expansion mismatch',m=>{m.exportAudit.canonicalRows=938;}],
  ['source count mismatch',m=>{m.exportAudit.sourceTotalResults=2333;}],
  ['audit issues',m=>{m.exportAudit.issues.push({type:'missing-batch'});}],
  ['incomplete adaptation',m=>{m.exportAudit.exportComplete=false;}],
  ['record count uses event rows',m=>{m.exportAudit.batches[0].physicalDataRows=300;}],
  ['list pages confused with export batches',m=>{m.resultPageCount=10;}],
  ['invalid sampled page',m=>{m.sampledResultPages=[48];}],
  ['invalid visited page',m=>{m.visitedResultPages=[1,1];}],
  ['login expired',m=>{m.loginStatus='expired';}],
  ['not complete',m=>{m.exportComplete=false;}],
  ['wrong raw/native audit',m=>{m.xlsxInfo={issues:[{reason:'bad native intro'}]};}],
  ['native query mismatch',m=>{m.xlsxInfo={nativeFormat:true,sourceSearchQuery:'another query'};}],
  ['null adaptation',m=>{m.exportAudit=null;}],
  ['null batch entry',m=>{m.exportAudit.batches[0]=null;}],
  ['unsupported schema',m=>{m.coverageSchemaVersion=3;}],
  ['explicit batch/audit conflict',m=>{m.exportBatches=clone(batches);m.exportBatches[0].sha256='d'.repeat(64);}],
];
for(const [name,change] of invalidCases){
  report=compare(change);assert.equal(report.runState,'exception-review-required',name);
  assert.ok(report.counts.anomalies>0,name);assert.throws(()=>core.makeSnapshot(report,true),undefined,name);
}
const altered=clone(rows);altered[0].sourceFileSha256='e'.repeat(64);
assert.equal(compare(()=>{},altered).runState,'exception-review-required','original row must match declared batch provenance');
const legacy=clone(metadata);
for(const key of ['coverageSchemaVersion','resultPageCount','resultPageSize','expectedExportBatches','downloadedExportBatches','sampledResultPages','exportAudit'])delete legacy[key];
legacy.expectedPages=10;legacy.downloadedPages=10;
report=core.compare(rows,baseline,legacy,profile);
assert.equal(report.counts.anomalies,0);assert.equal(report.coverage.mode,'legacy-unspecified-page-count');
assert.equal(report.coverage.resultPageCount,null);assert.equal(report.coverage.allResultPagesVisited,false);
assert.ok(report.coverage.warnings.length);
console.log('PASS: 938 publications / 2333 events / 47 result pages / 10 export batches; 22 incomplete/conflicting coverage cases, legacy and provenance guards');
