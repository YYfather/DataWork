import {
  flattenLibrary,
  filterLibrary,
  clampProgress,
  progressStorageKey,
} from './core.mjs';
import * as pdfjs from './vendor/pdf.min.mjs';

pdfjs.GlobalWorkerOptions.workerSrc = './vendor/pdf.worker.min.mjs';

const $ = (id) => document.getElementById(id);
const els = {
  library: $('library'), bookList: $('bookList'), stats: $('libraryStats'), size: $('librarySize'),
  search: $('searchInput'), collapseAll: $('collapseAll'), recentBlock: $('recentBlock'), recentBook: $('recentBook'),
  stage: $('readingStage'), pages: $('pages'), empty: $('emptyState'), loading: $('loadingState'), loadingText: $('loadingText'),
  error: $('errorState'), errorText: $('errorText'), retry: $('retryButton'), title: $('bookTitle'), collection: $('bookCollection'),
  controls: $('readerControls'), footer: $('readerFooter'), pageInput: $('pageInput'), pageCount: $('pageCount'),
  prev: $('prevPage'), next: $('nextPage'), progress: $('progressBar'), progressText: $('progressText'),
  pageMode: $('pageMode'), scrollMode: $('scrollMode'), toast: $('toast'),
};

const state = {
  library: { collections: [], total: 0, bytes: 0 },
  currentBook: null,
  pdf: null,
  page: 1,
  mode: localStorage.getItem('reader-next:mode') || 'page',
  zoom: 1,
  fit: true,
  epoch: 0,
  observer: null,
  collapsed: new Set(),
};

function formatBytes(bytes) {
  if (!bytes) return '0 MB';
  const mb = bytes / 1024 / 1024;
  return mb > 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`;
}

function readProgress(book) {
  try { return JSON.parse(localStorage.getItem(progressStorageKey(book.path))) || null; }
  catch { return null; }
}

function saveProgress() {
  if (!state.currentBook || !state.pdf) return;
  const payload = { page: state.page, pages: state.pdf.numPages, updatedAt: Date.now() };
  localStorage.setItem(progressStorageKey(state.currentBook.path), JSON.stringify(payload));
  localStorage.setItem('reader-next:last-book', state.currentBook.path);
  updateProgressUI();
}

function progressPercent(book) {
  const saved = readProgress(book);
  if (!saved?.pages) return 0;
  return Math.round((clampProgress(saved.page, saved.pages) / saved.pages) * 100);
}

function renderLibrary(query = '') {
  const collections = filterLibrary(state.library.collections, query);
  if (!collections.length) {
    els.bookList.innerHTML = '<div class="empty-list">没有找到这本书，换个关键词试试。</div>';
    return;
  }
  els.bookList.innerHTML = collections.map((collection) => {
    const collapsed = state.collapsed.has(collection.name);
    const books = collection.books.map((book) => {
      const percent = progressPercent(book);
      const active = state.currentBook?.path === book.path;
      return `<button class="book-row${active ? ' active' : ''}" data-path="${encodeURIComponent(book.path)}" title="${escapeHtml(book.name)}">
        <strong>${escapeHtml(book.name)}</strong>
        <small>${percent ? `${percent}% 已读` : formatBytes(book.size)}</small>
        ${percent ? `<span class="row-progress"><i style="width:${percent}%"></i></span>` : ''}
      </button>`;
    }).join('');
    return `<section class="collection${collapsed ? ' collapsed' : ''}" data-collection="${encodeURIComponent(collection.name)}">
      <button class="collection-head" aria-expanded="${!collapsed}"><i data-lucide="chevron-down"></i><strong>${escapeHtml(collection.name)}</strong><span>${collection.books.length}</span></button>
      <div class="collection-books">${books}</div>
    </section>`;
  }).join('');
  refreshIcons();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

function findBook(path) {
  for (const collection of state.library.collections) {
    const book = collection.books.find((item) => item.path === path);
    if (book) return book;
  }
  return null;
}

function updateRecent() {
  const lastPath = localStorage.getItem('reader-next:last-book');
  const book = lastPath && findBook(lastPath);
  const saved = book && readProgress(book);
  if (!book || !saved) { els.recentBlock.hidden = true; return; }
  els.recentBlock.hidden = false;
  els.recentBook.dataset.path = encodeURIComponent(book.path);
  els.recentBook.innerHTML = `<strong>${escapeHtml(book.name)}</strong><span>第 ${saved.page} 页 · ${progressPercent(book)}% 已读</span>`;
}

async function loadLibrary() {
  els.stats.textContent = '正在整理书架…';
  try {
    const response = await fetch('api.php', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || '书库接口返回异常');
    state.library = flattenLibrary(data.folders);
    els.stats.textContent = `${state.library.collections.length} 个系列 · ${state.library.total} 本书`;
    els.size.textContent = formatBytes(state.library.bytes);
    renderLibrary();
    updateRecent();
  } catch (error) {
    els.stats.textContent = '书架加载失败';
    els.bookList.innerHTML = `<div class="empty-list">${escapeHtml(error.message)}<br><button class="text-btn" id="retryLibrary">重新加载</button></div>`;
    $('retryLibrary')?.addEventListener('click', loadLibrary);
  }
}

function showView(name) {
  els.empty.hidden = name !== 'empty';
  els.loading.hidden = name !== 'loading';
  els.error.hidden = name !== 'error';
  els.pages.hidden = name !== 'pages';
}

async function openBook(book) {
  if (!book) return;
  state.currentBook = book;
  state.epoch += 1;
  const epoch = state.epoch;
  showView('loading');
  els.loadingText.textContent = '正在翻开书页…';
  els.title.textContent = book.name;
  els.collection.textContent = book.collection;
  els.controls.hidden = true;
  els.footer.hidden = true;
  closeLibrary();
  renderLibrary(els.search.value);
  try {
    state.pdf = await pdfjs.getDocument({ url: book.url, cMapPacked: true }).promise;
    if (epoch !== state.epoch) return;
    const saved = readProgress(book);
    state.page = clampProgress(saved?.page || 1, state.pdf.numPages);
    els.pageCount.textContent = state.pdf.numPages;
    els.controls.hidden = false;
    els.footer.hidden = false;
    await renderDocument();
    updateProgressUI();
    updateRecent();
    document.title = `${book.name} · 一隅书房`;
  } catch (error) {
    if (state.currentBook?.path !== book.path) return;
    showView('error');
    els.errorText.textContent = error?.message || 'PDF 文件加载失败，请稍后重试。';
  }
}

async function renderDocument() {
  if (!state.pdf) return;
  state.epoch += 1;
  const epoch = state.epoch;
  state.observer?.disconnect();
  els.pages.innerHTML = '';
  els.pages.className = `pages ${state.mode === 'scroll' ? 'continuous' : 'single'}`;
  showView('pages');
  updateModeUI();
  if (state.mode === 'scroll') await renderContinuous(epoch);
  else await renderSingle(epoch);
}

async function pageScale(page) {
  const base = page.getViewport({ scale: 1 });
  if (!state.fit) return state.zoom;
  const horizontalPadding = window.innerWidth <= 760 ? 24 : 100;
  return Math.max(.25, Math.min(2.2, (els.stage.clientWidth - horizontalPadding) / base.width));
}

async function renderPage(pageNumber, shell, epoch) {
  if (epoch !== state.epoch || shell.dataset.rendered) return;
  shell.dataset.rendered = 'loading';
  const page = await state.pdf.getPage(pageNumber);
  if (epoch !== state.epoch) return;
  const scale = await pageScale(page);
  const viewport = page.getViewport({ scale });
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const canvas = document.createElement('canvas');
  canvas.width = Math.floor(viewport.width * ratio);
  canvas.height = Math.floor(viewport.height * ratio);
  canvas.style.width = `${Math.floor(viewport.width)}px`;
  canvas.style.height = `${Math.floor(viewport.height)}px`;
  const context = canvas.getContext('2d', { alpha: false });
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  await page.render({ canvasContext: context, viewport }).promise;
  if (epoch !== state.epoch) return;
  shell.replaceChildren(canvas);
  const badge = document.createElement('span');
  badge.className = 'page-badge';
  badge.textContent = pageNumber;
  shell.appendChild(badge);
  shell.dataset.rendered = 'true';
}

async function renderSingle(epoch) {
  const shell = document.createElement('article');
  shell.className = 'page-shell';
  shell.setAttribute('aria-label', `第 ${state.page} 页`);
  shell.innerHTML = '<div class="page-skeleton"></div>';
  els.pages.appendChild(shell);
  await renderPage(state.page, shell, epoch);
  updateProgressUI();
}

async function renderContinuous(epoch) {
  const shells = [];
  for (let page = 1; page <= state.pdf.numPages; page += 1) {
    const shell = document.createElement('article');
    shell.className = 'page-shell';
    shell.dataset.page = page;
    shell.setAttribute('aria-label', `第 ${page} 页`);
    shell.innerHTML = '<div class="page-skeleton"></div>';
    els.pages.appendChild(shell);
    shells.push(shell);
  }
  state.observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) renderPage(Number(entry.target.dataset.page), entry.target, epoch);
    });
  }, { root: els.stage, rootMargin: '700px 0px' });
  shells.forEach((shell) => state.observer.observe(shell));
  await new Promise((resolve) => requestAnimationFrame(resolve));
  shells[state.page - 1]?.scrollIntoView({ block: 'start' });
}

function updateProgressUI() {
  if (!state.pdf) return;
  state.page = clampProgress(state.page, state.pdf.numPages);
  const percent = Math.round((state.page / state.pdf.numPages) * 100);
  els.pageInput.value = state.page;
  els.pageCount.textContent = state.pdf.numPages;
  els.progress.style.width = `${percent}%`;
  els.progressText.textContent = `${percent}% 已读`;
  els.prev.disabled = state.page <= 1;
  els.next.disabled = state.page >= state.pdf.numPages;
}

async function goToPage(page) {
  if (!state.pdf) return;
  state.page = clampProgress(page, state.pdf.numPages);
  saveProgress();
  if (state.mode === 'scroll') {
    els.pages.querySelector(`[data-page="${state.page}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    updateProgressUI();
  } else await renderDocument();
}

function updateModeUI() {
  const scroll = state.mode === 'scroll';
  els.pageMode.classList.toggle('active', !scroll);
  els.scrollMode.classList.toggle('active', scroll);
}

async function setMode(mode) {
  if (!state.pdf || state.mode === mode) return;
  state.mode = mode;
  localStorage.setItem('reader-next:mode', mode);
  await renderDocument();
}

async function adjustZoom(delta) {
  state.fit = false;
  state.zoom = Math.min(3, Math.max(.4, state.zoom + delta));
  showToast(`${Math.round(state.zoom * 100)}%`);
  await renderDocument();
}

function openLibrary() { document.body.classList.add('library-open'); setTimeout(() => els.search.focus(), 180); }
function closeLibrary() { document.body.classList.remove('library-open'); }
function refreshIcons() { window.lucide?.createIcons({ attrs: { 'aria-hidden': 'true' } }); }
let toastTimer;
function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove('show'), 1300);
}

els.bookList.addEventListener('click', (event) => {
  const row = event.target.closest('.book-row');
  if (row) return openBook(findBook(decodeURIComponent(row.dataset.path)));
  const head = event.target.closest('.collection-head');
  if (head) {
    const section = head.closest('.collection');
    const name = decodeURIComponent(section.dataset.collection);
    section.classList.toggle('collapsed');
    head.setAttribute('aria-expanded', !section.classList.contains('collapsed'));
    if (section.classList.contains('collapsed')) state.collapsed.add(name); else state.collapsed.delete(name);
  }
});
els.search.addEventListener('input', () => renderLibrary(els.search.value));
els.collapseAll.addEventListener('click', () => {
  const shouldCollapse = state.collapsed.size < state.library.collections.length;
  state.collapsed = new Set(shouldCollapse ? state.library.collections.map((item) => item.name) : []);
  els.collapseAll.textContent = shouldCollapse ? '全部展开' : '全部收起';
  renderLibrary(els.search.value);
});
els.recentBook.addEventListener('click', () => openBook(findBook(decodeURIComponent(els.recentBook.dataset.path))));
els.prev.addEventListener('click', () => goToPage(state.page - 1));
els.next.addEventListener('click', () => goToPage(state.page + 1));
els.pageInput.addEventListener('change', () => goToPage(Number(els.pageInput.value)));
$('zoomIn').addEventListener('click', () => adjustZoom(.15));
$('zoomOut').addEventListener('click', () => adjustZoom(-.15));
$('fitWidth').addEventListener('click', async () => { state.fit = true; showToast('已适应宽度'); await renderDocument(); });
els.pageMode.addEventListener('click', () => setMode('page'));
els.scrollMode.addEventListener('click', () => setMode('scroll'));
$('openLibrary').addEventListener('click', openLibrary);
$('mobilePick').addEventListener('click', openLibrary);
$('closeLibrary').addEventListener('click', closeLibrary);
$('scrim').addEventListener('click', closeLibrary);
els.retry.addEventListener('click', () => openBook(state.currentBook));
$('themeToggle').addEventListener('click', () => {
  const night = document.documentElement.dataset.theme !== 'night';
  document.documentElement.dataset.theme = night ? 'night' : 'paper';
  localStorage.setItem('reader-next:theme', night ? 'night' : 'paper');
  $('themeToggle').innerHTML = `<i data-lucide="${night ? 'sun' : 'moon'}"></i>`;
  refreshIcons();
});
$('fullscreen').addEventListener('click', async () => {
  if (!document.fullscreenElement) await $('reader').requestFullscreen(); else await document.exitFullscreen();
});
els.stage.addEventListener('scroll', () => {
  if (state.mode !== 'scroll' || !state.pdf) return;
  const marker = els.stage.getBoundingClientRect().top + 80;
  let nearest = state.page;
  let distance = Infinity;
  els.pages.querySelectorAll('[data-page]').forEach((shell) => {
    const value = Math.abs(shell.getBoundingClientRect().top - marker);
    if (value < distance) { distance = value; nearest = Number(shell.dataset.page); }
  });
  if (nearest !== state.page) { state.page = nearest; saveProgress(); }
}, { passive: true });

document.addEventListener('keydown', (event) => {
  const typing = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName);
  if (event.key === '/' && !typing) { event.preventDefault(); openLibrary(); els.search.focus(); return; }
  if (event.key === 'Escape') {
    if (els.library.classList.contains('open')) closeLibrary();
    else window.location.href = '../';
  }
  if (typing) return;
  if (event.key === 'ArrowLeft') goToPage(state.page - 1);
  if (event.key === 'ArrowRight' || event.key === ' ') { event.preventDefault(); goToPage(state.page + 1); }
  if (event.key.toLowerCase() === 'f') $('fullscreen').click();
});
window.addEventListener('beforeunload', saveProgress);
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (state.pdf && state.fit) renderDocument(); }, 180);
});

document.documentElement.dataset.theme = localStorage.getItem('reader-next:theme') || 'paper';
refreshIcons();
loadLibrary();
