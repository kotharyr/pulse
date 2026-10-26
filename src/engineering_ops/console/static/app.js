const FALLBACK_DEFAULT_JQL = "updated >= -30d ORDER BY updated DESC";
const VIEW_TITLE_FALLBACK = "Engineering Review";
const THEME_KEY = "engineeringOpsConsole.theme.v2";
const TASK_NOTES_KEY = "engineeringOpsConsole.taskNotes.v1";
const SIDEBAR_KEY = "engineeringOpsConsole.sidebarCollapsed.v1";

const state = {
  authToken: "",
  instance: "cloud",
  instances: [],
  page: 1,
  pageSize: 25,
  currentPreviewId: null,
  recoveryId: null,
  workflowResult: null,
  savedViews: [],
  jqlTouched: false,
  activeView: "workflow-view",
  theme: "dark",
  sidebarCollapsed: false,
  sprintDiscovery: null,
  environment: null,
  repositories: [],
  security: null,
  hygieneReview: null,
  hygienePreviewId: null,
  selectedSavedView: null,
};

const els = {
  consoleToken: document.getElementById("console-token"),
  consoleConnect: document.getElementById("console-connect"),
  appShell: document.querySelector(".app-shell"),
  mode: document.getElementById("mode-pill"),
  sidebarToggle: document.getElementById("sidebar-toggle"),
  themeToggle: document.getElementById("theme-toggle"),
  viewTitle: document.getElementById("view-title"),
  navItems: document.querySelectorAll("[data-view-target]"),
  views: document.querySelectorAll(".view"),
  instance: document.getElementById("instance-select"),
  jql: document.getElementById("jql-input"),
  search: document.getElementById("search-button"),
  saveView: document.getElementById("save-view-button"),
  savedViews: document.getElementById("saved-views"),
  prev: document.getElementById("prev-page"),
  next: document.getElementById("next-page"),
  pageLabel: document.getElementById("page-label"),
  issuesBody: document.getElementById("issues-body"),
  sprintId: document.getElementById("sprint-id"),
  nextSprintId: document.getElementById("next-sprint-id"),
  loadSprint: document.getElementById("load-sprint"),
  sprintName: document.getElementById("sprint-name"),
  nextSprintName: document.getElementById("next-sprint-name"),
  sprintWindow: document.getElementById("sprint-window"),
  nextSprintStrategy: document.getElementById("next-sprint-strategy"),
  sprintStatus: document.getElementById("sprint-status"),
  sprintRing: document.getElementById("sprint-ring"),
  ringPercent: document.getElementById("ring-percent"),
  ringPoints: document.getElementById("ring-points"),
  completion: document.getElementById("metric-completion"),
  completedPoints: document.getElementById("metric-completed-points"),
  remainingPoints: document.getElementById("metric-remaining-points"),
  projectedLoad: document.getElementById("metric-projected-load"),
  capacity: document.getElementById("metric-capacity"),
  overcommit: document.getElementById("metric-overcommit"),
  overcommitCard: document.getElementById("overcommit-card"),
  teamProgress: document.getElementById("team-progress"),
  engineerProgress: document.getElementById("engineer-progress"),
  blockedWork: document.getElementById("blocked-work"),
  rollover: document.getElementById("rollover-candidates"),
  splitProposals: document.getElementById("split-proposals"),
  rolloverAll: document.getElementById("rollover-all"),
  previewClose: document.getElementById("preview-close"),
  previewStatus: document.getElementById("preview-status"),
  previewOutput: document.getElementById("preview-output"),
  reconcilePreview: document.getElementById("reconcile-preview"),
  resumePreview: document.getElementById("resume-preview"),
  rejectPreview: document.getElementById("reject-preview"),
  applyPreview: document.getElementById("apply-preview"),
  history: document.getElementById("execution-history"),
  workflowStatus: document.getElementById("workflow-status"),
  workflowButtons: document.querySelectorAll("[data-workflow]"),
  workflowProject: document.getElementById("workflow-project"),
  workflowTeam: document.getElementById("workflow-team"),
  workflowSavedView: document.getElementById("workflow-saved-view"),
  workflowSprint: document.getElementById("workflow-sprint"),
  workflowNextSprint: document.getElementById("workflow-next-sprint"),
  workflowQuarter: document.getElementById("workflow-quarter"),
  workflowPreviewId: document.getElementById("workflow-preview-id"),
  workflowTitle: document.getElementById("workflow-title"),
  workflowConfidence: document.getElementById("workflow-confidence"),
  workflowMetrics: document.getElementById("workflow-metrics"),
  workflowRisks: document.getElementById("workflow-risks"),
  workflowRecommendations: document.getElementById("workflow-recommendations"),
  workflowCoverage: document.getElementById("workflow-coverage"),
  workflowPreview: document.getElementById("workflow-preview"),
  workflowIssues: document.getElementById("workflow-issues"),
  workflowOutput: document.getElementById("workflow-output"),
  jumpButtons: document.querySelectorAll("[data-jump-view]"),
  taskSavedViews: document.getElementById("task-saved-views"),
  taskNotes: document.getElementById("task-notes"),
  envRefresh: document.getElementById("env-refresh"),
  envCacheAge: document.getElementById("env-cache-age"),
  envProjectCount: document.getElementById("env-project-count"),
  envBoardCount: document.getElementById("env-board-count"),
  envSprintCount: document.getElementById("env-sprint-count"),
  envFieldCount: document.getElementById("env-field-count"),
  envProjects: document.getElementById("env-projects"),
  envBoards: document.getElementById("env-boards"),
  envValues: document.getElementById("env-values"),
  envFields: document.getElementById("env-fields"),
  envErrors: document.getElementById("env-errors"),
  opsViewsRefresh: document.getElementById("ops-views-refresh"),
  opsViewsList: document.getElementById("ops-views-list"),
  opsViewTitle: document.getElementById("ops-view-title"),
  opsViewCount: document.getElementById("ops-view-count"),
  opsViewJql: document.getElementById("ops-view-jql"),
  opsViewResults: document.getElementById("ops-view-results"),
  repoRefresh: document.getElementById("repo-refresh"),
  repoFilter: document.getElementById("repo-filter"),
  repoCount: document.getElementById("repo-count"),
  packageCount: document.getElementById("package-count"),
  imageCount: document.getElementById("image-count"),
  repoConfigured: document.getElementById("repo-configured"),
  repoStatus: document.getElementById("repo-status"),
  repoList: document.getElementById("repo-list"),
  securityRefresh: document.getElementById("security-refresh"),
  securityTicketCount: document.getElementById("security-ticket-count"),
  securityActionCount: document.getElementById("security-action-count"),
  securityRepoCount: document.getElementById("security-repo-count"),
  securityMode: document.getElementById("security-mode"),
  securityStatus: document.getElementById("security-status"),
  securityActions: document.getElementById("security-actions"),
  hygieneStatus: document.getElementById("hygiene-status"),
  hygieneReview: document.getElementById("hygiene-review"),
  hygieneQuarter: document.getElementById("hygiene-quarter"),
  hygieneProject: document.getElementById("hygiene-project"),
  hygieneTeam: document.getElementById("hygiene-team"),
  hygienePt: document.getElementById("hygiene-pt"),
  hygieneSavedView: document.getElementById("hygiene-saved-view"),
  hygieneIssueType: document.getElementById("hygiene-type"),
  hygieneCategory: document.getElementById("hygiene-category"),
  hygieneFixability: document.getElementById("hygiene-fixability"),
  hygieneLimit: document.getElementById("hygiene-limit"),
  hygieneAncestry: document.getElementById("hygiene-ancestry"),
  hygieneDateCount: document.getElementById("hygiene-date-count"),
  hygieneMissingLabels: document.getElementById("hygiene-missing-labels"),
  hygieneWrongLabels: document.getElementById("hygiene-wrong-labels"),
  hygieneSafeFixes: document.getElementById("hygiene-safe-fixes"),
  hygieneManual: document.getElementById("hygiene-manual"),
  hygieneFindings: document.getElementById("hygiene-findings"),
  hygienePreviewAll: document.getElementById("hygiene-preview-all"),
  hygienePreviewSelected: document.getElementById("hygiene-preview-selected"),
  hygieneReject: document.getElementById("hygiene-reject"),
  hygieneApply: document.getElementById("hygiene-apply"),
  hygienePreviewStatus: document.getElementById("hygiene-preview-status"),
  hygienePreviewOutput: document.getElementById("hygiene-preview-output"),
  hygieneHistory: document.getElementById("hygiene-history"),
  systemRefresh: document.getElementById("system-refresh"),
  systemReadiness: document.getElementById("system-readiness"),
  systemMode: document.getElementById("system-mode"),
  systemConnectorsCount: document.getElementById("system-connectors-count"),
  systemAuditCount: document.getElementById("system-audit-count"),
  systemConfig: document.getElementById("system-config"),
  systemConnectors: document.getElementById("system-connectors"),
  systemMetrics: document.getElementById("system-metrics"),
  systemAudit: document.getElementById("system-audit"),
  systemDiagnosticsStatus: document.getElementById("system-diagnostics-status"),
  systemDiagnostics: document.getElementById("system-diagnostics"),
  toast: document.getElementById("toast"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value) {
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric)) return "0";
  return new Intl.NumberFormat(undefined, {maximumFractionDigits: 1}).format(numeric);
}

function formatPercent(value) {
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric)) return "0%";
  return `${formatNumber(numeric)}%`;
}

function percentWidth(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, numeric));
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date;
}

function formatDate(value) {
  const date = parseDate(value);
  if (!date) return "";
  return new Intl.DateTimeFormat(undefined, {month: "short", day: "numeric"}).format(date);
}

function formatDateTime(value) {
  const date = parseDate(value);
  if (!date) return "";
  return new Intl.DateTimeFormat(undefined, {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}).format(date);
}

function formatAge(seconds) {
  const numeric = Number(seconds);
  if (!Number.isFinite(numeric)) return "Unknown age";
  if (numeric < 60) return `${Math.max(0, Math.round(numeric))}s old`;
  if (numeric < 3600) return `${Math.round(numeric / 60)}m old`;
  if (numeric < 86400) return `${Math.round(numeric / 3600)}h old`;
  return `${Math.round(numeric / 86400)}d old`;
}

function sprintLabel(sprint) {
  if (!sprint) return "Not detected";
  const name = sprint.name || `Sprint ${sprint.id}`;
  return sprint.id ? `${name} #${sprint.id}` : name;
}

function sprintWindow(sprint) {
  if (!sprint) return "No sprint loaded";
  const start = formatDate(sprint.startDate);
  const end = formatDate(sprint.endDate);
  if (start && end) return `${start} - ${end}`;
  if (start) return `Starts ${start}`;
  if (end) return `Ends ${end}`;
  return sprint.state ? `${sprint.state} sprint` : "No dates";
}

function strategyLabel(strategy) {
  if (strategy === "number") return "Number match";
  if (strategy === "date") return "Date match";
  if (strategy === "order") return "Next future sprint";
  return "Not selected";
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(state.authToken ? {Authorization: `Bearer ${state.authToken}`} : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request failed with ${response.status}`);
  }
  return data;
}

function setTheme(theme) {
  const normalized = theme === "dark" ? "dark" : "light";
  state.theme = normalized;
  document.documentElement.dataset.theme = normalized;
  els.themeToggle.checked = normalized === "dark";
  localStorage.setItem(THEME_KEY, normalized);
}

function initTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  setTheme(stored || "dark");
}

function setSidebarCollapsed(collapsed) {
  state.sidebarCollapsed = Boolean(collapsed);
  els.appShell.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
  const action = state.sidebarCollapsed ? "Expand" : "Collapse";
  els.sidebarToggle.setAttribute("aria-label", `${action} side menu`);
  els.sidebarToggle.setAttribute("aria-expanded", String(!state.sidebarCollapsed));
  els.sidebarToggle.title = `${action} menu`;
  localStorage.setItem(SIDEBAR_KEY, String(state.sidebarCollapsed));
}

function initSidebar() {
  setSidebarCollapsed(localStorage.getItem(SIDEBAR_KEY) === "true");
}

function setActiveView(viewId) {
  state.activeView = viewId;
  els.views.forEach((view) => view.classList.toggle("active", view.id === viewId));
  els.navItems.forEach((item) => item.classList.toggle("active", item.dataset.viewTarget === viewId));
  const view = document.getElementById(viewId);
  els.viewTitle.textContent = view?.dataset.viewTitle || VIEW_TITLE_FALLBACK;
  if (viewId === "environment-view") loadEnvironment();
  if (viewId === "saved-views-view") loadViews();
  if (viewId === "repositories-view") loadRepositories();
  if (viewId === "security-view") loadSecurity();
  if (viewId === "hygiene-view") {
    preferOnPremInstance();
    loadHygieneContext().then(() => loadHygiene());
  }
  if (viewId === "system-view") loadPlatform();
  if (viewId === "sprint-ops-view") sprintOps.open();
}

function preferOnPremInstance() {
  const current = state.instances.find((item) => item.name === state.instance);
  if (current && ["datacenter", "server"].includes(current.kind)) return;
  const onprem = state.instances.find((item) => ["datacenter", "server"].includes(item.kind) || item.name === "onprem");
  if (!onprem) return;
  state.instance = onprem.name;
  els.instance.value = onprem.name;
  if (!state.jqlTouched && els.jql) {
    els.jql.value = defaultJqlForInstance(state.instance);
  }
}

function fieldValue(issue, name) {
  const fields = issue.fields || {};
  const value = fields[name];
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value.displayName || value.name || value.value || value.key || "";
  }
  if (Array.isArray(value)) {
    return value.map((item) => (typeof item === "object" ? item.name || item.value || item.key : item)).filter(Boolean).join(", ");
  }
  return value ?? "";
}

function quoteJqlValue(value) {
  const text = String(value || "").trim();
  if (/^[A-Z][A-Z0-9_]*$/.test(text)) {
    return text;
  }
  return `"${text.replaceAll('"', '\\"')}"`;
}

function compactPayload(payload) {
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => {
    if (value == null) return false;
    if (typeof value === "string" && !value.trim()) return false;
    if (Array.isArray(value) && !value.length) return false;
    return true;
  }));
}

function sprintPayloadValue(value, idKey, nameKey) {
  const text = String(value || "").trim();
  if (!text || text.toLowerCase() === "current" || text.toLowerCase() === "next") return {};
  if (/^\d+$/.test(text)) return {[idKey]: Number(text)};
  return {[nameKey]: text};
}

function defaultJqlForInstance(instanceName) {
  const row = state.instances.find((item) => item.name === instanceName);
  if (row?.default_project) {
    return `project = ${quoteJqlValue(row.default_project)} ORDER BY updated DESC`;
  }
  return FALLBACK_DEFAULT_JQL;
}

async function loadViews() {
  try {
    const data = await api("/api/views");
    state.savedViews = data.views || [];
  } catch (error) {
    state.savedViews = [];
    toast(error.message);
  }
  renderSavedViews();
  renderOperationalViews();
}

function renderTaskSavedViews() {
  if (!els.taskSavedViews) return;
  if (!state.savedViews.length) {
    els.taskSavedViews.innerHTML = '<div class="empty">No saved views.</div>';
    return;
  }
  els.taskSavedViews.innerHTML = state.savedViews.slice(0, 6).map((view) => `
    <div class="mini-item">
      <strong>${escapeHtml(view.name)}</strong>
      <span>${escapeHtml(view.instance)}</span>
      <span class="list-meta">${escapeHtml(view.jql)}</span>
    </div>
  `).join("");
}

function renderSavedViews() {
  if (!els.savedViews) return;
  if (!state.savedViews.length) {
    els.savedViews.innerHTML = "";
    renderTaskSavedViews();
    renderOperationalViews();
    return;
  }
  els.savedViews.innerHTML = state.savedViews.map((view, index) => (
    `<button class="saved-view" type="button" data-view="${index}">${escapeHtml(view.name)}</button>`
  )).join("");
  els.savedViews.querySelectorAll("button[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const view = state.savedViews[Number(button.dataset.view)];
      if (view.instance) {
        state.instance = view.instance;
        els.instance.value = view.instance;
      }
      els.jql.value = view.jql;
      state.page = 1;
      searchIssues();
    });
  });
  renderTaskSavedViews();
  renderOperationalViews();
}

function renderOperationalViews() {
  if (!els.opsViewsList) return;
  if (!state.savedViews.length) {
    els.opsViewsList.innerHTML = '<div class="empty">No saved views.</div>';
    return;
  }
  els.opsViewsList.innerHTML = state.savedViews.map((view, index) => `
    <div class="mini-item">
      <strong>${escapeHtml(view.name)}</strong>
      <span>${escapeHtml(view.instance)} | ${escapeHtml(view.dashboard_type || "issue_list")}</span>
      <span class="list-meta">${escapeHtml(view.jql)}</span>
      <div class="button-row">
        <button type="button" data-run-view="${index}">Run</button>
        <button type="button" data-load-view="${index}">Load JQL</button>
      </div>
    </div>
  `).join("");
  els.opsViewsList.querySelectorAll("button[data-run-view]").forEach((button) => {
    button.addEventListener("click", () => runOperationalView(Number(button.dataset.runView)));
  });
  els.opsViewsList.querySelectorAll("button[data-load-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const view = state.savedViews[Number(button.dataset.loadView)];
      if (!view) return;
      state.instance = view.instance || state.instance;
      els.instance.value = state.instance;
      els.jql.value = view.jql;
      setActiveView("jira-view");
    });
  });
}

async function loadInstances() {
  try {
    const data = await api("/api/instances");
    if (!data.instances?.length) {
      els.sprintStatus.textContent = "No instances";
      return;
    }
    state.instances = data.instances;
    els.instance.innerHTML = data.instances.map((row) => {
      const label = row.kind === "cloud" ? "Cloud" : row.kind === "datacenter" || row.kind === "server" ? "On-Prem" : row.name;
      return `<option value="${escapeHtml(row.name)}">${escapeHtml(label)} (${escapeHtml(row.name)})</option>`;
    }).join("");
    state.instance = data.instances[0].name;
    els.instance.value = state.instance;
    if (!state.jqlTouched) {
      els.jql.value = defaultJqlForInstance(state.instance);
    }
    await loadSprintDiscovery();
  } catch (error) {
    els.sprintStatus.textContent = "Manual selection";
    toast(error.message);
  }
}

function renderIssues(data) {
  const rows = data.issues || [];
  if (!rows.length) {
    els.issuesBody.innerHTML = '<tr><td colspan="6" class="empty">No issues found.</td></tr>';
  } else {
    els.issuesBody.innerHTML = rows.map((issue) => {
      const summary = fieldValue(issue, "summary");
      const status = fieldValue(issue, "status");
      const assignee = fieldValue(issue, "assignee") || "Unassigned";
      const points = fieldValue(issue, "Story Points");
      const updated = fieldValue(issue, "updated");
      return `
        <tr>
          <td class="key-cell">${escapeHtml(issue.key)}</td>
          <td>${escapeHtml(summary)}</td>
          <td>${escapeHtml(status)}</td>
          <td>${escapeHtml(assignee)}</td>
          <td>${escapeHtml(points)}</td>
          <td>${escapeHtml(updated)}</td>
        </tr>
      `;
    }).join("");
  }
  const pagination = data.pagination || {};
  state.page = pagination.page || state.page;
  els.pageLabel.textContent = `Page ${state.page}`;
  els.prev.disabled = !pagination.has_previous;
  els.next.disabled = !pagination.has_next;
}

function renderOperationalViewResults(data) {
  const rows = data.issues || [];
  const pagination = data.pagination || {};
  els.opsViewCount.textContent = rows.length ? `${rows.length} issues` : "No issues";
  if (!rows.length) {
    els.opsViewResults.innerHTML = '<tr><td colspan="4" class="empty">No issues found.</td></tr>';
    return;
  }
  els.opsViewResults.innerHTML = rows.map((issue) => `
    <tr>
      <td class="key-cell">${escapeHtml(issue.key)}</td>
      <td>${escapeHtml(fieldValue(issue, "summary"))}</td>
      <td>${escapeHtml(fieldValue(issue, "status"))}</td>
      <td>${escapeHtml(fieldValue(issue, "assignee") || "Unassigned")}</td>
    </tr>
  `).join("");
  if (pagination.page) {
    els.opsViewCount.textContent = `${rows.length} issues | page ${pagination.page}`;
  }
}

async function runOperationalView(index) {
  const view = state.savedViews[index];
  if (!view) return;
  state.selectedSavedView = view;
  els.opsViewTitle.textContent = view.name;
  els.opsViewJql.textContent = view.jql;
  els.opsViewCount.textContent = "Loading";
  try {
    const params = new URLSearchParams({page: "1", page_size: String(state.pageSize)});
    const data = await api(`/api/views/${encodeURIComponent(view.name)}/issues?${params}`);
    renderOperationalViewResults(data.results || data);
  } catch (error) {
    els.opsViewCount.textContent = "Load failed";
    els.opsViewResults.innerHTML = `<tr><td colspan="4" class="empty">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function searchIssues() {
  const jql = els.jql.value.trim();
  if (!jql) {
    toast("JQL is required");
    return;
  }
  try {
    els.search.disabled = true;
    const params = new URLSearchParams({
      instance: state.instance,
      jql,
      page: String(state.page),
      page_size: String(state.pageSize),
    });
    renderIssues(await api(`/api/issues?${params}`));
  } catch (error) {
    toast(error.message);
  } finally {
    els.search.disabled = false;
  }
}

function renderBarList(element, rows) {
  if (!rows?.length) {
    element.innerHTML = '<div class="empty">No data.</div>';
    return;
  }
  element.innerHTML = rows.map((row) => {
    const percent = row.story_point_completion_percent ?? row.completion_percent ?? 0;
    return `
      <div class="bar-row">
        <div>
          <div class="bar-heading">
            <strong>${escapeHtml(row.name)}</strong>
            <span>${formatPercent(percent)}</span>
          </div>
          <div class="bar-track"><div class="bar-fill" style="width: ${percentWidth(percent)}%"></div></div>
        </div>
        <div class="bar-meta">${escapeHtml(formatNumber(row.done_story_points))}/${escapeHtml(formatNumber(row.story_points))} pts</div>
      </div>
    `;
  }).join("");
}

function renderEngineerWorkload(element, rows) {
  if (!rows?.length) {
    element.innerHTML = '<div class="empty">No data.</div>';
    return;
  }
  const maxCommitted = Math.max(...rows.map((row) => Number(row.story_points || 0)), 1);
  element.innerHTML = rows.map((row) => {
    const committed = Number(row.story_points || 0);
    const done = Number(row.done_story_points || 0);
    const committedWidth = percentWidth((committed / maxCommitted) * 100);
    const doneWidth = percentWidth((done / maxCommitted) * 100);
    return `
      <div class="workload-row">
        <div class="bar-heading">
          <strong>${escapeHtml(row.name)}</strong>
          <span>${escapeHtml(formatNumber(done))} / ${escapeHtml(formatNumber(committed))} pts</span>
        </div>
        <div class="commit-track" aria-label="${escapeHtml(row.name)} done versus committed">
          <div class="commit-fill committed" style="width: ${committedWidth}%"></div>
          <div class="commit-fill done" style="width: ${doneWidth}%"></div>
        </div>
      </div>
    `;
  }).join("");
}

function renderMiniList(element, rows, blocked = false) {
  if (!rows?.length) {
    element.innerHTML = '<div class="empty">None.</div>';
    return;
  }
  element.innerHTML = rows.slice(0, 8).map((row) => `
    <div class="mini-item ${blocked || row.blocked ? "blocked" : ""}">
      <strong>${escapeHtml(row.issue_key)}</strong>
      <span>${escapeHtml(row.summary)}</span>
      <span class="list-meta">${escapeHtml(row.assignee)} | ${escapeHtml(row.status)} | ${escapeHtml(formatNumber(row.story_points))} pts</span>
    </div>
  `).join("");
}

function renderSplitProposals(rows) {
  if (!rows?.length) {
    els.splitProposals.innerHTML = '<div class="empty">None.</div>';
    return;
  }
  els.splitProposals.innerHTML = rows.slice(0, 8).map((row) => `
    <div class="mini-item">
      <strong>${escapeHtml(row.source_issue_key)}</strong>
      <span>${escapeHtml(row.new_summary)}</span>
      <span class="list-meta">${escapeHtml(formatNumber(row.story_points))} pts | ${escapeHtml(row.reason)}</span>
    </div>
  `).join("");
}

function renderEnvironment(data) {
  state.environment = data;
  const projects = data.projects || [];
  const boards = data.boards || [];
  const sprints = data.sprints || [];
  const fields = data.custom_fields || data.fields || [];
  const errors = data.errors || [];
  els.envProjectCount.textContent = formatNumber(projects.length);
  els.envBoardCount.textContent = formatNumber(boards.length);
  els.envSprintCount.textContent = formatNumber(sprints.length);
  els.envFieldCount.textContent = formatNumber(fields.length);
  els.envCacheAge.textContent = `${formatAge(data.cache_age_seconds)}${data.refreshed_at ? ` | ${formatDateTime(data.refreshed_at)}` : ""}`;

  els.envProjects.innerHTML = projects.length ? projects.slice(0, 12).map((project) => `
    <div class="mini-item">
      <strong>${escapeHtml(project.key || project.name)}</strong>
      <span>${escapeHtml(project.name || "")}</span>
    </div>
  `).join("") : '<div class="empty">No projects discovered.</div>';

  els.envBoards.innerHTML = boards.length || sprints.length ? [
    ...boards.slice(0, 8).map((board) => {
      const boardSprints = sprints.filter((sprint) => sprint.board_name === board.name).slice(0, 4);
      return `
        <div class="mini-item">
          <strong>${escapeHtml(board.name)}</strong>
          <span>${escapeHtml(board.project_key || "")} ${escapeHtml(board.type || "")}</span>
          <span class="list-meta">${escapeHtml(boardSprints.map((sprint) => `${sprint.name} (${sprint.state})`).join(" | ") || "No active/future sprint data")}</span>
        </div>
      `;
    }),
    ...(!boards.length ? sprints.slice(0, 8).map((sprint) => `
      <div class="mini-item">
        <strong>${escapeHtml(sprint.name)}</strong>
        <span>${escapeHtml(sprint.state)} | ${escapeHtml(sprint.board_name || "")}</span>
      </div>
    `) : []),
  ].join("") : '<div class="empty">No boards or sprints discovered.</div>';

  const valueRows = [
    ["Target Quarter", data.target_quarter_values || []],
    ["Architectural Domain", data.architectural_domain_values || []],
    ...Object.entries(data.select_field_values || {}).slice(0, 6),
  ].filter(([, values]) => values?.length);
  els.envValues.innerHTML = valueRows.length ? valueRows.map(([name, values]) => `
    <div class="mini-item">
      <strong>${escapeHtml(name)}</strong>
      <span>${escapeHtml(values.slice(0, 10).join(", "))}</span>
      ${values.length > 10 ? `<span class="list-meta">+${values.length - 10} more</span>` : ""}
    </div>
  `).join("") : '<div class="empty">No select values discovered.</div>';

  els.envFields.innerHTML = fields.length ? fields.slice(0, 16).map((field) => `
    <div class="mini-item">
      <strong>${escapeHtml(field.name)}</strong>
      <span>${escapeHtml(field.type || "custom field")}</span>
    </div>
  `).join("") : '<div class="empty">No custom fields discovered.</div>';

  els.envErrors.innerHTML = errors.length ? errors.map((error) => `
    <div class="mini-item blocked">
      <strong>${escapeHtml(error.area || "Discovery")}</strong>
      <span>${escapeHtml(error.error)}</span>
    </div>
  `).join("") : '<div class="empty">No discovery errors.</div>';
}

async function loadEnvironment({refresh = false} = {}) {
  if (!els.envRefresh || !state.instance) return;
  try {
    els.envRefresh.disabled = true;
    els.envCacheAge.textContent = refresh ? "Refreshing" : "Loading";
    const data = refresh
      ? await api("/api/environment/refresh", {method: "POST", body: JSON.stringify({instance: state.instance})})
      : await api(`/api/environment?${new URLSearchParams({instance: state.instance})}`);
    renderEnvironment(data);
  } catch (error) {
    els.envCacheAge.textContent = "Unavailable";
    toast(error.message);
  } finally {
    els.envRefresh.disabled = false;
  }
}

function repositorySearchText(repo) {
  return [
    repo.name,
    repo.relative_path,
    repo.codeowners,
    ...(repo.languages || []),
    ...(repo.packages || []).map((pkg) => `${pkg.package || pkg.name} ${pkg.version || ""} ${pkg.ecosystem || ""}`),
    ...(repo.container_images || []).map((image) => `${image.image || ""} ${image.package || ""} ${image.version || ""}`),
  ].join(" ").toLowerCase();
}

function renderRepositories(data = {}) {
  const repos = data.repositories || state.repositories || [];
  state.repositories = repos;
  const filter = (els.repoFilter?.value || "").trim().toLowerCase();
  const visible = filter ? repos.filter((repo) => repositorySearchText(repo).includes(filter)) : repos;
  const packageCount = data.package_count ?? repos.reduce((total, repo) => total + (repo.packages || []).length, 0);
  const imageCount = data.container_image_count ?? repos.reduce((total, repo) => total + (repo.container_images || []).length, 0);
  els.repoCount.textContent = formatNumber(repos.length);
  els.packageCount.textContent = formatNumber(packageCount);
  els.imageCount.textContent = formatNumber(imageCount);
  els.repoConfigured.textContent = data.configured === false ? "No" : "Yes";
  els.repoStatus.textContent = data.root ? data.root : data.error || `${visible.length} shown`;
  if (!visible.length) {
    els.repoList.innerHTML = `<div class="empty">${escapeHtml(data.error || "No repositories found.")}</div>`;
    return;
  }
  els.repoList.innerHTML = visible.map((repo) => {
    const packages = (repo.packages || []).slice(0, 5).map((pkg) => `${pkg.package || pkg.name}${pkg.version ? `@${pkg.version}` : ""}`);
    const images = (repo.container_images || []).slice(0, 3).map((image) => image.image || image.package).filter(Boolean);
    return `
      <div class="mini-item">
        <strong>${escapeHtml(repo.name)}</strong>
        <span>${escapeHtml((repo.languages || []).join(", ") || "Language not detected")} | ${escapeHtml(repo.relative_path || "")}</span>
        <span class="list-meta">${escapeHtml(repo.codeowners || "No CODEOWNERS")} | ${escapeHtml(packages.join(", ") || "No package manifests")}</span>
        ${images.length ? `<span class="list-meta">Images: ${escapeHtml(images.join(", "))}</span>` : ""}
      </div>
    `;
  }).join("");
}

async function loadRepositories() {
  if (!els.repoRefresh) return;
  try {
    els.repoRefresh.disabled = true;
    els.repoStatus.textContent = "Scanning";
    const data = await api("/api/repositories");
    renderRepositories(data);
  } catch (error) {
    els.repoStatus.textContent = "Unavailable";
    toast(error.message);
  } finally {
    els.repoRefresh.disabled = false;
  }
}

function renderSecurity(data) {
  state.security = data;
  const actions = data.remediation_actions || [];
  const inventory = data.repository_inventory || [];
  els.securityTicketCount.textContent = formatNumber(data.matched_tickets || 0);
  els.securityActionCount.textContent = formatNumber(actions.length);
  els.securityRepoCount.textContent = formatNumber(inventory.length);
  els.securityMode.textContent = els.mode.textContent || "recommend_only";
  els.securityStatus.textContent = data.repo_scan_available ? "Repository scan included" : "Repository scan unavailable";
  if (!actions.length) {
    els.securityActions.innerHTML = '<div class="empty">No remediation actions detected.</div>';
    return;
  }
  els.securityActions.innerHTML = actions.map((action) => `
    <div class="mini-item ${action.unknown_repositories?.length ? "blocked" : ""}">
      <strong>${escapeHtml(action.component)}${action.required_version ? ` >= ${escapeHtml(action.required_version)}` : ""}</strong>
      <span>${escapeHtml(action.action_type)} | ${escapeHtml(formatNumber(action.confidence * 100))}% confidence</span>
      <span class="list-meta">Issues: ${escapeHtml((action.affected_jira_issues || []).join(", "))}</span>
      <span class="list-meta">Upgrade: ${escapeHtml((action.repositories_requiring_upgrade || []).join(", ") || "None detected")} | Already fixed: ${escapeHtml((action.already_fixed_repositories || []).join(", ") || "None detected")}</span>
    </div>
  `).join("");
}

async function loadSecurity() {
  if (!els.securityRefresh || !state.instance) return;
  try {
    els.securityRefresh.disabled = true;
    els.securityStatus.textContent = "Analyzing";
    const params = new URLSearchParams({instance: state.instance, limit: "2000"});
    const data = await api(`/api/security/remediation?${params}`);
    renderSecurity(data);
  } catch (error) {
    els.securityStatus.textContent = "Unavailable";
    toast(error.message);
  } finally {
    els.securityRefresh.disabled = false;
  }
}

function hygienePayload() {
  return compactPayload({
    instance: state.instance,
    quarter: els.hygieneQuarter?.value.trim(),
    project: els.hygieneProject?.value.trim(),
    team: els.hygieneTeam?.value,
    pt: els.hygienePt?.value,
    saved_view: els.hygieneSavedView?.value.trim(),
    limit: Number(els.hygieneLimit?.value || 500),
  });
}

function setSelectOptions(select, options, {includeAll = false, allLabel = "All"} = {}) {
  if (!select) return;
  const current = select.value;
  const rows = includeAll ? [{value: "", label: allLabel}] : [];
  rows.push(...(options || []).map((value) => ({value, label: value})));
  select.innerHTML = rows.map((row) => `<option value="${escapeHtml(row.value)}">${escapeHtml(row.label)}</option>`).join("");
  if (rows.some((row) => row.value === current)) {
    select.value = current;
  } else if (rows.length) {
    select.value = rows[0].value;
  }
}

async function loadHygieneContext() {
  if (!els.hygieneQuarter || !state.instance) return;
  try {
    const params = new URLSearchParams({instance: state.instance});
    const context = await api(`/api/hygiene/context?${params}`);
    if (context.fiscal_quarter?.name) {
      els.hygieneQuarter.value = context.fiscal_quarter.name;
      els.hygieneQuarter.title = `${context.fiscal_quarter.start || ""} to ${context.fiscal_quarter.end || ""}`.trim();
    }
    setSelectOptions(els.hygieneTeam, context.team_options || ["Platform Excellence"]);
    setSelectOptions(els.hygienePt, context.pt_options || ["Muon", "Atlas", "Phoenix", "Dragon"], {includeAll: true, allLabel: "All PTs"});
  } catch (error) {
    toast(error.message);
  }
}

function printableValue(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return value ?? "";
}

function filteredHygieneFindings() {
  const findings = state.hygieneReview?.findings || [];
  const type = els.hygieneIssueType?.value || "";
  const category = els.hygieneCategory?.value || "";
  const fixability = els.hygieneFixability?.value || "";
  return findings.filter((finding) => {
    if (type && finding.issue_type !== type) return false;
    if (category && finding.category !== category) return false;
    if (fixability === "auto" && !finding.auto_fixable) return false;
    if (fixability === "manual" && finding.auto_fixable) return false;
    return true;
  });
}

function selectedHygieneFindings() {
  const selected = new Set(Array.from(document.querySelectorAll("[data-hygiene-finding]:checked")).map((input) => input.value));
  return (state.hygieneReview?.findings || []).filter((finding) => selected.has(finding.id));
}

function renderHygieneFindings() {
  const rows = filteredHygieneFindings();
  if (!rows.length) {
    els.hygieneFindings.innerHTML = '<tr><td colspan="11" class="empty">No findings match the current filters.</td></tr>';
    els.hygienePreviewSelected.disabled = true;
    return;
  }
  els.hygieneFindings.innerHTML = rows.map((finding) => {
    const path = (finding.ancestry_path || []).map((row) => row.issue_key).filter(Boolean).join(" > ");
    const selectedTeam = els.hygieneTeam?.value || finding.team;
    const teamPt = [finding.team || selectedTeam, finding.pt || finding.team_pt].filter(Boolean).join(" / ");
    return `
      <tr>
        <td><input type="checkbox" value="${escapeHtml(finding.id)}" data-hygiene-finding ${finding.auto_fixable ? "" : "disabled"}></td>
        <td class="key-cell">${escapeHtml(finding.issue_key)}</td>
        <td>${escapeHtml(finding.issue_type || "")}</td>
        <td>${escapeHtml(teamPt || finding.project || "")}</td>
        <td>${escapeHtml(finding.target_quarter || "")}</td>
        <td>${escapeHtml(finding.problem || "")}</td>
        <td>${escapeHtml(printableValue(finding.current_value))}</td>
        <td>${escapeHtml(printableValue(finding.expected_value))}</td>
        <td>${finding.auto_fixable ? "Yes" : "Manual"}</td>
        <td>${escapeHtml(path)}</td>
        <td>${escapeHtml(finding.recommended_action || "")}</td>
      </tr>
    `;
  }).join("");
  els.hygieneFindings.querySelectorAll("[data-hygiene-finding]").forEach((input) => {
    input.addEventListener("change", () => {
      els.hygienePreviewSelected.disabled = selectedHygieneFindings().length === 0;
    });
  });
  els.hygienePreviewSelected.disabled = true;
}

function renderHygiene(data) {
  state.hygieneReview = data;
  const total = Number(data.total_checked || 0);
  const valid = Number(data.initiative_ancestry_valid_count || 0);
  const coverage = total ? (valid / total) * 100 : 0;
  const dates = data.date_violations || {};
  const labels = data.label_violations || {};
  els.hygieneStatus.textContent = data.review_id ? `Review ${data.review_id}` : "Review complete";
  if (data.fiscal_quarter?.name && !els.hygieneQuarter.value) {
    els.hygieneQuarter.value = data.fiscal_quarter.name;
  }
  els.hygieneAncestry.textContent = formatPercent(coverage);
  els.hygieneDateCount.textContent = formatNumber(dates.total || 0);
  els.hygieneMissingLabels.textContent = formatNumber(labels.missing || 0);
  els.hygieneWrongLabels.textContent = formatNumber((labels.wrong_quarter || 0) + (labels.multiple || 0));
  els.hygieneSafeFixes.textContent = formatNumber(data.auto_fixable_count || 0);
  els.hygieneManual.textContent = formatNumber(data.manual_review_count || 0);
  els.hygienePreviewAll.disabled = !(data.proposed_changes || []).length;
  renderHygieneFindings();
}

async function loadHygiene() {
  if (!els.hygieneReview || !state.instance) return;
  try {
    els.hygieneReview.disabled = true;
    els.hygieneStatus.textContent = "Reviewing";
    const data = await api("/api/hygiene/review", {
      method: "POST",
      body: JSON.stringify(hygienePayload()),
    });
    renderHygiene(data);
  } catch (error) {
    els.hygieneStatus.textContent = "Unavailable";
    toast(error.message);
  } finally {
    els.hygieneReview.disabled = false;
  }
}

function renderHygienePreview(record) {
  state.hygienePreviewId = record.preview_id;
  state.currentPreviewId = record.preview_id;
  const preview = record.preview || {};
  els.hygienePreviewStatus.textContent = preview.can_apply ? "Ready for safe apply" : "Apply blocked by mode or preview state";
  els.hygienePreviewOutput.textContent = JSON.stringify(record, null, 2);
  els.hygieneReject.disabled = false;
  els.hygieneApply.disabled = !preview.can_apply;
}

async function previewHygieneFixes({selected = false} = {}) {
  const selectedFindings = selected ? selectedHygieneFindings() : [];
  if (selected && !selectedFindings.length) {
    toast("Select at least one auto-fixable finding");
    return;
  }
  const category = els.hygieneCategory?.value;
  const payload = selected
    ? {...hygienePayload(), findings: selectedFindings}
    : {...hygienePayload(), categories: category ? [category] : []};
  try {
    els.hygienePreviewAll.disabled = true;
    els.hygienePreviewSelected.disabled = true;
    const record = await api("/api/hygiene/preview", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderHygienePreview(record);
    await loadHistory();
  } catch (error) {
    toast(error.message);
  } finally {
    els.hygienePreviewAll.disabled = !(state.hygieneReview?.proposed_changes || []).length;
    els.hygienePreviewSelected.disabled = selectedHygieneFindings().length === 0;
  }
}

async function applyHygienePreview() {
  if (!state.hygienePreviewId) return;
  const confirmed = window.confirm("Apply the stored Portfolio Hygiene preview? Only safe date and label fixes will be attempted.");
  if (!confirmed) return;
  try {
    const result = await api("/api/hygiene/apply", {
      method: "POST",
      body: JSON.stringify({preview_id: state.hygienePreviewId}),
    });
    els.hygienePreviewOutput.textContent = JSON.stringify(result, null, 2);
    els.hygienePreviewStatus.textContent = result.applied ? "Apply succeeded" : result.reason || "Apply failed";
    els.hygieneApply.disabled = true;
    await loadHistory();
  } catch (error) {
    toast(error.message);
  }
}

async function rejectHygienePreview() {
  if (!state.hygienePreviewId) return;
  try {
    const record = await api(`/api/executions/${encodeURIComponent(state.hygienePreviewId)}/reject`, {method: "POST"});
    els.hygienePreviewOutput.textContent = JSON.stringify(record, null, 2);
    els.hygienePreviewStatus.textContent = "Preview rejected";
    state.hygienePreviewId = null;
    els.hygieneReject.disabled = true;
    els.hygieneApply.disabled = true;
    await loadHistory();
  } catch (error) {
    toast(error.message);
  }
}

function renderKeyValues(element, rows) {
  if (!rows?.length) {
    element.innerHTML = '<div class="empty">No data.</div>';
    return;
  }
  element.innerHTML = rows.map(([key, value]) => `
    <div class="mini-item">
      <strong>${escapeHtml(key)}</strong>
      <span>${escapeHtml(value)}</span>
    </div>
  `).join("");
}

function renderPlatform({configuration, connectors, audit, metrics, diagnostics}) {
  const connectorRows = connectors.connectors || configuration.connectors || [];
  const auditRows = audit.events || [];
  els.systemReadiness.textContent = diagnostics.status || "unknown";
  els.systemMode.textContent = configuration.mode || "unknown";
  els.systemConnectorsCount.textContent = formatNumber(connectorRows.length);
  els.systemAuditCount.textContent = formatNumber(audit.count ?? auditRows.length);
  els.systemDiagnosticsStatus.textContent = diagnostics.status || "loaded";
  els.systemDiagnostics.textContent = JSON.stringify(diagnostics, null, 2);

  renderKeyValues(els.systemConfig, [
    ["Product", configuration.product || "Pulse"],
    ["MCP", `${configuration.mcp?.host || "unknown"}:${configuration.mcp?.port || "unknown"}`],
    ["Authentication", configuration.mcp?.authentication_required ? "required" : "loopback/dev"],
    ["Repo Root", configuration.local_repo_root || "not configured"],
    ["Scheduler", configuration.scheduler?.environment_refresh?.mode || "manual"],
  ]);

  renderWorkflowList(els.systemConnectors, connectorRows, "No connectors.", (row) => `
    <div class="mini-item ${row.status === "needs_credentials" ? "blocked" : ""}">
      <strong>${escapeHtml(row.name)}</strong>
      <span>${escapeHtml(row.connector)} | ${escapeHtml(row.status)}</span>
      <span class="list-meta">${escapeHtml(row.type || "")}${row.base_url ? ` | ${escapeHtml(row.base_url)}` : ""}</span>
    </div>
  `);

  renderKeyValues(els.systemMetrics, [
    ["Uptime", `${formatNumber(metrics.uptime_seconds)}s`],
    ["Python", metrics.python_version || "unknown"],
    ["Cached Environments", formatNumber(metrics.cached_environments)],
    ["Saved Views", formatNumber(metrics.saved_views)],
    ["Execution Records", formatNumber(metrics.execution_records)],
  ]);

  renderWorkflowList(els.systemAudit, auditRows, "No audit events.", (row) => `
    <div class="mini-item">
      <strong>${escapeHtml(row.action)} | ${escapeHtml(row.outcome)}</strong>
      <span>${escapeHtml(row.target || "platform")}</span>
      <span class="list-meta">${escapeHtml(row.created_at)}</span>
    </div>
  `);
}

async function loadPlatform() {
  if (!els.systemRefresh) return;
  try {
    els.systemRefresh.disabled = true;
    els.systemDiagnosticsStatus.textContent = "Loading";
    const [configuration, connectors, audit, metrics, diagnostics] = await Promise.all([
      api("/api/platform/configuration"),
      api("/api/platform/connectors"),
      api("/api/platform/audit?limit=12"),
      api("/api/platform/metrics"),
      api("/api/platform/diagnostics"),
    ]);
    renderPlatform({configuration, connectors, audit, metrics, diagnostics});
  } catch (error) {
    els.systemDiagnosticsStatus.textContent = "Unavailable";
    toast(error.message);
  } finally {
    els.systemRefresh.disabled = false;
  }
}

function workflowPayload(kind) {
  const project = els.workflowProject.value.trim();
  const team = els.workflowTeam.value.trim();
  const savedView = els.workflowSavedView.value.trim();
  const quarter = els.workflowQuarter.value.trim();
  const sprintBits = sprintPayloadValue(els.workflowSprint.value, "sprint_id", "sprint_name");
  const nextBits = sprintPayloadValue(els.workflowNextSprint.value, "next_sprint_id", "next_sprint_name");
  const base = compactPayload({instance: state.instance, project, team});
  if (kind === "engineering-review") {
    return compactPayload({...base, saved_view: savedView, include_sections: ["sprint", "backlog", "portfolio", "security", "repositories", "saved_view"]});
  }
  if (kind === "sprint-analysis") {
    return compactPayload({...base, ...sprintBits, ...nextBits});
  }
  if (kind === "sprint-close-preview") {
    return compactPayload({...base, ...sprintBits, ...nextBits, rollover_all_incomplete: true});
  }
  if (kind === "sprint-close-apply") {
    return compactPayload({preview_id: els.workflowPreviewId.value.trim() || state.currentPreviewId});
  }
  if (kind === "portfolio-review") {
    return compactPayload({...base, quarter});
  }
  if (kind === "backlog-review") {
    return compactPayload({...base});
  }
  if (kind === "security-remediation-analysis") {
    return compactPayload({...base});
  }
  if (kind === "saved-view-review") {
    return compactPayload({view_name: savedView, instance: state.instance});
  }
  return base;
}

function collectWorkflowIssues(node, rows = []) {
  if (!node || rows.length >= 50) return rows;
  if (Array.isArray(node)) {
    node.forEach((item) => collectWorkflowIssues(item, rows));
    return rows;
  }
  if (typeof node !== "object") return rows;
  if (node.key && node.fields && !rows.some((row) => row.key === node.key)) {
    rows.push(node);
    return rows;
  }
  Object.entries(node).forEach(([key, value]) => {
    if (["issues", "paginated_issues", "sections", "instances", "sprint_health", "backlog", "portfolio", "security", "saved_view"].includes(key)) {
      collectWorkflowIssues(value, rows);
    } else if (typeof value === "object" && value && rows.length < 50) {
      collectWorkflowIssues(value, rows);
    }
  });
  return rows;
}

function renderWorkflowList(element, rows, emptyText, rowRenderer) {
  if (!rows?.length) {
    element.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  element.innerHTML = rows.map(rowRenderer).join("");
}

function renderWorkflowResult(data) {
  state.workflowResult = data;
  const confidence = data.confidence || {};
  els.workflowTitle.textContent = data.summary || data.workflow || "Workflow complete";
  els.workflowConfidence.textContent = `${escapeHtml(confidence.level || "unknown")} confidence${confidence.score != null ? ` | ${formatPercent(Number(confidence.score) * 100)}` : ""}`;
  els.workflowOutput.textContent = JSON.stringify(data, null, 2);

  const metrics = data.metrics || [];
  els.workflowMetrics.innerHTML = metrics.length ? metrics.slice(0, 6).map((metric) => `
    <article class="metric">
      <span>${escapeHtml(metric.name)}</span>
      <strong>${escapeHtml(metric.unit === "percent" ? formatPercent(metric.value) : formatNumber(metric.value))}</strong>
    </article>
  `).join("") : '<div class="empty">No metrics.</div>';

  renderWorkflowList(els.workflowRisks, data.risks || [], "No risks reported.", (risk) => `
    <div class="mini-item ${risk.severity === "high" ? "blocked" : ""}">
      <strong>${escapeHtml(risk.title)}</strong>
      <span>${escapeHtml(risk.description)}</span>
      <span class="list-meta">${escapeHtml(risk.severity || "medium")}</span>
    </div>
  `);
  renderWorkflowList(els.workflowRecommendations, data.recommendations || [], "No recommendations.", (recommendation) => `
    <div class="mini-item">
      <strong>${escapeHtml(recommendation.action)}</strong>
      <span>${escapeHtml(recommendation.rationale)}</span>
      <span class="list-meta">${escapeHtml(recommendation.priority || "medium")}</span>
    </div>
  `);
  renderWorkflowList(els.workflowCoverage, data.source_coverage || [], "No source coverage reported.", (source) => `
    <div class="mini-item ${source.status === "failed" ? "blocked" : ""}">
      <strong>${escapeHtml(source.source)}</strong>
      <span>${escapeHtml(source.status)}</span>
      <span class="list-meta">${escapeHtml(source.details || source.error || "")}</span>
    </div>
  `);

  const preview = data.execution_preview;
  if (preview?.preview_id) {
    state.currentPreviewId = preview.preview_id;
    els.workflowPreviewId.value = preview.preview_id;
    els.workflowPreview.innerHTML = `
      <div class="mini-item">
        <strong>${escapeHtml(preview.action)} | ${escapeHtml(preview.status)}</strong>
        <span>${escapeHtml(preview.preview_id)}</span>
        <span class="list-meta">${preview.can_apply ? "Apply enabled by mode and preview state" : "Apply blocked until safety gates pass"}</span>
      </div>
    `;
  } else {
    els.workflowPreview.innerHTML = '<div class="empty">No execution preview.</div>';
  }

  const issues = collectWorkflowIssues(data);
  if (!issues.length) {
    els.workflowIssues.innerHTML = '<tr><td colspan="4" class="empty">No drill-down issues.</td></tr>';
  } else {
    els.workflowIssues.innerHTML = issues.slice(0, 25).map((issue) => `
      <tr>
        <td class="key-cell">${escapeHtml(issue.key)}</td>
        <td>${escapeHtml(fieldValue(issue, "summary"))}</td>
        <td>${escapeHtml(fieldValue(issue, "status"))}</td>
        <td>${escapeHtml(fieldValue(issue, "assignee") || "Unassigned")}</td>
      </tr>
    `).join("");
  }
}

async function runWorkflow(kind) {
  const payload = workflowPayload(kind);
  if (kind === "saved-view-review" && !payload.view_name) {
    toast("Saved view name is required");
    return;
  }
  if (kind === "sprint-close-apply" && !payload.preview_id) {
    toast("Preview ID is required");
    return;
  }
  const button = Array.from(els.workflowButtons).find((item) => item.dataset.workflow === kind);
  try {
    if (button) button.disabled = true;
    els.workflowStatus.textContent = "Running";
    const data = await api(`/api/orchestration/${kind}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderWorkflowResult(data);
    els.workflowStatus.textContent = "Complete";
    if (kind.includes("sprint-close")) await loadHistory();
  } catch (error) {
    els.workflowStatus.textContent = "Failed";
    toast(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

function renderSprintHeader(data, selection = {}) {
  const sprint = data?.sprint || data?.current_sprint || null;
  const nextSprint = data?.next_sprint || null;
  els.sprintName.textContent = sprintLabel(sprint);
  els.nextSprintName.textContent = sprintLabel(nextSprint);
  els.sprintWindow.textContent = sprintWindow(sprint);
  els.nextSprintStrategy.textContent = strategyLabel(selection.next_strategy);
}

function renderSprint(data) {
  const analysis = data.analysis || {};
  const points = analysis.story_points || {};
  const load = analysis.projected_next_sprint_load || {};
  const capacity = analysis.next_sprint_capacity || {};
  const overcommit = analysis.overcommit || {};
  const completion = points.completion_percent ?? analysis.completion_percent ?? 0;
  const completedPoints = Number(points.completed || 0);
  const totalPoints = Number(points.total || 0);

  els.mode.textContent = data.mode || "recommend_only";
  renderSprintHeader(data, state.sprintDiscovery?.selection || {});
  els.completion.textContent = formatPercent(completion);
  els.sprintRing.style.setProperty("--progress", `${percentWidth(completion)}%`);
  els.ringPercent.textContent = formatPercent(completion);
  els.ringPoints.textContent = `${formatNumber(completedPoints)} / ${formatNumber(totalPoints)} pts`;
  els.completedPoints.textContent = formatNumber(completedPoints);
  els.remainingPoints.textContent = formatNumber(points.remaining ?? 0);
  els.projectedLoad.textContent = `${formatNumber(load.projected_story_points ?? 0)} pts`;
  if (capacity.story_points != null) {
    els.capacity.textContent = `${formatNumber(capacity.story_points)} pts`;
  } else if (capacity.issue_count != null) {
    els.capacity.textContent = `${formatNumber(capacity.issue_count)} issues`;
  } else {
    els.capacity.textContent = "Unknown";
  }
  els.overcommit.textContent = overcommit.overcommit_percentage == null ? "Unknown" : formatPercent(overcommit.overcommit_percentage);
  els.overcommitCard.classList.toggle("active", Boolean(overcommit.overcommitted));
  renderBarList(els.teamProgress, analysis.progress_by_team);
  renderEngineerWorkload(els.engineerProgress, analysis.progress_by_engineer);
  renderMiniList(els.blockedWork, analysis.blocked_work, true);
  renderMiniList(els.rollover, analysis.rollover_candidates);
  renderSplitProposals(analysis.issue_split_proposals);
}

async function loadSprintDiscovery() {
  if (!state.instance) return;
  els.sprintStatus.textContent = "Finding sprint";
  els.sprintName.textContent = "Detecting active sprint";
  els.nextSprintName.textContent = "Detecting next sprint";
  els.sprintWindow.textContent = "No sprint loaded";
  els.nextSprintStrategy.textContent = "Waiting for Jira";
  try {
    const params = new URLSearchParams({instance: state.instance});
    const data = await api(`/api/sprint/discovery?${params}`);
    state.sprintDiscovery = data;
    renderSprintHeader(data, data.selection || {});
    const current = data.current_sprint;
    const next = data.next_sprint;
    if (!current?.id) {
      els.sprintStatus.textContent = "No active sprint";
      return;
    }
    els.sprintId.value = current.id;
    els.nextSprintId.value = next?.id || "";
    els.sprintStatus.textContent = next?.id ? "Auto-loaded" : "Active loaded";
    await loadSprint({auto: true});
  } catch (error) {
    state.sprintDiscovery = null;
    els.sprintStatus.textContent = "Manual selection";
    toast(error.message);
  }
}

async function loadSprint({auto = false} = {}) {
  const sprintId = Number(els.sprintId.value);
  const nextSprintId = Number(els.nextSprintId.value);
  if (!sprintId) {
    if (!auto) toast("Sprint ID is required");
    return;
  }
  try {
    els.loadSprint.disabled = true;
    if (!auto) els.sprintStatus.textContent = "Loading";
    const params = new URLSearchParams({instance: state.instance, sprint_id: String(sprintId)});
    if (nextSprintId) params.set("next_sprint_id", String(nextSprintId));
    renderSprint(await api(`/api/sprint/analysis?${params}`));
    els.sprintStatus.textContent = auto ? "Auto-loaded" : "Loaded";
  } catch (error) {
    els.sprintStatus.textContent = auto ? "Manual selection" : "Load failed";
    toast(error.message);
  } finally {
    els.loadSprint.disabled = false;
  }
}

function renderPreview(record) {
  state.recoveryId = null;
  els.resumePreview.disabled = true;
  els.reconcilePreview.disabled = record.status !== "recovery_required";
  state.currentPreviewId = record.preview_id;
  const preview = record.preview || {};
  els.mode.textContent = preview.mode || els.mode.textContent;
  els.previewStatus.textContent = record.status === "previewed"
    ? (preview.can_apply ? "Ready for approval" : "Apply blocked")
    : record.status.replaceAll("_", " ");
  els.previewOutput.textContent = JSON.stringify(record, null, 2);
  els.rejectPreview.disabled = !["previewed", "failed"].includes(record.status);
  els.applyPreview.disabled = record.status !== "previewed" || !preview.can_apply;
}

async function previewCloseSprint() {
  const sprintId = Number(els.sprintId.value);
  const nextSprintId = Number(els.nextSprintId.value);
  if (!sprintId || !nextSprintId) {
    toast("Sprint and next sprint IDs are required");
    return;
  }
  try {
    els.previewClose.disabled = true;
    const record = await api("/api/executions/preview", {
      method: "POST",
      body: JSON.stringify({
        action: "close_sprint",
        parameters: {
          instance: state.instance,
          sprint_id: sprintId,
          next_sprint_id: nextSprintId,
          rollover_all_incomplete: els.rolloverAll.checked,
        },
      }),
    });
    renderPreview(record);
    await loadHistory();
  } catch (error) {
    toast(error.message);
  } finally {
    els.previewClose.disabled = false;
  }
}

async function reconcilePreview() {
  if (!state.currentPreviewId) return;
  state.recoveryId = null;
  els.resumePreview.disabled = true;
  try {
    const review = await api(`/api/executions/${encodeURIComponent(state.currentPreviewId)}/reconcile`, {method: "POST"});
    els.previewOutput.textContent = JSON.stringify(review, null, 2);
    els.previewStatus.textContent = review.can_resume ? "Review recovery observations before resuming" : "Recovery blocked: unresolved outcomes";
    if (review.can_resume) {
      state.recoveryId = review.recovery_id;
      els.resumePreview.disabled = false;
    }
  } catch (error) { toast(error.message); }
}

async function resumePreview() {
  if (!state.currentPreviewId || !state.recoveryId) return;
  try {
    els.resumePreview.disabled = true;
    const record = await api(`/api/executions/${encodeURIComponent(state.currentPreviewId)}/resume`, {
      method: "POST", body: JSON.stringify({recovery_id: state.recoveryId}),
    });
    renderPreview(record);
    await loadHistory();
  } catch (error) { state.recoveryId = null; toast(error.message); }
}

async function applyPreview() {
  if (!state.currentPreviewId) return;
  try {
    const record = await api(`/api/executions/${encodeURIComponent(state.currentPreviewId)}/apply`, {method: "POST"});
    renderPreview(record);
    toast(record.status === "succeeded" ? "Execution succeeded" : record.error || "Execution failed");
    await loadHistory();
  } catch (error) {
    toast(error.message);
    await loadHistory();
  }
}

async function rejectPreview() {
  if (!state.currentPreviewId) return;
  try {
    const record = await api(`/api/executions/${encodeURIComponent(state.currentPreviewId)}/reject`, {method: "POST"});
    state.currentPreviewId = null;
    els.previewStatus.textContent = "Preview rejected";
    els.previewOutput.textContent = JSON.stringify(record, null, 2);
    els.rejectPreview.disabled = true;
    els.applyPreview.disabled = true;
    await loadHistory();
  } catch (error) {
    toast(error.message);
  }
}

async function loadHistory() {
  try {
    const data = await api("/api/executions?limit=12");
    const rows = data.executions || [];
    if (!rows.length) {
      els.history.innerHTML = '<div class="empty">No execution history.</div>';
      if (els.hygieneHistory) els.hygieneHistory.innerHTML = '<div class="empty">No hygiene execution history.</div>';
      return;
    }
    els.history.innerHTML = rows.map((row) => `
      <div class="history-item">
        <button type="button" data-execution-id="${escapeHtml(row.preview_id)}">${escapeHtml(row.action)} | ${escapeHtml(row.status)}</button>
        <span class="history-meta">${escapeHtml(row.instance)} | ${escapeHtml(row.preview_id)} | ${escapeHtml(row.updated_at)}</span>
      </div>
    `).join("");
    els.history.querySelectorAll("[data-execution-id]").forEach((button) => {
      button.addEventListener("click", () => {
        renderPreview(rows.find((row) => row.preview_id === button.dataset.executionId));
      });
    });
    if (els.hygieneHistory) {
      const hygieneRows = rows.filter((row) => row.action === "portfolio_hygiene_fix");
      els.hygieneHistory.innerHTML = hygieneRows.length ? hygieneRows.map((row) => `
        <div class="history-item">
          <strong>${escapeHtml(row.status)}</strong>
          <span class="history-meta">${escapeHtml(row.instance)} | ${escapeHtml(row.preview_id)}</span>
          <span class="history-meta">${escapeHtml(row.updated_at)}</span>
        </div>
      `).join("") : '<div class="empty">No hygiene execution history.</div>';
    }
  } catch (error) {
    els.history.innerHTML = '<div class="empty">History unavailable.</div>';
    if (els.hygieneHistory) els.hygieneHistory.innerHTML = '<div class="empty">History unavailable.</div>';
  }
}

async function saveView() {
  const jql = els.jql.value.trim();
  if (!jql) {
    toast("JQL is required");
    return;
  }
  const name = window.prompt("View name", jql.slice(0, 42));
  if (!name) return;
  try {
    els.saveView.disabled = true;
    await api("/api/views", {
      method: "POST",
      body: JSON.stringify({name, instance: state.instance, jql, dashboard_type: "issue_list"}),
    });
    await loadViews();
    toast("Saved view updated");
  } catch (error) {
    toast(error.message);
  } finally {
    els.saveView.disabled = false;
  }
}

function restoreTaskNotes() {
  if (!els.taskNotes) return;
  els.taskNotes.value = localStorage.getItem(TASK_NOTES_KEY) || "";
  els.taskNotes.addEventListener("input", () => {
    localStorage.setItem(TASK_NOTES_KEY, els.taskNotes.value);
  });
}

function bindEvents() {
  sprintOps.bind({api, toast, getInstances: () => state.instances, refreshHistory: loadHistory, onMode: (mode) => { els.mode.textContent = mode; }});
  els.consoleConnect.addEventListener("click", async () => {
    // Keep credentials in memory only; do not persist them in browser storage.
    state.authToken = els.consoleToken.value.trim();
    els.consoleToken.value = "";
    await loadInstances();
    await loadViews();
    await loadHistory();
    await loadPlatform();
  });
  els.sidebarToggle.addEventListener("click", () => setSidebarCollapsed(!state.sidebarCollapsed));
  els.themeToggle.addEventListener("change", () => setTheme(els.themeToggle.checked ? "dark" : "light"));
  els.navItems.forEach((item) => {
    item.addEventListener("click", () => setActiveView(item.dataset.viewTarget));
  });
  els.instance.addEventListener("change", async () => {
    state.instance = els.instance.value;
    state.page = 1;
    if (!state.jqlTouched) {
      els.jql.value = defaultJqlForInstance(state.instance);
    }
    await loadSprintDiscovery();
    if (state.activeView === "environment-view") await loadEnvironment();
    if (state.activeView === "security-view") await loadSecurity();
    if (state.activeView === "hygiene-view") {
      await loadHygieneContext();
      await loadHygiene();
    }
  });
  els.jql.addEventListener("input", () => {
    state.jqlTouched = true;
  });
  els.search.addEventListener("click", () => {
    state.page = 1;
    searchIssues();
  });
  els.prev.addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      searchIssues();
    }
  });
  els.next.addEventListener("click", () => {
    state.page += 1;
    searchIssues();
  });
  els.saveView.addEventListener("click", saveView);
  els.loadSprint.addEventListener("click", () => loadSprint());
  els.previewClose.addEventListener("click", previewCloseSprint);
  els.applyPreview.addEventListener("click", applyPreview);
  els.rejectPreview.addEventListener("click", rejectPreview);
  els.reconcilePreview.addEventListener("click", reconcilePreview);
  els.resumePreview.addEventListener("click", resumePreview);
  els.workflowButtons.forEach((button) => {
    button.addEventListener("click", () => runWorkflow(button.dataset.workflow));
  });
  els.jumpButtons.forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.jumpView));
  });
  els.envRefresh.addEventListener("click", () => loadEnvironment({refresh: true}));
  els.opsViewsRefresh.addEventListener("click", loadViews);
  els.repoRefresh.addEventListener("click", loadRepositories);
  els.repoFilter.addEventListener("input", () => renderRepositories());
  els.securityRefresh.addEventListener("click", loadSecurity);
  els.hygieneReview.addEventListener("click", loadHygiene);
  els.hygienePreviewAll.addEventListener("click", () => previewHygieneFixes({selected: false}));
  els.hygienePreviewSelected.addEventListener("click", () => previewHygieneFixes({selected: true}));
  els.hygieneApply.addEventListener("click", applyHygienePreview);
  els.hygieneReject.addEventListener("click", rejectHygienePreview);
  [els.hygieneIssueType, els.hygieneCategory, els.hygieneFixability].forEach((control) => {
    control.addEventListener("change", renderHygieneFindings);
  });
  els.systemRefresh.addEventListener("click", loadPlatform);
}

async function init() {
  initTheme();
  initSidebar();
  bindEvents();
  restoreTaskNotes();
  await loadViews();
  setActiveView(state.activeView);
  await loadInstances();
  await loadHistory();
}

init();
