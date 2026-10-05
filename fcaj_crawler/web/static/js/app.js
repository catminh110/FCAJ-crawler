// FCAJ Crawler Dashboard Client - Enhanced UI & Credit Management

let allWorkshops = [];
let categories = [];
let selectedIds = new Set();
let currentCategory = 'all';
let currentStatusFilter = 'all'; // 'all' | 'pending' | 'done'
let currentDlFilter = 'all'; // 'all' | 'pdf' | 'md'
let isRunning = false;
let completedPdfs = new Map(); // id -> file info
let allDownloadedFiles = [];

// DOM Elements
const tbody = document.getElementById('workshops-tbody');
const categoryPillsContainer = document.getElementById('category-pills');
const searchInput = document.getElementById('input-search');
const btnClearSearch = document.getElementById('btn-clear-search');
const langSelect = document.getElementById('select-lang');
const formatSelect = document.getElementById('select-format');
const btnSelectAll = document.getElementById('btn-select-all');
const btnDeselectAll = document.getElementById('btn-deselect-all');
const btnSelectVisible = document.getElementById('btn-select-visible');
const btnStartCrawl = document.getElementById('btn-start-crawl');
const btnStartCrawlLabel = document.getElementById('btn-start-crawl-label');
const btnStopCrawl = document.getElementById('btn-stop-crawl');
const btnScan = document.getElementById('btn-scan');
const btnScanText = document.getElementById('btn-scan-text');
const thCheckbox = document.getElementById('th-checkbox');
const selectedCountSpan = document.getElementById('selected-count');
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
const dlCountPdf = document.getElementById('dl-count-pdf');
const dlCountMd = document.getElementById('dl-count-md');

// Advisory Banner
const budgetAdvisoryCard = document.querySelector('.budget-advisory-card');
const btnCloseAdvisory = document.getElementById('btn-close-advisory');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  initAdvisoryState();
  loadCatalog();
  loadDownloads();
  connectSSE();
  bindEvents();
});

function initAdvisoryState() {
  if (btnCloseAdvisory && budgetAdvisoryCard) {
    if (localStorage.getItem('fcaj_advisory_hidden') === 'true') {
      budgetAdvisoryCard.style.display = 'none';
    }
    btnCloseAdvisory.addEventListener('click', () => {
      budgetAdvisoryCard.style.display = 'none';
      localStorage.setItem('fcaj_advisory_hidden', 'true');
    });
  }
}

function bindEvents() {
  // Search
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

  // Status Filter Tabs
  document.querySelectorAll('.btn-group-toggle .btn-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-group-toggle .btn-toggle').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentStatusFilter = btn.dataset.status;
      renderWorkshops();
    });
  });

  // Downloads Filter Tabs
  document.querySelectorAll('.dl-filter-pills .dl-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.dl-filter-pills .dl-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentDlFilter = btn.dataset.dlFilter;
      renderDownloads();
    });
  });

  // Select / Deselect
  btnSelectAll.addEventListener('click', () => {
    allWorkshops.forEach(w => selectedIds.add(w.id));
    updateSelectionUI();
    renderWorkshops();
  });

  btnDeselectAll.addEventListener('click', () => {
    selectedIds.clear();
    updateSelectionUI();
    renderWorkshops();
  });

  if (btnSelectVisible) {
    btnSelectVisible.addEventListener('click', () => {
      getFilteredWorkshops().forEach(w => selectedIds.add(w.id));
      updateSelectionUI();
      renderWorkshops();
    });
  }

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
  btnStartCrawl.addEventListener('click', startCrawl);
  btnStopCrawl.addEventListener('click', stopCrawl);

  // Scan Catalog
  btnScan.addEventListener('click', async () => {
    if (confirm('Quét lại toàn bộ catalog từ cloudjourney.awsstudygroup.com? Thao tác này mất ~5 giây.')) {
      const icon = btnScan.querySelector('.icon');
      if (icon) icon.classList.add('spinning');
      if (btnScanText) btnScanText.textContent = 'Đang quét...';
      btnScan.disabled = true;

      try {
        await fetch('/api/scan', { method: 'POST' });
        appendLog('[QUÉT] Đã gửi yêu cầu quét catalog mới...');
      } catch (e) {
        appendLog(`[LỖI] Quét catalog thất bại: ${e}`, 'ERROR');
      } finally {
        setTimeout(() => {
          if (icon) icon.classList.remove('spinning');
          if (btnScanText) btnScanText.textContent = 'Quét Catalog';
          btnScan.disabled = false;
        }, 1500);
      }
    }
  });

  // Terminal Controls
  btnToggleTerminal.addEventListener('click', () => {
    const isCollapsed = terminalWrapper.classList.toggle('collapsed');
    btnToggleTerminal.classList.toggle('collapsed', isCollapsed);
    terminalToggleText.textContent = isCollapsed ? 'Mở rộng Log' : 'Thu gọn Log';
  });

  btnClearLogs.addEventListener('click', () => {
    terminalScreen.textContent = '';
  });

  if (btnCopyLogs) {
    btnCopyLogs.addEventListener('click', () => {
      navigator.clipboard.writeText(terminalScreen.textContent).then(() => {
        const orig = btnCopyLogs.textContent;
        btnCopyLogs.textContent = 'Đã chép!';
        setTimeout(() => { btnCopyLogs.textContent = orig; }, 1500);
      }).catch(err => {
        console.error('Không thể sao chép log:', err);
      });
    });
  }

  btnRefreshDownloads.addEventListener('click', loadDownloads);
}

// Load Catalog
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
    appendLog(`[LỖI] Không thể tải catalog: ${err}`, 'ERROR');
  }
}

function updateFilterCounts() {
  const total = allWorkshops.length;
  const done = completedPdfs.size;
  const pending = Math.max(0, total - done);

  if (countFilterAll) countFilterAll.textContent = total;
  if (countFilterPending) countFilterPending.textContent = pending;
  if (countFilterDone) countFilterDone.textContent = done;
  if (statCompletedPdf) statCompletedPdf.textContent = done;
}

// Category Pills
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
    btn.textContent = `${cat.title} (${count})`;
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
    
    // Status Filter
    const hasFile = completedPdfs.has(ws.id);
    let matchStatus = true;
    if (currentStatusFilter === 'pending') {
      matchStatus = !hasFile;
    } else if (currentStatusFilter === 'done') {
      matchStatus = hasFile;
    }

    return matchCat && matchSearch && matchStatus;
  });
}

// Render Table
function renderWorkshops() {
  const filtered = getFilteredWorkshops();
  visibleCountSpan.textContent = filtered.length;
  tbody.innerHTML = '';

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 36px 12px; color: var(--text-muted);">Không tìm thấy workshop nào phù hợp với bộ lọc hiện tại.</td></tr>`;
    updateSelectionUI();
    return;
  }

  filtered.forEach(ws => {
    const tr = document.createElement('tr');
    const isSelected = selectedIds.has(ws.id);
    const completedInfo = completedPdfs.get(ws.id);

    tr.innerHTML = `
      <td>
        <input type="checkbox" class="ws-cb" data-id="${ws.id}" ${isSelected ? 'checked' : ''}>
      </td>
      <td>
        <span class="id-badge">${ws.id}</span>
      </td>
      <td>
        <div class="ws-title">${escapeHtml(ws.title)}</div>
        <a class="ws-link" href="${ws.url}" target="_blank">${ws.domain} ↗</a>
      </td>
      <td>
        <span class="cat-tag">${escapeHtml(ws.category || 'Mặc định')}</span>
        ${ws.subcategory ? `<br><small style="color: var(--text-muted); font-size: 0.72rem;">${escapeHtml(ws.subcategory)}</small>` : ''}
      </td>
      <td>
        ${completedInfo 
          ? `<span class="badge-status done">✓ Đã có file</span>` 
          : `<span class="badge-status not-started">Chưa cào</span>`
        }
      </td>
      <td style="text-align: right;">
        <div class="row-actions-group">
          ${completedInfo ? `
            <a href="/preview/${completedInfo.relative_path}" target="_blank" class="btn btn-outline btn-sm" title="Xem trước tài liệu">
              Xem
            </a>
            <a href="/download/${completedInfo.relative_path}" class="btn btn-primary btn-sm" title="Tải file về máy">
              Tải
            </a>
            <button class="btn btn-outline btn-sm btn-crawl-single" data-id="${ws.id}" title="Cào cập nhật lại nội dung mới nhất">
              🔄
            </button>
          ` : `
            <button class="btn btn-primary btn-sm btn-crawl-single" data-id="${ws.id}" title="Bắt đầu xuất bản bài này">
              Cào bài này
            </button>
          `}
        </div>
      </td>
    `;

    // Row checkbox
    const cb = tr.querySelector('.ws-cb');
    cb.addEventListener('change', (e) => {
      if (e.target.checked) selectedIds.add(ws.id);
      else selectedIds.delete(ws.id);
      updateSelectionUI();
    });

    // Single crawl button
    tr.querySelector('.btn-crawl-single').addEventListener('click', () => {
      startCrawlWithIds([ws.id]);
    });

    tbody.appendChild(tr);
  });

  updateSelectionUI();
}

function updateSelectionUI() {
  const count = selectedIds.size;
  selectedCountSpan.textContent = count;
  const visible = getFilteredWorkshops();
  const allVisibleSelected = visible.length > 0 && visible.every(w => selectedIds.has(w.id));
  thCheckbox.checked = allVisibleSelected;

  // Dynamic Button Label
  const format = formatSelect ? formatSelect.value : 'both';
  let formatText = 'xuất bản';
  if (format === 'md') formatText = 'xuất Markdown';
  else if (format === 'pdf') formatText = 'xuất PDF';

  if (btnStartCrawlLabel) {
    btnStartCrawlLabel.innerHTML = `Bắt đầu ${formatText} (<span id="selected-count">${count}</span>)`;
  }

  btnStartCrawl.disabled = isRunning;
  btnStartCrawl.style.opacity = isRunning ? '0.6' : '1';
}

// Start Crawl
async function startCrawl() {
  if (selectedIds.size === 0) {
    const proceed = confirm(
      '⚠️ Bạn chưa chọn workshop cụ thể nào.\n\n' +
      'Bạn có muốn cào TOÀN BỘ 127+ workshop không?\n' +
      '(Lưu ý: Quá trình cào PDF toàn bộ sẽ tốn thời gian và tài nguyên CPU máy chủ).'
    );
    if (!proceed) return;
  }

  const ids = Array.from(selectedIds);
  startCrawlWithIds(ids);
}

async function startCrawlWithIds(ids) {
  const lang = langSelect.value;
  const format = formatSelect.value;
  setRunningState(true);

  try {
    const res = await fetch('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: ids.length > 0 ? ids : null, lang: lang, format: format })
    });
    const data = await res.json();
    if (data.status === 'started') {
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

function setRunningState(running) {
  isRunning = running;
  statusDot.className = `status-indicator ${running ? 'running' : 'done'}`;
  btnStartCrawl.style.display = running ? 'none' : 'inline-flex';
  btnStopCrawl.style.display = running ? 'inline-flex' : 'none';
  updateSelectionUI();
}

// Load Downloads
async function loadDownloads() {
  try {
    const res = await fetch('/api/downloads');
    const data = await res.json();
    allDownloadedFiles = data.files || [];

    completedPdfs.clear();
    allDownloadedFiles.forEach(f => completedPdfs.set(f.id, f));

    // Update download counts
    const total = allDownloadedFiles.length;
    const pdfCount = allDownloadedFiles.filter(f => f.filename.endsWith('.pdf')).length;
    const mdCount = allDownloadedFiles.filter(f => f.filename.endsWith('.md')).length;

    if (downloadCountSpan) downloadCountSpan.textContent = total;
    if (dlCountAll) dlCountAll.textContent = total;
    if (dlCountPdf) dlCountPdf.textContent = pdfCount;
    if (dlCountMd) dlCountMd.textContent = mdCount;

    updateFilterCounts();
    renderDownloads();
    renderWorkshops(); // re-render to update badges & table action buttons
  } catch (err) {
    console.error('Lỗi khi tải downloads:', err);
  }
}

function renderDownloads() {
  let files = allDownloadedFiles;
  if (currentDlFilter === 'pdf') {
    files = files.filter(f => f.filename.endsWith('.pdf'));
  } else if (currentDlFilter === 'md') {
    files = files.filter(f => f.filename.endsWith('.md'));
  }

  if (files.length === 0) {
    downloadsList.innerHTML = `<div class="empty-state">Chưa có tài liệu nào trong bộ lọc này. Hãy chọn workshop và bắt đầu cào!</div>`;
    return;
  }

  downloadsList.innerHTML = '';
  files.forEach(file => {
    const isMd = file.filename.endsWith('.md');
    const item = document.createElement('div');
    item.className = 'download-item';
    item.innerHTML = `
      <div class="dl-info">
        <div class="dl-name-row">
          <span class="badge-file-type ${isMd ? 'md' : 'pdf'}">${isMd ? 'MD' : 'PDF'}</span>
          <span class="id-badge">${file.id}</span>
          <span class="dl-name" title="${escapeHtml(file.filename)}">${escapeHtml(file.filename)}</span>
        </div>
        <div class="dl-meta">
          Dung lượng: <strong>${file.size_mb} MB</strong> • Cập nhật: ${file.updated_at}
        </div>
      </div>
      <div class="dl-actions">
        <a href="/preview/${file.relative_path}" target="_blank" class="btn btn-outline btn-sm" title="Xem trực tiếp trên trình duyệt">
          Xem
        </a>
        <a href="/download/${file.relative_path}" class="btn btn-primary btn-sm" title="Tải file về máy">
          Tải
        </a>
      </div>
    `;
    downloadsList.appendChild(item);
  });
}

// Server-Sent Events (SSE)
function connectSSE() {
  const eventSource = new EventSource('/api/stream');

  eventSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);

      if (payload.type === 'init') {
        const state = payload.state;
        if (state.is_running) {
          setRunningState(true);
        }
        if (state.recent_logs) {
          state.recent_logs.forEach(l => appendLog(l));
        }
      } 
      else if (payload.type === 'progress') {
        const d = payload.data;
        statusText.textContent = `[${d.index}/${d.total}] Đang xử lý: #${d.workshop_id} - ${d.title}`;
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
        appendLog(`[QUÉT XONG] Đã tìm thấy tổng cộng ${payload.total} workshops.`);
        loadCatalog();
      } 
      else if (payload.type === 'crawl_finished') {
        setRunningState(false);
        statusText.textContent = 'Hoàn tất quá trình cào!';
        progressPercent.textContent = '100%';
        progressFill.style.width = '100%';
        progressSubtext.textContent = 'Tất cả file tài liệu đã được tạo thành công trong thư mục output_fcaj.';
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

function appendLog(msg, level = 'INFO') {
  const line = typeof msg === 'string' ? msg : JSON.stringify(msg);
  terminalScreen.textContent += line + '\n';
  terminalScreen.scrollTop = terminalScreen.scrollHeight;
}

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
