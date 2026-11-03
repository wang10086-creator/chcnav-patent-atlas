/* Private manual monitoring. Authentication and approval are enforced by the server. */
(() => {
  'use strict';
  const SOURCE = 'https://www-incopat-com-s-6.proxy.itic-sci.com/';
  const state = { session: null, config: null, runs: [], selected: null, busy: false, loginBusy: false };
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const list = value => Array.isArray(value) ? value : [];
  const date = value => { if (!value) return '尚无记录'; const d = new Date(value); return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) + '（北京时间）'; };
  const count = value => Number.isFinite(value) ? value.toLocaleString('zh-CN') : '—';
  const userName = () => typeof state.session?.user === 'string' ? state.session.user : state.session?.user?.username || state.session?.user?.login || '管理员';
  const unwrapRun = result => result?.run || result;
  const errorText = data => typeof data?.error === 'string' ? data.error : data?.error?.message || data?.message || '请求未能完成，请检查管理服务后重试。';
  class ApiError extends Error { constructor(message, status, code) { super(message); this.status = status; this.code = code; } }
  async function api(path, options = {}) {
    const method = options.method || 'GET', headers = { Accept: 'application/json' };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET' && state.session?.csrfToken) headers['X-CSRF-Token'] = state.session.csrfToken;
    let response;
    try { response = await fetch(path, { method, headers, credentials: 'same-origin', cache: 'no-store', body: options.body === undefined ? undefined : JSON.stringify(options.body), redirect: 'error' }); }
    catch { throw new ApiError('私有管理服务无法连接。未确认完成的操作不会被显示为成功。', 0, 'network'); }
    let data;
    try { data = await response.json(); } catch { throw new ApiError('管理服务返回的内容不完整，请核对会话或服务状态。', response.status, 'invalid-response'); }
    if (!response.ok) {
      if (response.status === 401 && path !== '/api/login' && path !== '/api/session') lock('管理员会话已过期，请重新登录。正在核查的结果须重新确认后才能保存。');
      throw new ApiError(errorText(data), response.status, data?.code || data?.error?.code);
    }
    return data;
  }
  function authNotice(message, kind = '') { const el = $('#auth-message'); el.className = 'notice ' + kind; el.textContent = message; }
  function lock(message, unconfigured = false) {
    state.session = null; state.config = null; state.runs = []; state.selected = null; state.busy = false;
    $('#workspace').hidden = true; $('#workspace').replaceChildren(); $('#auth-view').hidden = false;
    $('#session-tools').hidden = true; $('#private-label').hidden = false;
    $('#login-form').hidden = unconfigured; $('#login-password').value = '';
    authNotice(message, unconfigured ? 'warning' : '');
  }
  async function establishSession(session) {
    if (!session?.csrfToken || !session?.user) throw new ApiError('管理员会话不完整，操作保持锁定。', 401, 'session-incomplete');
    state.session = session;
    const [config, runs] = await Promise.all([api('/api/config'), api('/api/runs')]);
    state.config = config; state.runs = list(runs?.runs || runs);
    $('#auth-view').hidden = true; $('#workspace').hidden = false; $('#session-tools').hidden = false; $('#private-label').hidden = true;
    $('#session-user').textContent = userName() + ' · 管理员';
    $('#workspace').innerHTML = workspaceHtml(); bindWorkspace(); renderHistory();
  }
  function baselinesHtml() {
    return '<option value="">首次观察：与现有文献清单比对</option>' + list(state.config?.baselines).map(b => `<option value="${esc(b.id)}">${esc(b.label || b.id)} · ${esc(date(b.reviewedAt))}</option>`).join('');
  }
  function workspaceHtml() {
    const config = state.config || {}, profile = config.profile || {}, source = config.source || {}, c = config.baselineCounts || {};
    const names = list(profile.inScopeApplicantNames), name = profile.name || '华测导航（CHCNAV）';
    const limit = Number(config.maxUploadBytes) > 0 ? Number(config.maxUploadBytes) : 40 * 1048576;
    return `<section class="intro"><div><span class="eyebrow">PRIVATE · MANUAL REVIEW</span><h1>专利变动手动监控</h1><p>管理员手动导入授权来源，在核对变化与覆盖情况后保存观察基线。此工作台不运行定时检索，也不自动发布网站。</p></div><span class="verified-session">已通过服务端管理员验证</span></section>
      <div class="scope-bar"><span class="scope-name">${esc(name)}</span><span><b>${count(c.documents ?? c.documentCount)}</b> 条文献</span><span><b>${count(c.applications ?? c.applicationCount)}</b> 个申请</span><span>会话到期：${esc(date(state.session.expiresAt))}</span></div>
      <div class="steps"><section class="card"><div class="step-heading"><span class="step-number">1</span><h2>在授权来源手动检索</h2></div><p class="muted">在已登录的 IncoPat 中按完整申请人名称精确检索，记录实际检索式、列表页数及全部导出批次。</p><div class="source-names" id="exact-applicant-names">${names.length ? names.map(esc).join('；') : '请核对管理员配置中的精确申请人范围'}</div><div class="source-actions"><a class="button" href="${SOURCE}" target="_blank" rel="noopener noreferrer">打开 IncoPat ↗</a><button class="secondary" id="copy-applicant" type="button">复制申请人名称</button></div><p id="source-message" class="muted" role="status">打开来源页面不表示已执行检索或完成登录。</p></section>
      <section class="card"><div class="step-heading"><span class="step-number">2</span><h2>导入、比对并人工复核</h2></div><span class="source-status">手动执行 · ${esc(source.cloudStatus === 'connected' ? '按实际执行记录核查' : '不依赖自动云浏览器')}</span><p class="muted">文件提交至当前私有管理服务，完整导出、报告与基线保存在私有位置，不进入公开站点。一次观察不等于已证实的法律状态变化。</p><p class="muted">来源文件总量上限 ${Math.floor(limit / 1048576)} MiB。既有已审核基线可继续对照；未审核记录不能充当已确认历史。</p></section></div>
      <div class="import-layout"><div class="import-main"><section class="card"><div class="form-title"><h2>开始一次手动核查</h2><p class="muted">不会自动修改正式专利数据</p></div>
      <form id="manual-import-form"><div class="form-grid"><label class="wide">授权导出文件<input id="monitor-files" type="file" accept=".xlsx,.csv,.tsv" multiple required><small>可选择多个原生 XLSX 批次，或一个已规范化的 CSV／TSV。必须保留完整公开号和申请号。</small><span id="selected-files" class="file-summary">尚未选择文件</span></label>
      <label class="wide">来源适配审计（规范 CSV 配套 JSON，可选）<input id="monitor-audit" type="file" accept=".json"><small>规范 CSV 应同时提供真实原文件范围与校验值审计，不用增加或改写总数来消除覆盖异常。</small></label>
      <label class="wide">对照的已审核观察基线<select id="baseline-select">${baselinesHtml()}</select></label>
      <label class="wide">实际检索条件<textarea id="monitor-query" rows="2" maxlength="12000" placeholder="填写在 IncoPat 实际执行的完整检索式与精确申请人范围" required></textarea></label>
      <label>检索时间范围起<input id="monitor-time-from" type="date" required></label><label>检索时间范围止<input id="monitor-time-to" type="date" required></label>
      <label class="wide">来源检索实际执行时间（含时区）<input id="monitor-executed-at" type="text" placeholder="例如 2026-11-03T17:08:19+08:00" maxlength="50" required><small>保留来源实际时间，不能用本次导入时间代替。</small></label>
      <label>来源显示总文献数<input id="monitor-total" type="number" min="0" step="1" required></label><label>检索列表每页条数<input id="monitor-page-size" type="number" min="1" step="1" placeholder="例如 20" required></label>
      <label>检索列表总页数<input id="monitor-result-pages" type="number" min="0" step="1" placeholder="例如 47" required></label><label>应取得的导出批次数<input id="monitor-batches-expected" type="number" min="0" step="1" placeholder="例如 10" required></label>
      <label>已取得的导出批次数<input id="monitor-batches-actual" type="number" min="0" step="1" required></label><label>导出时的登录与机构授权<select id="monitor-login-status"><option value="unconfirmed">尚未确认</option><option value="authenticated">已确认导出时有效</option><option value="expired">已失效／下载受阻</option></select></label>
      <label class="wide check-label"><input id="monitor-export-complete" type="checkbox"><span>我已核对本次全部导出批次、范围和来源总数，确认文件完整。</span></label></div>
      <details class="disclosure"><summary>额外来源记录</summary><div class="form-grid"><label class="wide">原始执行／批次清单 JSON（可选）<input id="monitor-manifest" type="file" accept=".json"><small>仅用于来源审计。批次文件路径不会被网页当作可访问的电脑路径。</small></label><label class="wide">实际抽查过的检索列表页（可选）<input id="monitor-sampled-pages" type="text" placeholder="例如 2,47"><small>只记录实际抽查页；导出完整不等于逐页浏览过所有列表页。</small></label></div></details>
      <div class="form-actions"><button class="primary" id="monitor-run-button" type="submit">导入并生成待核对结果</button><span id="import-message" role="status"></span></div></form></section><section id="run-detail" class="card result" aria-live="polite"><div class="empty">尚未选择核查记录。开始手动导入，或从右侧打开已保存记录。</div></section></div>
      <aside class="card history-panel"><div class="history-heading"><h2>私有核查记录</h2><button id="refresh-runs" class="text-button" type="button">刷新</button></div><p class="muted">来源、报告及审核记录由管理服务保存，普通访客不可读取。</p><div id="run-list" class="run-list"></div><p id="history-message" class="muted" role="status"></p></aside></div>`;
  }
  function runLabel(run) {
    if (run.status === 'approved' || run.approvedAt) return '已审核 · 已保存基线';
    if (run.status === 'rejected' || run.rejectedAt) return '未通过审核';
    if (['failed', 'import-failed'].includes(run.status)) return '执行异常 · 待复核';
    if (run.report?.anomalies?.length || run.report?.runState === 'exception-review-required') return '存在异常 · 待复核';
    return '待人工核对';
  }
  function renderHistory() {
    const target = $('#run-list'); if (!target) return;
    target.innerHTML = state.runs.length ? state.runs.map(run => `<button type="button" data-run-id="${esc(run.id)}" class="${state.selected?.id === run.id ? 'active' : ''}"><strong>${esc(date(run.createdAt))}</strong><span class="run-status ${run.status === 'approved' ? 'approved' : 'warning'}">${esc(runLabel(run))}</span><span>${esc(run.id)}</span></button>`).join('') : '<p class="history-empty">还没有手动核查记录。</p>';
    target.querySelectorAll('[data-run-id]').forEach(button => { button.onclick = () => selectRun(button.dataset.runId); });
  }
  function cell(value) { if (value === null || value === undefined || value === '') return '—'; return typeof value === 'object' ? JSON.stringify(value, null, 1) : String(value); }
  function table(columns, rows) {
    if (!list(rows).length) return '<p class="muted">本组无记录。</p>';
    return `<div class="table-scroll"><table><thead><tr>${columns.map(([, title]) => `<th>${esc(title)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0, 100).map(row => `<tr>${columns.map(([key]) => `<td>${esc(cell(row[key]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${rows.length > 100 ? `<p class="table-note">页面展示前 100 / ${rows.length} 条，完整内容保留于私有报告下载。</p>` : ''}`;
  }
  function section(title, columns, rows, open = false) { return list(rows).length ? `<details class="result-section" ${open ? 'open' : ''}><summary>${esc(title)}（${rows.length}）</summary>${table(columns, rows)}</details>` : ''; }
  function canApprove(run) {
    const r = run.report || {}, coverage = run.coverage || r.coverage;
    return !['approved', 'rejected', 'failed', 'import-failed'].includes(run.status) && !run.approvedAt && !run.rejectedAt && r.kind === 'incopat-review-report' && Array.isArray(r.anomalies) && r.anomalies.length === 0 && coverage?.complete === true && ['review-required', 'no-difference-in-complete-export'].includes(r.runState);
  }
  function renderRun(run) {
    state.selected = run; renderHistory();
    const r = run.report || {}, c = r.counts || run.counts || {}, m = r.metadata || run.metadata || {}, cov = run.coverage || r.coverage || {};
    const approved = run.status === 'approved' || !!run.approvedAt, rejected = run.status === 'rejected' || !!run.rejectedAt;
    const id = encodeURIComponent(run.id), eligible = canApprove(run);
    $('#run-detail').innerHTML = `<div class="result-heading"><div><span class="run-status ${approved ? 'approved' : 'warning'}">${esc(runLabel(run))}</span><h2>本次核查结果</h2><p class="muted">创建 ${esc(date(run.createdAt))} · <span class="mono">${esc(run.id)}</span></p></div><a class="button" href="/api/runs/${id}/report" download>下载私有完整报告 ↓</a></div>
      <div class="metrics">${[['导入行', c.importedRows], ['去重文献', c.distinctPublications], ['首次状态观察', c.firstStatusObservations], ['状态文字变化', c.stateChanges], ['法律事件', c.legalEvents ?? list(r.legalEvents).length], ['新增申请', c.newApplicationCount], ['既有申请新版本', c.newPublicationVersions], ['异常', c.anomalies ?? list(r.anomalies).length]].map(([title, value]) => `<div class="metric"><b>${count(value)}</b><span>${esc(title)}</span></div>`).join('')}</div>
      <p class="notice ${list(r.anomalies).length || !cov.complete ? 'warning' : ''}">${esc(approved ? '本批记录已由管理员审核并保存为观察基线' : rejected ? '本批记录未通过审核，未设为观察基线' : r.runStateLabel || '结果尚待核对。')}。首次取得的状态与有前后依据的变化分别记录；文献未出现在本次导出中，不会被推断为失效或删除。</p>
      ${section('执行异常与待复核项', [['type', '类型'], ['publicationNumber', '公开号'], ['reason', '原因']], r.anomalies, true)}
      ${section('状态文字变化', [['publicationNumber', '完整公开号'], ['before', '之前'], ['after', '此次来源文字'], ['evidence', '时间与来源证据']], r.stateChanges, true)}
      ${section('首次状态观察（不是已证实的状态变化）', [['publicationNumber', '完整公开号'], ['before', '之前依据'], ['after', '此次来源文字'], ['evidence', '来源证据']], r.firstStatusObservations)}
      ${section('法律事件', [['publicationNumber', '完整公开号'], ['event', '事件原文'], ['eventDate', '事件日期'], ['evidence', '来源证据']], r.legalEvents)}
      ${section('新增公布与文献版本', [['publicationNumber', '完整公开号'], ['applicationNumber', '申请号'], ['title', '名称'], ['kind', '归类'], ['evidence', '来源证据']], list(r.newPublications).map(x => ({ ...x, kind: x.kind === 'new-publication-version' ? '既有申请的新版本' : '新申请的公布文献' })), true)}
      ${section('已识别的重复导出行', [['publicationNumber', '完整公开号'], ['sourceRows', '源行号']], r.duplicateRows)}
      <details class="result-section"><summary>覆盖、执行条件与来源审计</summary><dl class="audit-grid"><dt>来源检索执行时间</dt><dd>${esc(date(m.executedAt))}</dd><dt>实际检索条件</dt><dd>${esc(m.searchQuery || '未提供')}</dd><dt>来源文献总数</dt><dd>${count(m.totalResults)} · ${esc(m.resultCountBasis === 'rows' ? '原导出行口径' : '完整公开号去重口径')}</dd><dt>列表总页数</dt><dd>${count(cov.resultPageCount ?? m.resultPageCount)} 页${cov.allResultPagesVisited === true ? ' · 另有全部逐页浏览记录' : ' · 不认定已逐页浏览全部列表'}</dd><dt>导出批次</dt><dd>${count(cov.downloadedExportBatches ?? m.downloadedExportBatches)} / ${count(cov.expectedExportBatches ?? m.expectedExportBatches)} 批</dd><dt>覆盖一致性</dt><dd>${cov.complete === true ? '检查通过（不替代整体异常与人工审核）' : '未确认完整'}</dd><dt>来源文件 SHA-256</dt><dd class="hash">${esc(m.fileSha256 || '见私有逐文件审计')}</dd></dl>${section('批次范围与校验值', [['fileName', '文件'], ['range', '来源序号范围'], ['recordCount', '原始文献数'], ['sha256', '原文件 SHA-256']], cov.exportBatches)}${list(cov.warnings).length ? `<ul class="muted">${cov.warnings.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</details>
      ${approved ? `<div class="review-box"><h3>已审核并保存观察基线</h3><p class="muted">${esc(date(run.approvedAt || run.reviewedAt))} · ${esc(run.reviewNote || '')}</p><div class="result-downloads">${run.baselineId ? `<a class="button" href="/api/baselines/${encodeURIComponent(run.baselineId)}" download>下载私有观察基线 ↓</a>` : ''}<a class="button" href="/api/runs/${id}/public-summary" download>下载可公开摘要 ↓</a></div><p class="muted">下载公开摘要不会自动更新网站。原始导出、完整状态记录与审核证据继续保存在私有管理服务中。</p></div>` : rejected ? `<div class="review-box"><h3>本次记录未通过审核</h3><p>${esc(run.rejectionReason || run.reason || run.reviewNote || '具体原因保留于私有审核记录。')}</p><p class="muted">没有将其设为新的已审核观察基线。</p></div>` : `<div class="review-box"><h3>人工核对与保存</h3><p class="muted">核对原始批次、状态文字、事件日期与来源。点击确认后，服务端保存新的观察基线，供下一次手动监控对照。</p>${eligible ? `<form id="approve-form"><label class="check-label"><input id="review-acknowledged" type="checkbox" required><span>我已逐项核对本批来源与覆盖，并确认需纳入基线的状态和事件记录。</span></label><label>人工核对备注<textarea id="review-note" minlength="10" maxlength="2000" required placeholder="至少 10 字，记录核对范围、来源和仍需保留的限制"></textarea></label><div class="review-actions"><button id="approve-button" class="primary" type="submit" disabled>确认核对并保存基线</button><span id="review-message" class="review-message" role="status"></span></div></form>` : '<p class="notice warning">本批次有异常、覆盖尚未确认或结果不可审核，不能设为已审核基线。请先补全来源或重新导入。</p>'}<details class="disclosure"><summary>将此记录标为未通过审核</summary><form id="reject-form" class="reject-form"><label>未通过原因<textarea id="reject-reason" minlength="10" maxlength="2000" required></textarea></label><div><button class="secondary danger" type="submit">保存未通过原因</button></div><p id="reject-message" role="status" class="muted"></p></form></details></div>`}`;
    bindRun(run);
  }
  async function refreshRuns() {
    const result = await api('/api/runs'); state.runs = list(result?.runs || result); renderHistory();
  }
  async function refreshBaselines() {
    const config = await api('/api/config'); state.config = config;
    const selected = $('#baseline-select')?.value || '';
    if ($('#baseline-select')) { $('#baseline-select').innerHTML = baselinesHtml(); if (list(config.baselines).some(b => b.id === selected)) $('#baseline-select').value = selected; }
  }
  async function selectRun(id) {
    if (state.busy) return;
    $('#history-message').textContent = '正在读取私有核查记录…';
    try { renderRun(unwrapRun(await api('/api/runs/' + encodeURIComponent(id)))); $('#history-message').textContent = ''; }
    catch (error) { if ($('#history-message')) $('#history-message').textContent = error.message; }
  }
  function bindRun(run) {
    const approve = $('#approve-form');
    if (approve) {
      const ack = $('#review-acknowledged'), note = $('#review-note'), button = $('#approve-button');
      const update = () => { button.disabled = state.busy || !ack.checked || note.value.trim().length < 10; };
      ack.onchange = update; note.oninput = update;
      approve.onsubmit = async event => {
        event.preventDefault(); if (state.busy || !approve.reportValidity() || !ack.checked) return;
        state.busy = true; update(); $('#review-message').textContent = '正在提交人工审核记录…';
        try { const result = unwrapRun(await api('/api/runs/' + encodeURIComponent(run.id) + '/approve', { method: 'POST', body: { acknowledged: true, reviewNote: note.value.trim() } })); renderRun(result); await Promise.all([refreshRuns(), refreshBaselines()]); }
        catch (error) { if ($('#review-message')) $('#review-message').textContent = error.message; }
        finally { state.busy = false; if ($('#approve-button')) $('#approve-button').disabled = !$('#review-acknowledged').checked || $('#review-note').value.trim().length < 10; }
      };
    }
    const reject = $('#reject-form');
    if (reject) reject.onsubmit = async event => {
      event.preventDefault(); if (state.busy || !reject.reportValidity()) return;
      state.busy = true; const button = reject.querySelector('button'); button.disabled = true; $('#reject-message').textContent = '正在保存审核原因…';
      try { renderRun(unwrapRun(await api('/api/runs/' + encodeURIComponent(run.id) + '/reject', { method: 'POST', body: { reason: $('#reject-reason').value.trim() } }))); await refreshRuns(); }
      catch (error) { if ($('#reject-message')) $('#reject-message').textContent = error.message; }
      finally { state.busy = false; if (button.isConnected) button.disabled = false; }
    };
  }
  async function readJson(file, label) {
    if (!file) return undefined;
    if (file.size > 8 * 1048576) throw new Error(label + '超过 8 MiB，请核对所选文件。');
    try { const parsed = JSON.parse(await file.text()); if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(); return parsed; }
    catch { throw new Error(label + '不是完整的 JSON 对象。'); }
  }
  async function filePayload(file) {
    const bytes = new Uint8Array(await file.arrayBuffer()), chunks = [];
    for (let start = 0; start < bytes.length; start += 8192) chunks.push(String.fromCharCode(...bytes.subarray(start, start + 8192)));
    return { name: file.name, contentBase64: btoa(chunks.join('')) };
  }
  function samplePages(value, total) {
    if (!value.trim()) return [];
    const parts = value.split(/[,，\s]+/).filter(Boolean);
    if (parts.some(x => !/^\d+$/.test(x) || Number(x) < 1 || Number(x) > total)) throw new Error('抽查页码须是列表总页数内的正整数，用逗号分隔。');
    return [...new Set(parts.map(Number))];
  }
  function bindWorkspace() {
    const filesInput = $('#monitor-files'), importForm = $('#manual-import-form');
    filesInput.onchange = () => { const files = Array.from(filesInput.files || []); $('#selected-files').textContent = files.length ? `${files.length} 个文件 · ${(files.reduce((n, f) => n + f.size, 0) / 1048576).toFixed(2)} MiB · ${files.map(f => f.name).join('；')}` : '尚未选择文件'; };
    $('#copy-applicant').onclick = async () => {
      const names = list(state.config?.profile?.inScopeApplicantNames).join('；');
      if (!names) { $('#source-message').textContent = '尚未配置可靠的完整申请人范围。'; return; }
      try { await navigator.clipboard.writeText(names); $('#source-message').textContent = '已复制完整申请人名称，请在来源申请人字段使用精确范围。'; }
      catch { $('#source-message').textContent = '浏览器未允许复制，请从上方手动复制申请人名称。'; }
    };
    $('#refresh-runs').onclick = async () => { if (state.busy) return; $('#history-message').textContent = '正在刷新…'; try { await refreshRuns(); $('#history-message').textContent = ''; } catch (error) { if ($('#history-message')) $('#history-message').textContent = error.message; } };
    importForm.onsubmit = async event => {
      event.preventDefault(); if (state.busy || !importForm.reportValidity()) return;
      const message = $('#import-message'), files = Array.from(filesInput.files || []), limit = Number(state.config?.maxUploadBytes) || 40 * 1048576;
      message.textContent = '';
      if (!files.length) return;
      if (files.some(f => !/\.(?:xlsx|csv|tsv)$/i.test(f.name))) { message.textContent = '只支持来源 XLSX 或规范 CSV／TSV，请保留原文件并重新选择。'; return; }
      if (files.some(f => f.size === 0) || files.reduce((n, f) => n + f.size, 0) > limit) { message.textContent = '来源文件为空或总量超过私有服务单批限制。请使用本地导入命令，不要删减结果凑覆盖。'; return; }
      const value = id => $('#' + id).value.trim(), number = id => Number(value(id));
      const executedAt = value('monitor-executed-at');
      if (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(executedAt) || Number.isNaN(Date.parse(executedAt))) { message.textContent = '来源执行时间必须包含实际日期、时间和时区，例如 2026-11-03T17:08:19+08:00。'; return; }
      state.busy = true; $('#monitor-run-button').disabled = true; message.textContent = '正在提交至私有管理服务并校验完整覆盖…';
      try {
        const exportAudit = await readJson($('#monitor-audit').files[0], '来源适配审计'), sourceManifest = await readJson($('#monitor-manifest').files[0], '执行批次清单');
        const metadata = { searchQuery: value('monitor-query'), timeFrom: value('monitor-time-from'), timeTo: value('monitor-time-to'), executedAt, sourceUrl: SOURCE, loginStatus: value('monitor-login-status'), exportComplete: $('#monitor-export-complete').checked, totalResults: number('monitor-total'), resultCountBasis: 'publications', coverageSchemaVersion: 2, resultPageCount: number('monitor-result-pages'), resultPageSize: number('monitor-page-size'), expectedExportBatches: number('monitor-batches-expected'), downloadedExportBatches: number('monitor-batches-actual'), sampledResultPages: samplePages(value('monitor-sampled-pages'), number('monitor-result-pages')) };
        const uploaded = []; for (const file of files) uploaded.push(await filePayload(file));
        const result = await api('/api/runs', { method: 'POST', body: { files: uploaded, metadata, ...(value('baseline-select') ? { baselineId: value('baseline-select') } : {}), ...(exportAudit ? { exportAudit } : {}), ...(sourceManifest ? { sourceManifest } : {}) } });
        renderRun(unwrapRun(result)); await refreshRuns();
        message.textContent = '私有核查记录已保存，请核对结果、异常及来源；尚未审核或发布。';
        $('#run-detail').scrollIntoView({ block: 'start', behavior: 'smooth' });
      } catch (error) { if ($('#import-message')) $('#import-message').textContent = error.message; }
      finally { state.busy = false; if ($('#monitor-run-button')) $('#monitor-run-button').disabled = false; }
    };
  }
  $('#login-form').onsubmit = async event => {
    event.preventDefault(); if (state.loginBusy || !$('#login-form').reportValidity()) return;
    state.loginBusy = true; $('#login-button').disabled = true; authNotice('正在验证管理员身份…');
    const username = $('#login-username').value.trim(), password = $('#login-password').value;
    $('#login-password').value = '';
    try { await establishSession(await api('/api/login', { method: 'POST', body: { username, password } })); }
    catch (error) { lock(error.status === 503 ? '管理员尚未配置。请在私有执行端初始化管理员后再登录；当前没有管理操作被解锁。' : error.message, error.status === 503); }
    finally { state.loginBusy = false; $('#login-button').disabled = false; }
  };
  $('#logout-button').onclick = async () => {
    if (state.busy || !state.session) return;
    try { await api('/api/logout', { method: 'POST', body: {} }); lock('已退出管理员会话。'); }
    catch (error) { if (state.session) { $('#session-user').textContent = '退出未确认，请关闭此工作台并检查服务。'; $('#logout-button').title = error.message; } }
  };
  (async () => {
    try { await establishSession(await api('/api/session')); }
    catch (error) { lock(error.status === 503 ? '管理员尚未配置。请在私有执行端初始化管理员后重新载入；当前不能导入、审核或保存基线。' : error.status === 401 ? '请使用管理员账号登录。机构网页登录不代表拥有本工作台管理权限。' : error.message, error.status === 503); }
  })();
})();
