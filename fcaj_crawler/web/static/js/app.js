// FCAJ Crawler Dashboard Client

let allWorkshops = [];
let categories = [];
let selectedIds = new Set();
let currentCategory = 'all';
let isRunning = false;
let completedPdfs = new Map(); // id -> file info

// DOM Elements
const tbody = document.getElementById('workshops-tbody');
const categoryPillsContainer = document.getElementById('category-pills');
const searchInput = document.getElementById('input-search');
const langSelect = document.getElementById('select-lang');
const btnSelectAll = document.getElementById('btn-select-all');
const btnDeselectAll = document.getElementById('btn-deselect-all');
const btnStartCrawl = document.getElementById('btn-start-crawl');
const btnStopCrawl = document.getElementById('btn-stop-crawl');
const btnScan = document.getElementById('btn-scan');
const thCheckbox = document.getElementById('th-checkbox');
const selectedCountSpan = document.getElementById('selected-count');
const visibleCountSpan = document.getElementById('visible-count');
const statTotalWs = document.getElementById('stat-total-ws');
const statCompletedPdf = document.getElementById('stat-completed-pdf');

// Progress & Terminal Elements
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const progressPercent = document.getElementById('progress-percent');
const progressFill = document.getElementById('progress-fill');
const progressSubtext = document.getElementById('progress-subtext');
const terminalScreen = document.getElementById('terminal-screen');
const btnClearLogs = document.getElementById('btn-clear-logs');
const downloadsList = document.getElementById('downloads-list');
const downloadCountSpan = document.getElementById('download-count');
const btnRefreshDownloads = document.getElementById('btn-refresh-downloads');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  loadCatalog();
  loadDownloads();
  connectSSE();
  bindEvents();
});

function bindEvents() {
  searchInput.addEventListener('input', renderWorkshops);

  btnSelectAll.addEventListener('click', () => {
    getFilteredWorkshops().forEach(w => selectedIds.add(w.id));
    updateSelectionUI();
  });

  btnDeselectAll.addEventListener('click', () => {
    selectedIds.clear();
    updateSelectionUI();
  });

  thCheckbox.addEventListener('change', (e) => {
    const visible = getFilteredWorkshops();
    if (e.target.checked) {
      visible.forEach(w => selectedIds.add(w.id));
    } else {
      visible.forEach(w => selectedIds.delete(w.id));
    }
    updateSelectionUI();
  });

  btnStartCrawl.addEventListener('click', startCrawl);
  btnStopCrawl.addEventListener('click', stopCrawl);

  btnScan.addEventListener('click', () => {
    if (confirm('Quét lại toàn bộ catalog từ cloudjourney.awsstudygroup.com?')) {
      fetch('/api/scan', { method: 'POST' });
    }
  });

  btnClearLogs.addEventListener('click', () => {
    terminalScreen.textContent = '';
  });

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

    renderCategoryPills();
    renderWorkshops();
  } catch (err) {
    appendLog(`[LỖI] Không thể tải catalog: ${err}`, 'ERROR');
  }
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
  return allWorkshops.filter(w => {
    const matchCat = currentCategory === 'all' || w.category === currentCategory;
    const matchSearch = !query || 
      w.id.toLowerCase().includes(query) || 
      w.title.toLowerCase().includes(query) || 
      (w.subcategory && w.subcategory.toLowerCase().includes(query));
    return matchCat && matchSearch;
  });
}

// Render Table
function renderWorkshops() {
  const filtered = getFilteredWorkshops();
  visibleCountSpan.textContent = filtered.length;
  tbody.innerHTML = '';

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 30px; color: var(--text-muted);">Không tìm thấy workshop nào phù hợp.</td></tr>`;
    return;
  }

  filtered.forEach(ws => {
    const tr = document.createElement('tr');
    const isSelected = selectedIds.has(ws.id);
    const hasPdf = completedPdfs.has(ws.id);

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
        ${hasPdf 
          ? `<span class="badge-status done">✓ Đã có PDF</span>` 
          : `<span class="badge-status not-started">Chưa cào</span>`
        }
      </td>
      <td style="text-align: right;">
        <button class="btn btn-outline btn-sm btn-crawl-single" data-id="${ws.id}">
          Cào bài này
        </button>
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
  selectedCountSpan.textContent = selectedIds.size;
  const visible = getFilteredWorkshops();
  const allVisibleSelected = visible.length > 0 && visible.every(w => selectedIds.has(w.id));
  thCheckbox.checked = allVisibleSelected;

  btnStartCrawl.disabled = isRunning;
  btnStartCrawl.style.opacity = isRunning ? '0.6' : '1';
}

// Start Crawl
async function startCrawl() {
  if (selectedIds.size === 0) {
    if (!confirm('Bạn chưa chọn workshop nào. Bạn có muốn cào TOÀN BỘ 127+ workshop không?')) {
      return;
    }
  }

  const ids = Array.from(selectedIds);
  startCrawlWithIds(ids);
}

async function startCrawlWithIds(ids) {
  const lang = langSelect.value;
  setRunningState(true);

  try {
    const res = await fetch('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: ids.length > 0 ? ids : null, lang: lang })
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
    const files = data.files || [];

    completedPdfs.clear();
    files.forEach(f => completedPdfs.set(f.id, f));
    statCompletedPdf.textContent = completedPdfs.size;
    downloadCountSpan.textContent = files.length;

    renderDownloads(files);
    renderWorkshops(); // re-render to update badges
  } catch (err) {
    console.error(err);
  }
}

function renderDownloads(files) {
  if (files.length === 0) {
    downloadsList.innerHTML = `<div class="empty-state">Chưa có file PDF nào được xuất. Hãy chọn workshop và bắt đầu cào!</div>`;
    return;
  }

  downloadsList.innerHTML = '';
  files.forEach(file => {
    const item = document.createElement('div');
    item.className = 'download-item';
    item.innerHTML = `
      <div class="dl-info">
        <div class="dl-name" title="${escapeHtml(file.filename)}">
          <span class="id-badge">${file.id}</span> ${escapeHtml(file.filename)}
        </div>
        <div class="dl-meta">
          Dung lượng: <strong>${file.size_mb} MB</strong> • Cập nhật: ${file.updated_at}
        </div>
      </div>
      <div class="dl-actions">
        <a href="/preview/${file.relative_path}" target="_blank" class="btn btn-outline btn-sm" title="Xem trực tiếp trên trình duyệt">
          Xem
        </a>
        <a href="/download/${file.relative_path}" class="btn btn-primary btn-sm" title="Tải file PDF về máy">
          Tải PDF
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
        progressSubtext.textContent = 'Tất cả file PDF đã được tạo thành công trong thư mục output_fcaj.';
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
