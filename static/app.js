const navItems = [
  { id: "overview", label: "Обзор", role: "all" },
  { id: "tasks", label: "Мои задачи", role: "participant" },
  { id: "leaderboard", label: "Лидерборд", role: "all" },
  { id: "team", label: "Команда", role: "participant" },
  { id: "organizer", label: "Организатор", role: "organizer" },
  { id: "builder", label: "Конструктор", role: "organizer" },
  { id: "analytics", label: "Аналитика", role: "organizer" },
  { id: "challenges", label: "Челленджи", role: "all" },
];

const state = {
  app: null,
  me: null,
  currentRole: "participant",
  currentView: "overview",
  modal: null,
  busy: false,
};

const navRoot = document.getElementById("nav");
const roleSwitchRoot = document.getElementById("role-switch");
const viewRoot = document.getElementById("view-root");
const topbarTitle = document.getElementById("topbar-title");
const topbarLabel = document.getElementById("topbar-label");
const modal = document.getElementById("modal");
const modalCard = document.getElementById("modal-card");
const toast = document.getElementById("toast");
const resetDemoButton = document.getElementById("reset-demo-button");
const authPanelRoot = document.getElementById("auth-panel");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function initials(name) {
  return String(name)
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function formatDate(value) {
  if (!value) return "—";
  const normalized = String(value).includes("T") ? String(value) : `${String(value).replace(" ", "T")}`;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
  }).format(new Date(normalized));
}

function formatDateTime(value) {
  if (!value) return "—";
  const normalized = String(value).includes("T") ? String(value) : `${String(value).replace(" ", "T")}`;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(normalized));
}

function formatCompactDay(value) {
  if (!value) return "—";
  const normalized = String(value).includes("T") ? String(value) : `${String(value).replace(" ", "T")}`;
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "short",
  }).format(new Date(normalized));
}

function allowView(item) {
  return item.role === "all" || item.role === state.currentRole;
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  toast.style.background = isError ? "rgba(122, 27, 27, 0.96)" : "rgba(18, 34, 30, 0.96)";
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.classList.add("hidden");
  }, 3200);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({ ok: false, error: "Некорректный ответ сервера" }));
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || "Не удалось выполнить запрос");
  }
  return payload.data;
}

async function refreshState() {
  const [app, me] = await Promise.all([request("/api/bootstrap"), request("/api/me")]);
  state.app = app;
  state.me = me;
}

async function loadState() {
  state.busy = true;
  render();
  try {
    await refreshState();
    const allowedCurrentView = navItems.some((item) => item.id === state.currentView && allowView(item));
    if (!allowedCurrentView) {
      state.currentView = "overview";
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.busy = false;
    render();
  }
}

async function performRequest(path, payload = null) {
  state.busy = true;
  render();
  try {
    state.app = await request(path, {
      method: "POST",
      body: payload ? JSON.stringify(payload) : JSON.stringify({}),
    });
    state.me = await request("/api/me");
    closeModal();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.busy = false;
    render();
  }
}

async function performAuthRequest(path, payload = null) {
  state.busy = true;
  render();
  try {
    const response = await request(path, {
      method: "POST",
      body: payload ? JSON.stringify(payload) : JSON.stringify({}),
    });
    state.app = response.bootstrap;
    state.me = response.me;
    closeModal();
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  } finally {
    state.busy = false;
    render();
  }
}

function setRole(nextRole) {
  state.currentRole = nextRole;
  const allowedCurrentView = navItems.some((item) => item.id === state.currentView && allowView(item));
  if (!allowedCurrentView) {
    state.currentView = "overview";
  }
  render();
}

function setView(nextView) {
  state.currentView = nextView;
  render();
}

function openReportModal(taskId) {
  const task = state.app?.participantBoard?.tasks?.find((item) => item.participant_task_id === taskId);
  if (!task) return;
  state.modal = { type: "report", taskId };
  renderModal();
}

function openLoginModal() {
  state.modal = { type: "login" };
  renderModal();
}

function closeModal() {
  state.modal = null;
  renderModal();
}

function renderNav() {
  const items = navItems.filter(allowView);
  navRoot.innerHTML = items
    .map(
      (item) => `
        <button class="nav-button ${item.id === state.currentView ? "active" : ""}" type="button" data-view="${item.id}">
          <span class="nav-label">
            <strong>${escapeHtml(item.label)}</strong>
            <span class="nav-role">${item.role === "all" ? "Общий экран" : item.role === "participant" ? "Участник" : "Организатор"}</span>
          </span>
          <span>→</span>
        </button>
      `
    )
    .join("");
}

function renderRoleSwitch() {
  roleSwitchRoot.innerHTML = `
    <button class="role-button ${state.currentRole === "participant" ? "active" : ""}" type="button" data-role="participant">Роль: участник</button>
    <button class="role-button ${state.currentRole === "organizer" ? "active" : ""}" type="button" data-role="organizer">Роль: организатор</button>
  `;
}

function renderAuthPanel() {
  if (!state.me) {
    authPanelRoot.innerHTML = "";
    return;
  }

  authPanelRoot.className = "auth-panel";
  const title = state.me.authenticated
    ? state.me.user?.fullName || state.me.user?.email || "Аккаунт"
    : "Auth foundation";
  const subtitle = state.me.authenticated
    ? `${state.me.user?.email || ""} • ${state.me.source}`
    : "dev fallback active";
  const badge = state.me.authenticated
    ? `<span class="badge success">session</span>`
    : `<span class="badge info">fallback</span>`;
  const action = state.me.authenticated
    ? `<button class="inline-button" type="button" data-action="logout">Выйти</button>`
    : `<button class="inline-button" type="button" data-action="open-login">Demo login</button>`;

  authPanelRoot.innerHTML = `
    ${badge}
    <div class="auth-panel-copy">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(subtitle)}</span>
    </div>
    ${action}
  `;
}

function renderAvatar(person, large = false) {
  return `
    <div class="${large ? "avatar-large" : "avatar"}" style="background:${escapeHtml(person.avatar_bg)}">
      ${escapeHtml(initials(person.full_name))}
    </div>
  `;
}

function renderTaskCard(task) {
  const reportBox = task.report_content
    ? `
      <div class="report-box">
        <div class="eyebrow">Отчёт участника</div>
        <strong>${escapeHtml(task.report_type || "report")}</strong>
        <p class="subtle">${escapeHtml(task.report_content)}</p>
        <div class="task-meta">
          <span>${escapeHtml(task.attachment_name || "Без вложения")}</span>
          <span>${escapeHtml(task.report_status || "accepted")}</span>
        </div>
      </div>
    `
    : "";

  let actionMarkup = "";
  if (task.status === "completed") {
    actionMarkup = `<button class="secondary-button" type="button" data-action="open-report" data-task-id="${task.participant_task_id}">Обновить отчёт</button>`;
  } else if (task.status === "missed") {
    actionMarkup = `<button class="primary-button" type="button" data-action="soft-return" data-task-id="${task.participant_task_id}">Мягкий возврат</button>`;
  } else if (task.report_required) {
    actionMarkup = `<button class="primary-button" type="button" data-action="open-report" data-task-id="${task.participant_task_id}">Сдать отчёт</button>`;
  } else {
    actionMarkup = `<button class="secondary-button" type="button" data-action="complete-task" data-task-id="${task.participant_task_id}">Отметить выполненным</button>`;
  }

  return `
    <article class="task-card">
      <div class="task-head">
        <div>
          <div class="eyebrow">${escapeHtml(task.module_title)}</div>
          <h3>${escapeHtml(task.title)}</h3>
        </div>
        <span class="badge ${escapeHtml(task.badge.tone)}">${escapeHtml(task.badge.label)}</span>
      </div>
      <p class="task-description">${escapeHtml(task.description)}</p>
      <div class="task-meta">
        <span>${escapeHtml(formatDate(task.scheduled_for))}</span>
        <span>${escapeHtml(task.points)} XP</span>
        <span>${escapeHtml(task.estimated_minutes)} мин</span>
        <span>${escapeHtml(task.submission_mode)}</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" style="width:${Math.max(0, Math.min(100, Number(task.participant_progress)))}%"></div>
      </div>
      ${task.status === "missed" ? `<div class="report-box"><strong>Мягкий возврат:</strong><p class="subtle">${escapeHtml(task.soft_return_copy)}</p></div>` : ""}
      ${reportBox}
      <div class="button-row">
        ${actionMarkup}
      </div>
    </article>
  `;
}

function renderNotificationCard(item) {
  return `
    <article class="notification-card">
      <div class="task-head">
        <div>
          <div class="eyebrow">${escapeHtml(item.notification_type)}</div>
          <h3>${escapeHtml(item.title)}</h3>
        </div>
        ${item.is_read ? `<span class="badge neutral">Прочитано</span>` : `<span class="badge info">Новое</span>`}
      </div>
      <p>${escapeHtml(item.message)}</p>
      <div class="task-meta">
        <span>${escapeHtml(item.cta_label)}</span>
        <span>${escapeHtml(formatDateTime(item.created_at))}</span>
      </div>
      ${item.is_read ? "" : `<button class="inline-button" type="button" data-action="notification-read" data-id="${item.id}">Пометить прочитанным</button>`}
    </article>
  `;
}

function renderHero() {
  const { program, participant, participantBoard } = state.app;
  return `
    <section class="hero">
      <div class="hero-grid">
        <div>
          <div class="eyebrow hero-eyebrow">GoalMate / ${escapeHtml(state.currentRole === "participant" ? "Experience Layer" : "Operator Layer")}</div>
          <h2>${escapeHtml(program.name)}</h2>
          <p>${escapeHtml(program.description)}</p>
          <div class="hero-actions" style="margin-top:18px">
            <span class="chip">Прогресс ${escapeHtml(participant.progress_percent)}%</span>
            <span class="chip">Ранг #${escapeHtml(participant.rank)}</span>
            <span class="chip">${escapeHtml(participant.xp)} XP</span>
            <span class="chip">${escapeHtml(participantBoard.unreadNotifications)} непрочитанных nudges</span>
          </div>
        </div>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="eyebrow">Сегодня в фокусе</div>
            <div class="stat-value">${escapeHtml(participantBoard.todayFocus)} / ${escapeHtml(participantBoard.totalFocus)}</div>
            <div class="stat-caption">задач уже в движении</div>
          </div>
          <div class="stat-card">
            <div class="eyebrow">Мини-команда</div>
            <div class="stat-value">${escapeHtml(state.app.team.done_today)} / ${escapeHtml(state.app.team.member_count)}</div>
            <div class="stat-caption">участников держат темп</div>
          </div>
          <div class="stat-card">
            <div class="eyebrow">Мягкий возврат</div>
            <div class="stat-value">${escapeHtml(participantBoard.softReturnCount)}</div>
            <div class="stat-caption">использован без потери прогресса</div>
          </div>
          <div class="stat-card">
            <div class="eyebrow">B2B эффект</div>
            <div class="stat-value">${escapeHtml(state.app.organizerDashboard.hoursSavedPerWeek)}</div>
            <div class="stat-caption">часов экономии в неделю</div>
          </div>
        </div>
      </div>
    </section>
  `;
}

function renderOverview() {
  const { participantBoard, notifications, organizerDashboard, privateChallenges, participant } = state.app;
  const previewTasks = participantBoard.tasks.slice(0, 4).map(renderTaskCard).join("");
  const previewNotifications = notifications.slice(0, 3).map(renderNotificationCard).join("");
  const challenges = privateChallenges
    .slice(0, 2)
    .map(
      (challenge) => `
        <article class="challenge-card">
          <div class="task-head">
            <div>
              <div class="eyebrow">B2C growth loop</div>
              <h3>${escapeHtml(challenge.name)}</h3>
            </div>
            <span class="badge neutral">${escapeHtml(challenge.status)}</span>
          </div>
          <p>${escapeHtml(challenge.goal_text)}</p>
          <div class="task-meta">
            <span>${escapeHtml(challenge.member_count)} / ${escapeHtml(challenge.target_team_size)} участников</span>
            <span>${escapeHtml(challenge.target_per_week)} шагов в неделю</span>
          </div>
        </article>
      `
    )
    .join("");

  return `
    ${renderHero()}
    <section class="split-grid">
      <div class="panel">
        <div class="table-toolbar">
          <div>
            <div class="eyebrow">Основной сценарий участника</div>
            <h3>Текущая неделя без перегруза</h3>
          </div>
          <button class="secondary-button" type="button" data-view="tasks">Открыть все задачи</button>
        </div>
        <div class="task-grid" style="margin-top:18px">${previewTasks}</div>
      </div>
      <div class="share-card">
        <div class="eyebrow">Виральный артефакт</div>
        <h3>${escapeHtml(participant.shareCard.title)}</h3>
        <p class="subtle">${escapeHtml(participant.shareCard.subtitle)}</p>
        <div class="list-stack" style="margin-top:18px">
          <div class="mini-stat"><div class="status-dot"></div><strong>${escapeHtml(participant.shareCard.progress_percent)}%</strong><span class="subtle">общий прогресс в потоке</span></div>
          <div class="mini-stat"><div class="status-dot"></div><strong>${escapeHtml(participant.shareCard.xp)} XP</strong><span class="subtle">накоплено на этой неделе</span></div>
          <div class="mini-stat"><div class="status-dot"></div><strong>#${escapeHtml(participant.shareCard.rank)}</strong><span class="subtle">позиция в лидерборде</span></div>
          <div class="mini-stat"><div class="status-dot"></div><strong>${escapeHtml(participant.shareCard.team_name)}</strong><span class="subtle">мини-команда поддерживает темп</span></div>
        </div>
      </div>
    </section>

    <section class="split-grid">
      <div class="panel">
        <div class="table-toolbar">
          <div>
            <div class="eyebrow">B2B dashboard</div>
            <h3>Что видит организатор прямо сейчас</h3>
          </div>
          <button class="secondary-button" type="button" data-view="organizer">Открыть экран организатора</button>
        </div>
        <div class="kpi-grid" style="margin-top:18px">
          <div class="kpi">
            <div class="eyebrow">Участники</div>
            <div class="kpi-value">${escapeHtml(organizerDashboard.totalParticipants)}</div>
            <div class="kpi-caption">в активном потоке</div>
          </div>
          <div class="kpi">
            <div class="eyebrow">Доходимость</div>
            <div class="kpi-value">${escapeHtml(organizerDashboard.completionRate)}%</div>
            <div class="kpi-caption">текущий средний прогресс</div>
          </div>
          <div class="kpi">
            <div class="eyebrow">Риск оттока</div>
            <div class="kpi-value">${escapeHtml(organizerDashboard.atRiskCount)}</div>
            <div class="kpi-caption">нужны nudges</div>
          </div>
          <div class="kpi">
            <div class="eyebrow">Отчёты сегодня</div>
            <div class="kpi-value">${escapeHtml(organizerDashboard.reportsToday)}</div>
            <div class="kpi-caption">уже принято системой</div>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="eyebrow">Контекстные уведомления</div>
        <h3>Smart nudges вместо обычных пушей</h3>
        <div class="notification-stack" style="margin-top:18px">${previewNotifications}</div>
      </div>
    </section>

    <section class="challenge-grid">
      <div class="panel">
        <div class="eyebrow">Органический рост</div>
        <h3>Приватные челленджи после марафона</h3>
        <p class="subtle">Тот же продукт можно использовать без организатора. Это даёт естественный B2C-канал поверх B2B-дистрибуции.</p>
        <div class="list-stack" style="margin-top:18px">${challenges || '<div class="empty-card">Пока нет приватных челленджей</div>'}</div>
      </div>
      <div class="panel">
        <div class="eyebrow">Архитектура MVP</div>
        <h3>Что уже заложено в демке</h3>
        <div class="list-stack" style="margin-top:18px">
          <div class="list-box"><strong>No-code конструктор</strong><p class="subtle">Можно добавлять модули и задания в поток без кода.</p></div>
          <div class="list-box"><strong>Локальная SQLite база</strong><p class="subtle">Все действия сохраняются локально и переживают перезагрузку страницы.</p></div>
          <div class="list-box"><strong>Два сценария</strong><p class="subtle">Участник и организатор работают на одном стеке данных.</p></div>
        </div>
      </div>
    </section>
  `;
}

function renderTasksView() {
  const { participantBoard, notifications } = state.app;
  return `
    ${renderHero()}
    <section class="split-grid">
      <div class="panel">
        <div class="table-toolbar">
          <div>
            <div class="eyebrow">Мои задания</div>
            <h3>Неделя, где можно вернуться без чувства провала</h3>
          </div>
          <div class="chip-row">
            <span class="chip" style="color:#fff">${escapeHtml(participantBoard.missedCount)} пропущено</span>
            <span class="chip" style="color:#fff">${escapeHtml(participantBoard.softReturnCount)} мягких возвратов</span>
          </div>
        </div>
        <div class="task-grid" style="margin-top:18px">
          ${participantBoard.tasks.map(renderTaskCard).join("")}
        </div>
      </div>
      <div class="panel">
        <div class="eyebrow">Nudges</div>
        <h3>Напоминания, привязанные к контексту</h3>
        <div class="notification-stack" style="margin-top:18px">
          ${notifications.map(renderNotificationCard).join("")}
        </div>
      </div>
    </section>
  `;
}

function renderLeaderboardView() {
  const { leaderboard, participant, team } = state.app;
  return `
    ${renderHero()}
    <section class="split-grid">
      <div class="panel">
        <div class="eyebrow">Общий зачёт</div>
        <h3>Лидерборд потока</h3>
        <div class="podium" style="margin-top:18px">
          ${leaderboard.topThree
            .map((person, index) => {
              const classes = ["second", "first", "third"][index] || "";
              return `
                <article class="podium-card ${classes}">
                  ${renderAvatar(person, true)}
                  <h3 style="margin-top:14px">${escapeHtml(person.full_name)}</h3>
                  <p class="subtle">#${escapeHtml(person.rank)} • ${escapeHtml(person.xp)} XP • ${escapeHtml(person.progress_percent)}%</p>
                </article>
              `;
            })
            .join("")}
        </div>
      </div>
      <div class="share-card">
        <div class="eyebrow">Командная динамика</div>
        <h3>Твоя команда: ${escapeHtml(team.name)}</h3>
        <p class="subtle">${escapeHtml(team.goal_text)}</p>
        <div class="list-stack" style="margin-top:18px">
          <div class="mini-stat"><div class="status-dot"></div><strong>${escapeHtml(team.xp_total)} XP</strong><span class="subtle">суммарно набрала команда</span></div>
          <div class="mini-stat"><div class="status-dot"></div><strong>${escapeHtml(team.progress_percent)}%</strong><span class="subtle">общий темп команды</span></div>
          <div class="mini-stat"><div class="status-dot"></div><strong>#${escapeHtml(participant.rank)}</strong><span class="subtle">твоё место в общем зачёте</span></div>
        </div>
      </div>
    </section>

    <section class="table-card">
      <div class="table-toolbar">
        <div>
          <div class="eyebrow">Полный список</div>
          <h3>Кто держит темп, а кому нужен мягкий nudging</h3>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Участник</th>
            <th>Прогресс</th>
            <th>XP</th>
            <th>Состояние</th>
          </tr>
        </thead>
        <tbody>
          ${leaderboard.rows
            .map(
              (row) => `
                <tr class="${row.participant_id === participant.id ? "highlight-row" : ""}">
                  <td>${escapeHtml(row.rank)}</td>
                  <td>
                    <div class="person-cell">
                      ${renderAvatar(row)}
                      <div>
                        <strong>${escapeHtml(row.full_name)}</strong>
                        <div class="subtle">${escapeHtml(formatDateTime(row.last_active_at))}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div class="progress-track"><div class="progress-fill" style="width:${escapeHtml(row.progress_percent)}%"></div></div>
                    <div class="subtle" style="margin-top:6px">${escapeHtml(row.progress_percent)}%</div>
                  </td>
                  <td>${escapeHtml(row.xp)}</td>
                  <td>${row.at_risk ? '<span class="badge warning">Нужен возврат</span>' : '<span class="badge success">В ритме</span>'}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </section>
  `;
}

function renderTeamView() {
  const { team, organizerDashboard } = state.app;
  return `
    ${renderHero()}
    <section class="split-grid">
      <div class="panel">
        <div class="table-toolbar">
          <div>
            <div class="eyebrow">Мини-команда ${escapeHtml(team.name)}</div>
            <h3>Accountability на 3-7 человек вместо шума в общем чате</h3>
          </div>
          <span class="badge success">${escapeHtml(team.progress_percent)}% командного прогресса</span>
        </div>
        <div class="team-member-grid" style="margin-top:18px">
          ${team.members
            .map(
              (member) => `
                <article class="team-member-card">
                  <div class="task-head">
                    <div class="person-cell">
                      ${renderAvatar(member)}
                      <div>
                        <strong>${escapeHtml(member.full_name)}</strong>
                        <div class="member-meta">${member.is_captain ? "Капитан команды" : "Участник"}</div>
                      </div>
                    </div>
                    <span class="badge ${member.progress_percent >= 80 ? "success" : "info"}">${escapeHtml(member.progress_percent)}%</span>
                  </div>
                  <div class="task-meta">
                    <span>${escapeHtml(member.xp)} XP</span>
                    <span>${escapeHtml(member.streak_days)} дней streak</span>
                  </div>
                </article>
              `
            )
            .join("")}
        </div>
      </div>
      <div class="panel">
        <div class="eyebrow">Командная лента</div>
        <h3>Последние отчёты, которые держат ритм</h3>
        <div class="list-stack" style="margin-top:18px">
          ${organizerDashboard.recentReports
            .slice(0, 4)
            .map(
              (report) => `
                <div class="list-box">
                  <div class="task-head">
                    <strong>${escapeHtml(report.full_name)}</strong>
                    <span class="badge neutral">${escapeHtml(report.report_type)}</span>
                  </div>
                  <p class="subtle">${escapeHtml(report.title)}</p>
                  <p class="subtle">${escapeHtml(report.content)}</p>
                </div>
              `
            )
            .join("")}
        </div>
      </div>
    </section>
  `;
}

function renderOrganizerView() {
  const { organizerDashboard, organizer } = state.app;
  return `
    ${renderHero()}
    <section class="panel">
      <div class="eyebrow">Операционный центр организатора</div>
      <h3>Вместо Google Sheets + Telegram + ручных напоминаний</h3>
      <div class="kpi-grid" style="margin-top:18px">
        <div class="kpi"><div class="eyebrow">Участники</div><div class="kpi-value">${escapeHtml(organizerDashboard.totalParticipants)}</div><div class="kpi-caption">внутри текущего потока</div></div>
        <div class="kpi"><div class="eyebrow">Доходимость</div><div class="kpi-value">${escapeHtml(organizerDashboard.completionRate)}%</div><div class="kpi-caption">в среднем по потоку</div></div>
        <div class="kpi"><div class="eyebrow">В риске</div><div class="kpi-value">${escapeHtml(organizerDashboard.atRiskCount)}</div><div class="kpi-caption">требуют внимания</div></div>
        <div class="kpi"><div class="eyebrow">Экономия</div><div class="kpi-value">${escapeHtml(organizerDashboard.hoursSavedPerWeek)}</div><div class="kpi-caption">часов в неделю</div></div>
      </div>
    </section>

    <section class="org-grid">
      <div class="panel">
        <div class="eyebrow">Риск оттока</div>
        <h3>Кого ловить до того, как человек отвалится</h3>
        <div class="list-stack" style="margin-top:18px">
          ${organizerDashboard.atRiskParticipants
            .map(
              (person) => `
                <div class="list-box">
                  <div class="task-head">
                    <div class="person-cell">
                      ${renderAvatar(person)}
                      <div>
                        <strong>${escapeHtml(person.full_name)}</strong>
                        <div class="subtle">${escapeHtml(formatDateTime(person.last_active_at))}</div>
                      </div>
                    </div>
                    <span class="badge warning">${escapeHtml(person.soft_return_count)} возврата</span>
                  </div>
                  <p class="subtle">Прогресс ${escapeHtml(person.progress_percent)}%, очки ${escapeHtml(person.xp)}. Этому участнику лучше отправить поддерживающий nudging, а не жёсткий выговор.</p>
                </div>
              `
            )
            .join("")}
        </div>
      </div>
      <div class="panel">
        <div class="eyebrow">Последние отчёты</div>
        <h3>Что участники уже сдали системе</h3>
        <div class="list-stack" style="margin-top:18px">
          ${organizerDashboard.recentReports
            .map(
              (report) => `
                <div class="list-box">
                  <div class="task-head">
                    <strong>${escapeHtml(report.full_name)}</strong>
                    <span class="badge success">${escapeHtml(report.status)}</span>
                  </div>
                  <p class="subtle">${escapeHtml(report.title)}</p>
                  <p class="subtle">${escapeHtml(report.content)}</p>
                </div>
              `
            )
            .join("")}
        </div>
      </div>
    </section>

    <section class="org-grid">
      <div class="panel">
        <div class="eyebrow">Smart triggers</div>
        <h3>Автоматизации, которые уже можно масштабировать</h3>
        <div class="list-stack" style="margin-top:18px">
          ${organizerDashboard.smartTriggers
            .map(
              (item) => `
                <div class="list-box">
                  <strong>${escapeHtml(item.title)}</strong>
                  <p class="subtle">${escapeHtml(item.description)}</p>
                </div>
              `
            )
            .join("")}
        </div>
      </div>

      <div class="form-card">
        <div class="eyebrow">White label</div>
        <h3>Настройки брендинга организатора</h3>
        <form id="branding-form">
          <div class="form-grid">
            <label>
              Название бренда
              <input name="brandName" value="${escapeHtml(organizer.brand_name)}" required />
            </label>
            <label>
              Support email
              <input name="supportEmail" value="${escapeHtml(organizer.support_email)}" required />
            </label>
            <label>
              Primary color
              <input name="primaryColor" value="${escapeHtml(organizer.primary_color)}" required />
            </label>
            <label>
              Accent color
              <input name="accentColor" value="${escapeHtml(organizer.accent_color)}" required />
            </label>
          </div>
          <button class="primary-button" type="submit">Сохранить брендинг</button>
        </form>
      </div>
    </section>
  `;
}

function renderBuilderView() {
  const { builder } = state.app;
  return `
    ${renderHero()}
    <section class="org-grid">
      <div class="panel">
        <div class="table-toolbar">
          <div>
            <div class="eyebrow">No-code конструктор</div>
            <h3>Структура текущего марафона</h3>
          </div>
          <button class="secondary-button" type="button" data-action="duplicate-program" data-id="1">Клонировать поток</button>
        </div>
        <div class="module-stack" style="margin-top:18px">
          ${builder.modules
            .map(
              (module) => `
                <article class="module-card">
                  <div class="task-head">
                    <div>
                      <div class="eyebrow">${escapeHtml(module.week_label)}</div>
                      <h3>${escapeHtml(module.title)}</h3>
                    </div>
                    <span class="badge neutral">${escapeHtml(module.tasks.length)} задач</span>
                  </div>
                  <p class="subtle">${escapeHtml(module.description)}</p>
                  <div class="module-tasks">
                    ${module.tasks
                      .map(
                        (task) => `
                          <div class="module-task-pill">
                            <strong>${escapeHtml(task.title)}</strong>
                            <span class="subtle">${escapeHtml(task.task_type)} • ${escapeHtml(task.points)} XP • ${escapeHtml(task.submission_mode)}</span>
                          </div>
                        `
                      )
                      .join("")}
                  </div>
                </article>
              `
            )
            .join("")}
        </div>
      </div>

      <div class="panel">
        <div class="eyebrow">Библиотека шаблонов</div>
        <h3>Переиспользование прошлых запусков</h3>
        <div class="list-stack" style="margin-top:18px">
          ${builder.reusablePrograms
            .map(
              (program) => `
                <div class="list-box">
                  <div class="task-head">
                    <div>
                      <strong>${escapeHtml(program.name)}</strong>
                      <div class="subtle">${escapeHtml(program.status)} • ${escapeHtml(program.module_count)} модулей • ${escapeHtml(program.task_count)} задач</div>
                    </div>
                    <button class="inline-button" type="button" data-action="duplicate-program" data-id="${program.id}">Дублировать</button>
                  </div>
                </div>
              `
            )
            .join("")}
        </div>
      </div>
    </section>

    <section class="org-grid">
      <div class="form-card">
        <div class="eyebrow">Новый модуль</div>
        <h3>Добавить этап программы</h3>
        <form id="module-form">
          <div class="form-grid">
            <label>
              Название модуля
              <input name="title" placeholder="Например: Рефлексия и закрепление" required />
            </label>
            <label>
              Лейбл недели
              <input name="weekLabel" placeholder="Неделя 4" required />
            </label>
          </div>
          <label>
            Описание
            <textarea name="description" placeholder="Кратко объясни, зачем нужен этот этап."></textarea>
          </label>
          <button class="primary-button" type="submit">Добавить модуль</button>
        </form>
      </div>

      <div class="form-card">
        <div class="eyebrow">Новое задание</div>
        <h3>Добавить шаг в программу</h3>
        <form id="task-form">
          <div class="form-grid">
            <label>
              Модуль
              <select name="moduleId" required>
                ${builder.modules.map((module) => `<option value="${module.id}">${escapeHtml(module.week_label)} / ${escapeHtml(module.title)}</option>`).join("")}
              </select>
            </label>
            <label>
              Название
              <input name="title" placeholder="Например: 10 минут тишины" required />
            </label>
            <label>
              Тип
              <input name="taskType" value="reflection" required />
            </label>
            <label>
              Формат сдачи
              <select name="submissionMode">
                <option value="text">text</option>
                <option value="photo">photo</option>
                <option value="voice">voice</option>
                <option value="checklist">checklist</option>
              </select>
            </label>
            <label>
              XP
              <input name="points" type="number" value="120" min="10" required />
            </label>
            <label>
              Минуты
              <input name="estimatedMinutes" type="number" value="15" min="1" required />
            </label>
            <label>
              Дата
              <input name="scheduledFor" type="date" required />
            </label>
            <label>
              Мягкий возврат
              <input name="softReturnCopy" placeholder="Как участнику вернуться без стыда" />
            </label>
          </div>
          <label>
            Описание
            <textarea name="description" placeholder="Что именно должен сделать участник."></textarea>
          </label>
          <button class="primary-button" type="submit">Добавить задание</button>
        </form>
      </div>
    </section>
  `;
}

function renderAnalyticsView() {
  const { analytics, organizerDashboard } = state.app;
  const maxCompletion = Math.max(...analytics.dailyMetrics.map((item) => Number(item.completion_rate)), 1);
  return `
    ${renderHero()}
    <section class="analytics-grid">
      <div class="metric-card">
        <div class="metric-card-header">
          <div>
            <div class="eyebrow">Engagement pulse</div>
            <h3>Динамика по дням</h3>
          </div>
        </div>
        <div class="metric-bars" style="margin-top:18px">
          ${analytics.dailyMetrics
            .map(
              (item) => `
                <div class="metric-bar">
                  <div class="metric-bar-track">
                    <div class="metric-bar-fill" style="height:${Math.max(24, (Number(item.completion_rate) / maxCompletion) * 210)}px"></div>
                  </div>
                  <strong>${escapeHtml(item.completion_rate)}%</strong>
                  <div class="metric-bar-label">${escapeHtml(formatCompactDay(item.metric_date))}</div>
                </div>
              `
            )
            .join("")}
        </div>
      </div>

      <div class="panel">
        <div class="eyebrow">Cohorts</div>
        <h3>Сегментация участников</h3>
        <div class="list-stack" style="margin-top:18px">
          ${analytics.cohorts
            .map(
              (cohort) => `
                <div class="list-box">
                  <div class="task-head">
                    <strong>${escapeHtml(cohort.label)}</strong>
                    <span class="badge ${escapeHtml(cohort.tone)}">${escapeHtml(cohort.count)}</span>
                  </div>
                </div>
              `
            )
            .join("")}
        </div>
      </div>
    </section>

    <section class="org-grid">
      <div class="panel">
        <div class="eyebrow">Drop-off signals</div>
        <h3>Что видно в локальной аналитике</h3>
        <div class="list-stack" style="margin-top:18px">
          ${analytics.dailyMetrics
            .slice()
            .reverse()
            .map(
              (item) => `
                <div class="list-box">
                  <div class="task-head">
                    <strong>${escapeHtml(formatDate(item.metric_date))}</strong>
                    <span class="badge ${item.missed_tasks > 8 ? "warning" : "info"}">${escapeHtml(item.missed_tasks)} missed</span>
                  </div>
                  <p class="subtle">${escapeHtml(item.active_participants)} активных участников, ${escapeHtml(item.reports_submitted)} отчётов, completion ${escapeHtml(item.completion_rate)}%.</p>
                </div>
              `
            )
            .join("")}
        </div>
      </div>

      <div class="panel">
        <div class="eyebrow">Automation layer</div>
        <h3>Какие действия стоит автоматизировать дальше</h3>
        <div class="list-stack" style="margin-top:18px">
          ${organizerDashboard.smartTriggers
            .map(
              (item) => `
                <div class="list-box">
                  <strong>${escapeHtml(item.title)}</strong>
                  <p class="subtle">${escapeHtml(item.description)}</p>
                </div>
              `
            )
            .join("")}
        </div>
      </div>
    </section>
  `;
}

function renderChallengesView() {
  const { privateChallenges, participant } = state.app;
  return `
    ${renderHero()}
    <section class="challenge-grid">
      <div class="form-card">
        <div class="eyebrow">B2C сценарий</div>
        <h3>Создать приватный челлендж с друзьями</h3>
        <form id="challenge-form">
          <div class="form-grid">
            <label>
              Название
              <input name="name" placeholder="Например: Утренний бег без срывов" required />
            </label>
            <label>
              Цель
              <input name="goalText" placeholder="4 пробежки в неделю" required />
            </label>
            <label>
              Шагов в неделю
              <input name="targetPerWeek" type="number" value="4" min="1" required />
            </label>
            <label>
              Размер команды
              <input name="targetTeamSize" type="number" value="4" min="2" max="7" required />
            </label>
            <label>
              Длительность, недели
              <input name="durationWeeks" type="number" value="3" min="1" required />
            </label>
          </div>
          <label>
            Контекст
            <textarea name="description" placeholder="Коротко опиши механику для друзей."></textarea>
          </label>
          <button class="primary-button" type="submit">Создать челлендж</button>
        </form>
      </div>

      <div class="share-card">
        <div class="eyebrow">Почему это работает</div>
        <h3>Growth loop поверх B2B дистрибуции</h3>
        <p class="subtle">Участник уже понял ценность продукта внутри потока. Дальше он создаёт свой челлендж и тянет новых пользователей в тот же продукт.</p>
        <div class="list-stack" style="margin-top:18px">
          <div class="mini-stat"><div class="status-dot"></div><strong>${escapeHtml(participant.xp)} XP</strong><span class="subtle">социальное доказательство для приглашений</span></div>
          <div class="mini-stat"><div class="status-dot"></div><strong>${escapeHtml(participant.progress_percent)}%</strong><span class="subtle">личный результат уже есть</span></div>
          <div class="mini-stat"><div class="status-dot"></div><strong>${escapeHtml(participant.streak_days)} дней</strong><span class="subtle">есть история, которой хочется делиться</span></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="eyebrow">Текущие приватные челленджи</div>
      <h3>Seeded сценарии для дальнейшего развития B2C</h3>
      <div class="challenge-grid" style="margin-top:18px">
        ${privateChallenges
          .map(
            (challenge) => `
              <article class="challenge-card">
                <div class="task-head">
                  <div>
                    <div class="eyebrow">${escapeHtml(challenge.visibility)}</div>
                    <h3>${escapeHtml(challenge.name)}</h3>
                  </div>
                  <span class="badge ${challenge.status === "active" ? "success" : "neutral"}">${escapeHtml(challenge.status)}</span>
                </div>
                <p>${escapeHtml(challenge.description)}</p>
                <div class="task-meta">
                  <span>${escapeHtml(challenge.goal_text)}</span>
                  <span>${escapeHtml(challenge.member_count)} / ${escapeHtml(challenge.target_team_size)} участников</span>
                </div>
                <div class="person-cell" style="margin-top:14px; flex-wrap:wrap">
                  ${challenge.members.map((member) => renderAvatar(member)).join("")}
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderCurrentView() {
  if (!state.app) {
    return `
      <section class="loading-state">
        <div class="spinner"></div>
        <p>Подключаем локальную демку GoalMate...</p>
      </section>
    `;
  }

  const views = {
    overview: renderOverview,
    tasks: renderTasksView,
    leaderboard: renderLeaderboardView,
    team: renderTeamView,
    organizer: renderOrganizerView,
    builder: renderBuilderView,
    analytics: renderAnalyticsView,
    challenges: renderChallengesView,
  };

  return views[state.currentView]?.() ?? renderOverview();
}

function renderModal() {
  if (!state.modal || !state.app) {
    modal.classList.add("hidden");
    modalCard.innerHTML = "";
    return;
  }

  if (state.modal.type === "report") {
    const task = state.app.participantBoard.tasks.find((item) => item.participant_task_id === state.modal.taskId);
    modalCard.innerHTML = `
      <div class="table-toolbar">
        <div>
          <div class="eyebrow">Сдать отчёт</div>
          <h3>${escapeHtml(task.title)}</h3>
        </div>
        <button class="inline-button" type="button" data-close-modal="true">Закрыть</button>
      </div>
      <p class="subtle">${escapeHtml(task.description)}</p>
      <form id="report-form" style="margin-top:18px">
        <input type="hidden" name="participantTaskId" value="${task.participant_task_id}" />
        <div class="form-grid">
          <label>
            Формат отчёта
            <select name="reportType">
              <option value="text">text</option>
              <option value="photo">photo</option>
              <option value="voice">voice</option>
            </select>
          </label>
          <label>
            Имя вложения
            <input name="attachmentName" placeholder="Например: report-photo.jpg" value="${escapeHtml(task.attachment_name || "")}" />
          </label>
        </div>
        <label>
          Текст отчёта
          <textarea name="content" placeholder="Что получилось, где было трудно, какой результат виден уже сейчас." required>${escapeHtml(task.report_content || "")}</textarea>
        </label>
        <button class="primary-button" type="submit">Отправить отчёт</button>
      </form>
    `;
  }

  if (state.modal.type === "login") {
    const recommended = state.me?.demoCredentials?.[0] || {
      email: "demo@goalmate.local",
      password: "goalmate-demo",
      role: "mixed",
    };
    const credentialRows = (state.me?.demoCredentials || [])
      .map(
        (item) => `
          <div class="list-box">
            <div class="task-head">
              <strong>${escapeHtml(item.email)}</strong>
              <span class="badge neutral">${escapeHtml(item.role)}</span>
            </div>
            <p class="subtle">Пароль: <code>${escapeHtml(item.password)}</code></p>
          </div>
        `
      )
      .join("");

    modalCard.innerHTML = `
      <div class="table-toolbar">
        <div>
          <div class="eyebrow">Auth foundation</div>
          <h3>Создать demo-сессию</h3>
        </div>
        <button class="inline-button" type="button" data-close-modal="true">Закрыть</button>
      </div>
      <p class="subtle">Реальная auth уже заведена в локальной базе, но development fallback всё ещё активен. Ниже можно создать настоящую cookie-сессию и проверить следующий слой архитектуры.</p>
      <form id="login-form" style="margin-top:18px">
        <div class="form-grid">
          <label>
            Email
            <input name="email" value="${escapeHtml(recommended.email)}" required />
          </label>
          <label>
            Пароль
            <input name="password" value="${escapeHtml(recommended.password)}" required />
          </label>
        </div>
        <button class="primary-button" type="submit">Войти</button>
      </form>
      <div class="list-stack" style="margin-top:18px">
        ${credentialRows}
      </div>
    `;
  }

  modal.classList.remove("hidden");
}

function render() {
  renderNav();
  renderRoleSwitch();
  renderAuthPanel();
  if (state.app) {
    topbarTitle.textContent = state.currentRole === "participant" ? "GoalMate: участник" : "GoalMate: организатор";
    const authMode = state.me?.authenticated ? "session" : state.app.meta.contextSource;
    topbarLabel.textContent = `${state.app.program.brand_name} • ${state.currentRole === "participant" ? "participant demo" : "operator demo"} • ${authMode}`;
  }

  viewRoot.innerHTML = renderCurrentView();
  renderModal();
  resetDemoButton.disabled = state.busy;
}

document.addEventListener("click", async (event) => {
  const viewButton = event.target.closest("[data-view]");
  if (viewButton) {
    setView(viewButton.dataset.view);
    return;
  }

  const roleButton = event.target.closest("[data-role]");
  if (roleButton) {
    setRole(roleButton.dataset.role);
    return;
  }

  const closeModalButton = event.target.closest("[data-close-modal]");
  if (closeModalButton) {
    closeModal();
    return;
  }

  const actionButton = event.target.closest("[data-action]");
  if (!actionButton || state.busy) return;

  const action = actionButton.dataset.action;
  const id = Number(actionButton.dataset.id || actionButton.dataset.taskId || 0);

  if (action === "complete-task") {
    await performRequest(`/api/participant-tasks/${id}/complete`);
    showToast("Задача отмечена выполненной");
    return;
  }

  if (action === "soft-return") {
    await performRequest(`/api/participant-tasks/${id}/soft-return`);
    showToast("Мягкий возврат активирован");
    return;
  }

  if (action === "open-report") {
    openReportModal(id);
    return;
  }

  if (action === "open-login") {
    openLoginModal();
    return;
  }

  if (action === "logout") {
    const ok = await performAuthRequest("/api/auth/logout");
    if (ok) {
      showToast("Сессия завершена, включился development fallback");
    }
    return;
  }

  if (action === "notification-read") {
    await performRequest(`/api/notifications/${id}/read`);
    showToast("Уведомление помечено прочитанным");
    return;
  }

  if (action === "duplicate-program") {
    await performRequest(`/api/programs/${id}/duplicate`);
    showToast("Программа клонирована");
  }
});

document.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy) return;

  const form = event.target;
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  if (form.id === "report-form") {
    payload.participantTaskId = Number(payload.participantTaskId);
    await performRequest("/api/reports", payload);
    showToast("Отчёт отправлен и прогресс обновлён");
    return;
  }

  if (form.id === "login-form") {
    const ok = await performAuthRequest("/api/auth/login", payload);
    if (ok) {
      showToast("Demo-сессия создана");
    }
    return;
  }

  if (form.id === "branding-form") {
    await performRequest("/api/settings/branding", payload);
    showToast("Брендинг обновлён");
    return;
  }

  if (form.id === "module-form") {
    await performRequest("/api/builder/modules", payload);
    form.reset();
    showToast("Модуль добавлен в программу");
    return;
  }

  if (form.id === "task-form") {
    payload.moduleId = Number(payload.moduleId);
    payload.points = Number(payload.points);
    payload.estimatedMinutes = Number(payload.estimatedMinutes);
    await performRequest("/api/builder/tasks", payload);
    form.reset();
    showToast("Задание добавлено в поток");
    return;
  }

  if (form.id === "challenge-form") {
    payload.targetPerWeek = Number(payload.targetPerWeek);
    payload.targetTeamSize = Number(payload.targetTeamSize);
    payload.durationWeeks = Number(payload.durationWeeks);
    await performRequest("/api/private-challenges", payload);
    form.reset();
    showToast("Приватный челлендж создан");
  }
});

resetDemoButton.addEventListener("click", async () => {
  if (state.busy) return;
  await performRequest("/api/reset-demo");
  showToast("Демо сброшено к начальному состоянию");
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeModal();
  }
});

loadState();
