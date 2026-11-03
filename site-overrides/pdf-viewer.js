// PDF pages are loaded only after this standalone viewer is opened.
// Official API: https://mozilla.github.io/pdf.js/examples/
// https://mozilla.github.io/pdf.js/api/draft/module-pdfjsLib.html
const $ = selector => document.querySelector(selector);
const state = { id: '', record: null, index: null, pdf: null, page: 1, total: 0,
  mode: 'none', task: null, renderTask: null, renderSequence: 0, loading: false,
  fallback: null, fallbackManifest: null, error: '', shown: false };
const publicationPattern = /^CN\d+[ABUS]\d?$/;
const exactPath = (path, id) => typeof path === 'string' && !/[\\?#]/.test(path) &&
  path.split('/').every(part => part && part !== '.' && part !== '..') &&
  path.split('/').at(-1).startsWith(id + '_') && path.toLowerCase().endsWith('.pdf');
const safeImage = path => typeof path === 'string' && /^assets\/design-views\//.test(path) &&
  !/[\\?#]/.test(path) && path.split('/').every(part => part && part !== '.' && part !== '..');
const parsePage = value => /^\d+$/.test(String(value)) && Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;
function notice(title, detail = '') {
  const el = $('#pv-message'); el.replaceChildren(); el.hidden = !title;
  if (!title) return;
  const strong = document.createElement('strong'); strong.textContent = title; el.append(strong);
  if (detail) { const span = document.createElement('span'); span.textContent = detail; el.append(span); }
}
function status(text) { $('#pv-status').textContent = text; }
function updateControls() {
  const ready = !state.loading && state.shown && state.total > 0 && (state.mode === 'pdf' || state.mode === 'fallback');
  $('#pv-prev').disabled = !ready || state.page <= 1;
  $('#pv-next').disabled = !ready || state.page >= state.total;
  $('#pv-go').disabled = !state.record || state.loading;
  $('#pv-zoom').disabled = state.mode !== 'pdf' || state.loading;
  $('#pv-total').textContent = '/ ' + (state.total || '—');
  if (state.total) $('#pv-page').max = String(state.total); else $('#pv-page').removeAttribute('max');
}
function updateLocation(page) {
  const url = new URL(location.href); url.search = ''; url.searchParams.set('id', state.id);
  url.searchParams.set('page', String(page)); history.replaceState(null, '', url);
}
async function jsonFile(path) {
  const response = await fetch(path, { credentials: 'omit', cache: 'no-cache' });
  if (!response.ok) throw new Error(`资料清单读取失败（HTTP ${response.status}）`);
  return response.json();
}
async function loadFallbackManifest() {
  if (state.fallbackManifest) return state.fallbackManifest;
  const manifest = await jsonFile('data/design-views.json');
  if (manifest.schemaVersion !== 1 || manifest.sourcePdfCommit !== state.index.commit) throw new Error('原页清单与 PDF 来源版本不一致');
  state.fallbackManifest = manifest;
  return manifest;
}
async function showFallback(pageNumber, reason) {
  state.error = reason;
  $('#pv-retry').hidden = false;
  try {
    const manifest = await loadFallbackManifest(), record = manifest.documents?.[state.id];
    if (!record || !['verified-text', 'verified-ocr'].includes(record.identity?.status) ||
      record.id !== state.id || record.pdf?.commit !== state.index.commit ||
      record.pdf?.sha256 !== state.record.sha256 || record.pdf.path !== state.record.path) throw new Error('此文献没有可确认对应关系的原页渲染记录');
    const page = record.pages.find(item => item.pageNumber === pageNumber);
    if (!page || !safeImage(page.image)) throw new Error('所请求的页码没有可展示的原页渲染图');
    state.mode = 'fallback'; state.fallback = record; state.total = record.pdf.pageCount;
    state.page = pageNumber; state.shown = true; $('#pv-page').value = String(pageNumber);
    $('#pv-sheet').hidden = false; $('#pv-canvas').hidden = true;
    const image = $('#pv-fallback'); image.hidden = false;
    image.src = page.image; image.alt = `${state.id} · PDF 第 ${pageNumber} 页的已保存完整原页渲染图`;
    image.width = page.width || 1000; image.height = page.height || 1400;
    status(`${state.id} · 第 ${pageNumber} / ${state.total} 页 · 已保存的原页渲染图`);
    notice('PDF 原文件当前无法读取或渲染，已展示对应页的原页渲染图。',
      `原因：${reason}。当前图片不是本次实时 PDF 渲染；它对应同一公开号、同一 PDF 版本和校验值。可重试读取或使用下方原始文件入口。`);
    updateLocation(pageNumber); updateControls();
    image.onerror = () => { image.hidden = true; notice('对应原页渲染图也未能读取。', '请检查网络后重试，或使用下方原始 PDF 文件入口；此页未显示任何替代内容。'); };
    return true;
  } catch (error) {
    state.mode = 'error'; state.total = 0; state.shown = false; $('#pv-sheet').hidden = true;
    status('PDF 页面未能显示。');
    notice('PDF 原文件当前无法读取或渲染。', `原因：${reason}。${error.message}。请重试或打开下方原文件；没有将其他文献或页码作为替代。`);
    updateControls(); return false;
  }
}
async function renderPage(pageNumber) {
  if (!state.pdf) return;
  if (pageNumber > state.pdf.numPages) { notice('页码超出文件范围。', `该 PDF 共 ${state.pdf.numPages} 页，请输入 1 至 ${state.pdf.numPages}。`); updateControls(); return; }
  const sequence = ++state.renderSequence;
  if (state.renderTask) { state.renderTask.cancel(); await state.renderTask.promise.catch(() => {}); }
  status(`正在渲染第 ${pageNumber} / ${state.pdf.numPages} 页…`);
  try {
    const page = await state.pdf.getPage(pageNumber); if (sequence !== state.renderSequence) return;
    const base = page.getViewport({ scale: 1 }), sheet = $('#pv-sheet'); sheet.hidden = false;
    const availableWidth = Math.max(180, sheet.clientWidth - (innerWidth <= 600 ? 10 : 28));
    const selectedZoom = $('#pv-zoom').value, scale = selectedZoom === 'fit' ? availableWidth / base.width : Number(selectedZoom);
    const viewport = page.getViewport({ scale }), outputScale = Math.min(devicePixelRatio || 1, 2);
    const canvas = $('#pv-canvas'); canvas.hidden = false; $('#pv-fallback').hidden = true;
    canvas.width = Math.ceil(viewport.width * outputScale); canvas.height = Math.ceil(viewport.height * outputScale);
    canvas.style.width = `${Math.floor(viewport.width)}px`; canvas.style.height = `${Math.floor(viewport.height)}px`;
    const context = canvas.getContext('2d', { alpha: false });
    state.renderTask = page.render({ canvasContext: context, viewport,
      transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null });
    await state.renderTask.promise; if (sequence !== state.renderSequence) return;
    state.mode = 'pdf'; state.page = pageNumber; state.shown = true; state.total = state.pdf.numPages;
    $('#pv-page').value = String(pageNumber); $('#pv-retry').hidden = true;
    notice(''); status(`${state.id} · PDF 第 ${pageNumber} / ${state.total} 页 · 原文件 SHA-256 校验通过`);
    canvas.setAttribute('aria-label', `${state.id} · PDF 第 ${pageNumber} / ${state.total} 页`);
    updateLocation(pageNumber); updateControls();
  } catch (error) {
    if (error?.name === 'RenderingCancelledException' || sequence !== state.renderSequence) return;
    await showFallback(pageNumber, String(error.message || error));
  }
}
async function loadPdf(pageNumber) {
  if (!state.record || state.loading) return;
  state.loading = true; state.mode = 'loading'; notice(''); updateControls();
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 45000);
  try {
    status(`正在读取 ${state.id} 原文件（${(state.record.sizeBytes / 1048576).toFixed(2)} MB），仅加载当前选中的这一份 PDF…`);
    const response = await fetch(state.downloadUrl, { mode: 'cors', credentials: 'omit',
      redirect: 'error', referrerPolicy: 'no-referrer', signal: controller.signal });
    if (!response.ok) throw new Error(`原始 PDF 下载失败（HTTP ${response.status}）`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length !== state.record.sizeBytes || !bytes.subarray(0, 5).every((value, i) => value === [37, 80, 68, 70, 45][i])) throw new Error('返回文件大小或 PDF 标识与清单不一致');
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(value => value.toString(16).padStart(2, '0')).join('');
    if (digest !== state.record.sha256) throw new Error('原始 PDF 的 SHA-256 与对应清单不一致');
    status('原文件校验通过，正在读取 PDF 页序…');
    const pdfjs = await import('./vendor/pdfjs/build/pdf.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdfjs/build/pdf.worker.mjs', import.meta.url).href;
    const vendor = new URL('./vendor/pdfjs/', import.meta.url).href;
    if (state.pdf) await state.pdf.destroy();
    state.task = pdfjs.getDocument({ data: bytes, withCredentials: false,
      enableXfa: false, disableWorkerRendering: true, cMapUrl: vendor + 'cmaps/', cMapPacked: true,
      standardFontDataUrl: vendor + 'standard_fonts/', wasmUrl: vendor + 'wasm/', iccUrl: vendor + 'iccs/' });
    state.pdf = await state.task.promise; state.total = state.pdf.numPages; state.mode = 'pdf';
    if (pageNumber > state.total) { status(`${state.id} · 原文件已读取，共 ${state.total} 页。`); notice('页码超出文件范围。', `该 PDF 共 ${state.total} 页，请输入 1 至 ${state.total}。`); return; }
    await renderPage(pageNumber);
  } catch (error) {
    const reason = error?.name === 'AbortError' ? '读取原始 PDF 超时' : error?.message === 'Failed to fetch' ? '原始 PDF 网络请求失败（可能是网络或跨域访问受限）' : String(error.message || error);
    await showFallback(pageNumber, reason);
  } finally { clearTimeout(timer); state.loading = false; updateControls(); }
}
async function showPage(value) {
  const pageNumber = parsePage(value);
  if (!pageNumber) { notice('页码必须是 1 以上的整数。', '请更正页码后点击跳转；不会自动替换为其他页。'); return; }
  if (state.total && pageNumber > state.total) { notice('页码超出文件范围。', `该 PDF 共 ${state.total} 页，请输入 1 至 ${state.total}。`); return; }
  if (state.mode === 'fallback') await showFallback(pageNumber, state.error);
  else if (state.pdf) await renderPage(pageNumber);
  else await loadPdf(pageNumber);
}
$('#pv-page-form').addEventListener('submit', event => { event.preventDefault(); showPage($('#pv-page').value); });
$('#pv-prev').addEventListener('click', () => showPage(state.page - 1));
$('#pv-next').addEventListener('click', () => showPage(state.page + 1));
$('#pv-zoom').addEventListener('change', () => { if (state.pdf) renderPage(state.page); });
$('#pv-retry').addEventListener('click', () => loadPdf(parsePage($('#pv-page').value) || state.page));
let resizeTimer;
addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.mode === 'pdf' && $('#pv-zoom').value === 'fit') renderPage(state.page); }, 180); });
async function init() {
  const params = new URLSearchParams(location.search), id = (params.get('id') || '').trim().toUpperCase(), rawPage = params.get('page') || '1';
  $('#pv-page').value = rawPage;
  if (!publicationPattern.test(id)) { status('未选择可确认的专利文献。'); notice('缺少或无法识别完整公开号。', '请从专利详情中的 PDF 对应页入口进入；本阅读器不接受任意文件网址。'); return; }
  try {
    const index = await jsonFile('data/pdf-index.json'), record = index.documents?.[id];
    if (index.schemaVersion !== 1 || index.repository !== 'wang10086-creator/chcnav-patent-pdfs' || !/^[a-f0-9]{40}$/.test(index.commit)) throw new Error('PDF 来源清单格式或仓库不正确');
    if (!record || !exactPath(record.path, id) || !/^[a-f0-9]{64}$/.test(record.sha256) || !Number.isSafeInteger(record.sizeBytes) || record.sizeBytes <= 0) throw new Error('该完整公开号不在已核对的 PDF 白名单中');
    state.id = id; state.index = index; state.record = record;
    const encoded = record.path.split('/').map(encodeURIComponent).join('/');
    state.downloadUrl = `https://raw.githubusercontent.com/${index.repository}/${index.commit}/${encoded}`;
    $('#pv-document').textContent = `${id} · 申请号 ${record.applicationNumber} · ${record.path.split('/').at(-1)}`;
    $('#pv-back').href = `index.html#patent/${encodeURIComponent(id)}`;
    $('#pv-source').href = `https://github.com/${index.repository}/blob/${index.commit}/${encoded}`;
    $('#pv-download').href = state.downloadUrl;
    $('#pv-source').hidden = false; $('#pv-download').hidden = false;
    $('#pv-provenance').textContent = `固定来源版本 ${index.commit} · SHA-256 ${record.sha256}`;
    updateControls(); await showPage(rawPage);
  } catch (error) { status('文献索引未能核对。'); notice('无法打开所请求的 PDF。', String(error.message || error)); }
}
init();
