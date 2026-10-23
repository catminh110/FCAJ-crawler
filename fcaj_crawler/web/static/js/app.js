// FCAJ Crawler Dashboard Client

let allWorkshops = [];
let categories = [];
let selectedIds = new Set();
let currentCategory = 'all';
let currentStatusFilter = 'all'; // 'all' | 'pending' | 'done'
let currentDlFilter = 'all'; // 'all' | 'bundle' | 'pdf' | 'md'
let isRunning = false;
let filesByWorkshop = new Map(); // ws_id -> Array<file>
let allDownloadedFiles = [];

// DOM Elements
const tbody = document.getElementById('workshops-tbody');
const categoryPillsContainer = document.getElementById('category-pills');
const searchInput = document.getElementById('input-search');
const btnClearSearch = document.getElementById('btn-clear-search');
const langSelect = document.getElementById('select-lang');
const formatSelect = document.getElementById('select-format');
const chkBundle = document.getElementById('chk-bundle');
const btnDeselectAll = document.getElementById('btn-deselect-all');
const btnBundleExisting = document.getElementById('btn-bundle-existing');
const btnCrawlAll = document.getElementById('btn-crawl-all');
const btnStartCrawl = document.getElementById('btn-start-crawl');
const btnStartCrawlLabel = document.getElementById('btn-start-crawl-label');
const btnStopCrawl = document.getElementById('btn-stop-crawl');
const btnScan = document.getElementById('btn-scan');
const btnScanText = document.getElementById('btn-scan-text');
const thCheckbox = document.getElementById('th-checkbox');
const visibleCountSpan = document.getElementById('visible-count');
const statTotalWs = document.getElementById('stat-total-ws');
const statCompletedPdf = document.getElementById('stat-completed-pdf');

// Filter counts
const countFilterAll = document.getElementById('count-filter-all');
const countFilterPending = document.getElementById('count-filter-pending');
const countFilterDone = document.getElementById('count-filter-done');

// Progress & Terminal Elements
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const progressPercent = document.getElementById('progress-percent');
const progressFill = document.getElementById('progress-fill');
const progressSubtext = document.getElementById('progress-subtext');
const terminalWrapper = document.getElementById('terminal-wrapper');
const terminalScreen = document.getElementById('terminal-screen');
const btnToggleTerminal = document.getElementById('btn-toggle-terminal');
const terminalToggleText = document.getElementById('terminal-toggle-text');
const btnClearLogs = document.getElementById('btn-clear-logs');
const btnCopyLogs = document.getElementById('btn-copy-logs');

// Downloads Library Elements
const downloadsList = document.getElementById('downloads-list');
const downloadCountSpan = document.getElementById('download-count');
const btnRefreshDownloads = document.getElementById('btn-refresh-downloads');
const dlCountAll = document.getElementById('dl-count-all');
const dlCountBundle = document.getElementById('dl-count-bundle');
const dlCountPdf = document.getElementById('dl-count-pdf');
const dlCountMd = document.getElementById('dl-count-md');

// Output Directory Elements
const inputOutputDir = document.getElementById('input-output-dir');
const btnBrowseDir = document.getElementById('btn-browse-dir');
const btnSaveDir = document.getElementById('btn-save-dir');
const btnOpenDir = document.getElementById('btn-open-dir');
const footerOutputDir = document.getElementById('footer-output-dir');

document.addEventListener('DOMContentLoaded', () => {
  loadCatalog();
  loadDownloads();
  connectSSE();
  bindEvents();
});

function formatCategoryName(raw) {
  if (!raw) return 'Mặc định';
  return String(raw).replace(/^\d+\.\s*/, '').trim() || raw;
}

function resetScanButton() {
  const icon = btnScan ? btnScan.querySelector('.icon') : null;
  if (icon) icon.classList.remove('spinning');
  if (btnScanText) btnScanText.textContent = 'Làm mới danh mục';
  if (btnScan) btnScan.disabled = false;
}

function bindEvents() {
  searchInput.addEventListener('input', () => {
    btnClearSearch.style.display = searchInput.value ? 'block' : 'none';
    renderWorkshops();
  });

  btnClearSearch.addEventListener('click', () => {
    searchInput.value = '';
    btnClearSearch.style.display = 'none';
    renderWorkshops();
    searchInput.focus();
  });

  document.querySelectorAll('.btn-group-toggle .btn-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-group-toggle .btn-toggle').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentStatusFilter = btn.dataset.status;
      renderWorkshops();
    });
  });

  document.querySelectorAll('.dl-filter-pills .dl-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.dl-filter-pills .dl-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentDlFilter = btn.dataset.dlFilter;
      renderDownloads();
    });
  });

  btnDeselectAll.addEventListener('click', () => {
    selectedIds.clear();
    updateSelectionUI();
    renderWorkshops();
  });

  thCheckbox.addEventListener('change', (e) => {
    const visible = getFilteredWorkshops();
    if (e.target.checked) {
      visible.forEach(w => selectedIds.add(w.id));
    } else {
      visible.forEach(w => selectedIds.delete(w.id));
    }
    updateSelectionUI();
    renderWorkshops();
  });

  formatSelect.addEventListener('change', updateSelectionUI);
  if (chkBundle) chkBundle.addEventListener('change', updateSelectionUI);
  btnStartCrawl.addEventListener('click', startSelectedCrawl);
  if (btnCrawlAll) {
    btnCrawlAll.addEventListener('click', startAllCrawl);
  }
  if (btnBundleExisting) {
    btnBundleExisting.addEventListener('click', startBundleOnly);
  }
  btnStopCrawl.addEventListener('click', stopCrawl);

  btnScan.addEventListener('click', async () => {
    if (confirm('Quét lại danh sách workshop từ cloudjourney.awsstudygroup.com?')) {
      const icon = btnScan.querySelector('.icon');
      if (icon) icon.classList.add('spinning');
      if (btnScanText) btnScanText.textContent = 'Đang quét...';
      btnScan.disabled = true;

      try {
        await fetch('/api/scan', { method: 'POST' });
        appendLog('[QUÉT] Đã gửi yêu cầu làm mới danh mục...');
      } catch (e) {
        appendLog(`[LỖI] Không thể quét danh mục: ${e}`, 'ERROR');
        resetScanButton();
      }
    }
  });

  btnToggleTerminal.addEventListener('click', () => {
    const isCollapsed = terminalWrapper.classList.toggle('collapsed');
    btnToggleTerminal.classList.toggle('collapsed', isCollapsed);
    terminalToggleText.textContent = isCollapsed ? 'Hiện nhật ký' : 'Ẩn nhật ký';
  });

  btnClearLogs.addEventListener('click', () => {
    terminalScreen.textContent = '';
  });

  if (btnCopyLogs) {
    btnCopyLogs.addEventListener('click', () => {
      navigator.clipboard.writeText(terminalScreen.textContent).then(() => {
        const orig = btnCopyLogs.textContent;
        btnCopyLogs.textContent = 'Đã chép';
        setTimeout(() => { btnCopyLogs.textContent = orig; }, 1500);
      }).catch(err => {
        console.error('Không thể sao chép:', err);
      });
    });
  }

  btnRefreshDownloads.addEventListener('click', loadDownloads);

  if (btnSaveDir) {
    btnSaveDir.addEventListener('click', () => {
      if (inputOutputDir) applyOutputDir(inputOutputDir.value.trim());
    });
  }
  if (inputOutputDir) {
    inputOutputDir.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        applyOutputDir(inputOutputDir.value.trim());
      }
    });
  }
  if (btnBrowseDir) {
    btnBrowseDir.addEventListener('click', browseOutputDir);
  }
  if (btnOpenDir) {
    btnOpenDir.addEventListener('click', openOutputDir);
  }
}

function syncOutputDirUI(dirPath) {
  if (!dirPath) return;
  if (inputOutputDir) inputOutputDir.value = dirPath;
  if (footerOutputDir) footerOutputDir.textContent = dirPath;
}

async function applyOutputDir(newDir) {
  if (!newDir) return;
  try {
    const res = await fetch('/api/output-dir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ output_dir: newDir }),
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      syncOutputDirUI(data.output_dir);
      appendLog(`[THƯ MỤC] ${data.message}`);
      progressSubtext.textContent = `Đã đổi thư mục lưu sang: ${data.output_dir}`;
      loadDownloads();
    } else {
      alert(data.message || 'Không thể đổi thư mục lưu.');
    }
  } catch (err) {
    appendLog(`[LỖI] Không thể đổi thư mục: ${err}`);
  }
}

async function browseOutputDir() {
  if (btnBrowseDir) {
    btnBrowseDir.disabled = true;
    btnBrowseDir.textContent = 'Đang mở...';
  }
  try {
    const res = await fetch('/api/output-dir/browse', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      syncOutputDirUI(data.output_dir);
      appendLog(`[THƯ MỤC] ${data.message}`);
      progressSubtext.textContent = `Đã chọn thư mục lưu: ${data.output_dir}`;
      loadDownloads();
    } else if (!res.ok) {
      alert(data.message || 'Không thể mở cửa sổ chọn thư mục.');
    }
  } catch (err) {
    appendLog(`[LỖI] Không thể mở hộp thoại chọn thư mục: ${err}`);
  } finally {
    if (btnBrowseDir) {
      btnBrowseDir.disabled = false;
      btnBrowseDir.textContent = 'Chọn thư mục...';
    }
  }
}

async function openOutputDir() {
  try {
    if (inputOutputDir && inputOutputDir.value.trim()) {
      await fetch('/api/output-dir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir: inputOutputDir.value.trim() }),
      });
    }
    const res = await fetch('/api/output-dir/open', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      alert(data.message || 'Không thể mở thư mục trên máy.');
    }
  } catch (err) {
    console.error('Lỗi mở thư mục:', err);
  }
}

async function loadCatalog() {
  try {
    const res = await fetch('/api/catalog');
    const data = await res.json();
    allWorkshops = data.workshops || [];
    categories = data.categories || [];
    statTotalWs.textContent = allWorkshops.length;

    updateFilterCounts();
    renderCategoryPills();
    renderWorkshops();
  } catch (err) {
    appendLog(`[LỖI] Không thể tải danh mục: ${err}`, 'ERROR');
  }
}

function updateFilterCounts() {
  const total = allWorkshops.length;
  const done = filesByWorkshop.size;
  const pending = Math.max(0, total - done);

  if (countFilterAll) countFilterAll.textContent = total;
  if (countFilterPending) countFilterPending.textContent = pending;
  if (countFilterDone) countFilterDone.textContent = done;
  if (statCompletedPdf) statCompletedPdf.textContent = done;
}

function renderCategoryPills() {
  categoryPillsContainer.innerHTML = '';

  const allBtn = document.createElement('button');
  allBtn.className = `pill ${currentCategory === 'all' ? 'active' : ''}`;
  allBtn.dataset.cat = 'all';
  allBtn.textContent = `Tất cả (${allWorkshops.length})`;
  allBtn.onclick = () => selectCategory('all');
  categoryPillsContainer.appendChild(allBtn);

  categories.forEach(cat => {
    const count = allWorkshops.filter(w => w.category === cat.title).length;
    const btn = document.createElement('button');
    btn.className = `pill ${currentCategory === cat.title ? 'active' : ''}`;
    btn.dataset.cat = cat.title;
    btn.textContent = `${formatCategoryName(cat.title)} (${count})`;
    btn.onclick = () => selectCategory(cat.title);
    categoryPillsContainer.appendChild(btn);
  });
}

function selectCategory(cat) {
  currentCategory = cat;
  document.querySelectorAll('.category-pills .pill').forEach(p => {
    p.classList.toggle('active', p.dataset.cat === cat);
  });
  renderWorkshops();
}

function getFilteredWorkshops() {
  const query = searchInput.value.trim().toLowerCase();
  return allWorkshops.filter(ws => {
    const matchCat = currentCategory === 'all' || ws.category === currentCategory;
    const matchSearch = !query ||
      ws.id.toLowerCase().includes(query) ||
      ws.title.toLowerCase().includes(query) ||
      (ws.subcategory && ws.subcategory.toLowerCase().includes(query));

    const hasFile = filesByWorkshop.has(ws.id);
    let matchStatus = true;
    if (currentStatusFilter === 'pending') {
      matchStatus = !hasFile;
    } else if (currentStatusFilter === 'done') {
      matchStatus = hasFile;
    }

    return matchCat && matchSearch && matchStatus;
  });
}

function encodePath(relPath) {
  if (!relPath) return '';
  return String(relPath)
    .replace(/\\/g, '/')
    .split('/')
    .map(seg => encodeURIComponent(seg))
    .join('/');
}

function renderWorkshops() {
  const filtered = getFilteredWorkshops();
  visibleCountSpan.textContent = filtered.length;
  tbody.innerHTML = '';

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 32px 12px; color: var(--text-muted);">Không có workshop nào khớp với bộ lọc hiện tại.</td></tr>`;
    updateSelectionUI();
    return;
  }

  filtered.forEach(ws => {
    const tr = document.createElement('tr');
    const isSelected = selectedIds.has(ws.id);
    const wsFiles = filesByWorkshop.get(ws.id) || [];
    const catClean = formatCategoryName(ws.category);
    const showSubcat = ws.subcategory && ws.subcategory.toLowerCase() !== catClean.toLowerCase();

    let badgesHtml = `<span class="status-empty">Chưa tải</span>`;
    if (wsFiles.length > 0) {
      const seenBadges = new Set();
      const parts = [];
      wsFiles.forEach(f => {
        const isMd = f.filename.endsWith('.md');
        const fmt = isMd ? 'MD' : 'PDF';
        const lang = (f.lang || 'VI').toUpperCase();
        const key = `${lang}-${fmt}`;
        if (!seenBadges.has(key)) {
          seenBadges.add(key);
          const enc = encodePath(f.relative_path);
          parts.push(`<a href="/preview/${enc}" target="_blank" class="fmt-badge ${isMd ? 'md' : 'pdf'}" title="Xem ${escapeHtml(f.filename)}">${lang}·${fmt}</a>`);
        }
      });
      badgesHtml = `<div class="format-badges">${parts.join('')}</div>`;
    }

    const primaryFile = wsFiles.find(f => f.filename.endsWith('.pdf')) || wsFiles[0];
    const primaryEnc = primaryFile ? encodePath(primaryFile.relative_path) : '';

    tr.innerHTML = `
      <td>
        <input type="checkbox" class="ws-cb" data-id="${escapeHtml(ws.id)}" ${isSelected ? 'checked' : ''}>
      </td>
      <td>
        <span class="id-code">${escapeHtml(ws.id)}</span>
      </td>
      <td>
        <a class="ws-title-link" href="${escapeHtml(ws.url)}" target="_blank" rel="noopener">${escapeHtml(ws.title)}</a>
        ${showSubcat ? `<div class="ws-sub">${escapeHtml(ws.subcategory)}</div>` : ''}
      </td>
      <td>
        <span class="cat-tag">${escapeHtml(catClean)}</span>
      </td>
      <td>
        ${badgesHtml}
      </td>
      <td style="text-align: right;">
        <div class="row-actions-group">
          ${primaryFile ? `
            <a href="/download/${primaryEnc}" class="btn btn-outline btn-sm" title="Tải ${escapeHtml(primaryFile.filename)}">
              Tải về
            </a>
            <button class="btn btn-outline btn-sm btn-crawl-single" data-id="${escapeHtml(ws.id)}" title="Cào cập nhật lại bài này">
              Cào lại
            </button>
          ` : `
            <button class="btn btn-outline btn-sm btn-crawl-single" data-id="${escapeHtml(ws.id)}" title="Tải bài này">
              Tải bài này
            </button>
          `}
        </div>
      </td>
    `;

    const cb = tr.querySelector('.ws-cb');
    cb.addEventListener('change', (e) => {
      if (e.target.checked) selectedIds.add(ws.id);
      else selectedIds.delete(ws.id);
      updateSelectionUI();
    });

    tr.querySelector('.btn-crawl-single').addEventListener('click', () => {
      startCrawlWithIds([ws.id], false);
    });

    tbody.appendChild(tr);
  });

  updateSelectionUI();
}

function updateSelectionUI() {
  const count = selectedIds.size;
  const visible = getFilteredWorkshops();
  const allVisibleSelected = visible.length > 0 && visible.every(w => selectedIds.has(w.id));
  thCheckbox.checked = allVisibleSelected;

  if (btnDeselectAll) {
    btnDeselectAll.style.display = count > 0 ? 'inline-flex' : 'none';
    btnDeselectAll.innerHTML = `Bỏ chọn (<span id="selected-count">${count}</span>)`;
  }

  const format = formatSelect ? formatSelect.value : 'both';
  let formatText = 'Markdown + PDF';
  if (format === 'md') formatText = 'Markdown';
  else if (format === 'pdf') formatText = 'PDF';

  const bundleChecked = chkBundle ? chkBundle.checked : false;
  const bundleSuffix = bundleChecked ? ' · Gộp 1 file' : '';

  if (btnStartCrawlLabel) {
    btnStartCrawlLabel.textContent = count > 0
      ? `Tải ${count} bài đã chọn (${formatText}${bundleSuffix})`
      : 'Chọn bài để tải';
  }

  if (btnBundleExisting) {
    btnBundleExisting.textContent = count > 0
      ? `Gộp ${count} bài đã chọn thành 1 file`
      : `Gộp 1 file từ bài đã tải (${filesByWorkshop.size})`;
    btnBundleExisting.disabled = isRunning || (count === 0 && filesByWorkshop.size === 0);
  }

  btnStartCrawl.disabled = isRunning || count === 0;
  if (btnCrawlAll) btnCrawlAll.disabled = isRunning;
}

async function startSelectedCrawl() {
  if (selectedIds.size === 0) return;
  const bundle = chkBundle ? chkBundle.checked : false;
  startCrawlWithIds(Array.from(selectedIds), bundle);
}

async function startAllCrawl() {
  const total = allWorkshops.length || 127;
  const bundle = chkBundle ? chkBundle.checked : true;
  const msg = bundle
    ? `Tải toàn bộ ${total} workshop và gộp chung vào 1 file duy nhất (FCAJ_ALL)?`
    : `Bạn có chắc muốn tải toàn bộ ${total} workshop không?`;
  if (!confirm(msg)) return;
  startCrawlWithIds([], bundle);
}

async function startBundleOnly() {
  const lang = langSelect.value;
  const format = formatSelect.value;
  const ids = Array.from(selectedIds);

  // Check if any selected workshop is not yet downloaded
  const missingIds = ids.filter(id => !filesByWorkshop.has(id));
  let crawlIfMissing = false;
  if (missingIds.length > 0) {
    crawlIfMissing = confirm(
      `Có ${missingIds.length}/${ids.length} bài đã chọn chưa được tải về máy.\n` +
      `Bạn có muốn tự động tải các bài này rồi gộp thành 1 file duy nhất không?`
    );
    if (!crawlIfMissing) return;
  }

  setRunningState(true);
  statusText.textContent = 'Đang gộp thành 1 file duy nhất...';
  progressSubtext.textContent = 'Đang tổng hợp nội dung các workshop...';

  try {
    const res = await fetch('/api/bundle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ids: ids.length > 0 ? ids : null,
        lang: lang,
        format: format,
        crawl_if_missing: crawlIfMissing,
        output_dir: inputOutputDir ? inputOutputDir.value.trim() : undefined,
      }),
    });
    const data = await res.json();
    if (data.status === 'started') {
      if (data.output_dir) syncOutputDirUI(data.output_dir);
      appendLog(`[GỘP FILE] ${data.message}`);
    } else {
      appendLog(`[LỖI] ${data.message}`, 'ERROR');
      setRunningState(false);
    }
  } catch (err) {
    appendLog(`[LỖI] Kết nối API thất bại: ${err}`, 'ERROR');
    setRunningState(false);
  }
}

async function startCrawlWithIds(ids, bundle = false) {
  const lang = langSelect.value;
  const format = formatSelect.value;
  setRunningState(true);

  try {
    const res = await fetch('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ids: ids.length > 0 ? ids : null,
        lang: lang,
        format: format,
        bundle: bundle,
        output_dir: inputOutputDir ? inputOutputDir.value.trim() : undefined,
      })
    });
    const data = await res.json();
    if (data.status === 'started') {
      if (data.output_dir) syncOutputDirUI(data.output_dir);
      appendLog(`[BẮT ĐẦU] ${data.message}`);
    } else {
      appendLog(`[LỖI] ${data.message}`, 'ERROR');
      setRunningState(false);
    }
  } catch (err) {
    appendLog(`[LỖI] Kết nối API thất bại: ${err}`, 'ERROR');
    setRunningState(false);
  }
}

async function stopCrawl() {
  try {
    await fetch('/api/stop', { method: 'POST' });
    appendLog('[DỪNG] Đã yêu cầu dừng tiến trình...', 'WARNING');
  } catch (err) {
    console.error(err);
  }
}

function setRunningState(running, indicatorState = null) {
  isRunning = running;
  const stateCls = indicatorState || (running ? 'running' : 'done');
  statusDot.className = `status-indicator ${stateCls}`;
  btnStartCrawl.style.display = running ? 'none' : 'inline-flex';
  if (btnCrawlAll) btnCrawlAll.style.display = running ? 'none' : 'inline-flex';
  if (btnBundleExisting) btnBundleExisting.style.display = running ? 'none' : 'inline-flex';
  btnStopCrawl.style.display = running ? 'inline-flex' : 'none';
  updateSelectionUI();
}

async function loadDownloads() {
  try {
    const res = await fetch('/api/downloads');
    const data = await res.json();
    allDownloadedFiles = data.files || [];

    filesByWorkshop.clear();
    allDownloadedFiles.forEach(f => {
      if (f.is_bundle) return;
      if (!filesByWorkshop.has(f.id)) {
        filesByWorkshop.set(f.id, []);
      }
      filesByWorkshop.get(f.id).push(f);
    });

    const total = allDownloadedFiles.length;
    const bundleCount = allDownloadedFiles.filter(f => f.is_bundle).length;
    const pdfCount = allDownloadedFiles.filter(f => f.filename.endsWith('.pdf')).length;
    const mdCount = allDownloadedFiles.filter(f => f.filename.endsWith('.md')).length;

    if (downloadCountSpan) downloadCountSpan.textContent = total;
    if (dlCountAll) dlCountAll.textContent = total;
    if (dlCountBundle) dlCountBundle.textContent = bundleCount;
    if (dlCountPdf) dlCountPdf.textContent = pdfCount;
    if (dlCountMd) dlCountMd.textContent = mdCount;

    updateFilterCounts();
    renderDownloads();
    renderWorkshops();
  } catch (err) {
    console.error('Lỗi khi tải danh sách tệp:', err);
  }
}

function renderDownloads() {
  let files = allDownloadedFiles;
  if (currentDlFilter === 'bundle') {
    files = files.filter(f => f.is_bundle);
  } else if (currentDlFilter === 'pdf') {
    files = files.filter(f => f.filename.endsWith('.pdf'));
  } else if (currentDlFilter === 'md') {
    files = files.filter(f => f.filename.endsWith('.md'));
  }

  if (files.length === 0) {
    downloadsList.innerHTML = `<div class="empty-state">Chưa có tệp nào trong bộ lọc này.</div>`;
    return;
  }

  downloadsList.innerHTML = '';
  files.forEach(file => {
    const isMd = file.filename.endsWith('.md');
    const isBundle = Boolean(file.is_bundle);
    const encodedRel = encodePath(file.relative_path);
    const lang = (file.lang || 'VI').toUpperCase();
    const item = document.createElement('div');
    item.className = `download-item ${isBundle ? 'bundle-item' : ''}`;
    item.innerHTML = `
      <div class="dl-info">
        <div class="dl-name-row">
          ${isBundle ? `<span class="fmt-badge bundle">FILE GỘP</span>` : ''}
          <span class="fmt-badge ${isMd ? 'md' : 'pdf'}">${lang}·${isMd ? 'MD' : 'PDF'}</span>
          ${!isBundle ? `<span class="id-code">${escapeHtml(file.id)}</span>` : ''}
          <span class="dl-name" title="${escapeHtml(file.filename)}">${escapeHtml(file.filename)}</span>
        </div>
        <div class="dl-meta">
          ${file.size_mb} MB · ${escapeHtml(file.updated_at)}
        </div>
      </div>
      <div class="dl-actions">
        <a href="/preview/${encodedRel}" target="_blank" class="btn btn-outline btn-sm" title="Xem trên trình duyệt">
          Xem
        </a>
        <a href="/download/${encodedRel}" class="btn btn-outline btn-sm" title="Tải tệp về máy">
          Tải
        </a>
        ${isMd ? `<a href="/download-zip/${encodedRel}" class="btn btn-outline btn-sm" title="Tải kèm thư mục ảnh (.zip) để chép sang máy khác không mất hình">ZIP</a>` : ''}
        <button class="btn-delete-file" data-path="${escapeHtml(file.relative_path)}" data-name="${escapeHtml(file.filename)}" title="Xóa tệp này">
          ✕
        </button>
      </div>
    `;

    const delBtn = item.querySelector('.btn-delete-file');
    delBtn.addEventListener('click', async () => {
      if (!confirm(`Xóa tệp "${file.filename}"?`)) return;
      try {
        const res = await fetch(`/api/downloads/${encodedRel}`, { method: 'DELETE' });
        if (res.ok) {
          loadDownloads();
        }
      } catch (e) {
        console.error('Lỗi khi xóa tệp:', e);
      }
    });

    downloadsList.appendChild(item);
  });
}

function connectSSE() {
  const eventSource = new EventSource('/api/stream');

  eventSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);

      if (payload.type === 'init') {
        const state = payload.state;
        if (state.output_dir) {
          syncOutputDirUI(state.output_dir);
        }
        if (state.is_running) {
          setRunningState(true);
        }
        if (state.recent_logs && state.recent_logs.length > 0) {
          terminalScreen.textContent = '';
          state.recent_logs.forEach(l => appendLog(l));
        }
      }
      else if (payload.type === 'progress') {
        const d = payload.data;
        statusText.textContent = `[${d.index}/${d.total}] #${d.workshop_id} — ${d.title}`;
        progressPercent.textContent = `${d.progress}%`;
        progressFill.style.width = `${d.progress}%`;
        progressSubtext.textContent = d.step;
        setRunningState(true);
      }
      else if (payload.type === 'log') {
        appendLog(payload.message);
      }
      else if (payload.type === 'scan_progress') {
        statusText.textContent = payload.message;
        progressPercent.textContent = `${payload.percent}%`;
        progressFill.style.width = `${payload.percent}%`;
      }
      else if (payload.type === 'scan_complete') {
        appendLog(`[QUÉT XONG] Tìm thấy ${payload.total} workshops.`);
        resetScanButton();
        loadCatalog();
      }
      else if (payload.type === 'scan_error') {
        resetScanButton();
      }
      else if (payload.type === 'crawl_finished') {
        const s = payload.summary || {};
        const processed = s.processed ?? 0;
        const failed = s.failed ?? 0;
        const total = s.total ?? (processed + failed);
        const bundleFiles = s.bundle_files || [];

        progressPercent.textContent = '100%';
        progressFill.style.width = '100%';

        if (failed > 0 && processed === 0) {
          setRunningState(false, 'error');
          statusText.textContent = `Thất bại (${failed}/${total} bài)`;
          progressSubtext.textContent = 'Có lỗi xảy ra khi xuất tệp. Bấm "Hiện nhật ký" để xem nguyên nhân.';
          terminalWrapper.classList.remove('collapsed');
          btnToggleTerminal.classList.remove('collapsed');
          terminalToggleText.textContent = 'Ẩn nhật ký';
        } else if (failed > 0) {
          setRunningState(false, 'warning');
          statusText.textContent = `Hoàn tất một phần (${processed} thành công, ${failed} lỗi)`;
          progressSubtext.textContent = 'Một số tệp gặp lỗi khi xuất. Kiểm tra nhật ký để biết chi tiết.';
        } else {
          setRunningState(false, 'done');
          statusText.textContent = 'Hoàn tất';
          if (bundleFiles.length > 0) {
            progressSubtext.textContent = `Đã tạo tệp gộp duy nhất (${processed} workshop) trong mục "Tệp đã xuất".`;
          } else {
            progressSubtext.textContent = `Đã xuất thành công ${processed} bài vào thư mục output_fcaj.`;
          }
        }
        loadDownloads();
      }
    } catch (e) {
      console.error('SSE parse error:', e);
    }
  };

  eventSource.onerror = () => {
    console.warn('SSE connection disconnected. Retrying...');
  };
}

function appendLog(msg) {
  const line = typeof msg === 'string' ? msg : JSON.stringify(msg);
  terminalScreen.textContent += line + '\n';
  terminalScreen.scrollTop = terminalScreen.scrollHeight;
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
