
// ==================== STATE ====================
// 从当前页面 URL 推断 API 地址（兼容 /vault/、/vault、/vault/index.html）
(function() {
  let p = location.pathname;
  if (!p.endsWith('/')) {
    const seg = p.split('/').pop() || '';
    if (seg.includes('.')) p = p.substring(0, p.lastIndexOf('/') + 1); // 含扩展名 → 是文件路径
    else p += '/'; // 无扩展名 → 目录路径，补斜杠
  }
  window.__API_BASE = location.origin + p;
})();
const API = window.__API_BASE + 'api.php';
const PERSISTENT_TOKEN_KEY = 'vault_token';
const SESSION_TOKEN_KEY = 'vault_session_token';
const REMEMBER_KEY = 'vault_remember';

// 只有勾选「七天免登录」的会话才能跨浏览器重启保存。
// 兼容旧版本：此前所有令牌都写进 localStorage；无 remember 标记的旧令牌
// 会在当前标签页迁移为 sessionStorage，避免继续产生意外的长期免登录。
function restoreStoredToken() {
  const persistentToken = localStorage.getItem(PERSISTENT_TOKEN_KEY) || '';
  const sessionToken = sessionStorage.getItem(SESSION_TOKEN_KEY) || '';
  const isRemembered = localStorage.getItem(REMEMBER_KEY) === '1';

  if (isRemembered && persistentToken) return persistentToken;
  if (persistentToken) {
    sessionStorage.setItem(SESSION_TOKEN_KEY, persistentToken);
    localStorage.removeItem(PERSISTENT_TOKEN_KEY);
    localStorage.removeItem(REMEMBER_KEY);
    return persistentToken;
  }
  return sessionToken;
}

function hasRememberedLogin() {
  return localStorage.getItem(REMEMBER_KEY) === '1' && !!localStorage.getItem(PERSISTENT_TOKEN_KEY);
}

function saveStoredToken(nextToken, remember) {
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
  localStorage.removeItem(PERSISTENT_TOKEN_KEY);
  localStorage.removeItem(REMEMBER_KEY);
  if (remember) {
    localStorage.setItem(PERSISTENT_TOKEN_KEY, nextToken);
    localStorage.setItem(REMEMBER_KEY, '1');
  } else {
    sessionStorage.setItem(SESSION_TOKEN_KEY, nextToken);
  }
}

function clearStoredToken() {
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
  sessionStorage.removeItem('vault_idle_logged_out');
  localStorage.removeItem(PERSISTENT_TOKEN_KEY);
  localStorage.removeItem(REMEMBER_KEY);
}

let token = restoreStoredToken();
let currentUser = null;
let categories = [];
let entries = [];
let activeCatId = null;

// ==================== NAVIGATION ====================
function updateBreadcrumb(catName) {
  var bc = document.getElementById('navBreadcrumb');
  if (!bc) return;
  if (catName) {
    bc.innerHTML = '<a href="../">🏠 主页</a><span class="sep">›</span><a href="javascript:void(0)" onclick="backToCategories()">🔒 凭证保险箱</a><span class="sep">›</span><span class="current">' + esc(catName) + '</span>';
  } else {
    bc.innerHTML = '<a href="../">🏠 主页</a><span class="sep">›</span><span class="current">🔒 凭证保险箱</span>';
  }
}

function goBack() {
  var openModals = document.querySelectorAll('.modal-overlay.show');
  if (openModals.length > 0) {
    openModals[openModals.length - 1].classList.remove('show');
    return;
  }
  if (activeCatId) { backToCategories(); return; }
  window.location.href = '../';
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    if (document.querySelector('.modal-overlay.show')) return;
    if (document.querySelector('.auth-screen:not(.hidden)')) return;
    goBack();
  }
});
const ICONS = [
  '🔐','🔑','🔒','🗝️','🛡️','🔏',
  '🌐','💻','🖥️','📱','⌨️','🖱️','🖨️','📡','🛰️','📺',
  '📧','💬','📱','📞','📨','📩',
  '☁️','💾','💿','📀','🗄️','📦','🧰','🛠️','⚙️','🔧',
  '🏦','💳','💰','🪙','💎','💵','🛒','🧾',
  '👤','👥','🪪','🪝','🆔','🏠','🏢','🏭',
  '🎮','🎬','🎵','📷','📹','🎧','📺',
  '🚗','✈️','🚀','🛸','🚢','🚂',
  '📂','📁','📝','📌','⭐','🔔','🏷️','🔖','📋','📊',
  '🧪','🔬','🧬','⚡','🔥','☀️','🌙','🍀','🌸','❤️',
  '🎯','🎲','🏆','🎪','🎭','🧩',
  '🔗','📎','✂️','📐','🖊️','✏️','🖌️','🖍️',
];
let canWrite = false;
// ---- 提案系统状态 ----
let myProposals = [];
let reviews = [];
let myProposalsFilter = 'all';
let reviewFilter = 'all';
let reportTargetEntry = null;

// ==================== HISTORY NAVIGATION ====================
let _skipNextPopState = false;

function showModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!el.classList.contains('show')) {
    el.classList.add('show');
    history.pushState({ type: 'modal', modalId: id }, '');
  }
}

function closeModalHistCleanup() {
  if (history.state && history.state.type === 'modal') {
    _skipNextPopState = true;
    history.back();
  }
}

window.addEventListener('popstate', function(e) {
  if (_skipNextPopState) { _skipNextPopState = false; return; }
  // 优先级1：关闭最顶层弹窗
  const openModals = document.querySelectorAll('.modal-overlay.show');
  if (openModals.length > 0) {
    openModals[openModals.length - 1].classList.remove('show');
    return;
  }
  // 优先级2：从条目列表返回分类
  if (activeCatId) {
    backToCategories(true);
    return;
  }
});

history.replaceState({ type: 'categories' }, '');

// ==================== DRAG & DROP ====================
let _drag = null;

function startDrag(e, type, id) {
  e.preventDefault();
  e.stopPropagation();
  const selector = type === 'entry' ? '.entry-card' : '.mf-row';
  const card = e.currentTarget.closest(selector);
  if (!card) return;
  const rect = card.getBoundingClientRect();
  const ghost = card.cloneNode(true);
  ghost.style.cssText = 'position:fixed;left:' + rect.left + 'px;top:' + rect.top + 'px;width:' + rect.width + 'px;height:' + rect.height + 'px;z-index:10000;pointer-events:none;opacity:0.85;box-shadow:0 8px 32px rgba(0,0,0,0.25);border-radius:var(--radius);background:var(--c-card);overflow:hidden;transition:none';
  document.body.appendChild(ghost);
  card.classList.add('dragging');
  _drag = { type, sourceId: type === 'entry' ? id : parseInt(id), ghost, card, startY: e.clientY, startTop: rect.top, moved: false };
  document.addEventListener('pointermove', onDragMove);
  document.addEventListener('pointerup', onDragEnd);
  document.addEventListener('pointercancel', onDragCancel);
}

function onDragMove(e) {
  if (!_drag) return;
  e.preventDefault();
  if (Math.abs(e.clientY - _drag.startY) > 5) _drag.moved = true;
  _drag.ghost.style.top = (_drag.startTop + (e.clientY - _drag.startY)) + 'px';
  _drag.ghost.style.display = 'none';
  const target = document.elementFromPoint(e.clientX, e.clientY);
  _drag.ghost.style.display = '';
  document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
  if (target) {
    const card = target.closest(_drag.type === 'entry' ? '.entry-card' : '.mf-row');
    if (card && card !== _drag.card) card.classList.add('drag-over');
  }
}

function onDragEnd(e) {
  if (!_drag) return;
  cleanupDragListeners();
  if (_drag.moved) {
    _drag.ghost.style.display = 'none';
    const target = document.elementFromPoint(e.clientX, e.clientY);
    _drag.ghost.style.display = '';
    if (target) {
      const card = target.closest(_drag.type === 'entry' ? '.entry-card' : '.mf-row');
      if (card && card !== _drag.card) {
        if (_drag.type === 'entry') dropEntryReorder(card);
        else dropFieldReorder(card);
      }
    }
  }
  cleanupDragVisuals();
}

function onDragCancel() { if (_drag) { cleanupDragListeners(); cleanupDragVisuals(); } }

function cleanupDragListeners() {
  document.removeEventListener('pointermove', onDragMove);
  document.removeEventListener('pointerup', onDragEnd);
  document.removeEventListener('pointercancel', onDragCancel);
}

function cleanupDragVisuals() {
  document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
  if (_drag.card) _drag.card.classList.remove('dragging');
  if (_drag.ghost) _drag.ghost.remove();
  _drag = null;
}

async function dropEntryReorder(targetCard) {
  const targetId = parseInt(targetCard.dataset.entryId);
  const sourceId = _drag.sourceId;
  if (sourceId === targetId) return;
  const fromIdx = entries.findIndex(e => e.id === sourceId);
  const toIdx = entries.findIndex(e => e.id === targetId);
  if (fromIdx === -1 || toIdx === -1) return;
  const [moved] = entries.splice(fromIdx, 1);
  entries.splice(toIdx, 0, moved);
  renderEntries();
  const ids = entries.map(e => e.id);
  const r = await apiPost('reorder-entries', { category_id: activeCatId, ids: ids });
  if (r && r.ok) { showToast('排序已保存', 'success'); markDataDirty(); }
  else showToast(r?.error || '排序保存失败', 'error');
}

function dropFieldReorder(targetCard) {
  const targetIdx = parseInt(targetCard.dataset.fieldIdx);
  const sourceIdx = _drag.sourceId;
  if (isNaN(sourceIdx) || isNaN(targetIdx) || sourceIdx === targetIdx) return;
  const [moved] = modalFields.splice(sourceIdx, 1);
  modalFields.splice(targetIdx, 0, moved);
  renderModalFields();
}

// ==================== AUTH ====================
let authMode = 'login'; // 'login' | 'setup'

async function init() {
  // 主题初始化（由 shared/theme.js 的 ThemeManager 管理）
  if (typeof ThemeManager !== 'undefined') ThemeManager.init();
  else { const t = localStorage.getItem('vault_theme'); if (t === 'dark') document.body.setAttribute('data-theme', 'dark'); }
  // 无操作退出后：勾选了「七天免登录」则自动恢复，否则要求重新输入密码
  if (sessionStorage.getItem('vault_idle_logged_out')) {
    sessionStorage.removeItem('vault_idle_logged_out');
    if (!hasRememberedLogin()) {
      token = '';
      sessionStorage.removeItem(SESSION_TOKEN_KEY);
      checkSetup();
      return;
    }
    // 有记忆标志 → 尝试用现有 token 自动登录
  }
  if (token) {
    // 验证 token
    const r = await apiGet('me');
    if (r && r.ok) {
      currentUser = r.user;
      renderApp();
      return;
    }
    // token 过期
    token = '';
    clearStoredToken();
  }
  // 检查是否需要首次设置
  checkSetup();
}

async function checkSetup() {
  document.getElementById('authScreen').classList.remove('hidden');
  // 加载用户列表到下拉框
  loadUserList();
}

async function loadUserList() {
  const sel = document.getElementById('authUsername');
  sel.innerHTML = '<option value="">加载中...</option>';
  try {
    const r = await apiGet('list-users');
    if (r && r.ok && r.users && r.users.length > 0) {
      sel.innerHTML = '<option value="" disabled selected>选择账号登录</option>'
        + r.users.map(u =>
          `<option value="${escAttr(u.username)}">${esc(u.display_name || u.username)}</option>`
        ).join('');
    } else {
      sel.innerHTML = '<option value="">请先创建主账号</option>';
    }
  } catch(e) {
    sel.innerHTML = '<option value="">加载失败，请刷新</option>';
  }
}

function switchAuthMode() {
  authMode = authMode === 'login' ? 'setup' : 'login';
  const isSetup = authMode === 'setup';
  document.getElementById('authDesc').textContent = isSetup ? '首次使用，创建主账号' : '登录以访问你的保险箱';
  document.getElementById('authBtn').textContent = isSetup ? '创建主账号' : '登录';
  document.getElementById('authSelectWrap').style.display = isSetup ? 'none' : 'block';
  document.getElementById('authTextWrap').style.display = isSetup ? 'block' : 'none';
  document.getElementById('authRememberWrap').style.display = isSetup ? 'none' : 'flex';
  document.getElementById('authSwitch').innerHTML = isSetup
    ? '<span>已有账号？</span><button onclick="switchAuthMode()">登录</button>'
    : '<span>首次使用？</span><button onclick="switchAuthMode()">设置主账号</button>';
  document.getElementById('authHint').textContent = isSetup ? '设置主账号后，你可以创建子账号并分配权限' : '1 小时无操作自动退出';
  document.getElementById('authMsg').textContent = '';
}

async function handleAuth() {
  const username = authMode === 'setup'
    ? document.getElementById('authTextUser').value.trim()
    : document.getElementById('authUsername').value.trim();
  const password = document.getElementById('authPassword').value;
  const remember = document.getElementById('authRemember').checked;
  if (!username || !password) { showAuthMsg('请选择账号并输入密码'); return; }
  const btn = document.getElementById('authBtn');
  btn.disabled = true; btn.textContent = '处理中...';
  try {
    const action = authMode === 'setup' ? 'setup' : 'login';
    const r = await apiPost(action, { username, password, remember });
    if (!r || !r.ok) { showAuthMsg(!r ? '网络错误，请检查服务器' : (r.error || '操作失败')); btn.disabled = false; btn.textContent = authMode === 'setup' ? '创建主账号' : '登录'; return; }
    if (action === 'setup') {
      showAuthMsg('主账号创建成功，请登录', 'success');
      authMode = 'login';
      switchAuthMode();
      btn.disabled = false; btn.textContent = '登录';
      return;
    }
    token = r.token;
    currentUser = r.user;
    // 后端决定的 remember 值为准，确保仅七天会话写入持久化存储。
    saveStoredToken(token, r.remember === true);
    renderApp();
  } catch(e) {
    showAuthMsg('网络错误: ' + e.message);
    btn.disabled = false; btn.textContent = authMode === 'setup' ? '创建主账号' : '登录';
  }
}

function showAuthMsg(msg, type) {
  const el = document.getElementById('authMsg');
  el.textContent = msg;
  el.style.color = type === 'success' ? 'var(--c-success)' : 'var(--c-error)';
}

async function handleLogout() {
  await apiGet('logout');
  token = '';
  currentUser = null;
  clearStoredToken();
  document.getElementById('app').classList.remove('show');
  document.getElementById('authScreen').classList.remove('hidden');
  document.getElementById('authPassword').value = '';
  authMode = 'login';
  switchAuthMode();
  loadUserList();
}

// ==================== APP ====================
function renderApp() {
  document.getElementById('authScreen').classList.add('hidden');
  document.getElementById('app').classList.add('show');
  document.getElementById('userDisplayName').textContent = currentUser.display_name || currentUser.username;
  document.getElementById('roleTag').textContent = currentUser.role === 'master' ? '主人' : '成员';
  document.getElementById('adminBtn').style.display = currentUser.role === 'master' ? 'flex' : 'none';
  document.getElementById('notifBtn').style.display = 'flex';
  loadNotifCount();
  loadCategories();
  initSyncState();
  resetAutoLock();
}

function backToCategories(fromPopState) {
  document.getElementById('entrySection').style.display = 'none';
  document.getElementById('categorySection').style.display = 'block';
  document.getElementById('searchInput').value = '';
  activeCatId = null;
  if (!fromPopState) history.replaceState({ type: 'categories' }, '');
  updateBreadcrumb();
}

// ==================== CATEGORIES ====================
async function loadCategories() {
  const r = await apiGet('get-categories');
  if (!r || !r.ok) return;
  categories = r.categories;
  renderCategories();
}

function renderCategories() {
  const list = document.getElementById('categoryList');
  if (!categories.length) {
    list.innerHTML = '<div style="text-align:center;padding:40px;color:var(--c-text2)">暂无分类</div>';
    return;
  }
  list.innerHTML = categories.map(c =>
    `<div class="cat-card${activeCatId === c.id ? ' active' : ''}" onclick="loadEntries(${c.id})">
      <div class="cat-icon">${esc(c.icon || '🔑')}</div>
      <div class="cat-name">${esc(c.name)}</div>
      <div class="cat-count">点击查看</div>
      ${!c.can_write ? '<div class="cat-badge">只读</div>' : ''}
    </div>`
  ).join('');
}

// ==================== ENTRIES ====================
async function loadEntries(catId) {
  const isNewNav = activeCatId !== catId;
  activeCatId = catId;
  const cat = categories.find(c => c.id === catId);
  if (!cat) return;
  document.getElementById('entriesCatIcon').textContent = cat.icon || '🔑';
  document.getElementById('entriesCatName').textContent = cat.name;
  document.getElementById('categorySection').style.display = 'none';
  document.getElementById('entrySection').style.display = 'block';
  document.getElementById('addEntryBtn').style.display = (cat.can_write || (currentUser && currentUser.role !== 'master')) ? 'flex' : 'none';
  canWrite = cat.can_write;
  if (isNewNav) history.pushState({ type: 'entries', catId: catId }, '');
  updateBreadcrumb(cat.name);

  const r = await apiGet(`get-entries&category_id=${catId}`);
  if (!r || !r.ok) return;
  entries = r.entries || [];
  canWrite = r.can_write !== undefined ? r.can_write : canWrite;
  renderEntries();
}

// 从条目提取字段列表（兼容旧格式和新格式）
function getEntryFields(entry) {
  const f = entry._fields;
  if (Array.isArray(f) && f.length > 0) return f;
  // 优先从 notes 解析 JSON 字段数组
  if (entry.notes) {
    try {
      const parsed = JSON.parse(entry.notes);
      if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].key !== undefined) {
        entry._fields = parsed;
        return parsed;
      }
      if (typeof parsed === 'object' && !Array.isArray(parsed)) {
        const fields = [];
        for (const [k, v] of Object.entries(parsed)) {
          const isPwd = /密码|pass|key|secret|token|秘钥/i.test(k);
          const isUrl = /链接|网址|url|http|官网|订阅|仪表盘/i.test(k);
          fields.push({ key: k, value: v, type: isPwd ? 'password' : isUrl ? 'url' : 'text' });
        }
        if (fields.length > 0) { entry._fields = fields; return fields; }
      }
    } catch {}
  }
  // 兜底：从 flat 字段构建
  const fields = [];
  if (entry.username) fields.push({ key: '用户名', value: entry.username, type: 'text' });
  if (entry.password) fields.push({ key: '密码', value: entry.password, type: 'password' });
  if (entry.url) fields.push({ key: '链接', value: entry.url, type: 'url' });
  if (entry.notes && typeof entry.notes === 'string') {
    try { JSON.parse(entry.notes); } catch { fields.push({ key: '备注', value: entry.notes, type: 'text' }); }
  }
  return fields;
}

function renderEntries() {
  const list = document.getElementById('entryList');
  if (!entries.length) {
    list.innerHTML = '<div class="entry-empty">📭 暂无条目</div>';
    return;
  }
  list.innerHTML = entries.map(e => {
    const fields = getEntryFields(e);
    const preview = fields.length > 0 ? fields[0].key + ': ' + (fields[0].type === 'password' ? '••••••••••••' : maskValue(fields[0].value, fields[0].type)) : '';
    return `<div class="entry-card" id="entry-${e.id}" data-entry-id="${e.id}">
      <div class="entry-card-row" onclick="toggleEntry(${e.id})">
        ${currentUser && currentUser.role === 'master' ? '<div class="drag-handle" onpointerdown="startDrag(event,\'entry\',' + e.id + ')">⠿</div>' : ''}
        <div class="entry-icon">${esc(e.icon || '🔐')}</div>
        <div class="entry-info">
          <div class="title">${esc(e.title || '(无标题)')}</div>
          <div class="sub">${esc(preview)}</div>
        </div>
        <div class="entry-actions">
          <button class="icon-btn" onclick="event.stopPropagation();${currentUser && currentUser.role !== 'master' ? 'openEntryModalForSuggest' : 'openEntryModal'}(${e.id})" title="${currentUser && currentUser.role !== 'master' ? '建议修改' : '编辑'}">✏️</button>
          <span class="entry-toggle${e._expanded ? ' open' : ''}" onclick="event.stopPropagation();toggleEntry(${e.id})">▼</span>
        </div>
      </div>
      <div class="entry-fields${e._expanded ? ' show' : ''}">
        ${fields.map((f, fi) => {
          const val = f.value || '';
          const isSecret = f.type === 'password';
          const isLink = f.type === 'url';
          const revealed = e._revealed && e._revealed[fi];
          const displayVal = isSecret && !revealed ? '••••••••••••' : esc(val);
          return `<div class="field-row">
            <span class="field-label">${esc(f.key)}</span>
            <span class="field-value${isSecret && !revealed ? ' masked' : ''}${isLink ? ' field-link' : ''}"${isLink ? ' onclick="event.stopPropagation();openLink(\'' + escAttr(val) + '\')"' : ''}>${displayVal}</span>
            ${isSecret ? `<button class="field-copy" onclick="event.stopPropagation();toggleReveal(${e.id},${fi})" title="${revealed ? '隐藏' : '显示'}">${revealed ? '🙈' : '👁️'}</button>` : ''}
            ${isLink ? `<button class="field-copy" onclick="event.stopPropagation();openLink('${escAttr(val)}')" title="打开链接">🔗</button>` : ''}
            <button class="field-copy" onclick="event.stopPropagation();copyField(this,'${escAttr(val)}')" title="复制">📋</button>
          </div>`;
        }).join('')}
      </div>
      ${currentUser && currentUser.role !== 'master' ? `<div style="display:flex;gap:6px;padding:0 16px 10px">
        <button class="btn btn-secondary" style="flex:1;padding:7px;border-radius:8px;font-size:12px" onclick="event.stopPropagation();openEntryModalForSuggest(${e.id})">✏️ 建议修改</button>
        <button class="btn btn-secondary" style="flex:1;padding:7px;border-radius:8px;font-size:12px" onclick="event.stopPropagation();openReportModal(${e.id})">🚩 报告问题</button>
      </div>` : ''}
    </div>`;
  }).join('');
}

function toggleEntry(id) {
  if (_drag) return;
  const e = entries.find(x => x.id === id);
  if (!e) return;
  e._expanded = !e._expanded;
  if (!e._revealed) e._revealed = {};
  renderEntries();
}

function toggleReveal(entryId, fieldIdx) {
  const e = entries.find(x => x.id === entryId);
  if (!e) return;
  if (!e._revealed) e._revealed = {};
  e._revealed[fieldIdx] = !e._revealed[fieldIdx];
  renderEntries();
}

async function copyField(btn, text) {
  if (!text) { showToast('无可复制的内容', 'info'); return; }
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = '✅';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '📋'; btn.classList.remove('copied'); }, 1500);
    showToast('已复制', 'success');
  } catch { showToast('复制失败', 'error'); }
}

function maskValue(val, type) {
  if (!val) return '';
  if (type === 'password') return '••••••••';
  return val.length > 30 ? val.slice(0, 30) + '…' : val;
}

// ==================== ENTRY CRUD ====================
let editingEntryId = null;

function parseEntryFields(e) {
  // 尝试从 notes 解析 JSON 字段数组
  if (e.notes) {
    try {
      const parsed = JSON.parse(e.notes);
      // 新格式：[{key, value, type}, ...]
      if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].key !== undefined) {
        return parsed;
      }
      // 旧导入格式：{key: value, ...} 扁平对象
      if (typeof parsed === 'object' && !Array.isArray(parsed)) {
        const fields = [];
        for (const [k, v] of Object.entries(parsed)) {
          const isPwd = /密码|pass|key|secret|token|秘钥/i.test(k);
          const isUrl = /链接|网址|url|http|官网|订阅|仪表盘/i.test(k);
          fields.push({ key: k, value: v, type: isPwd ? 'password' : isUrl ? 'url' : 'text' });
        }
        if (fields.length > 0) return fields;
      }
    } catch {}
  }
  // 兜底：从 flat 字段构建
  const fields = [];
  if (e.username) fields.push({ key: '用户名', value: e.username, type: 'text' });
  if (e.password) fields.push({ key: '密码', value: e.password, type: 'password' });
  if (e.url) fields.push({ key: '链接', value: e.url, type: 'url' });
  if (e.notes && typeof e.notes === 'string') {
    try { JSON.parse(e.notes); } catch { fields.push({ key: '备注', value: e.notes, type: 'text' }); }
  }
  if (!fields.length) fields.push({ key: '内容', value: '', type: 'text' });
  return fields;
}

let modalFields = [];

function openEntryModal(entryId) {
  editingEntryId = entryId || null;
  document.getElementById('entryDelBtn').style.display = entryId && canWrite ? 'block' : 'none';
  document.getElementById('entryModalTitle').textContent = entryId ? '✏️ 编辑条目' : '➕ 添加条目';

  if (entryId) {
    const e = entries.find(x => x.id === entryId);
    if (!e) return;
    document.getElementById('entryTitle').value = e.title || '';
    document.getElementById('entryIcon').value = e.icon || '🔐';
    // 解析字段
    e._fields = e._fields || parseEntryFields(e);
    modalFields = e._fields.map(f => ({ ...f }));
    document.getElementById('entrySaveBtn').textContent = '保存';
  } else {
    document.getElementById('entryTitle').value = '';
    document.getElementById('entryIcon').value = '🔐';
    modalFields = [{ key: '用户名', value: '', type: 'text' }, { key: '密码', value: '', type: 'password' }];
    document.getElementById('entrySaveBtn').textContent = '添加';
  }
  updateIconPreview('entryIcon', 'entryIconPreview');
  renderIconPicker('entryIconGrid', 'entryIcon', 'entryIconPreview', document.getElementById('entryIcon').value || '🔐');
  renderModalFields();
  // 子账号：显示「提交审核」而非直接保存
  if (currentUser && currentUser.role !== 'master') {
    document.getElementById('entrySaveBtn').style.display = 'none';
    document.getElementById('entrySubmitBtn').style.display = '';
  } else {
    document.getElementById('entrySaveBtn').style.display = '';
    document.getElementById('entrySubmitBtn').style.display = 'none';
  }
  showModal('entryModal');
}

function renderModalFields() {
  const container = document.getElementById('mfList');
  container.innerHTML = modalFields.map((f, i) =>
    `<div class="mf-row" data-field-idx="${i}">
      <div class="drag-handle" onpointerdown="startDrag(event,'field',${i})">⠿</div>
      <input class="mf-key" placeholder="名称" value="${esc(f.key)}" onchange="modalFields[${i}].key=this.value">
      <input class="mf-val" placeholder="内容" value="${esc(f.value)}" onchange="modalFields[${i}].value=this.value"
        type="${f.type === 'password' && !f._revealed ? 'password' : 'text'}">
      <button class="field-copy" onclick="event.stopPropagation();toggleFieldType(${i})" title="${f.type === 'password' ? '密码' : f.type === 'url' ? '链接' : '文本'}">${f.type === 'password' ? '👁️' : f.type === 'url' ? '🔗' : '🔤'}</button>
      <button class="mf-del" onclick="event.stopPropagation();removeModalField(${i})" title="删除">✕</button>
    </div>`
  ).join('');
}

function addModalField() {
  modalFields.push({ key: '', value: '', type: 'text' });
  renderModalFields();
}

function removeModalField(idx) {
  if (modalFields.length <= 1) { showToast('至少保留一个字段', 'info'); return; }
  modalFields.splice(idx, 1);
  renderModalFields();
}

function toggleFieldType(idx) {
  const f = modalFields[idx];
  if (f.type === 'text') { f.type = 'password'; }
  else if (f.type === 'password') { f.type = 'url'; }
  else { f.type = 'text'; }
  f._revealed = false;
  renderModalFields();
}

function openLink(url) {
  if (!url) return;
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
  window.open(url, '_blank', 'noopener');
}

function closeEntryModal() {
  document.getElementById('entryModal').classList.remove('show');
  editingEntryId = null;
  closeModalHistCleanup();
}

async function saveEntry() {
  if (!canWrite) { showToast('你只有只读权限', 'error'); return; }
  const title = document.getElementById('entryTitle').value.trim() || '无标题';
  // 同步最后一个输入框的值
  const inputs = document.querySelectorAll('#mfList .mf-val');
  inputs.forEach((el, i) => { if (modalFields[i]) modalFields[i].value = el.value; });
  // 从 fields 提取旧格式兼容字段
  const findField = (keys) => {
    for (const f of modalFields) {
      if (keys.some(k => f.key.toLowerCase().includes(k))) return f.value;
    }
    return '';
  };
  const data = {
    category_id: activeCatId,
    title: title,
    icon: document.getElementById('entryIcon').value.trim() || '',
    username: findField(['用户', '邮箱', '账号', 'id', 'user', 'email']),
    password: findField(['密码', 'pass', 'key', 'secret']),
    url: findField(['链接', '网址', 'url', 'http']),
    notes: JSON.stringify(modalFields.filter(f => f.value || f.key)),
  };
  let r;
  if (editingEntryId) {
    data.id = editingEntryId;
    r = await apiPost('edit-entry', data);
  } else {
    r = await apiPost('add-entry', data);
  }
  if (r && r.ok) {
    closeEntryModal();
    loadEntries(activeCatId);
    showToast(editingEntryId ? '已更新' : '已添加', 'success');
    markDataDirty();
  } else {
    showToast(r?.error || '操作失败', 'error');
  }
}

async function deleteEntry() {
  if (!canWrite) { showToast('你只有只读权限', 'error'); return; }
  if (!confirm('确定删除该条目？')) return;
  const r = await apiPost('delete-entry', { id: editingEntryId });
  if (r && r.ok) {
    closeEntryModal();
    loadEntries(activeCatId);
    showToast('已删除', 'info');
    markDataDirty();
  } else {
    showToast(r?.error || '删除失败', 'error');
  }
}

// ==================== ADMIN ====================
async function openAdmin() {
  if (currentUser.role !== 'master') return;
  showModal('adminModal');
  loadAdminUsers();
  loadAdminCats();
  loadStats();
  loadPermUsers();
  webdavLoadConfig();
  loadWebdavVersions();
  serverchanLoadConfig();
}

function closeAdmin() { closeModal('adminModal'); }

// -- Stats --
async function loadStats() {
  const r = await apiGet('get-stats');
  if (!r || !r.ok) return;
  const s = r.stats;
  document.getElementById('statUsers').textContent = s.active_users + '/' + s.total_users;
  document.getElementById('statCats').textContent = s.total_categories;
  document.getElementById('statEntries').textContent = s.total_entries;
}

// -- Users --
async function loadAdminUsers() {
  const r = await apiGet('get-users');
  if (!r || !r.ok) return;
  const list = document.getElementById('userList');
  list.innerHTML = r.users.map(u => {
    const lastLogin = u.last_login ? new Date(u.last_login).toLocaleString() : '从未';
    const statusBadge = u.role === 'master'
      ? '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:var(--c-primary-light);color:var(--c-primary)">主人</span>'
      : u.is_active
        ? '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#d1fae5;color:#059669">正常</span>'
        : '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#fef2f2;color:#ef4444">禁用</span>';
    return `<div class="admin-user-item" style="flex-wrap:wrap">
      <div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0">
        <div style="width:36px;height:36px;border-radius:50%;background:var(--c-primary-light);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0">${u.role === 'master' ? '👑' : '👤'}</div>
        <div style="min-width:0">
          <div style="font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px">${esc(u.display_name || u.username)} ${statusBadge}</div>
          <div style="font-size:11px;color:var(--c-text2)">@${esc(u.username)} · 登录 ${u.login_count} 次 · 最近 ${lastLogin}</div>
        </div>
      </div>
      <div class="actions">
        ${u.role !== 'master' ? `
          <button class="btn-edit" onclick="showEditUser(${u.id},'${escAttr(u.display_name || u.username)}')">编辑</button>
          <button class="btn-edit" onclick="showUserDetail(${u.id})">详情</button>
          <button class="btn-toggle" onclick="toggleUser(${u.id})">${u.is_active ? '禁用' : '启用'}</button>
          <button class="btn-edit" onclick="showResetPwd(${u.id})">改密</button>
          <button class="btn-del" onclick="deleteUser(${u.id},'${escAttr(u.username)}')">删除</button>
        ` : `
          <button class="btn-edit" onclick="showEditUser(${u.id},'${escAttr(u.display_name || u.username)}')">编辑</button>
        `}
      </div>
    </div>`;
  }).join('');
}

function showAddUser() {
  document.getElementById('newUserName').value = '';
  document.getElementById('newUserPwd').value = '';
  showModal('addUserModal');
}

async function addUser() {
  const username = document.getElementById('newUserName').value.trim();
  const password = document.getElementById('newUserPwd').value;
  if (!username || !password) { showToast('请填写完整', 'error'); return; }
  const r = await apiPost('add-user', { username, password });
  if (r && r.ok) {
    closeModal('addUserModal');
    await Promise.all([loadAdminUsers(), loadPermUsers(), loadStats()]);
    showToast('用户已创建', 'success');
  } else {
    showToast(r?.error || '创建失败', 'error');
  }
}

async function toggleUser(id) {
  const r = await apiPost('toggle-user', { id });
  if (r && r.ok) { loadAdminUsers(); loadStats(); showToast('已更新', 'success'); }
  else showToast(r?.error || '操作失败', 'error');
}

async function deleteUser(id, name) {
  if (!confirm(`确定删除用户「${name}」？该用户的会话和权限将一并清除。`)) return;
  const r = await apiPost('delete-user', { id });
  if (r && r.ok) { await Promise.all([loadAdminUsers(), loadPermUsers(), loadStats()]); showToast('已删除', 'info'); }
  else showToast(r?.error || '删除失败', 'error');
}

function showResetPwd(id) {
  document.getElementById('resetPwdUserId').value = id;
  document.getElementById('resetPwdInput').value = '';
  showModal('resetPwdModal');
}

async function resetUserPwd() {
  const id = parseInt(document.getElementById('resetPwdUserId').value);
  const password = document.getElementById('resetPwdInput').value;
  if (!password) { showToast('请输入新密码', 'error'); return; }
  const r = await apiPost('reset-user-pwd', { id, password });
  if (r && r.ok) { closeModal('resetPwdModal'); showToast('密码已重置', 'success'); }
  else showToast(r?.error || '重置失败', 'error');
}

// -- Edit User --
function showEditUser(id, displayName) {
  document.getElementById('editUserId').value = id;
  document.getElementById('editUserName').value = displayName;
  showModal('editUserModal');
}

async function saveEditUser() {
  const id = parseInt(document.getElementById('editUserId').value);
  const displayName = document.getElementById('editUserName').value.trim();
  if (!displayName) { showToast('请输入显示名称', 'error'); return; }
  const r = await apiPost('update-user', { id, display_name: displayName });
  if (r && r.ok) {
    closeModal('editUserModal');
    await loadAdminUsers();
    showToast('已更新', 'success');
  } else {
    showToast(r?.error || '保存失败', 'error');
  }
}

// -- User Detail --
async function showUserDetail(userId) {
  const content = document.getElementById('userDetailContent');
  content.innerHTML = '<div style="text-align:center;padding:20px;color:var(--c-text2)">加载中...</div>';
  showModal('userDetailModal');

  const r = await apiGet(`get-user-detail&user_id=${userId}`);
  if (!r || !r.ok) {
    content.innerHTML = '<div style="text-align:center;padding:20px;color:var(--c-error)">加载失败</div>';
    return;
  }
  const u = r.user;
  const catPerms = r.category_permissions || [];
  const entrySummary = r.entry_summary || [];

  const lastLogin = u.last_login ? new Date(u.last_login).toLocaleString() : '从未';
  const statusBadge = u.is_active
    ? '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#d1fae5;color:#059669">正常</span>'
    : '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#fef2f2;color:#ef4444">禁用</span>';

  let html = `
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding:12px;background:var(--c-input-bg);border-radius:10px">
      <div style="width:44px;height:44px;border-radius:50%;background:var(--c-primary-light);display:flex;align-items:center;justify-content:center;font-size:20px">👤</div>
      <div>
        <div style="font-size:16px;font-weight:600;display:flex;align-items:center;gap:6px">${esc(u.display_name || u.username)} ${statusBadge}</div>
        <div style="font-size:12px;color:var(--c-text2)">@${esc(u.username)} · ${u.role === 'master' ? '主账号' : '子账号'}</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px">
      <div style="padding:10px;background:var(--c-input-bg);border-radius:8px;text-align:center">
        <div style="font-size:18px;font-weight:700;color:var(--c-primary)">${u.login_count}</div>
        <div style="font-size:11px;color:var(--c-text2)">登录次数</div>
      </div>
      <div style="padding:10px;background:var(--c-input-bg);border-radius:8px;text-align:center">
        <div style="font-size:12px;font-weight:600;color:var(--c-primary);line-height:1.4">${lastLogin}</div>
        <div style="font-size:11px;color:var(--c-text2)">最近登录</div>
      </div>
    </div>
    <div style="font-size:12px;color:var(--c-text2);margin-bottom:4px">注册时间: ${u.created_at ? new Date(u.created_at).toLocaleString() : '-'}</div>
  `;

  // 权限摘要
  if (catPerms.length > 0) {
    html += `<div style="margin-top:16px"><div style="font-size:13px;font-weight:600;color:var(--c-text2);margin-bottom:8px">🔐 分类权限</div>`;
    html += '<div style="display:flex;flex-direction:column;gap:4px">';
    catPerms.forEach(cp => {
      const badges = [];
      if (cp.can_read) badges.push('<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:#d1fae5;color:#059669">可读</span>');
      if (cp.can_write) badges.push('<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:#dbeafe;color:#2563eb">可写</span>');
      // 查找条目可见性
      const es = entrySummary.find(e => e.category_id === cp.category_id);
      let entryInfo = '';
      if (es && es.hidden > 0) {
        entryInfo = `<span style="font-size:10px;color:var(--c-text2);margin-left:auto">${es.visible}/${es.total} 条可见</span>`;
      }
      html += `<div style="display:flex;align-items:center;gap:6px;padding:6px 8px;background:var(--c-input-bg);border-radius:6px;font-size:13px">
        <span>${cp.cat_icon || '🔑'}</span>
        <span style="flex:1">${esc(cp.cat_name)}</span>
        ${badges.join(' ')}
        ${entryInfo}
      </div>`;
    });
    html += '</div></div>';
  } else {
    html += '<div style="margin-top:16px;padding:12px;text-align:center;color:var(--c-text2);font-size:13px;background:var(--c-input-bg);border-radius:8px">暂未分配任何权限</div>';
  }

  content.innerHTML = html;
}

// -- Categories (admin) --
async function loadAdminCats() {
  const r = await apiGet('get-categories');
  if (!r || !r.ok) return;
  const list = document.getElementById('adminCatList');
  list.innerHTML = r.categories.map(c =>
    `<div class="admin-user-item">
      <div class="info">${c.icon || '🔑'} ${esc(c.name)}</div>
      <div class="actions">
        <button class="btn-edit" onclick="showRenameCat(${c.id},'${escAttr(c.name)}','${escAttr(c.icon || '🔑')}')">编辑</button>
      </div>
    </div>`
  ).join('');
}

function showAddCategory() {
  document.getElementById('newCatName').value = '';
  document.getElementById('newCatIcon').value = '🔑';
  updateIconPreview('newCatIcon', 'newCatIconPreview');
  renderIconPicker('newCatIconGrid', 'newCatIcon', 'newCatIconPreview', '🔑');
  showModal('addCatModal');
}

async function addCategory() {
  const name = document.getElementById('newCatName').value.trim();
  const icon = document.getElementById('newCatIcon').value.trim() || '🔑';
  if (!name) { showToast('请输入分类名称', 'error'); return; }
  const r = await apiPost('add-category', { name, icon });
  if (r && r.ok) {
    closeModal('addCatModal');
    await Promise.all([loadAdminCats(), loadPermUsers(), loadCategories()]);
    showToast('分类已创建', 'success');
    markDataDirty();
  } else showToast(r?.error || '创建失败', 'error');
}

function showRenameCat(id, name, icon) {
  document.getElementById('renameCatId').value = id;
  document.getElementById('renameCatName').value = name;
  document.getElementById('renameCatIcon').value = icon;
  updateIconPreview('renameCatIcon', 'renameCatIconPreview');
  renderIconPicker('renameCatIconGrid', 'renameCatIcon', 'renameCatIconPreview', icon || '🔑');
  showModal('renameCatModal');
}

async function renameCategory() {
  const id = parseInt(document.getElementById('renameCatId').value);
  const name = document.getElementById('renameCatName').value.trim();
  const icon = document.getElementById('renameCatIcon').value.trim() || '🔑';
  if (!name) { showToast('请输入名称', 'error'); return; }
  const r = await apiPost('rename-category', { id, name, icon });
  if (r && r.ok) {
    closeModal('renameCatModal');
    loadAdminCats(); loadCategories(); loadPermGrid();
    if (activeCatId) loadEntries(activeCatId);
    showToast('已保存', 'success');
    markDataDirty();
  } else showToast(r?.error || '保存失败', 'error');
}

async function deleteCategory() {
  if (!confirm('确定删除该分类？其中的所有条目将一并删除！')) return;
  const id = parseInt(document.getElementById('renameCatId').value);
  const r = await apiPost('delete-category', { id });
  if (r && r.ok) {
    closeModal('renameCatModal');
    await Promise.all([loadAdminCats(), loadCategories(), loadPermUsers()]);
    if (activeCatId === id) backToCategories();
    showToast('已删除', 'info');
    markDataDirty();
  } else showToast(r?.error || '删除失败', 'error');
}

// -- Permissions --
async function loadPermUsers() {
  const sel = document.getElementById('permUserSelectEl');
  const grid = document.getElementById('permGridContainer');
  try {
    const r = await apiGet('get-users');
    if (!r) { sel.innerHTML = '<option value="">网络错误</option>'; grid.innerHTML = '<div style="color:var(--c-error);padding:12px">网络错误，请检查连接</div>'; return; }
    if (!r.ok) { sel.innerHTML = '<option value="">加载失败</option>'; grid.innerHTML = '<div style="color:var(--c-error);padding:12px">' + esc(r.error || 'API 返回错误') + '</div>'; return; }
    const subs = (r.users || []).filter(u => u.role !== 'master');
    if (subs.length === 0) {
      sel.innerHTML = '<option value="">暂无子账号，请先添加</option>';
      grid.innerHTML = '<div style="color:var(--c-text2);padding:12px">请先在上方「用户管理」中添加子账号</div>';
      return;
    }
    const prev = sel.value;
    sel.innerHTML = subs.map(u =>
      `<option value="${u.id}">${esc(u.display_name || u.username)}${u.is_active ? '' : ' (已禁用)'}</option>`
    ).join('');
    sel.value = prev && subs.some(u => String(u.id) === prev) ? prev : String(subs[0].id);
    await loadPermGrid();
  } catch(e) {
    console.error('loadPermUsers:', e);
    sel.innerHTML = '<option value="">加载出错</option>';
    grid.innerHTML = '<div style="color:var(--c-error);padding:12px">JS 异常: ' + esc(e.message || '') + '</div>';
  }
}

async function loadPermGrid() {
  const container = document.getElementById('permGridContainer');
  const userId = parseInt(document.getElementById('permUserSelectEl').value);
  if (!userId) { container.innerHTML = '<div style="color:var(--c-text2);padding:12px">请选择用户</div>'; return; }
  try {
    const [catR, permR] = await Promise.all([apiGet('get-categories'), apiGet('get-permissions')]);
    if (!catR?.ok) { container.innerHTML = '<div style="color:var(--c-error);padding:12px">分类加载失败</div>'; return; }
    const perms = (permR?.permissions || []).filter(p => p.user_id === userId);
    const cats = catR.categories;
    if (!cats.length) { container.innerHTML = '<div style="color:var(--c-text2);padding:12px">暂无分类</div>'; return; }
    let html = '<div class="perm-grid"><div class="perm-header"><span>分类</span><span>条目</span><span>查看</span><span>编辑</span></div>';
    cats.forEach(c => {
      const p = perms.find(x => x.category_id === c.id);
      const read = p ? p.can_read : false;
      const write = p ? p.can_write : false;
      html += `<div class="perm-row">
        <span class="perm-cat">${c.icon || '🔑'} ${esc(c.name)}</span>
        <label style="display:flex;align-items:center;justify-content:center"><button class="field-copy" onclick="openEntryPermModal(${c.id},'${escAttr(c.name)}')" title="设置条目可见性" style="font-size:13px">👁️</button></label>
        <label><input type="checkbox" class="perm-read" data-cat="${c.id}" ${read ? 'checked' : ''}></label>
        <label><input type="checkbox" class="perm-write" data-cat="${c.id}" ${write ? 'checked' : ''}></label>
      </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
    // 只读时不勾选编辑
    document.querySelectorAll('.perm-read').forEach(cb => {
      cb.addEventListener('change', () => {
        const row = cb.closest('.perm-row');
        const writeCb = row.querySelector('.perm-write');
        if (!cb.checked) writeCb.checked = false;
      });
    });
    document.querySelectorAll('.perm-write').forEach(cb => {
      cb.addEventListener('change', () => {
        const row = cb.closest('.perm-row');
        const readCb = row.querySelector('.perm-read');
        if (cb.checked) readCb.checked = true;
      });
    });
  } catch(e) {
    console.error('loadPermGrid:', e);
    container.innerHTML = '<div style="color:var(--c-error);padding:12px">加载失败: ' + esc(e.message) + '</div>';
  }
}

function permSelectAll() {
  document.querySelectorAll('.perm-row').forEach(row => {
    row.querySelector('.perm-read').checked = true;
    row.querySelector('.perm-write').checked = true;
  });
}

function permSelectRead() {
  document.querySelectorAll('.perm-row').forEach(row => {
    row.querySelector('.perm-read').checked = true;
    row.querySelector('.perm-write').checked = false;
  });
}

function permClearAll() {
  document.querySelectorAll('.perm-row').forEach(row => {
    row.querySelector('.perm-read').checked = false;
    row.querySelector('.perm-write').checked = false;
  });
}

async function savePermissions() {
  const userId = parseInt(document.getElementById('permUserSelectEl').value);
  if (!userId) { showToast('请选择用户', 'error'); return; }
  const permissions = [];
  document.querySelectorAll('.perm-row').forEach(row => {
    const catId = parseInt(row.querySelector('.perm-read').dataset.cat);
    const read = row.querySelector('.perm-read').checked;
    const write = row.querySelector('.perm-write').checked;
    permissions.push({ category_id: catId, can_read: read, can_write: write });
  });
  const r = await apiPost('set-permissions', { user_id: userId, permissions });
  if (r && r.ok) { showToast('权限已保存', 'success'); loadPermGrid(); }
  else showToast(r?.error || '保存失败', 'error');
}

// ==================== 条目可见性管理 ====================
let entryPermUserId = null;
let entryPermCatId = null;
let entryPermData = {}; // {entryId: canView}

async function openEntryPermModal(catId, catName) {
  const userId = parseInt(document.getElementById('permUserSelectEl').value);
  if (!userId) { showToast('请先选择用户', 'error'); return; }
  entryPermUserId = userId;
  entryPermCatId = catId;
  document.getElementById('entryPermCatId').value = catId;
  document.getElementById('entryPermDesc').textContent = `设置用户可见的「${catName}」条目（未勾选的条目将被隐藏）`;
  document.getElementById('entryPermList').innerHTML = '<div style="color:var(--c-text2);padding:16px;text-align:center">加载中...</div>';
  showModal('entryPermModal');

  const r = await apiGet(`get-entry-perms&user_id=${userId}&category_id=${catId}`);
  if (!r || !r.ok) {
    document.getElementById('entryPermList').innerHTML = '<div style="color:var(--c-error);padding:16px;text-align:center">加载失败</div>';
    return;
  }
  const entries = r.entries || [];
  const perms = r.permissions || {};
  entryPermData = {};
  if (!entries.length) {
    document.getElementById('entryPermList').innerHTML = '<div style="color:var(--c-text2);padding:16px;text-align:center">该分类暂无条目</div>';
    return;
  }
  // 默认全部可见；只有明确标记 can_view=false 的才不可见
  entries.forEach(e => {
    entryPermData[e.id] = perms[e.id] !== undefined ? perms[e.id] : true;
  });
  renderEntryPermList(entries);
}

function renderEntryPermList(entries) {
  const list = document.getElementById('entryPermList');
  list.innerHTML = entries.map(e => {
    const visible = entryPermData[e.id] !== false;
    return `<label style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:var(--c-input-bg);border-radius:8px;margin-bottom:4px;cursor:pointer">
      <input type="checkbox" class="entry-perm-cb" data-eid="${e.id}" ${visible ? 'checked' : ''} style="width:18px;height:18px;cursor:pointer;accent-color:var(--c-primary)">
      <span style="font-size:14px;flex:1">${esc(e.title || '(无标题)')}</span>
    </label>`;
  }).join('');
}

function entryPermSelectAll() {
  document.querySelectorAll('.entry-perm-cb').forEach(cb => cb.checked = true);
}

function entryPermClearAll() {
  document.querySelectorAll('.entry-perm-cb').forEach(cb => cb.checked = false);
}

async function saveEntryPerms() {
  const userId = entryPermUserId;
  const catId = entryPermCatId;
  if (!userId || !catId) return;
  const visibleIds = [];
  document.querySelectorAll('.entry-perm-cb').forEach(cb => {
    if (cb.checked) visibleIds.push(parseInt(cb.dataset.eid));
  });
  const r = await apiPost('set-entry-perms', { user_id: userId, category_id: catId, visible_entry_ids: visibleIds });
  if (r && r.ok) {
    closeModal('entryPermModal');
    showToast('条目可见性已保存', 'success');
  } else {
    showToast(r?.error || '保存失败', 'error');
  }
}
// ==================== 数据导出/导入 ====================
async function exportData() {
  const r = await apiGet('export-data');
  if (!r || !r.ok) { showToast('导出失败', 'error'); return; }
  const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'vault-backup-' + new Date().toISOString().slice(0, 10) + '.json';
  a.click();
  URL.revokeObjectURL(url);
  showToast('导出成功', 'success');
}

async function importData(file) {
  if (!file) return;
  if (!confirm('导入将替换所有现有数据，此操作不可撤销！\n建议先点击「导出备份」。\n\n确定继续？')) {
    document.getElementById('importFileInput').value = '';
    return;
  }
  try {
    const text = await file.text();
    let data;
    try { data = JSON.parse(text); } catch {
      showToast('文件格式错误，请选择有效的 JSON 文件', 'error');
      document.getElementById('importFileInput').value = '';
      return;
    }
    const r = await apiPost('import-data', data);
    if (r && r.ok) {
      showToast('导入成功，刷新中...', 'success');
      setTimeout(() => location.reload(), 1000);
    } else {
      showToast(r?.error || '导入失败', 'error');
    }
  } catch(e) {
    showToast('读取文件失败: ' + e.message, 'error');
  }
  document.getElementById('importFileInput').value = '';
}

// ==================== 改密 ====================
function openChangeMyPwd() {
  document.getElementById('myOldPwd').value = '';
  document.getElementById('myNewPwd').value = '';
  document.getElementById('myNewPwd2').value = '';
  showModal('changeMyPwdModal');
}

async function changeMyPwd() {
  const oldPwd = document.getElementById('myOldPwd').value;
  const newPwd = document.getElementById('myNewPwd').value;
  const newPwd2 = document.getElementById('myNewPwd2').value;
  if (!oldPwd || !newPwd) { showToast('请填写完整', 'error'); return; }
  if (newPwd.length < 4) { showToast('新密码至少 4 位', 'error'); return; }
  if (newPwd !== newPwd2) { showToast('两次输入的密码不一致', 'error'); return; }
  const r = await apiPost('change-my-pwd', { old_password: oldPwd, new_password: newPwd });
  if (r && r.ok) {
    closeModal('changeMyPwdModal');
    showToast('密码已修改，请重新登录', 'success');
    // 密码已修改，后端已清除所有会话，强制跳转登录
    setTimeout(() => {
      token = '';
      currentUser = null;
      clearStoredToken();
      document.getElementById('app').classList.remove('show');
      document.getElementById('authScreen').classList.remove('hidden');
      document.getElementById('authPassword').value = '';
      document.getElementById('authRemember').checked = false;
      authMode = 'login';
      switchAuthMode();
      loadUserList();
    }, 1200);
  } else {
    showToast(r?.error || '修改失败', 'error');
  }
}

// ==================== 通知铃铛 ====================
async function loadNotifCount() {
  try {
    if (currentUser.role === 'master') {
      const r = await apiGet('get-pending-reviews&status=pending');
      if (r && r.ok) {
        updateNotifBadge((r.proposals || []).length);
      }
    } else {
      const r = await apiGet('get-notifications&unread=1');
      if (r && r.ok) {
        updateNotifBadge(r.unread_count || 0);
      }
    }
  } catch (e) { /* 静默失败 */ }
}

function updateNotifBadge(count) {
  const badge = document.getElementById('notifBadge');
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count > 99 ? '99+' : count;
    badge.style.display = '';
  } else {
    badge.style.display = 'none';
  }
}

function openNotifPanel() {
  if (currentUser.role === 'master') {
    openReviewModal();
  } else {
    openMyProposalsModal();
  }
}

async function refreshNotifAfterAction() {
  await loadNotifCount();
}

// ==================== 图标选择器 ====================
function renderIconPicker(gridId, inputId, previewId, selected) {
  const grid = document.getElementById(gridId);
  if (!grid) return;
  grid.innerHTML = ICONS.map(icon =>
    `<button type="button" class="${icon === selected ? 'active' : ''}" onclick="selectIcon('${icon}','${inputId}','${previewId}','${gridId}')">${icon}</button>`
  ).join('');
}

function selectIcon(icon, inputId, previewId, gridId) {
  const input = document.getElementById(inputId);
  if (input) input.value = icon;
  updateIconPreview(inputId, previewId);
  renderIconPicker(gridId, inputId, previewId, icon);
}

function updateIconPreview(inputId, previewId) {
  const icon = document.getElementById(inputId)?.value.trim() || '🔐';
  const preview = document.getElementById(previewId);
  if (preview) preview.textContent = icon;
}

// ==================== 提案系统 ====================

function openEntryModalForSuggest(entryId) {
  openEntryModal(entryId);
  document.getElementById('entrySubmitBtn').dataset.mode = 'update';
}

async function submitEntryForReview(btn) {
  const title = document.getElementById('entryTitle').value.trim();
  if (!title) { showToast('请输入标题', 'error'); return; }
  const rows = document.querySelectorAll('#mfList .mf-row');
  rows.forEach((row, i) => {
    if (!modalFields[i]) return;
    modalFields[i].key = row.querySelector('.mf-key')?.value || '';
    modalFields[i].value = row.querySelector('.mf-val')?.value || '';
    modalFields[i].type = row.querySelector('.mf-type')?.value || modalFields[i].type || 'text';
  });
  const fields = modalFields.filter(f => f.value || f.key);
  const reason = prompt('请说明提案原因（可选）：');
  if (reason === null) return;
  const data = {
    proposal_type: editingEntryId ? 'update' : 'create',
    title,
    icon: document.getElementById('entryIcon').value || '🔐',
    category_id: editingEntryId ? undefined : activeCatId,
    target_entry_id: editingEntryId || undefined,
    entry_data: { fields },
    reason: reason || '',
  };
  btn.disabled = true;
  btn.textContent = '提交中...';
  try {
    const r = await apiPost('create-proposal', data);
    if (r && r.ok) {
      showToast('提案已提交，等待主账号审核', 'success');
      closeEntryModal();
      refreshNotifAfterAction();
    } else {
      showToast(r?.error || '提交失败', 'error');
    }
  } catch (e) {
    showToast('提交失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '📤 提交审核';
  }
}

// ---- 我的提案 ----
async function openMyProposalsModal() {
  showModal('myProposalsModal');
  document.getElementById('myProposalsList').innerHTML = '<div style="color:var(--c-text2);padding:20px;text-align:center">加载中...</div>';
  await loadMyProposals();
  await apiPost('mark-notification-read', {});
  updateNotifBadge(0);
}

function closeMyProposalsModal() { closeModal('myProposalsModal'); }

function setMyProposalsFilter(filter, btn) {
  myProposalsFilter = filter;
  document.querySelectorAll('#myProposalsFilter button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderMyProposals();
}

async function loadMyProposals() {
  try {
    const r = await apiGet('get-my-proposals');
    if (r && r.ok) { myProposals = r.proposals || []; renderMyProposals(); }
  } catch (e) {
    document.getElementById('myProposalsList').innerHTML = '<div style="color:var(--c-error);padding:20px;text-align:center">加载失败</div>';
  }
}

function renderMyProposals() {
  const list = document.getElementById('myProposalsList');
  const filtered = myProposalsFilter === 'all' ? myProposals : myProposals.filter(p => p.status === myProposalsFilter);
  if (!filtered.length) { list.innerHTML = '<div style="color:var(--c-text2);padding:20px;text-align:center">暂无提案</div>'; return; }
  const statusMap = { pending: '⏳ 待审核', approved: '✅ 已通过', rejected: '❌ 已驳回' };
  const typeMap = { create: '📝 新条目', update: '✏️ 修改建议', report: '🚩 问题上报' };
  const statusColor = { pending: 'var(--c-warning)', approved: 'var(--c-success)', rejected: 'var(--c-error)' };
  list.innerHTML = filtered.map(p => `
    <div class="admin-user-card" style="border-left:3px solid ${statusColor[p.status] || 'var(--c-border)'}">
      <div class="admin-user-main" style="flex-direction:column;align-items:stretch;gap:4px">
        <div class="admin-user-name">${p.icon || '🔐'} ${esc(p.title)}
          <span style="font-size:11px;font-weight:400;padding:2px 6px;border-radius:4px;background:var(--c-primary-light);color:var(--c-primary)">${typeMap[p.proposal_type] || ''}</span>
          <span style="font-size:11px;font-weight:400;padding:2px 6px;border-radius:4px;background:var(--c-input-bg);color:${statusColor[p.status]}">${statusMap[p.status] || p.status}</span>
        </div>
        <div style="font-size:12px;color:var(--c-text2)">🕐 ${p.created_at}${p.category_name ? ' · 📂 ' + esc(p.category_name) : ''}</div>
        ${p.reason ? '<div style="font-size:13px;color:var(--c-text2);background:var(--c-badge);border-radius:6px;padding:6px 10px;margin-top:2px">💬 ' + esc(p.reason) + '</div>' : ''}
        ${p.review_comment ? '<div style="font-size:13px;color:var(--c-text);background:var(--c-input-bg);border-radius:6px;padding:6px 10px;margin-top:2px">📋 审核意见：' + esc(p.review_comment) + '</div>' : ''}
        ${p.status === 'pending' ? '<div style="display:flex;gap:6px;margin-top:4px"><button class="btn btn-secondary" style="padding:6px 12px;font-size:12px;border-radius:6px" onclick="deleteProposal(' + p.id + ')">🗑️ 撤回</button></div>' : ''}
      </div>
    </div>
  `).join('');
}

async function deleteProposal(id) {
  if (!confirm('确定要撤回这个提案吗？')) return;
  try {
    const r = await apiPost('delete-proposal', { id });
    if (r && r.ok) { showToast('已撤回', 'success'); await loadMyProposals(); refreshNotifAfterAction(); }
    else showToast(r?.error || '操作失败', 'error');
  } catch (e) { showToast('操作失败: ' + e.message, 'error'); }
}

// ---- 审核队列 ----
async function openReviewModal() {
  showModal('reviewModal');
  document.getElementById('reviewList').innerHTML = '<div style="color:var(--c-text2);padding:20px;text-align:center">加载中...</div>';
  await loadPendingReviews();
}

function closeReviewModal() { closeModal('reviewModal'); }

function setReviewFilter(filter, btn) {
  reviewFilter = filter;
  document.querySelectorAll('#reviewFilter button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderReviewList();
}

async function loadPendingReviews() {
  try {
    const r = await apiGet('get-pending-reviews&status=all');
    if (r && r.ok) { reviews = r.proposals || []; renderReviewList(); }
  } catch (e) {
    document.getElementById('reviewList').innerHTML = '<div style="color:var(--c-error);padding:20px;text-align:center">加载失败</div>';
  }
}

function renderReviewList() {
  const list = document.getElementById('reviewList');
  const badge = document.getElementById('reviewBadge');
  const filtered = reviewFilter === 'all' ? reviews : reviews.filter(p => p.proposal_type === reviewFilter);
  const pendingCount = reviews.filter(p => p.status === 'pending').length;
  badge.textContent = pendingCount > 0 ? '(' + pendingCount + ' 项待审)' : '';
  if (!filtered.length) { list.innerHTML = '<div style="color:var(--c-text2);padding:20px;text-align:center">暂无待审核提案</div>'; return; }
  const typeMap = { create: '📝 新条目', update: '✏️ 修改建议', report: '🚩 问题上报' };
  const statusMap = { pending: '⏳ 待审核', approved: '✅ 已通过', rejected: '❌ 已驳回' };
  const statusColor = { pending: 'var(--c-warning)', approved: 'var(--c-success)', rejected: 'var(--c-error)' };
  list.innerHTML = filtered.map(p => {
    const fieldsHtml = p.entry_data && p.entry_data.fields && p.entry_data.fields.length
      ? p.entry_data.fields.map(f => '<div style="font-size:13px;padding:2px 0"><strong>' + esc(f.key || '') + ':</strong> ' + (f.type === 'password' ? '••••••••' : esc(f.value || '')) + '</div>').join('')
      : '<div style="color:var(--c-text2);font-size:12px">无字段数据</div>';
    return '<div class="admin-user-card" style="border-left:3px solid ' + (statusColor[p.status] || 'var(--c-border)') + '">'
      + '<div class="admin-user-main" style="flex-direction:column;align-items:stretch;gap:6px">'
      + '<div class="admin-user-name">' + (p.icon || '🔐') + ' ' + esc(p.title)
      + ' <span style="font-size:11px;font-weight:400;padding:2px 6px;border-radius:4px;background:var(--c-primary-light);color:var(--c-primary)">' + (typeMap[p.proposal_type] || '') + '</span>'
      + ' <span style="font-size:11px;font-weight:400;padding:2px 6px;border-radius:4px;background:var(--c-input-bg);color:' + (statusColor[p.status]) + '">' + (statusMap[p.status] || p.status) + '</span></div>'
      + '<div style="font-size:12px;color:var(--c-text2)">👤 ' + esc(p.creator_name || '未知') + ' · 🕐 ' + p.created_at + (p.category_name ? ' · 📂 ' + esc(p.category_name) : '') + '</div>'
      + '<div style="background:var(--c-input-bg);border-radius:8px;padding:10px;margin:4px 0">' + fieldsHtml + '</div>'
      + (p.reason ? '<div style="font-size:13px;color:var(--c-text2);background:var(--c-badge);border-radius:6px;padding:6px 10px">💬 ' + esc(p.reason) + '</div>' : '')
      + (p.review_comment ? '<div style="font-size:13px;color:var(--c-text);background:var(--c-input-bg);border-radius:6px;padding:6px 10px">📋 审核意见：' + esc(p.review_comment) + '</div>' : '')
      + (p.status === 'pending' ? '<div style="display:flex;gap:6px;margin-top:4px;align-items:flex-end">'
        + '<textarea id="reviewComment_' + p.id + '" placeholder="审核意见（可选）" style="flex:1;padding:8px 10px;font-size:13px;min-height:36px;resize:vertical;border:2px solid var(--c-border);border-radius:8px;background:var(--c-input-bg);color:var(--c-text)" rows="1"></textarea>'
        + '<button class="btn btn-primary" style="padding:8px 16px;font-size:13px;white-space:nowrap;border-radius:8px" onclick="doReview(' + p.id + ', \'approve\')">✅ 批准</button>'
        + '<button class="btn btn-danger" style="padding:8px 16px;font-size:13px;white-space:nowrap;border-radius:8px" onclick="doReview(' + p.id + ', \'reject\')">❌ 驳回</button>'
        + '</div>' : '')
      + '</div></div>';
  }).join('');
}

async function doReview(proposalId, action) {
  if (!confirm('确定要' + (action === 'approve' ? '批准' : '驳回') + '这个提案吗？')) return;
  const comment = document.getElementById('reviewComment_' + proposalId)?.value?.trim() || '';
  try {
    const r = await apiPost('review-proposal', { proposal_id: proposalId, action, review_comment: comment });
    if (r && r.ok) {
      showToast(action === 'approve' ? '✅ 已批准并合并' : '已驳回', action === 'approve' ? 'success' : 'info');
      await loadPendingReviews();
      refreshNotifAfterAction();
      if (action === 'approve' && activeCatId) loadEntries(activeCatId);
      if (action === 'approve') markDataDirty();
    } else {
      showToast(r?.error || '操作失败', 'error');
    }
  } catch (e) { showToast('操作失败: ' + e.message, 'error'); }
}

// ---- 报告问题 ----
function openReportModal(entryId) {
  const entry = entries.find(e => e.id === parseInt(entryId));
  if (!entry) return;
  reportTargetEntry = entry;
  document.getElementById('reportEntryInfo').textContent = (entry.icon || '🔐') + ' ' + (entry.title || '');
  document.getElementById('reportReason').value = '';
  showModal('reportModal');
  setTimeout(() => document.getElementById('reportReason').focus(), 100);
}

function closeReportModal() {
  document.getElementById('reportModal').classList.remove('show');
  reportTargetEntry = null;
  closeModalHistCleanup();
}

async function submitReport() {
  if (!reportTargetEntry) return;
  const reason = document.getElementById('reportReason').value.trim();
  if (!reason) { showToast('请描述问题', 'error'); return; }
  const btn = document.getElementById('reportSubmitBtn');
  btn.disabled = true; btn.textContent = '提交中...';
  try {
    const r = await apiPost('create-proposal', {
      proposal_type: 'report', title: reportTargetEntry.title,
      category_id: reportTargetEntry.category_id, target_entry_id: reportTargetEntry.id,
      icon: reportTargetEntry.icon || '🔐', entry_data: { fields: [] }, reason,
    });
    if (r && r.ok) { showToast('问题已上报，等待主账号处理', 'success'); closeReportModal(); refreshNotifAfterAction(); }
    else showToast(r?.error || '提交失败', 'error');
  } catch (e) { showToast('提交失败: ' + e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = '提交'; }
}

// ==================== Server酱推送 ====================
async function serverchanLoadConfig() {
  const r = await apiGet('serverchan-config');
  if (r && r.ok) {
    document.getElementById('scSendKey').placeholder = r.has_key ? '已配置（留空不修改）' : '输入 SendKey';
    document.getElementById('scStatus').innerHTML = r.has_key ? '<span style="color:var(--c-success)">✅ 已配置</span>' : '<span style="color:var(--c-text2)">未配置</span>';
  }
}

async function serverchanSave() {
  const key = document.getElementById('scSendKey').value.trim();
  const r = await apiPost('serverchan-config-save', { sendkey: key });
  if (r && r.ok) {
    showToast('配置已保存', 'success');
    document.getElementById('scSendKey').value = '';
    document.getElementById('scSendKey').placeholder = key ? '已配置（留空不修改）' : '输入 SendKey';
    document.getElementById('scStatus').innerHTML = '<span style="color:var(--c-success)">✅ 已保存</span>';
    setTimeout(() => { document.getElementById('scStatus').innerHTML = ''; }, 2000);
  } else { showToast(r?.error || '保存失败', 'error'); }
}

async function serverchanTest() {
  const status = document.getElementById('scStatus');
  status.innerHTML = '<span style="color:var(--c-text2)">测试中...</span>';
  const r = await apiPost('serverchan-test', {});
  if (r && r.ok) { status.innerHTML = '<span style="color:var(--c-success)">✅ ' + esc(r.msg) + '</span>'; }
  else { status.innerHTML = '<span style="color:var(--c-error)">❌ ' + esc(r?.error || '测试失败') + '</span>'; }
}

// ==================== WebDAV ====================
async function webdavLoadConfig() {
  const r = await apiGet('webdav-config');
  if (r && r.ok) {
    document.getElementById('wdUrl').value = r.url || '';
    document.getElementById('wdUser').value = r.username || '';
    document.getElementById('wdPass').placeholder = r.has_password ? '已设置（留空不修改）' : '设置密码';
    const syncR = await apiGet('webdav-last-sync');
    if (syncR && syncR.ok && syncR.time) {
      document.getElementById('wdStatus').innerHTML = '<span style="color:var(--c-text2)">上次同步: ' + new Date(syncR.time).toLocaleString() + '</span>';
    }
  }
}

async function webdavSaveConfig() {
  const url = document.getElementById('wdUrl').value.trim();
  const username = document.getElementById('wdUser').value.trim();
  const password = document.getElementById('wdPass').value;
  if (!url) { showToast('请输入 WebDAV 地址', 'error'); return; }
  const r = await apiPost('webdav-config-save', { url, username, password });
  if (r && r.ok) {
    showToast('配置已保存', 'success');
    document.getElementById('wdPass').value = '';
    document.getElementById('wdPass').placeholder = '已设置（留空不修改）';
    document.getElementById('wdCfgStatus').innerHTML = '<span style="color:var(--c-success)">✅ 已保存</span>';
    setTimeout(() => { document.getElementById('wdCfgStatus').innerHTML = ''; }, 2000);
  } else {
    showToast(r?.error || '保存失败', 'error');
  }
}

async function webdavTest() {
  const cfgStatus = document.getElementById('wdCfgStatus');
  cfgStatus.innerHTML = '<span style="color:var(--c-text2)">测试中...</span>';
  const r = await apiPost('webdav-test', {});
  if (r && r.ok) {
    cfgStatus.innerHTML = '<span style="color:var(--c-success)">✅ ' + esc(r.msg) + '</span>';
  } else {
    cfgStatus.innerHTML = '<span style="color:var(--c-error)">❌ ' + esc(r?.error || '测试失败') + (r?.code ? ' [' + r.code + ']' : '') + '</span>';
  }
}

async function webdavUpload() {
  if (!confirm('确定将当前数据上传到 WebDAV 备份？')) return;
  const btn = document.getElementById('wdUploadBtn');
  const status = document.getElementById('wdStatus');
  btn.disabled = true; btn.textContent = '⏳ 上传中...';
  status.innerHTML = '<span style="color:var(--c-text2)">上传中...</span>';
  showLoadingOverlay('正在上传备份到云端...');
  try {
    const r = await apiPost('webdav-save', {}, 90000);
    if (r && r.ok) {
      showToast('已上传到 WebDAV', 'success');
      const size = r.size ? ' (' + (r.size / 1024).toFixed(1) + ' KB)' : '';
      status.innerHTML = '<span style="color:var(--c-success)">✅ 上次同步: ' + new Date().toLocaleString() + size + '</span>';
    } else {
      status.innerHTML = '<span style="color:var(--c-error)">❌ ' + esc(r?.error || '上传失败') + (r?.code ? ' [' + r.code + ']' : '') + '</span>';
    }
  } catch(e) { status.innerHTML = '<span style="color:var(--c-error)">网络错误: ' + esc(e.message) + '</span>'; }
  hideLoadingOverlay();
  btn.disabled = false; btn.textContent = '⬆️ 上传备份';
}

async function webdavDownload() {
  if (!confirm('从 WebDAV 下载将替换所有当前数据，确定继续？')) return;
  const btn = document.getElementById('wdDownloadBtn');
  const status = document.getElementById('wdStatus');
  btn.disabled = true; btn.textContent = '⏳ 下载中...';
  status.innerHTML = '<span style="color:var(--c-text2)">下载中...</span>';
  showLoadingOverlay('正在从云端下载备份...');
  try {
    const r = await apiPost('webdav-load', {}, 90000);
    if (!r || !r.ok) { status.innerHTML = '<span style="color:var(--c-error)">' + esc(r?.error || '下载失败') + '</span>'; btn.disabled = false; btn.textContent = '⬇️ 下载恢复'; return; }
    if (!r.data) { showToast('WebDAV 暂无备份', 'info'); status.innerHTML = '<span style="color:var(--c-text2)">WebDAV 暂无备份文件</span>'; btn.disabled = false; btn.textContent = '⬇️ 下载恢复'; return; }
    const imp = await apiPost('import-data', r.data);
    if (imp && imp.ok) {
      showToast('从 WebDAV 恢复成功，刷新中...', 'success');
      setTimeout(() => location.reload(), 1000);
    } else {
      status.innerHTML = '<span style="color:var(--c-error)">恢复失败: ' + esc(imp?.error || '') + '</span>';
    }
  } catch(e) { status.innerHTML = '<span style="color:var(--c-error)">网络错误: ' + esc(e.message) + '</span>'; }
  hideLoadingOverlay();
  btn.disabled = false; btn.textContent = '⬇️ 下载恢复';
}

async function loadWebdavVersions() {
  const list = document.getElementById('wdVersionList');
  list.innerHTML = '<div style="color:var(--c-text2);padding:8px;text-align:center">加载中...</div>';
  const r = await apiGet('webdav-versions');
  if (!r || !r.ok || !r.versions || !r.versions.length) {
    list.innerHTML = '<div style="color:var(--c-text2);padding:8px;text-align:center">暂无备份版本</div>';
    return;
  }
  list.innerHTML = r.versions.map(v => {
    const t = new Date(v.time);
    const timeStr = t.toLocaleDateString('zh-CN') + ' ' + t.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
    return `<div style="display:flex;align-items:center;justify-content:space-between;padding:7px 10px;background:var(--c-input-bg);border-radius:8px;margin-bottom:4px">
      <div>
        <div style="font-size:13px">${timeStr}</div>
        <div style="font-size:11px;color:var(--c-text2)">${esc(v.name)}</div>
      </div>
      <button style="font-size:11px;padding:3px 10px;border-radius:6px;color:#fff;background:var(--c-primary);border:none;cursor:pointer" onclick="restoreWebdavVersion('${escAttr(v.name)}')">恢复</button>
    </div>`;
  }).join('');
}

async function restoreWebdavVersion(name) {
  if (!confirm('确定恢复到版本 ' + name + '？所有当前数据将被替换。')) return;
  const btn = document.getElementById('wdDownloadBtn');
  btn.disabled = true; btn.textContent = '⏳ 恢复中...';
  showLoadingOverlay('正在恢复版本 ' + name + '...');
  try {
    // 用 webdav-load 拉最新，但这里需要拉指定版本
    // 直接构造下载 URL 来获取指定文件
    const r = await apiPost('webdav-load-version', { name }, 90000);
    if (!r || !r.ok || !r.data) { showToast(r?.error || '版本加载失败', 'error'); btn.disabled = false; btn.textContent = '⬇️ 下载恢复'; return; }
    const imp = await apiPost('import-data', r.data);
    if (imp && imp.ok) {
      showToast('已恢复到 ' + name + '，刷新中...', 'success');
      setTimeout(() => location.reload(), 1000);
    } else {
      showToast(imp?.error || '恢复失败', 'error');
    }
  } catch(e) { showToast('网络错误: ' + e.message, 'error'); }
  hideLoadingOverlay();
  btn.disabled = false; btn.textContent = '⬇️ 下载恢复';
}

// ==================== AUTO SYNC PROMPT ====================
let _dataDirty = false;
let _syncBarTimer = null;
let _webdavConfigured = false;
let _lastSyncTime = null;

async function initSyncState() {
  try {
    const r = await apiGet('webdav-config');
    _webdavConfigured = r && r.ok && !!r.url;
    if (_webdavConfigured) {
      const sr = await apiGet('webdav-last-sync');
      if (sr && sr.ok && sr.time) _lastSyncTime = sr.time;
      // 登录后检查云端是否有更新
      await checkCloudForUpdates();
    }
  } catch {}
}

// 登录时检查云端是否有比本地更新的备份
async function checkCloudForUpdates() {
  try {
    const r = await apiGet('webdav-cloud-latest');
    if (!r || !r.ok || !r.configured || !r.time) return;
    const cloudTime = new Date(r.time).getTime();
    const localTime = _lastSyncTime ? new Date(_lastSyncTime).getTime() : 0;
    // 本地从未同步且已有数据 → 不覆盖，跳过
    if (!_lastSyncTime) {
      const cats = await apiGet('get-categories');
      if (cats && cats.ok && cats.categories && cats.categories.length > 0) return;
    }
    // 云端比本地新（或本地从未同步且无数据）→ 弹窗询问
    if (cloudTime > localTime) {
      const cloudStr = new Date(r.time).toLocaleString();
      const localStr = _lastSyncTime ? new Date(_lastSyncTime).toLocaleString() : '从未同步';
      document.getElementById('cloudSyncInfo').innerHTML =
        '☁️ 云端最新备份: <strong>' + cloudStr + '</strong><br>' +
        '💾 本地上次同步: <strong>' + localStr + '</strong>';
      showModal('cloudSyncModal');
    }
  } catch {}
}

function dismissCloudSync() {
  closeModal('cloudSyncModal');
}

async function syncFromCloudPrompt() {
  const btn = document.getElementById('cloudSyncBtn');
  btn.disabled = true;
  btn.textContent = '⏳ 同步中...';
  showLoadingOverlay('正在从云端同步...');
  try {
    const r = await apiPost('webdav-load', {}, 90000);
    if (!r || !r.ok || !r.data) {
      showToast(r?.error || '下载失败', 'error');
      btn.disabled = false;
      btn.textContent = '⬇️ 从云端同步';
      return;
    }
    const imp = await apiPost('import-data', r.data);
    if (imp && imp.ok) {
      showToast('☁️ 从云端同步成功，刷新中...', 'success');
      closeModal('cloudSyncModal');
      _lastSyncTime = new Date().toISOString();
      setTimeout(() => location.reload(), 1000);
    } else {
      showToast(imp?.error || '恢复失败', 'error');
      btn.disabled = false;
      btn.textContent = '⬇️ 从云端同步';
    }
  } catch(e) {
    showToast('同步失败: ' + e.message, 'error');
    btn.disabled = false;
    btn.textContent = '⬇️ 从云端同步';
  }
  hideLoadingOverlay();
}

function markDataDirty() {
  if (!_webdavConfigured || !currentUser || currentUser.role !== 'master') return;
  _dataDirty = true;
  if (_syncBarTimer) clearTimeout(_syncBarTimer);
  _syncBarTimer = setTimeout(showSyncBar, 2000);
}

function hideSyncBar() {
  const bar = document.getElementById('syncBar');
  if (bar) bar.classList.remove('show');
  _dataDirty = false;
}

async function showSyncBar() {
  if (!_dataDirty) return;
  const bar = document.getElementById('syncBar');
  if (!bar) return;
  document.getElementById('syncBarDetail').textContent = '加载版本信息...';
  bar.classList.add('show');
  let cloudTimeStr = '暂无备份';
  try {
    const r = await apiGet('webdav-versions');
    if (r && r.ok && r.versions && r.versions.length > 0) cloudTimeStr = new Date(r.versions[0].time).toLocaleString();
  } catch {}
  const lastSyncStr = _lastSyncTime ? new Date(_lastSyncTime).toLocaleString() : '从未同步';
  document.getElementById('syncBarDetail').innerHTML = '本地: ' + lastSyncStr + ' · ☁️ 云端: ' + cloudTimeStr;
}

async function quickSync() {
  const btn = document.getElementById('syncBarBtn');
  btn.disabled = true; btn.textContent = '⏳';
  showLoadingOverlay('正在同步到云端...');
  try {
    const r = await apiPost('webdav-save', {}, 90000);
    if (r && r.ok) {
      showToast('☁️ 已同步到云端', 'success');
      _lastSyncTime = new Date().toISOString();
      hideSyncBar();
      // 同步后更新管理面板中的状态
      const wdStatus = document.getElementById('wdStatus');
      if (wdStatus) {
        const size = r.size ? ' (' + (r.size / 1024).toFixed(1) + ' KB)' : '';
        wdStatus.innerHTML = '<span style="color:var(--c-success)">✅ 上次同步: ' + new Date().toLocaleString() + size + '</span>';
      }
    } else showToast(r?.error || '同步失败', 'error');
  } catch(e) { showToast('同步失败: ' + e.message, 'error'); }
  hideLoadingOverlay();
  btn.disabled = false; btn.textContent = '☁️ 上传';
}

// ==================== DEBUG ====================
async function viewDebugLog() {
  showModal('debugLogModal');
  document.getElementById('debugLogContent').textContent = '加载中...';
  const r = await apiGet('debug-log&lines=100');
  if (!r || !r.ok) {
    document.getElementById('debugLogContent').textContent = '⚠️ 读取日志失败: ' + (r?.error || '未知错误');
    document.getElementById('debugLogInfo').textContent = '';
    return;
  }
  document.getElementById('debugLogInfo').textContent = '路径: ' + (r.path || '?') + ' | 大小: ' + (r.size || 0) + ' bytes';
  document.getElementById('debugLogContent').textContent = r.log || '(空)';
}

async function viewSystemInfo() {
  const info = [];
  info.push('API Base: ' + API);
  info.push('Token: ' + (token ? token.substring(0, 16) + '...' : '(无)'));
  info.push('Current User: ' + (currentUser ? currentUser.username + ' (' + currentUser.role + ')' : '(未登录)'));
  info.push('Categories: ' + categories.length);
  info.push('Theme: ' + (document.body.getAttribute('data-theme') || 'light'));
  info.push('User Agent: ' + navigator.userAgent);
  info.push('Time: ' + new Date().toISOString());
  
  const r = await apiGet('me');
  info.push('---');
  info.push('Auth check (me): ' + JSON.stringify(r));
  
  showModal('debugLogModal');
  document.getElementById('debugLogInfo').textContent = '系统信息';
  document.getElementById('debugLogContent').textContent = info.join('\n');
}

// ==================== SEARCH ====================

const debouncedSearch = debounce((query) => onSearch(query));

function onSearch(query) {
  const q = query.toLowerCase().trim();
  if (!q) {
    // 清空搜索：恢复原视图
    if (activeCatId) {
      renderEntries();
    } else {
      renderCategories();
    }
    return;
  }
  if (activeCatId) {
    // 在条目中搜索
    const filtered = entries.filter(e => {
      const fields = getEntryFields(e);
      return (e.title || '').toLowerCase().includes(q)
        || fields.some(f => (f.key + ' ' + f.value).toLowerCase().includes(q));
    });
    const list = document.getElementById('entryList');
    if (!filtered.length) {
      list.innerHTML = '<div class="entry-empty">🔍 未找到匹配条目</div>';
      return;
    }
    // 临时用 filtered 渲染
    const orig = entries;
    entries = filtered;
    renderEntries();
    entries = orig;
  } else {
    // 在分类中搜索
    const filtered = categories.filter(c => c.name.toLowerCase().includes(q));
    const list = document.getElementById('categoryList');
    if (!filtered.length) {
      list.innerHTML = '<div style="text-align:center;padding:40px;color:var(--c-text2)">🔍 未找到匹配分类</div>';
      return;
    }
    list.innerHTML = filtered.map(c =>
      `<div class="cat-card${activeCatId === c.id ? ' active' : ''}" onclick="loadEntries(${c.id})">
        <div class="cat-icon">${esc(c.icon || '🔑')}</div>
        <div class="cat-name">${esc(c.name)}</div>
        <div class="cat-count">点击查看</div>
        ${!c.can_write ? '<div class="cat-badge">只读</div>' : ''}
      </div>`
    ).join('');
  }
}

// ==================== AUTO-LOCK ====================
let autoLockTimer = null;
const AUTO_LOCK_MS = 60 * 60 * 1000; // 1 小时无操作退回登录页

function resetAutoLock() {
  if (autoLockTimer) clearTimeout(autoLockTimer);
  autoLockTimer = setTimeout(() => {
    if (token) {
      idleLogout();
    }
  }, AUTO_LOCK_MS);
}

// 用户活动时重置计时器
['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(evt => {
  document.addEventListener(evt, resetAutoLock, { passive: true });
});

// 无操作退出：退回登录页，不删除服务端会话（七天免登录时会话仍有效）
function idleLogout() {
  const keepForSevenDays = hasRememberedLogin();
  token = '';
  currentUser = null;
  // 普通会话在闲置锁定后必须重新登录；七天会话保留服务端会话，
  // 刷新页面时可在有效期内恢复。
  if (!keepForSevenDays) sessionStorage.removeItem(SESSION_TOKEN_KEY);
  sessionStorage.setItem('vault_idle_logged_out', '1');
  document.getElementById('app').classList.remove('show');
  document.getElementById('authScreen').classList.remove('hidden');
  document.getElementById('authPassword').value = '';
  authMode = 'login';
  switchAuthMode();
  loadUserList();
  showToast('长时间未操作，请重新登录', 'info');
}

// ==================== UTILS ====================
async function apiGet(action, timeoutMs = 30000) {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    const res = await fetch(API + '?action=' + action + '&_t=' + Date.now(), {
      headers: token ? { 'Authorization': 'Bearer ' + token } : {},
      signal: ctrl.signal
    });
    clearTimeout(timer);
    const json = await res.json();
    if (!json.ok) console.warn('[API GET]', action, '❌', json);
    return json;
  } catch(e) { console.error('[API GET]', action, '💥', e.message); return null; }
}

async function apiPost(action, data, timeoutMs = 30000) {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    const res = await fetch(API + '?action=' + action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': 'Bearer ' + token } : {}) },
      body: JSON.stringify(data),
      signal: ctrl.signal
    });
    clearTimeout(timer);
    const json = await res.json();
    if (!json.ok) console.warn('[API POST]', action, '❌', json);
    return json;
  } catch(e) { console.error('[API POST]', action, '💥', e.message); return null; }
}

function closeModal(id) {
  document.getElementById(id).classList.remove('show');
  closeModalHistCleanup();
}

// ==================== LOADING OVERLAY ====================
let _loadingTimer = null;
function showLoadingOverlay(text) {
  clearTimeout(_loadingTimer);
  _loadingTimer = setTimeout(() => {
    document.getElementById('loadingText').textContent = text || '处理中...';
    document.getElementById('loadingOverlay').classList.add('show');
  }, 300);
}
function hideLoadingOverlay() {
  clearTimeout(_loadingTimer);
  _loadingTimer = null;
  document.getElementById('loadingOverlay').classList.remove('show');
}

// 点击弹窗空白区域（overlay）关闭当前弹窗
document.addEventListener('click', function(e) {
  if (e.target.classList.contains('modal-overlay') && e.target.classList.contains('show')) {
    e.target.classList.remove('show');
    closeModalHistCleanup();
  }
});

// Escape 键关闭最顶层弹窗
document.addEventListener('keydown', function(e) {
  if (e.key !== 'Escape') return;
  const overlays = document.querySelectorAll('.modal-overlay.show');
  if (overlays.length) {
    overlays[overlays.length - 1].classList.remove('show');
    closeModalHistCleanup();
    e.preventDefault();
  }
});



async function copyText(text) {
  if (!text) { showToast('无可复制的内容', 'info'); return; }
  try {
    await navigator.clipboard.writeText(text);
    showToast('已复制', 'success');
  } catch {
    showToast('复制失败', 'error');
  }
}

// ==================== INIT ====================
init();

