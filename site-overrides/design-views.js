(function () {
  'use strict';
  let manifest = null, loadError = '', bound = false, opener = null;
  const modes = new Map();
  let active = { id: '', items: [], index: 0, actualSize: false };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const safeAsset = value => typeof value === 'string' && value.startsWith('assets/design-views/') && !value.split('/').some(x => !x || x === '..' || x === '.') && !/[\\?#]/.test(value);
  const safePdf = value => typeof value === 'string' && /^https:\/\/(?:github\.com|raw\.githubusercontent\.com)\/wang10086-creator\/chcnav-patent-pdfs\//.test(value);
  const verified = record => ['verified-text', 'verified-ocr'].includes(record?.identity?.status);
  async function load() {
    try {
      const response = await fetch('data/design-views.json');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (data.schemaVersion !== 1 || !data.documents || typeof data.documents !== 'object') throw new Error('核查清单格式不完整');
      for (const [id, record] of Object.entries(data.documents)) {
        if (!/^CN\d+S\d?$/.test(id) || record.id !== id || !Array.isArray(record.pages)) throw new Error('文献标识不完整');
        for (const page of record.pages) {
          if (!Number.isInteger(page.pageNumber) || page.pageNumber < 1 || !safeAsset(page.image) || !safeAsset(page.thumbnail)) throw new Error('原页资源索引不完整');
          for (const view of page.views || []) if (!safeAsset(view.image) || !safeAsset(view.thumbnail)) throw new Error('视图资源索引不完整');
        }
      }
      manifest = data;
      loadError = '';
      return data;
    } catch (error) {
      manifest = null;
      loadError = String(error.message || error);
      console.warn('Design view evidence could not be loaded', error);
      return null;
    }
  }
  function pageItems(record, supporting = false) {
    return record.pages.filter(page => supporting ? ['cover', 'description'].includes(page.pageKind) : !['cover', 'description'].includes(page.pageKind)).map(page => ({ ...page, label: page.labels?.length ? page.labels.join(' · ') : `PDF 第 ${page.pageNumber} 页 · 保留原页`, originalPage: true }));
  }
  function viewItems(record) {
    return record.pages.filter(page => !['cover', 'description'].includes(page.pageKind)).flatMap(page => { const crops=(page.views || []).map(view => ({ ...view, pageNumber: page.pageNumber, originalPage: false })); const fallback={ ...page, label: page.labels?.length ? `${page.labels.join(' · ')}（完整原页）` : `PDF 第 ${page.pageNumber} 页 · 原页待分图`, originalPage: true }; return crops.length && crops.length === page.labels?.length ? crops : [...crops, fallback]; });
  }
  function itemsFor(record, mode) { return mode === 'pages' ? pageItems(record) : mode === 'support' ? pageItems(record, true) : viewItems(record); }
  function card(item, id, index, mode) {
    return `<button type="button" class="dv-card" data-dv-open="${escape(id)}" data-dv-index="${index}" data-dv-kind="${mode}" aria-label="放大${escape(item.label)}，PDF 第 ${item.pageNumber} 页"><span class="dv-thumb"><img src="${escape(item.thumbnail)}" alt="${escape(item.label)}" loading="lazy" decoding="async" width="${item.width || 200}" height="${item.height || 280}"></span><span class="dv-card-label">${escape(item.label)}</span><small>PDF 第 ${item.pageNumber} 页${item.originalPage ? ' · 整页' : ''}</small></button>`;
  }
  function grid(record, mode) {
    const items = itemsFor(record, mode);
    if (!items.length) return '<p class="dv-note">此分组没有可展示的页面，请核对 PDF 与逐件清单。</p>';
    const first = items.slice(0, 6).map((item, i) => card(item, record.id, i, mode)).join('');
    const rest = items.slice(6).map((item, i) => card(item, record.id, i + 6, mode)).join('');
    return `<div class="dv-grid">${first}</div>${rest ? `<details class="dv-more"><summary>展开其余 ${items.length - 6} ${mode === 'views' ? '项视图／原页' : '页'}</summary><div class="dv-grid">${rest}</div></details>` : ''}`;
  }
  function render(id) {
    if (!/^CN\d+S\d?$/.test(id)) return '';
    if (!manifest) return `<section class="design-views"><h3>外观设计图文证据</h3><p class="dv-warning">${loadError ? '完整原页清单暂未载入，请刷新重试；原有图片和 PDF 入口继续保留。' : '完整原页清单正在载入。'}</p></section>`;
    const record = manifest.documents[id];
    if (!record) return '<section class="design-views"><h3>外观设计图文证据</h3><p class="dv-warning">此公开号尚无可核对的全页视图记录；不能据此认定视图已补全。请查看原 PDF。</p></section>';
    if (!verified(record)) return `<section class="design-views"><h3>外观设计图文证据</h3><p class="dv-warning">${escape(id)} 的 PDF 内部编号尚未可靠确认，候选文件未作为本专利完整视图展示。请核对逐件清单及原 PDF。</p>${safePdf(record.pdf?.viewUrl) ? `<a href="${escape(record.pdf.viewUrl)}" target="_blank" rel="noopener">核对候选 PDF 来源 ↗</a>` : ''}</section>`;
    const mode = modes.get(id) || (record.pages.some(page => page.views?.length) ? 'views' : 'pages');
    const support = pageItems(record, true);
    const counts = `原页 ${record.renderedPageCount ?? record.pages.length}/${record.pdf.pageCount} 页${Number.isInteger(record.expectedViewCount) ? ` · PDF 载明 ${record.expectedViewCount} 幅` : ' · PDF 总视图数待确认'}${Number.isInteger(record.recognizedViewCount) ? ` · 图页标签识别 ${record.recognizedViewCount} 项` : ''}`;
    return `<section class="design-views" data-dv-id="${escape(id)}"><div class="dv-heading"><h3>外观设计图文证据</h3><span>${escape(counts)}</span></div><p class="dv-note">${escape(record.coverageNote || '全部 PDF 页按原版渲染保留。无法可靠分图的内容以整页展示；页面覆盖不等于逐视图或外观保护范围已完成人工核验。')}</p><div class="dv-tabs" role="group" aria-label="外观证据展示方式"><button type="button" data-dv-mode="views" aria-pressed="${mode === 'views'}">视图与原页</button><button type="button" data-dv-mode="pages" aria-pressed="${mode === 'pages'}">图页原版</button><a href="data/design-views-audit.csv" download>逐件核对表 CSV ↓</a><a href="data/design-views.json" download>完整来源清单 ↓</a></div>${grid(record, mode)}${support.length ? `<details class="dv-support"><summary>封面、简要说明等证据页（${support.length} 页）</summary>${grid(record, 'support')}</details>` : ''}${record.limitations?.length ? `<details class="dv-limits"><summary>提取方法与待核事项</summary><ul>${record.limitations.map(value => `<li>${escape(value)}</li>`).join('')}</ul></details>` : ''}</section>`;
  }
  function ensureDialog() {
    let dialog = document.getElementById('design-viewer');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'design-viewer';
    dialog.className = 'design-viewer';
    dialog.setAttribute('aria-label', '外观设计原页与视图放大查看');
    dialog.innerHTML = '<header class="dv-viewer-header"><strong id="dv-viewer-title"></strong><button type="button" data-dv-close aria-label="关闭外观视图">关闭 ×</button></header><div class="dv-viewer-tools"><button type="button" data-dv-prev>← 上一项</button><span id="dv-viewer-position"></span><button type="button" data-dv-next>下一项 →</button><button type="button" data-dv-zoom aria-pressed="false">原尺寸</button><a id="dv-page-pdf" target="_blank" rel="noopener">打开 PDF 对应页 ↗</a><a id="dv-source-pdf" target="_blank" rel="noopener">PDF 来源 ↗</a></div><div class="dv-viewer-canvas"><img id="dv-viewer-image" alt=""></div><p class="dv-viewer-note">完整原页保留设计内容与标号。PDF 页码按文件实际页序；站内阅读器将定位到同一原始 PDF 的对应页，原始 PDF 来源入口继续保留。</p>';
    dialog.addEventListener('close', () => { document.getElementById('dv-viewer-image').removeAttribute('src'); opener?.focus?.(); });
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener('keydown', event => { if (event.key === 'ArrowLeft') { event.preventDefault(); step(-1); } else if (event.key === 'ArrowRight') { event.preventDefault(); step(1); } });
    document.body.append(dialog);
    return dialog;
  }
  function updateViewer() {
    const record = manifest.documents[active.id], item = active.items[active.index];
    const dialog = ensureDialog(), image = document.getElementById('dv-viewer-image');
    image.src = item.image;
    image.alt = `${active.id} · ${item.label} · PDF 第 ${item.pageNumber} 页`;
    image.width = item.width || 1000;
    image.height = item.height || 1400;
    dialog.classList.toggle('dv-actual-size', active.actualSize);
    document.getElementById('dv-viewer-title').textContent = `${active.id} · ${item.label}`;
    document.getElementById('dv-viewer-position').textContent = `${active.index + 1} / ${active.items.length} · PDF 第 ${item.pageNumber} 页`;
    dialog.querySelector('[data-dv-prev]').disabled = active.index === 0;
    dialog.querySelector('[data-dv-next]').disabled = active.index === active.items.length - 1;
    const zoom = dialog.querySelector('[data-dv-zoom]');
    zoom.textContent = active.actualSize ? '适合宽度' : '原尺寸';
    zoom.setAttribute('aria-pressed', String(active.actualSize));
    const pdf = document.getElementById('dv-page-pdf');
    const source = document.getElementById('dv-source-pdf');
    pdf.hidden = !safePdf(record.pdf.downloadUrl); source.hidden = !safePdf(record.pdf.viewUrl);
    if (!pdf.hidden) pdf.href = `pdf-viewer.html?id=${encodeURIComponent(active.id)}&page=${item.pageNumber}`;
    if (!source.hidden) source.href = record.pdf.viewUrl;
    dialog.querySelector('.dv-viewer-canvas').scrollTo(0, 0);
  }
  function step(delta) {
    const next = active.index + delta;
    if (next < 0 || next >= active.items.length) return;
    active.index = next;
    updateViewer();
  }
  function bind() {
    if (bound) return;
    bound = true;
    document.addEventListener('click', event => {
      const target = event.target.closest('[data-dv-mode], [data-dv-open], [data-dv-close], [data-dv-prev], [data-dv-next], [data-dv-zoom]');
      if (!target) return;
      if (target.hasAttribute('data-dv-mode')) {
        const section = target.closest('[data-dv-id]');
        if (!section) return;
        modes.set(section.dataset.dvId, target.dataset.dvMode);
        section.outerHTML = render(section.dataset.dvId);
      } else if (target.hasAttribute('data-dv-open')) {
        const id = target.dataset.dvOpen, record = manifest?.documents[id];
        if (!record || !verified(record)) return;
        const items = itemsFor(record, target.dataset.dvKind), index = Number(target.dataset.dvIndex);
        if (!items[index]) return;
        opener = target;
        active = { id, items, index, actualSize: false };
        const dialog = ensureDialog(); updateViewer();
        if (!dialog.open) dialog.showModal();
        dialog.querySelector('[data-dv-close]').focus();
      } else if (target.hasAttribute('data-dv-close')) ensureDialog().close();
      else if (target.hasAttribute('data-dv-prev')) step(-1);
      else if (target.hasAttribute('data-dv-next')) step(1);
      else { active.actualSize = !active.actualSize; updateViewer(); }
    });
  }
  window.DesignViews = { load, render, bind, getState: () => ({ loaded: !!manifest, error: loadError, documentCount: manifest ? Object.keys(manifest.documents).length : 0 }) };
}());
