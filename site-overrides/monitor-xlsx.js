/* Bounded, local-only XLSX reader. No dependencies, scripts, formulas or external fetches. */
(function(root){
 'use strict';
 const LIMIT={archive:40*1024*1024,expanded:80*1024*1024,entry:20*1024*1024,entries:2048,rows:50000,columns:512,cell:1024*1024,ratio:400};
 const fallback='请导出单工作表 CSV，或使用随附 Python/openpyxl 导入命令。';
 function fail(message){throw Error('XLSX：'+message+' '+fallback);}
 const utf8=new TextDecoder('utf-8',{fatal:true});
 const crcTable=Uint32Array.from({length:256},(_,n)=>{let c=n;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;return c>>>0;});
 function crc32(bytes){let crc=0xffffffff;for(const b of bytes)crc=crcTable[(crc^b)&255]^(crc>>>8);return (crc^0xffffffff)>>>0;}
 function xml(text,name){
  if(/<!DOCTYPE|<!ENTITY/i.test(text))fail(name+' 含不允许的 XML 实体声明');
  const doc=new DOMParser().parseFromString(text,'application/xml');
  if(doc.querySelector('parsererror'))fail(name+' XML 损坏');
  return doc;
 }
 const elements=(node,name)=>Array.from(node.getElementsByTagNameNS('*',name));
 function normalizePath(base,target){
  if(!target||/^[a-z]+:/i.test(target)||target.includes('\\'))fail('工作表关系路径不受支持');
  const stack=target.startsWith('/')?[]:base.split('/').slice(0,-1);
  for(const part of target.replace(/^\//,'').split('/')){
   if(!part||part==='.')continue;
   if(part==='..'){if(!stack.length)fail('工作表关系超出包目录');stack.pop();}else stack.push(part);
  }
  return stack.join('/');
 }
 async function openZip(buffer){
  if(!(buffer instanceof ArrayBuffer))fail('需要 ArrayBuffer 文件内容');
  if(buffer.byteLength>LIMIT.archive||buffer.byteLength<22)fail('文件大小无效或超过 40 MiB 限制');
  const bytes=new Uint8Array(buffer),view=new DataView(buffer);
  let end=-1;
  for(let i=bytes.length-22;i>=Math.max(0,bytes.length-65557);i--){if(view.getUint32(i,true)===0x06054b50&&i+22+view.getUint16(i+20,true)===bytes.length){end=i;break;}}
  if(end<0)fail('ZIP 目录缺失，文件可能未完整下载或不是 XLSX');
  const count=view.getUint16(end+10,true),size=view.getUint32(end+12,true),offset=view.getUint32(end+16,true);
  if(view.getUint16(end+4,true)||view.getUint16(end+6,true)||view.getUint16(end+8,true)!==count)fail('不支持分卷 ZIP');
  if(count===65535||size===0xffffffff||offset===0xffffffff)fail('不支持 ZIP64');
  if(count>LIMIT.entries||offset+size!==end)fail('ZIP 目录数量或范围不合法');
  const files=new Map();let cursor=offset,total=0;
  for(let i=0;i<count;i++){
   if(cursor+46>end||view.getUint32(cursor,true)!==0x02014b50)fail('ZIP 目录损坏');
   const flags=view.getUint16(cursor+8,true),method=view.getUint16(cursor+10,true),crc=view.getUint32(cursor+16,true);
   const packed=view.getUint32(cursor+20,true),unpacked=view.getUint32(cursor+24,true);
   const names=view.getUint16(cursor+28,true),extra=view.getUint16(cursor+30,true),comment=view.getUint16(cursor+32,true),disk=view.getUint16(cursor+34,true);
   const attributes=view.getUint32(cursor+38,true),local=view.getUint32(cursor+42,true),next=cursor+46+names+extra+comment;
   if(next>end||disk||flags&1||flags&0x40)fail('ZIP 条目损坏或已加密');
   if(method!==0&&method!==8)fail('不支持的 ZIP 压缩方式 '+method);
   if(packed===0xffffffff||unpacked===0xffffffff||local===0xffffffff)fail('不支持 ZIP64 条目');
   if(unpacked>LIMIT.entry||(total+=unpacked)>LIMIT.expanded||unpacked>Math.max(1,packed)*LIMIT.ratio)fail('解压大小或压缩率超出安全上限');
   let name;try{name=utf8.decode(bytes.subarray(cursor+46,cursor+46+names));}catch{fail('ZIP 文件名不是可识别的 UTF-8');}
   if(!name||name.startsWith('/')||name.includes('\\')||name.split('/').includes('..')||files.has(name)||(attributes>>>16&0xf000)===0xa000)fail('ZIP 包含重复或不安全路径');
   if(/(?:^|\/)vbaProject\.bin$/i.test(name))fail('宏工作簿不受支持');
   if(local+30>offset||view.getUint32(local,true)!==0x04034b50)fail('ZIP 本地条目缺失');
   const localFlags=view.getUint16(local+6,true),localMethod=view.getUint16(local+8,true),localNames=view.getUint16(local+26,true),localExtra=view.getUint16(local+28,true);
   const start=local+30+localNames+localExtra;
   if(localFlags!==flags||localMethod!==method||start+packed>offset||start<local)fail('ZIP 条目范围或压缩信息冲突');
   let localName;try{localName=utf8.decode(bytes.subarray(local+30,local+30+localNames));}catch{fail('ZIP 本地文件名无效');}
   if(localName!==name)fail('ZIP 文件名不一致');
   files.set(name,{method,crc,packed,unpacked,start});cursor=next;
  }
  if(cursor!==end)fail('ZIP 目录长度不一致');
  const cache=new Map();
  async function get(name,required=true){
   if(cache.has(name))return cache.get(name);
   const entry=files.get(name);if(!entry){if(required)fail('缺少 '+name);return null;}
   let data=bytes.subarray(entry.start,entry.start+entry.packed);
   if(entry.method===8){
    if(typeof DecompressionStream!=='function')fail('此浏览器缺少原生解压能力');
    let decompressor;try{decompressor=new DecompressionStream('deflate-raw');}catch{fail('此浏览器不支持 deflate-raw 解压');}
    // Read incrementally so a forged ZIP size cannot allocate an unbounded buffer.
    const stream=new Blob([data]).stream().pipeThrough(decompressor).getReader(),chunks=[];let length=0;
    try{for(;;){const item=await stream.read();if(item.done)break;length+=item.value.byteLength;if(length>entry.unpacked||length>LIMIT.entry){await stream.cancel();fail('实际解压大小超过声明值');}chunks.push(item.value);}}catch(e){if(String(e.message).startsWith('XLSX：'))throw e;fail('无法解压 '+name);}
    data=new Uint8Array(length);let position=0;for(const chunk of chunks){data.set(chunk,position);position+=chunk.length;}
   }
   if(data.length!==entry.unpacked||crc32(data)!==entry.crc)fail(name+' 的大小或 CRC 校验失败');
   let text;try{text=utf8.decode(data);}catch{fail(name+' 不是有效的 UTF-8 XML');}
   cache.set(name,text);return text;
  }
  return {get,files};
 }
 function columnIndex(ref){
  const match=/^([A-Z]+)([1-9]\d*)$/i.exec(ref||'');if(!match)fail('单元格引用无效');
  let index=0;for(const c of match[1].toUpperCase())index=index*26+c.charCodeAt(0)-64;
  if(index>LIMIT.columns||Number(match[2])>LIMIT.rows+1)fail('行列范围超限');
  return {column:index-1,row:Number(match[2])};
 }
 function dateSerial(value,date1904,hasTime){
  const serial=Number(value);if(!Number.isFinite(serial)||serial<0||serial>2958465)fail('Excel 日期数值无效');
  const whole=Math.floor(serial);if(!date1904&&whole===60)fail('Excel 1900-02-29 虚构日期不能可靠转换');
  const epoch=date1904?Date.UTC(1904,0,1):Date.UTC(1899,11,whole<60?31:30);
  const stamp=epoch+Math.round(serial*86400000),date=new Date(stamp);
  // Excel date cells contain wall time only; do not invent a UTC offset.
  return hasTime?date.toISOString().replace(/\.000Z$/,'').replace(/Z$/,''):date.toISOString().slice(0,10);
 }
 function styleFormats(doc){
  if(!doc)return [];
  const custom=new Map(elements(doc,'numFmt').map(node=>[Number(node.getAttribute('numFmtId')),node.getAttribute('formatCode')||'']));
  const cellXfs=elements(doc,'cellXfs')[0];if(!cellXfs)return [];
  return Array.from(cellXfs.children).filter(x=>x.localName==='xf').map(node=>{
   const id=Number(node.getAttribute('numFmtId')||0),raw=custom.get(id)||'',format=raw.replace(/"[^"]*"|\\.|\[[^\]]*\]/g,'');
   const date=(id>=14&&id<=22)||(id>=27&&id<=36)||(id>=45&&id<=47)||(id>=50&&id<=58)||(/[ymdhis]/i.test(format)&&!/[0#?].*[eE][+-]/.test(format));
   return {date,time:(id>=18&&id<=22)||(id>=45&&id<=47)||/[his]/i.test(format)};
  });
 }
 function canonicalHeader(value){return String(value||'').trim().replace(/[\s\u00a0\u3000]/g,'').replace(/\(/g,'（').replace(/\)/g,'）');}
 function validDate(value){
  const match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(value||'');if(!match)return false;
  const date=new Date(Date.UTC(Number(match[1]),Number(match[2])-1,Number(match[3])));
  return date.toISOString().slice(0,10)===value;
 }
 function parseLegalHistory(value){
  const raw=String(value||'').replace(/\r\n?/g,'\n');if(!raw.trim())return [];
  const pattern=/#法律状态公告日[：:]\s*(\d{8})[;；]/g,matches=Array.from(raw.matchAll(pattern));
  if(!matches.length||raw.slice(0,matches[0].index).trim())fail('法律历史不符合已核实的带日期 Incopat 格式，未猜测拆分');
  return matches.map((match,index)=>{
   const date=match[1].slice(0,4)+'-'+match[1].slice(4,6)+'-'+match[1].slice(6,8);
   if(!validDate(date))fail('法律历史包含无效公告日期');
   const start=match.index+match[0].length,end=index+1<matches.length?matches[index+1].index:raw.length,chunk=raw.slice(start,end);
   const event=/^\s*法律状态[：:]\s*([^\n]*?)[;；]\s*(?:\n|$)/.exec(chunk);
   const description=/(?:^|\n)\s*描述信息[：:]\s*([\s\S]*?)\s*$/.exec(chunk);
   if(!event||!event[1].trim()||!description)fail('带日期法律历史缺少事件或描述信息，未返回部分结果');
   return {event:event[1].trim(),eventDate:date,description:description[1],sourceBlock:raw.slice(match.index,end)};
  });
 }
 function nativeDate(cell,date1904){
  if(!cell?.text)return '';
  if(cell.numeric&&!cell.dateFormatted)return dateSerial(cell.text,date1904,false);
  const value=cell.text.trim();
  const date=/^\d{8}$/.test(value)?value.slice(0,4)+'-'+value.slice(4,6)+'-'+value.slice(6,8):value.replace(/(?: 00:00:00|T00:00:00)$/,'');
  if(!validDate(date))fail('原生公开（公告）日无法可靠转换');return date;
 }
 async function read(buffer){
  const zip=await openZip(buffer);
  const types=await zip.get('[Content_Types].xml');if(/macroEnabled|vbaProject/i.test(types))fail('宏工作簿不受支持');
  const workbookPath='xl/workbook.xml',workbook=xml(await zip.get(workbookPath),workbookPath);
  const relationships=xml(await zip.get('xl/_rels/workbook.xml.rels'),'workbook.xml.rels');
  const relations=new Map();
  for(const node of elements(relationships,'Relationship')){const id=node.getAttribute('Id');if(!id||relations.has(id))fail('工作簿关系标识缺失或重复');relations.set(id,node);}
  const sheets=elements(workbook,'sheet').map(node=>{
   const id=node.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships','id')||node.getAttribute('r:id'),rel=relations.get(id);
   if(!rel||!/\/worksheet$/.test(rel.getAttribute('Type')||''))return null;
   if(rel.getAttribute('TargetMode')==='External')fail('不允许外部工作表');
   return {name:node.getAttribute('name')||'未命名',state:node.getAttribute('state')||'visible',path:normalizePath(workbookPath,rel.getAttribute('Target'))};
  }).filter(Boolean);
  if(!sheets.length)fail('没有可读取的数据工作表');
  if(sheets.length>32)fail('工作表数量超过 32，无法可靠确认完整覆盖');
  if(new Set(sheets.map(s=>s.name)).size!==sheets.length||new Set(sheets.map(s=>s.path)).size!==sheets.length)fail('工作表名称或关系路径重复');
  const sharedRel=elements(relationships,'Relationship').find(x=>/\/sharedStrings$/.test(x.getAttribute('Type')||''));
  const sharedPath=sharedRel?normalizePath(workbookPath,sharedRel.getAttribute('Target')):'xl/sharedStrings.xml';
  const sharedXML=await zip.get(sharedPath,false),shared=sharedXML?elements(xml(sharedXML,sharedPath),'si').map(si=>elements(si,'t').map(t=>t.textContent||'').join('')):[];
  if(shared.some(value=>value.length>LIMIT.cell))fail('共享文字长度超限');
  const stylesRel=elements(relationships,'Relationship').find(x=>/\/styles$/.test(x.getAttribute('Type')||''));
  const stylesPath=stylesRel?normalizePath(workbookPath,stylesRel.getAttribute('Target')):'xl/styles.xml',stylesXML=await zip.get(stylesPath,false);
  const formats=styleFormats(stylesXML?xml(stylesXML,stylesPath):null);
  const date1904=['1','true'].includes(elements(workbook,'workbookPr')[0]?.getAttribute('date1904'));
  async function physicalSheet(candidate){
   const doc=xml(await zip.get(candidate.path),candidate.path),sheetData=elements(doc,'sheetData')[0],links=new Map();
   const parts=candidate.path.split('/'),filename=parts.pop(),relsPath=parts.join('/')+'/_rels/'+filename+'.rels';
   const relXML=await zip.get(relsPath,false),linkRelations=new Map();
   if(relXML)for(const relation of elements(xml(relXML,relsPath),'Relationship')){
    const id=relation.getAttribute('Id');if(!id||linkRelations.has(id))fail('工作表关系标识缺失或重复');linkRelations.set(id,relation);
   }
   for(const link of elements(doc,'hyperlink')){
    const ref=link.getAttribute('ref'),id=link.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships','id')||link.getAttribute('r:id');
    if(!id)continue;
    columnIndex(ref);if(links.has(ref))fail('同一单元格存在重复超链接');
    const relation=linkRelations.get(id);if(!relation||!/\/hyperlink$/.test(relation.getAttribute('Type')||''))fail('超链接关系缺失或类型错误');
    const target=relation.getAttribute('Target')||'';
    if(!/^https?:\/\//i.test(target)||target.length>LIMIT.cell)fail('超链接不是可保留的 HTTP 来源地址');
    try{const url=new URL(target);if(url.username||url.password)fail('超链接含用户凭据，拒绝导入');}catch(error){if(String(error.message).startsWith('XLSX：'))throw error;fail('超链接地址不合法');}
    links.set(ref,target);
   }
   const rows=[];let maxColumns=0,previousRow=0;
   for(const row of sheetData?Array.from(sheetData.children).filter(x=>x.localName==='row'):[]){
    const cells=[];let rowNumber=null;
    for(const cell of Array.from(row.children).filter(x=>x.localName==='c')){
     const coordinate=cell.getAttribute('r'),ref=columnIndex(coordinate);if(rowNumber!==null&&rowNumber!==ref.row)fail('单元格所在行不一致');rowNumber=ref.row;
     if(cells[ref.column]!==undefined)fail('重复单元格坐标');
     if(elements(cell,'f').length)fail('含公式单元格，未执行或采信公式缓存');
     const type=cell.getAttribute('t')||'n',value=elements(cell,'v')[0]?.textContent||'';
     let text='',numeric=false,dateFormatted=false;
     if(type==='s'){const n=Number(value);if(!/^\d+$/.test(value)||!Number.isInteger(n)||n<0||n>=shared.length)fail('共享文字引用无效');text=shared[n];}
     else if(type==='inlineStr')text=elements(cell,'t').map(t=>t.textContent||'').join('');
     else if(type==='str'||type==='d')text=value;
     else if(type==='b')text=value==='1'?'TRUE':'FALSE';
     else if(type==='e')fail('单元格包含 Excel 错误 '+value);
     else if(type==='n'){
      const style=Number(cell.getAttribute('s')||0),format=formats[style];
      if(value&&!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value))fail('数值单元格格式损坏');
      numeric=!!value;if(value&&format?.date){text=dateSerial(value,date1904,format.time);dateFormatted=true;}else text=value;
     }else fail('不支持单元格类型 '+type);
     if(text.length>LIMIT.cell)fail('单元格文字超限');
     cells[ref.column]={text,numeric,type,originalValue:value,dateFormatted,coordinate,hyperlink:links.get(coordinate)||''};maxColumns=Math.max(maxColumns,ref.column+1);
    }
    const declared=Number(row.getAttribute('r'));
    if(!Number.isInteger(declared)||declared<1||(rowNumber!==null&&declared!==rowNumber)||declared<=previousRow)fail('物理工作表行号缺失、重复或不按顺序');
    previousRow=declared;
    if(cells.some(c=>c?.text.trim()))rows.push({rowNumber:declared,cells});
    if(rows.length>LIMIT.rows+1)fail('有效数据行数超过 50000');
   }
   return {...candidate,rows,maxColumns,declaredDimension:elements(doc,'dimension')[0]?.getAttribute('ref')||null};
  }
  const parsedSheets=[];for(const candidate of sheets)parsedSheets.push(await physicalSheet(candidate));
  const populated=parsedSheets.filter(sheet=>sheet.rows.length);
  if(!populated.length)fail('没有非空数据工作表');
  const nativeSheets=populated.filter(sheet=>/^下载的著录项\d*$/.test(sheet.name));
  const nativeFormat=nativeSheets.length>0;
  let selectedSheet,introduction=null;
  if(nativeFormat){
   if(nativeSheets.length!==1)fail('存在多个原生著录项工作表，须分开导出并记录各表覆盖范围');
   const extra=populated.filter(sheet=>sheet!==nativeSheets[0]&&sheet.name!=='下载简介');
   if(extra.length)fail('包含未确认的数据工作表（'+extra.map(sheet=>sheet.name).join('、')+'），不能静默忽略');
   selectedSheet=nativeSheets[0];introduction=populated.find(sheet=>sheet.name==='下载简介')||null;
  }else{
   if(populated.length!==1)fail('包含多个非空数据工作表（'+populated.map(sheet=>sheet.name).join('、')+'），不能静默忽略其他表');
   selectedSheet=populated[0];
  }
  if(selectedSheet.state!=='visible')fail('数据工作表处于隐藏状态，不能自动确认导出范围');
  const first=selectedSheet.rows[0],header=first.cells,headers=Array.from({length:selectedSheet.maxColumns},(_,n)=>header[n]?.text.trim()||'');
  while(headers.length&&!headers.at(-1))headers.pop();
  const comparable=nativeFormat?headers.map(canonicalHeader):headers;
  if(!headers.length||headers.some(h=>!h)||new Set(comparable).size!==headers.length)fail('表头缺失、存在空列或重复列');
  const publicationHeaders=['publicationNumber','id','公开（公告）号','公开(公告)号','公开公告号','公开号','公告号'];
  const applicationHeaders=['applicationNumber','申请号','申请（专利）号','申请(专利)号'];
  if(nativeFormat){
   if(!['公开（公告）号','申请号','申请人','当前法律状态'].every(h=>comparable.includes(h)))fail('原生 Incopat XLSX 缺少完整公开号、申请号、申请人或当前法律状态必需表头');
  }else if(!publicationHeaders.some(h=>headers.includes(h))||!applicationHeaders.some(h=>headers.includes(h)))fail('缺少完整公开号或申请号必需表头，不能确认导出范围');
  const idColumns=comparable.map(h=>/^(?:publicationNumber|applicationNumber|id|申请号|申请[（(]专利[）)]号|公开[（(]公告[）)]号|公开公告号|公开号|公告号|专利号)$/i.test(h));
  const dataRows=selectedSheet.rows.slice(1),rawRecords=[],result=[],issues=[],sourceSequences=[];let outputBytes=0;
  const introRows=introduction?introduction.rows.map(row=>({sourceExcelRow:row.rowNumber,values:Array.from({length:introduction.maxColumns},(_,i)=>row.cells[i]?.text||'')})):[];
  const intro=Object.create(null);for(const row of introRows){
   const key=row.values[0]?.trim();
   if(!key||row.values.slice(2).some(value=>value.trim()))fail('下载简介不是已知的两列键值辅助表，不能静默忽略其中的数据');
   if(Object.hasOwn(intro,key))fail('下载简介键重复，无法可靠确认覆盖');intro[key]=row.values[1]||'';
  }
  if(introduction&&!['下载内容','数据范围','数量'].every(key=>Object.hasOwn(intro,key)))fail('下载简介缺少已知来源键，不能自动当作辅助表忽略');
  let digest=null;
  if(globalThis.crypto?.subtle)digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),value=>value.toString(16).padStart(2,'0')).join('');
  else if(nativeFormat)fail('原生导出审计需要 HTTPS 或 localhost 的浏览器校验能力');
  const sourceRange=String(intro['数据范围']||'').trim(),rangeMatch=/^([1-9]\d*)-([1-9]\d*)$/.exec(sourceRange);
  const sourceSearchQuery=String(intro['下载内容']||'');
  const countText=String(intro['数量']||'').trim(),sourceCount=/^\d+(?:\.0+)?$/.test(countText)?Number(countText):null;
  if(nativeFormat){
   if(!introduction)issues.push({type:'introduction-missing',reason:'缺少下载简介；无法自动确认本文件的查询式、范围与数量'});
   if(!sourceSearchQuery.trim())issues.push({type:'source-query',reason:'下载简介缺少实际检索式'});
   if(!rangeMatch||Number(rangeMatch[2])<Number(rangeMatch[1]))issues.push({type:'source-range',reason:'下载简介批次范围缺失或无效'});
   if(sourceCount===null||sourceCount!==dataRows.length)issues.push({type:'source-count',reason:'下载简介数量与原始物理记录数不一致'});
   if(rangeMatch&&Number(rangeMatch[2])-Number(rangeMatch[1])+1!==dataRows.length)issues.push({type:'source-range-count',reason:'批次范围数量与原始物理记录数不一致'});
  }
  for(const source of dataRows){
   const row=source.cells;
   if(row.some((c,i)=>i>=headers.length&&c?.text.trim()))fail('第 '+source.rowNumber+' 行超出表头列数');
   const raw=Object.fromEntries(headers.map((h,n)=>{
    if(idColumns[n]&&row[n]?.numeric)fail('第 '+source.rowNumber+' 行编号列为数值，可能丢失前缀、前导零或精度，必须按文本导出');
    return [h,row[n]?.text||''];
   }));
   if(!nativeFormat){
    if(Object.values(raw).some(value=>/#法律状态公告日[：:]/.test(value)))fail('发现带日期的原生法律历史，但工作表未识别为原生导出；请恢复著录项工作表名称或使用规范 CSV，不能静默略过历史拆分');
    result.push(raw);continue;
   }
   if(Object.values(raw).some(value=>value.trimStart().startsWith('=')))fail('原生文件含公式样式文本，须提供纯值');
   const byHeader=Object.fromEntries(comparable.map((h,n)=>[h,row[n]||{text:''}])),get=name=>byHeader[canonicalHeader(name)]?.text||'';
   const pub=get('公开（公告）号').replace(/\s/g,'').toUpperCase(),app=get('申请号').replace(/\s/g,'').toUpperCase();
   if(!/^CN\d{9}[ABUS]\d?$/.test(pub)||!/^CN\d{8,13}(?:\.[0-9X])?$/.test(app))fail('第 '+source.rowNumber+' 行完整公开号或申请号无法确认');
   const numberText=get('序号').trim(),number=/^\d+(?:\.0+)?$/.test(numberText)?Number(numberText):null;
   if(!Number.isSafeInteger(number)||!rangeMatch||number<Number(rangeMatch[1])||number>Number(rangeMatch[2]))issues.push({type:'source-sequence',row:source.rowNumber,reason:'原始序号缺失或不在已确认批次范围内'});else sourceSequences.push(number);
   const cells=Object.fromEntries(headers.map((h,n)=>[h,row[n]?{...row[n]}:{text:''}]));
   const rawIndex=rawRecords.length;rawRecords.push({sourceExcelRow:source.rowNumber,sourceSheet:selectedSheet.name,rawFields:raw,cells});
   const history=get('法律状态'),events=parseLegalHistory(history);
   const common={'公开（公告）号':pub,'申请号':app,'申请人':get('申请人'),'当前法律状态':get('当前法律状态'),
    publicationNumber:pub,applicationNumber:app,title:get('标题（中文）')||get('标题'),applicants:get('申请人'),
    legalStatus:get('当前法律状态'),publicationDate:nativeDate(byHeader['公开（公告）日'],date1904),
    familyId:get('简单同族ID')||get('同族ID'),evidenceUrl:byHeader['链接到incoPat']?.hyperlink||byHeader['链接到incopat']?.hyperlink||get('证据链接'),
    sourceFileSha256:digest,sourceSheet:selectedSheet.name,sourceExcelRow:source.rowNumber,
    sourceRawRecordIndex:rawIndex,sourceRecordNumber:numberText,sourceBatchRange:sourceRange};
   for(const [i,event] of (events.length?events:[null]).entries()){
    const item={...common,legalEvent:event?.event||get('法律事件'),eventDate:event?.eventDate||'',legalEventDescription:event?.description||'',sourceEventIndex:events.length?i+1:''};
    outputBytes+=new TextEncoder().encode(JSON.stringify(item)).byteLength;
    if(outputBytes>LIMIT.expanded)fail('展开后的规范记录超过 80 MiB，请使用本地命令保留完整资料');
    result.push(item);
    if(result.length>LIMIT.rows)fail('展开后法律事件行数超过 50000，请使用本地命令处理完整批次');
   }
  }
  if(nativeFormat&&new Set(sourceSequences).size!==sourceSequences.length)issues.push({type:'duplicate-sequences',reason:'原始记录序号重复'});
  if(nativeFormat&&new Set(rawRecords.map(record=>String(record.rawFields[headers[comparable.indexOf('公开（公告）号')]]).replace(/\s/g,'').toUpperCase())).size!==rawRecords.length)issues.push({type:'duplicate-publications',reason:'同一文件有重复原始文献记录'});
  const info={schemaVersion:2,sheet:selectedSheet.name,worksheet:selectedSheet.name,
   otherVisibleWorksheets:sheets.filter(sheet=>sheet.state==='visible'&&sheet.name!==selectedSheet.name).map(sheet=>sheet.name),
   nonEmptyDataSheets:1,rowCount:result.length,headers,dateTimezone:'Excel 日期／时间无时区；未推断 UTC 偏移',
   nativeFormat,declaredDimension:selectedSheet.declaredDimension,physicalXmlRowsUsed:true,
   worksheetRows:dataRows.length,physicalDataRows:dataRows.length,expandedEventRows:result.length,
   sourceFileSha256:digest,sha256:digest,bytes:buffer.byteLength,sourceRange,sourceSearchQuery,sourceCount,
   sourceSequences,downloadIntroduction:intro,downloadIntroductionRows:introRows,
   ignoredIntroductionSheet:!!introduction,rawRecords,issues,
   fileIntegrityVerified:!!digest,sourceCoverageVerified:nativeFormat&&issues.length===0,sourceVerified:nativeFormat&&issues.length===0,
   notice:nativeFormat?'仅解析和保留本地原始导出，未核验法律状态或自动完成覆盖复核。':'普通单表按原有字段读取；未执行外部链接或公式。'};
  Object.defineProperty(result,'xlsxInfo',{value:info,enumerable:false});return result;
 }
 root.MonitorXlsx={read,limits:Object.freeze({...LIMIT})};
})(typeof globalThis==='object'?globalThis:this);
