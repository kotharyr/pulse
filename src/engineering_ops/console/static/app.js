const state = {
  instance: "cloud",
  page: 1,
  pageSize: 25,
  currentPreviewId: null,
  savedViews: [],
};

const els = {
  mode: document.getElementById("mode-pill"),
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
  rejectPreview: document.getElementById("reject-preview"),
  applyPreview: document.getElementById("apply-preview"),
  history: document.getElementById("execution-history"),
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

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request failed with ${response.status}`);
  }
  return data;
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

function loadViews() {
  try {
    state.savedViews = JSON.parse(localStorage.getItem("engineeringOpsConsole.views.v1") || "[]");
  } catch {
    state.savedViews = [];
  }
}

function persistViews() {
  localStorage.setItem("engineeringOpsConsole.views.v1", JSON.stringify(state.savedViews));
}

function renderSavedViews() {
  if (!state.savedViews.length) {
    els.savedViews.innerHTML = "";
    return;
  }
  els.savedViews.innerHTML = state.savedViews.map((view, index) => (
    `<button class="saved-view" type="button" data-view="${index}">${escapeHtml(view.name)}</button>`
  )).join("");
  els.savedViews.querySelectorAll("button[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const view = state.savedViews[Number(button.dataset.view)];
      state.instance = view.instance;
      els.instance.value = view.instance;
      els.jql.value = view.jql;
      state.page = 1;
      searchIssues();
    });
  });
}

async function loadInstances() {
  try {
    const data = await api("/api/instances");
    if (!data.instances?.length) return;
    els.instance.innerHTML = data.instances.map((row) => {
      const label = row.kind === "cloud" ? "Cloud" : row.kind === "datacenter" || row.kind === "server" ? "On-Prem" : row.name;
      return `<option value="${escapeHtml(row.name)}">${escapeHtml(label)} (${escapeHtml(row.name)})</option>`;
    }).join("");
    state.instance = data.instances[0].name;
    els.instance.value = state.instance;
  } catch (error) {
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

function percentWidth(value) {
  const numeric = Number(value || 0);
  return Math.max(0, Math.min(100, numeric));
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
          <strong>${escapeHtml(row.name)}</strong>
          <div class="bar-track"><div class="bar-fill" style="width: ${percentWidth(percent)}%"></div></div>
        </div>
        <div class="bar-meta">${escapeHtml(percent)}% | ${escapeHtml(row.done_story_points)}/${escapeHtml(row.story_points)} pts</div>
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
      <span class="list-meta">${escapeHtml(row.assignee)} | ${escapeHtml(row.status)} | ${escapeHtml(row.story_points)} pts</span>
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
      <span class="list-meta">${escapeHtml(row.story_points)} pts | ${escapeHtml(row.reason)}</span>
    </div>
  `).join("");
}

function renderSprint(data) {
  const analysis = data.analysis || {};
  const points = analysis.story_points || {};
  const load = analysis.projected_next_sprint_load || {};
  const capacity = analysis.next_sprint_capacity || {};
  const overcommit = analysis.overcommit || {};
  els.mode.textContent = data.mode || "recommend_only";
  els.completion.textContent = `${analysis.completion_percent ?? 0}%`;
  els.completedPoints.textContent = points.completed ?? 0;
  els.remainingPoints.textContent = points.remaining ?? 0;
  els.projectedLoad.textContent = load.projected_story_points ?? 0;
  els.capacity.textContent = capacity.story_points ?? capacity.issue_count ?? "Unknown";
  els.overcommit.textContent = `${overcommit.overcommit_percentage ?? 0}%`;
  els.overcommitCard.classList.toggle("active", Boolean(overcommit.overcommitted));
  renderBarList(els.teamProgress, analysis.progress_by_team);
  renderBarList(els.engineerProgress, analysis.progress_by_engineer);
  renderMiniList(els.blockedWork, analysis.blocked_work, true);
  renderMiniList(els.rollover, analysis.rollover_candidates);
  renderSplitProposals(analysis.issue_split_proposals);
}

async function loadSprint() {
  const sprintId = Number(els.sprintId.value);
  const nextSprintId = Number(els.nextSprintId.value);
  if (!sprintId) {
    toast("Sprint ID is required");
    return;
  }
  try {
    els.loadSprint.disabled = true;
    const params = new URLSearchParams({instance: state.instance, sprint_id: String(sprintId)});
    if (nextSprintId) params.set("next_sprint_id", String(nextSprintId));
    renderSprint(await api(`/api/sprint/analysis?${params}`));
  } catch (error) {
    toast(error.message);
  } finally {
    els.loadSprint.disabled = false;
  }
}

function renderPreview(record) {
  state.currentPreviewId = record.preview_id;
  const preview = record.preview || {};
  els.mode.textContent = preview.mode || els.mode.textContent;
  els.previewStatus.textContent = preview.can_apply ? "Ready for approval" : "Apply blocked";
  els.previewOutput.textContent = JSON.stringify(record, null, 2);
  els.rejectPreview.disabled = false;
  els.applyPreview.disabled = !preview.can_apply;
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

async function applyPreview() {
  if (!state.currentPreviewId) return;
  try {
    const record = await api(`/api/executions/${encodeURIComponent(state.currentPreviewId)}/apply`, {method: "POST"});
    renderPreview(record);
    toast(record.status === "succeeded" ? "Execution succeeded" : record.error || "Execution failed");
    await loadHistory();
  } catch (error) {
    toast(error.message);
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
      return;
    }
    els.history.innerHTML = rows.map((row) => `
      <div class="history-item">
        <strong>${escapeHtml(row.action)} | ${escapeHtml(row.status)}</strong>
        <span class="history-meta">${escapeHtml(row.instance)} | ${escapeHtml(row.preview_id)} | ${escapeHtml(row.updated_at)}</span>
      </div>
    `).join("");
  } catch (error) {
    els.history.innerHTML = '<div class="empty">History unavailable.</div>';
  }
}

function saveView() {
  const jql = els.jql.value.trim();
  if (!jql) {
    toast("JQL is required");
    return;
  }
  const name = window.prompt("View name", jql.slice(0, 42));
  if (!name) return;
  state.savedViews = [
    {name, instance: state.instance, jql},
    ...state.savedViews.filter((view) => view.name !== name),
  ].slice(0, 10);
  persistViews();
  renderSavedViews();
}

els.instance.addEventListener("change", () => {
  state.instance = els.instance.value;
  state.page = 1;
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
els.loadSprint.addEventListener("click", loadSprint);
els.previewClose.addEventListener("click", previewCloseSprint);
els.applyPreview.addEventListener("click", applyPreview);
els.rejectPreview.addEventListener("click", rejectPreview);

loadViews();
renderSavedViews();
loadInstances();
loadHistory();
