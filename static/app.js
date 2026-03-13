// === State ===
const state = {
  user: null,
  token: localStorage.getItem('gm_token'),
  currentView: 'dashboard',
  currentProgram: null,
  modulesData: [],
  loading: false
};

// === DOM ===
const $ = (sel) => document.querySelector(sel);
const authScreen = $('#auth-screen');
const mainApp = $('#main-app');
const navRoot = $('#nav');
const viewRoot = $('#view-root');
const topbarTitle = $('#topbar-title');
const topbarLabel = $('#topbar-label');
const userAvatar = $('#user-avatar');
const userName = $('#user-name');
const userEmail = $('#user-email');
const userRoleBadge = $('#user-role-badge');
const modal = $('#modal');
const modalCard = $('#modal-card');
const toast = $('#toast');

// === API ===
const api = {
  async request(path, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...(state.token && { 'Authorization': `Bearer ${state.token}` }),
      ...options.headers
    };
    const res = await fetch(path, { ...options, headers });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Request failed');
    return data.data;
  },
  async post(path, body) { return this.request(path, { method: 'POST', body: JSON.stringify(body) }); },
  async get(path) { return this.request(path, { method: 'GET' }); }
};

// === Utils ===
function escapeHtml(str) { const div = document.createElement('div'); div.textContent = str ?? ''; return div.innerHTML; }
function initials(name) { return String(name).split(' ').filter(Boolean).slice(0,2).map(p => p[0]?.toUpperCase()).join('') || '?'; }
function formatDate(iso) { if (!iso) return '—'; return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }); }
function showToast(message, isError = false) {
  toast.textContent = message;
  toast.className = `toast ${isError ? 'error' : ''}`;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 3000);
}
function closeModal() { modal.classList.add('hidden'); modalCard.innerHTML = ''; }
function openModal(content) { modalCard.innerHTML = content; modal.classList.remove('hidden'); }

// === Auth ===
async function checkAuth() {
  if (!state.token) return showAuth();
  try {
    state.user = await api.get('/api/me');
    showApp();
    renderNav();
    loadView(state.currentView);
  } catch { logout(); }
}

function showAuth() { authScreen.classList.remove('hidden'); mainApp.classList.add('hidden'); }
function showApp() {
  authScreen.classList.add('hidden'); mainApp.classList.remove('hidden');
  userAvatar.textContent = initials(state.user.full_name);
  userAvatar.style.background = state.user.avatar_bg;
  userName.textContent = state.user.full_name;
  userEmail.textContent = state.user.email;
  userRoleBadge.textContent = state.user.role === 'creator' ? 'Создатель' : 'Участник';
  $('#create-program-btn').style.display = state.user.role === 'creator' ? 'inline-flex' : 'none';
  $('#join-code-btn').style.display = state.user.role === 'participant' ? 'inline-flex' : 'none';
}

async function login(payload) {
  try {
    const { token, ...user } = await api.post('/api/auth/login', payload);
    state.token = token; state.user = user;
    localStorage.setItem('gm_token', token);
    showApp(); renderNav(); loadView('dashboard');
    showToast('Добро пожаловать!');
  } catch (e) { showToast(e.message, true); }
}

async function register(payload) {
  try {
    const { token, ...user } = await api.post('/api/auth/register', payload);
    state.token = token; state.user = user;
    localStorage.setItem('gm_token', token);
    showApp(); renderNav(); loadView('dashboard');
    showToast('Регистрация успешна!');
  } catch (e) { showToast(e.message, true); }
}

function logout() {
  api.post('/api/auth/logout').catch(() => {});
  localStorage.removeItem('gm_token');
  state.token = null; state.user = null;
  showAuth();
}

// === Navigation ===
const navItems = {
  participant: [
    { id: 'dashboard', label: 'Дашборд', icon: '📊' },
    { id: 'programs', label: 'Мои марафоны', icon: '🎯' },
    { id: 'achievements', label: 'Достижения', icon: '🏆' },
  ],
  creator: [
    { id: 'dashboard', label: 'Дашборд', icon: '📊' },
    { id: 'programs', label: 'Мои марафоны', icon: '📚' },
    { id: 'builder', label: 'Конструктор', icon: '✏️' },
  ]
};

function renderNav() {
  if (!state.user) return;
  const items = navItems[state.user.role] || [];
  navRoot.innerHTML = items.map(item => `
    <button class="nav-btn ${item.id === state.currentView ? 'active' : ''}" data-view="${item.id}">
      <span class="icon">${item.icon}</span>
      <span>${item.label}</span>
    </button>
  `).join('');
}

function setView(viewId) {
  state.currentView = viewId;
  renderNav();
  loadView(viewId);
}

// === Views ===
async function loadView(viewId) {
  if (!state.user) return;
  viewRoot.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Загрузка...</p></div>';
  
  try {
    if (state.user.role === 'participant') {
      if (viewId === 'dashboard') await loadParticipantDashboard();
      else if (viewId === 'programs') await loadParticipantPrograms();
      else if (viewId === 'achievements') await loadAchievements();
    } else {
      if (viewId === 'dashboard') await loadCreatorDashboard();
      else if (viewId === 'programs') await loadCreatorPrograms();
      else if (viewId === 'builder') await loadBuilder();
    }
  } catch (e) {
    viewRoot.innerHTML = `<div class="card"><p class="subtle">Ошибка: ${escapeHtml(e.message)}</p></div>`;
  }
}

async function loadParticipantDashboard() {
  topbarTitle.textContent = 'Личный кабинет';
  topbarLabel.textContent = 'Участник';
  const data = await api.get('/api/participant/dashboard');
  
  viewRoot.innerHTML = `
    <section class="stats-grid">
      <div class="stat-card"><div class="eyebrow">Марафонов</div><div class="stat-value">${data.stats.programs_joined||0}</div></div>
      <div class="stat-card"><div class="eyebrow">Уроков</div><div class="stat-value">${data.stats.total_completed||0}</div></div>
      <div class="stat-card"><div class="eyebrow">XP</div><div class="stat-value">${data.stats.total_xp||0}</div></div>
      <div class="stat-card"><div class="eyebrow">Серия</div><div class="stat-value">${data.stats.best_streak||0}</div></div>
    </section>
    <section class="card">
      <div class="card-header"><h3>🎯 Активные марафоны</h3></div>
      ${data.active_programs.length ? `<div class="program-grid">${data.active_programs.map(p => renderProgramCard(p, false)).join('')}</div>` : '<p class="subtle">Нет активных марафонов. Используйте кнопку "+ Код".</p>'}
    </section>
    ${data.achievements.length ? `
    <section class="card">
      <div class="card-header"><h3>🏆 Последние достижения</h3></div>
      <div class="achievements-grid">${data.achievements.slice(0,4).map(a => `
        <div class="achievement-card unlocked"><div class="achievement-icon">${escapeHtml(a.icon)}</div><div class="achievement-title">${escapeHtml(a.title)}</div></div>
      `).join('')}</div>
    </section>` : ''}
  `;
}

async function loadParticipantPrograms() {
  topbarTitle.textContent = 'Мои марафоны';
  topbarLabel.textContent = 'Каталог';
  const programs = await api.get('/api/participant/programs');
  viewRoot.innerHTML = `<section class="card"><div class="program-grid">${programs.map(p => renderProgramCard(p, false)).join('')}</div></section>`;
  bindProgramClicks();
}

async function loadAchievements() {
  topbarTitle.textContent = 'Достижения';
  const data = await api.get('/api/participant/dashboard');
  viewRoot.innerHTML = `<section class="card"><div class="achievements-grid">${data.achievements.map(a => `
    <div class="achievement-card unlocked"><div class="achievement-icon">${escapeHtml(a.icon)}</div><div class="achievement-title">${escapeHtml(a.title)}</div><div class="achievement-desc subtle">${escapeHtml(a.description)}</div></div>
  `).join('')}</div></section>`;
}

async function loadCreatorDashboard() {
  topbarTitle.textContent = 'Панель создателя';
  topbarLabel.textContent = 'Организатор';
  const programs = await api.get('/api/creator/programs');
  viewRoot.innerHTML = `
    <section class="card">
      <div class="card-header"><h3>📚 Ваши марафоны</h3></div>
      ${programs.length ? `<div class="program-grid">${programs.map(p => renderProgramCard(p, true)).join('')}</div>` : '<p class="subtle">Нет марафонов. Создайте первый!</p>'}
    </section>`;
  bindProgramClicks();
}

async function loadCreatorPrograms() {
  topbarTitle.textContent = 'Управление марафонами';
  topbarLabel.textContent = 'Список';
  const programs = await api.get('/api/creator/programs');
  viewRoot.innerHTML = `<section class="card"><div class="program-grid">${programs.map(p => renderProgramCard(p, true)).join('')}</div></section>`;
  bindProgramClicks();
}

async function loadBuilder() {
  topbarTitle.textContent = 'Конструктор';
  topbarLabel.textContent = 'Структура курса';
  viewRoot.innerHTML = `
    <div class="card">
      <div class="card-header">
        <h3>Выберите марафон для редактирования</h3>
      </div>
      <div id="builder-select" class="program-grid"></div>
    </div>`;
  
  const programs = await api.get('/api/creator/programs');
  const container = $('#builder-select');
  if(!programs.length) {
    container.innerHTML = '<p class="subtle">Сначала создайте марафон в разделе "Мои марафоны"</p>';
    return;
  }
  container.innerHTML = programs.map(p => `
    <article class="card program-card" style="cursor:pointer" onclick="openProgramBuilder(${p.id})">
      <div class="program-cover">${escapeHtml(initials(p.name))}</div>
      <div><strong>${escapeHtml(p.name)}</strong><p class="subtle">${p.modules_count||0} модулей • ${p.lessons_count||0} уроков</p></div>
    </article>
  `).join('');
}

// === Components ===
function renderProgramCard(program, isCreator) {
  return `
    <article class="card program-card" data-program-id="${program.id}">
      <div class="program-cover">${escapeHtml(initials(program.name))}</div>
      <div>
        <strong>${escapeHtml(program.name)}</strong>
        <div class="program-meta" style="margin:8px 0">
          <span class="badge ${program.status==='active'?'badge-success':'badge-warning'}">${program.status}</span>
          ${isCreator ? `<span class="subtle">${program.enrolled_count||0} уч.</span>` : `<span class="subtle">${program.progress_percent||0}%</span>`}
        </div>
        <div class="button-row" style="gap:8px; margin-top:12px">
          ${isCreator ? `
            <button class="btn-secondary btn-sm" onclick="event.stopPropagation(); openProgramBuilder(${program.id})">Конструктор</button>
            <button class="btn-ghost btn-sm" onclick="event.stopPropagation(); openEditProgram(${program.id})">Настроить</button>
          ` : `<button class="btn-primary btn-sm" onclick="event.stopPropagation(); openParticipantView(${program.id})">Открыть</button>`}
        </div>
      </div>
    </article>`;
}

function bindProgramClicks() {
  document.querySelectorAll('.program-card').forEach(el => {
    el.addEventListener('click', (e) => {
      if (e.target.tagName === 'BUTTON') return;
      if (state.user.role === 'creator') openProgramBuilder(el.dataset.programId);
      else openParticipantView(el.dataset.programId);
    });
  });
}

// === Participant View ===
window.openParticipantView = async (id) => {
  state.currentProgram = id;
  topbarTitle.textContent = 'Марафон';
  viewRoot.innerHTML = '<div class="loading-state"><div class="spinner"></div></div>';
  
  try {
    const data = await api.get(`/api/programs/${id}/structure`);
    let html = `
      <div class="card">
        <div class="card-header">
          <div><h2>${escapeHtml(data.program.name)}</h2><p class="subtle">${escapeHtml(data.program.goal_text)}</p></div>
          <div style="text-align:right"><div class="eyebrow">Прогресс</div><strong>${data.progress}%</strong></div>
        </div>
      </div>
      <div class="module-list">
    `;
    
    data.modules.forEach(mod => {
      html += `
        <article class="module-card">
          <div class="module-header">
            <strong>${escapeHtml(mod.title)}</strong>
            <span class="badge ${mod.status==='available'?'badge-success':'badge-warning'}">${mod.status==='available'?'Доступен':'Закрыт'}</span>
          </div>
          <div class="module-body"><p class="subtle">${escapeHtml(mod.description||'')}</p>
          <div class="lesson-list">
      `;
      mod.lessons.forEach(les => {
        const statusIcon = les.status === 'completed' ? '✅' : les.status === 'in_progress' ? '⏳' : '🔒';
        html += `
          <div class="lesson-item ${les.status}" onclick="openLessonModal(${les.id})">
            <div style="display:flex;align-items:center;gap:12px">
              <span style="font-size:1.2rem">${statusIcon}</span>
              <div><strong>${escapeHtml(les.title)}</strong><div class="subtle" style="font-size:0.85rem">${les.estimated_minutes} мин • ${les.points} XP</div></div>
            </div>
            <span>→</span>
          </div>
        `;
      });
      html += `</div></div></article>`;
    });
    
    html += `</div>`;
    viewRoot.innerHTML = html;
  } catch (e) {
    viewRoot.innerHTML = `<div class="card"><p class="subtle">Ошибка: ${e.message}</p></div>`;
  }
};

window.openLessonModal = async (lessonId) => {
  // Находим урок в текущей структуре (упрощено: перезагружаем структуру или храним в state)
  // Для простоты демо: просто заглушка модального окна с действиями
  const data = await api.get(`/api/programs/${state.currentProgram}/structure`);
  let lesson = null;
  data.modules.forEach(m => { const l = m.lessons.find(x => x.id === lessonId); if(l) lesson = l; });
  if(!lesson) return;

  openModal(`
    <div class="modal-content">
      <div class="modal-header"><h3>${escapeHtml(lesson.title)}</h3><button class="modal-close" data-close-modal>&times;</button></div>
      <div class="lesson-body" style="padding:24px">
        <div class="lesson-content">${lesson.content_html || '<p>Текст урока...</p>'}</div>
        ${lesson.attachments.length ? `<div class="attachments-list" style="margin:16px 0">${lesson.attachments.map(a => `<a href="/uploads/${a.filename}" class="attachment-item" download>📎 ${a.original_name}</a>`).join('')}</div>` : ''}
        
        <div class="lesson-actions" style="display:flex;gap:8px;margin-top:20px;border-top:1px solid var(--border);padding-top:16px">
          ${lesson.status !== 'completed' ? `<button class="btn-primary" onclick="updateProgress(${lessonId}, 'completed')">Завершить урок</button>` : '<button class="btn-secondary" disabled>✅ Завершено</button>'}
          ${lesson.status === 'available' ? `<button class="btn-secondary" onclick="updateProgress(${lessonId}, 'in_progress')">Начать</button>` : ''}
        </div>

        <div class="rating-section" style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
          <span class="subtle">Оценка:</span>
          <div class="stars" style="display:inline-flex;gap:4px;margin-left:8px">
            ${[1,2,3,4,5].map(r => `<button style="background:none;border:none;font-size:1.5rem;cursor:pointer;color:${r<=lesson.my_rating?'var(--accent)':'#ccc'}" onclick="rateLesson(${lessonId},${r})">★</button>`).join('')}
          </div>
        </div>

        <div class="comments-section" style="margin-top:20px">
          <h4>Комментарии</h4>
          <div style="max-height:200px;overflow-y:auto;margin:8px 0">
            ${lesson.comments.map(c => `<div class="comment-item" style="background:#f9fafb;padding:8px;border-radius:8px;margin-bottom:8px"><strong>${escapeHtml(c.full_name)}</strong>: ${escapeHtml(c.content)}</div>`).join('')}
          </div>
          <form onsubmit="addComment(event, ${lessonId})"><textarea name="content" placeholder="Комментарий..." required style="width:100%;padding:8px;border:1px solid var(--border);border-radius:8px"></textarea><button type="submit" class="btn-ghost" style="margin-top:4px">Отправить</button></form>
        </div>
      </div>
    </div>
  `);
};

window.updateProgress = async (lid, status) => {
  await api.post(`/api/lessons/${lid}/progress`, { status, progress: status==='completed'?100:0 });
  showToast(status==='completed'?'Урок завершен!':'В процессе');
  closeModal();
  openParticipantView(state.currentProgram);
};

window.rateLesson = async (lid, rating) => {
  await api.post(`/api/lessons/${lid}/rating`, { rating });
  showToast('Спасибо за оценку!');
  openLessonModal(lid); // Refresh
};

window.addComment = async (e, lid) => {
  e.preventDefault();
  const content = e.target.content.value;
  await api.post(`/api/lessons/${lid}/comments`, { content });
  e.target.reset();
  showToast('Комментарий добавлен');
  openLessonModal(lid);
};

// === Creator Builder (Full CRUD) ===
window.openProgramBuilder = async (id) => {
  state.currentProgram = id;
  topbarTitle.textContent = 'Конструктор';
  viewRoot.innerHTML = `
    <div class="card">
      <div class="card-header">
        <h3>Модули и Уроки</h3>
        <button class="btn-primary" onclick="openCreateModule()">+ Модуль</button>
      </div>
      <div id="modules-container" class="module-list"><div class="loading-state"><div class="spinner"></div></div></div>
    </div>`;
  await loadModulesList();
};

async function loadModulesList() {
  try {
    state.modulesData = await api.get(`/api/programs/${state.currentProgram}/modules`);
    renderModules();
  } catch (e) { $('#modules-container').innerHTML = `<p class="subtle">Ошибка: ${e.message}</p>`; }
}

function renderModules() {
  const container = $('#modules-container');
  if (!state.modulesData.length) {
    container.innerHTML = '<p class="subtle" style="padding:20px;text-align:center">Нет модулей. Создайте первый!</p>';
    return;
  }
  container.innerHTML = state.modulesData.map(mod => `
    <div class="module-card" style="border:1px solid var(--border);border-radius:12px;margin-bottom:16px;overflow:hidden">
      <div class="module-header" style="background:#f9fafb;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border)">
        <div><strong style="font-size:1.1rem">${escapeHtml(mod.title)}</strong><span class="subtle" style="margin-left:8px;font-size:0.85rem">${mod.description||''}</span></div>
        <div style="display:flex;gap:8px">
          <button class="btn-ghost btn-sm" onclick="openEditModule(${mod.id})">✏️</button>
          <button class="btn-ghost btn-sm" style="color:var(--danger)" onclick="confirmDeleteModule(${mod.id})">🗑️</button>
          <button class="btn-primary btn-sm" onclick="openCreateLesson(${mod.id})">+ Урок</button>
        </div>
      </div>
      <div class="module-body" style="padding:12px 16px">
        ${mod.lessons.length ? mod.lessons.map(les => `
          <div class="lesson-item" style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid #eee">
            <div><strong>${escapeHtml(les.title)}</strong><div class="subtle" style="font-size:0.8rem">${les.estimated_minutes} мин • ${les.points} XP</div></div>
            <div style="display:flex;gap:8px">
              <button class="btn-ghost btn-sm" onclick="openEditLesson(${les.id})">✏️</button>
              <button class="btn-ghost btn-sm" style="color:var(--danger)" onclick="confirmDeleteLesson(${les.id})">🗑️</button>
            </div>
          </div>
        `).join('') : '<p class="subtle" style="padding:8px">Нет уроков</p>'}
      </div>
    </div>
  `).join('');
}

// Module Actions
window.openCreateModule = () => {
  openModal(`
    <div class="modal-content">
      <div class="modal-header"><h3>Новый модуль</h3><button class="modal-close" data-close-modal>&times;</button></div>
      <form id="form-module" class="form-body">
        <label>Название<input name="title" required></label>
        <label>Описание<textarea name="description"></textarea></label>
        <label>Дата открытия<input type="date" name="unlock_date"></label>
        <button type="submit" class="btn-primary" style="width:100%">Создать</button>
      </form>
    </div>`);
  $('#form-module').onsubmit = async (e) => {
    e.preventDefault();
    await api.post(`/api/programs/${state.currentProgram}/modules`, Object.fromEntries(new FormData(e.target)));
    closeModal(); loadModulesList(); showToast('Модуль создан');
  };
};

window.openEditModule = async (id) => {
  const mod = state.modulesData.find(m => m.id === id);
  if (!mod) return;
  openModal(`
    <div class="modal-content">
      <div class="modal-header"><h3>Редактировать модуль</h3><button class="modal-close" data-close-modal>&times;</button></div>
      <form id="form-module-edit" class="form-body">
        <label>Название<input name="title" value="${escapeHtml(mod.title)}" required></label>
        <label>Описание<textarea name="description">${escapeHtml(mod.description||'')}</textarea></label>
        <label>Дата открытия<input type="date" name="unlock_date" value="${mod.unlock_date||''}"></label>
        <button type="submit" class="btn-primary" style="width:100%">Сохранить</button>
      </form>
    </div>`);
  $('#form-module-edit').onsubmit = async (e) => {
    e.preventDefault();
    await api.post(`/api/modules/${id}/update`, Object.fromEntries(new FormData(e.target)));
    closeModal(); loadModulesList(); showToast('Изменения сохранены');
  };
};

window.confirmDeleteModule = async (id) => {
  if (!confirm('Удалить модуль и все уроки внутри?')) return;
  await api.post(`/api/modules/${id}/delete`);
  loadModulesList(); showToast('Модуль удален');
};

// Lesson Actions
window.openCreateLesson = (moduleId) => {
  openModal(`
    <div class="modal-content">
      <div class="modal-header"><h3>Новый урок</h3><button class="modal-close" data-close-modal>&times;</button></div>
      <form id="form-lesson" class="form-body">
        <label>Название<input name="title" required></label>
        <label>Контент (HTML)<textarea name="content_html" style="height:100px"></textarea></label>
        <div class="form-grid">
          <label>XP<input type="number" name="points" value="100"></label>
          <label>Минуты<input type="number" name="estimated_minutes" value="15"></label>
        </div>
        <label>Дата открытия<input type="date" name="unlock_date"></label>
        <button type="submit" class="btn-primary" style="width:100%">Добавить урок</button>
      </form>
    </div>`);
  $('#form-lesson').onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    data.points = parseInt(data.points); data.estimated_minutes = parseInt(data.estimated_minutes);
    await api.post(`/api/modules/${moduleId}/lessons`, data);
    closeModal(); loadModulesList(); showToast('Урок добавлен');
  };
};

window.openEditLesson = async (id) => {
  let lesson = null;
  state.modulesData.forEach(m => { const l = m.lessons.find(x => x.id === id); if(l) lesson = l; });
  if (!lesson) return;
  openModal(`
    <div class="modal-content">
      <div class="modal-header"><h3>Редактировать урок</h3><button class="modal-close" data-close-modal>&times;</button></div>
      <form id="form-lesson-edit" class="form-body">
        <label>Название<input name="title" value="${escapeHtml(lesson.title)}" required></label>
        <label>Контент (HTML)<textarea name="content_html" style="height:100px">${escapeHtml(lesson.content_html||'')}</textarea></label>
        <div class="form-grid">
          <label>XP<input type="number" name="points" value="${lesson.points}"></label>
          <label>Минуты<input type="number" name="estimated_minutes" value="${lesson.estimated_minutes}"></label>
        </div>
        <label>Дата открытия<input type="date" name="unlock_date" value="${lesson.unlock_date||''}"></label>
        <button type="submit" class="btn-primary" style="width:100%">Сохранить</button>
      </form>
    </div>`);
  $('#form-lesson-edit').onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    data.points = parseInt(data.points); data.estimated_minutes = parseInt(data.estimated_minutes);
    await api.post(`/api/lessons/${id}/update`, data);
    closeModal(); loadModulesList(); showToast('Урок обновлен');
  };
};

window.confirmDeleteLesson = async (id) => {
  if (!confirm('Удалить урок?')) return;
  await api.post(`/api/lessons/${id}/delete`);
  loadModulesList(); showToast('Урок удален');
};

window.openEditProgram = async (id) => {
  showToast('Функция редактирования настроек марафона в разработке', true);
};

// === Global Events ===
$('#create-program-btn')?.addEventListener('click', () => {
  openModal(`
    <div class="modal-content">
      <div class="modal-header"><h3>Новый марафон</h3><button class="modal-close" data-close-modal>&times;</button></div>
      <form id="form-program" class="form-body">
        <label>Название<input name="name" required></label>
        <label>Описание<textarea name="description" required></textarea></label>
        <label>Цель<input name="goal_text" required></label>
        <div class="form-grid">
          <label>Старт<input type="date" name="start_date" required></label>
          <label>Финиш<input type="date" name="end_date" required></label>
        </div>
        <button type="submit" class="btn-primary" style="width:100%">Создать</button>
      </form>
    </div>`);
  $('#form-program').onsubmit = async (e) => {
    e.preventDefault();
    const res = await api.post('/api/programs', Object.fromEntries(new FormData(e.target)));
    closeModal(); showToast(`Марафон создан! Код: ${res.invitation_code}`);
    loadView('dashboard');
  };
});

$('#join-code-btn')?.addEventListener('click', async () => {
  const code = prompt('Введите код приглашения:');
  if (!code) return;
  try {
    // Используем POST с телом для совместимости с нашей логикой, хотя API поддерживает и GET
    await api.post('/api/programs/join', { code }); 
    showToast('Вы присоединились к марафону! 🎉');
    loadView('programs');
  } catch (e) { showToast(e.message, true); }
});

document.addEventListener('click', (e) => {
  if (e.target.closest('[data-close-modal]') || e.target === modal) closeModal();
  const navBtn = e.target.closest('.nav-btn');
  if (navBtn) setView(navBtn.dataset.view);
});

$('#login-form')?.addEventListener('submit', (e) => { e.preventDefault(); login(Object.fromEntries(new FormData(e.target))); });
$('#register-form')?.addEventListener('submit', (e) => { e.preventDefault(); register(Object.fromEntries(new FormData(e.target))); });
$('#logout-btn')?.addEventListener('click', () => { if(confirm('Выйти?')) logout(); });

// === ЭТОТ БЛОК НУЖНО ДОБАВИТЬ В КОНЕЦ ФАЙЛА ===

document.addEventListener("DOMContentLoaded", () => {
  // 1. ЛОГИКА ПЕРЕКЛЮЧЕНИЯ ВКЛАДОК ВХОД / РЕГИСТРАЦИЯ
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const tabButtons = document.querySelectorAll('.tab-btn');

  if (loginForm && registerForm && tabButtons.length) {
    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        // Переключаем активный класс
        tabButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Показываем нужную форму
        const tab = btn.dataset.tab;
        if (tab === 'login') {
          loginForm.classList.remove('hidden');
          registerForm.classList.add('hidden');
        } else {
          loginForm.classList.add('hidden');
          registerForm.classList.remove('hidden');
        }
      });
    });

    // Обработчик отправки формы входа (вызывает твою функцию login)
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await login(Object.fromEntries(new FormData(loginForm)));
    });

    // Обработчик отправки формы регистрации (вызывает твою функцию register)
    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await register(Object.fromEntries(new FormData(registerForm)));
    });
  }
});

// Init
checkAuth();