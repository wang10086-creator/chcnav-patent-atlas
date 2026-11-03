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
 async function read(buffer){
  const zip=await openZip(buffer);
  const types=await zip.get('[Content_Types].xml');if(/macroEnabled|vbaProject/i.test(types))fail('宏工作簿不受支持');
  const workbookPath='xl/workbook.xml',workbook=xml(await zip.get(workbookPath),workbookPath);
  const relationships=xml(await zip.get('xl/_rels/workbook.xml.rels'),'workbook.xml.rels');
  const relations=new Map(elements(relationships,'Relationship').map(node=>[node.getAttribute('Id'),node]));
  const sheets=elements(workbook,'sheet').filter(node=>node.getAttribute('state')!=='hidden'&&node.getAttribute('state')!=='veryHidden').map(node=>{
   const id=node.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships','id')||node.getAttribute('r:id'),rel=relations.get(id);
   if(!rel||!/\/worksheet$/.test(rel.getAttribute('Type')||''))return null;
   if(rel.getAttribute('TargetMode')==='External')fail('不允许外部工作表');
   return {name:node.getAttribute('name')||'未命名',path:normalizePath(workbookPath,rel.getAttribute('Target'))};
  }).filter(Boolean);
  if(!sheets.length)fail('没有可读取的可见数据工作表');
  if(sheets.length>32)fail('工作表数量超过 32，无法可靠确认完整覆盖');
  const dataSheets=[];
  for(const candidate of sheets){
   const doc=xml(await zip.get(candidate.path),candidate.path),data=elements(doc,'sheetData')[0];
   if(data&&elements(data,'c').some(cell=>cell.textContent.trim()||elements(cell,'f').length))dataSheets.push({...candidate,doc});
  }
  if(!dataSheets.length)fail('没有非空数据工作表');
  if(dataSheets.length>1)fail('包含多个非空数据工作表（'+dataSheets.map(s=>s.name).join('、')+'），不能静默忽略其他表');
  const selectedSheet=dataSheets[0];
  const sharedRel=elements(relationships,'Relationship').find(x=>/\/sharedStrings$/.test(x.getAttribute('Type')||''));
  const sharedPath=sharedRel?normalizePath(workbookPath,sharedRel.getAttribute('Target')):'xl/sharedStrings.xml';
  const sharedXML=await zip.get(sharedPath,false),shared=sharedXML?elements(xml(sharedXML,sharedPath),'si').map(si=>elements(si,'t').map(t=>t.textContent||'').join('')):[];
  if(shared.some(value=>value.length>LIMIT.cell))fail('共享文字长度超限');
  const stylesRel=elements(relationships,'Relationship').find(x=>/\/styles$/.test(x.getAttribute('Type')||''));
  const stylesPath=stylesRel?normalizePath(workbookPath,stylesRel.getAttribute('Target')):'xl/styles.xml',stylesXML=await zip.get(stylesPath,false);
  const formats=styleFormats(stylesXML?xml(stylesXML,stylesPath):null);
  const date1904=['1','true'].includes(elements(workbook,'workbookPr')[0]?.getAttribute('date1904'));
  const sheet=selectedSheet.doc,sheetData=elements(sheet,'sheetData')[0];
  if(!sheetData)fail('工作表缺少数据区域');
  const rows=[];let maxColumns=0;
  for(const row of Array.from(sheetData.children).filter(x=>x.localName==='row')){
   const cells=[];let rowNumber=null;
   for(const cell of Array.from(row.children).filter(x=>x.localName==='c')){
    const ref=columnIndex(cell.getAttribute('r'));if(rowNumber!==null&&rowNumber!==ref.row)fail('单元格所在行不一致');rowNumber=ref.row;
    if(cells[ref.column]!==undefined)fail('重复单元格坐标');
    if(elements(cell,'f').length)fail('含公式单元格，未执行或采信公式缓存');
    const type=cell.getAttribute('t')||'n',value=elements(cell,'v')[0]?.textContent||'';
    let text='',numeric=false;
    if(type==='s'){const n=Number(value);if(!Number.isInteger(n)||n<0||n>=shared.length)fail('共享文字引用无效');text=shared[n];}
    else if(type==='inlineStr')text=elements(cell,'t').map(t=>t.textContent||'').join('');
    else if(type==='str'||type==='d')text=value;
    else if(type==='b')text=value==='1'?'TRUE':'FALSE';
    else if(type==='e')fail('单元格包含 Excel 错误 '+value);
    else if(type==='n'){
     const style=Number(cell.getAttribute('s')||0),format=formats[style];
     if(value&&!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value))fail('数值单元格格式损坏');
     numeric=!!value;if(value&&format?.date)text=dateSerial(value,date1904,format.time);else text=value;
    }else fail('不支持单元格类型 '+type);
    if(text.length>LIMIT.cell)fail('单元格文字超限');cells[ref.column]={text,numeric};maxColumns=Math.max(maxColumns,ref.column+1);
   }
   if(cells.some(c=>c?.text.trim()))rows.push(cells);
   if(rows.length>LIMIT.rows+1)fail('有效数据行数超过 50000');
  }
  if(!rows.length)fail('数据工作表为空');
  const header=rows.shift(),headers=Array.from({length:maxColumns},(_,n)=>header[n]?.text.trim()||'');
  while(headers.length&&!headers.at(-1))headers.pop();
  if(!headers.length||headers.some(h=>!h)||new Set(headers).size!==headers.length)fail('表头缺失、存在空列或重复列');
  const publicationHeaders=['publicationNumber','id','公开（公告）号','公开(公告)号','公开公告号','公开号','公告号'];
  const applicationHeaders=['applicationNumber','申请号','申请（专利）号','申请(专利)号'];
  if(!publicationHeaders.some(h=>headers.includes(h))||!applicationHeaders.some(h=>headers.includes(h)))fail('缺少完整公开号或申请号必需表头，不能确认导出范围');
  const idColumns=headers.map(h=>/^(?:publicationNumber|applicationNumber|id|申请号|申请[（(]专利[）)]号|公开[（(]公告[）)]号|公开公告号|公开号|公告号|专利号)$/i.test(h));
  const records=rows.map((row,index)=>{
   if(row.some((c,i)=>i>=headers.length&&c?.text.trim()))fail('第 '+(index+2)+' 行超出表头列数');
   return Object.fromEntries(headers.map((h,n)=>{
    if(idColumns[n]&&row[n]?.numeric)fail('第 '+(index+2)+' 行编号列为数值，可能丢失前缀、前导零或精度，必须按文本导出');
    return [h,row[n]?.text||''];
   }));
  });
  Object.defineProperty(records,'xlsxInfo',{value:{sheet:selectedSheet.name,otherVisibleWorksheets:sheets.filter(s=>s.name!==selectedSheet.name).map(s=>s.name),nonEmptyDataSheets:1,rowCount:records.length,headers,dateTimezone:'Excel 日期／时间无时区；未推断 UTC 偏移'},enumerable:false});
  return records;
 }
 root.MonitorXlsx={read,limits:Object.freeze({...LIMIT})};
})(typeof globalThis==='object'?globalThis:this);
