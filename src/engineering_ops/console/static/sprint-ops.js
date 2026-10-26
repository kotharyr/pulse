/* Cloud sprint accounting. Approval state is invalidated whenever inputs change. */
const sprintOps = (() => {
  let deps;
  let record = null;
  let recoveryId = null;
  let mappings = {};
  let contextGeneration = 0;
  let previewGeneration = 0;
  let busy = false;
  let uncertain = false;
  let canResume = false;
  const el = (id) => document.getElementById(`ops-${id}`);
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
  const storageKey = () => `pulse.sprintOpsMappings.v1:${el('source').value}:${el('target').value}:${el('project').value.trim().toUpperCase()}`;

  function invalidate() {
    record = null;
    recoveryId = null;
    uncertain = false;
    canResume = false;
    previewGeneration += 1;
    el('approve').checked = false;
    el('apply').disabled = true;
    el('reconcile').disabled = true;
    el('resume').disabled = true;
    el('status').textContent = 'Inputs changed. Refresh the preview before applying.';
  }

  function loadMappings() {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey()) || '{}');
      mappings = saved && typeof saved === 'object' && !Array.isArray(saved)
        ? Object.fromEntries(Object.entries(saved).filter(([, value]) => typeof value === 'string' && value.trim())) : {};
    }
    catch (_) { mappings = {}; }
  }

  function saveMappings() {
    try { localStorage.setItem(storageKey(), JSON.stringify(mappings)); }
    catch (_) { deps.toast('Username override could not be saved; keep this page open.'); }
  }

  function storyLinks(stories) {
    if (!stories?.length) return '<p>None.</p>';
    return '<ul>' + stories.map((story) => {
      let url;
      try { url = new URL(story.url); } catch (_) { return `<li>${escape(story.key)} — ${escape(story.summary)}</li>`; }
      if (!['https:', 'http:'].includes(url.protocol)) return `<li>${escape(story.key)}</li>`;
      return `<li><a href="${escape(url.href)}" target="_blank" rel="noopener noreferrer">${escape(story.key)}</a> — ${escape(story.summary)} (${escape(story.assignee)})</li>`;
    }).join('') + '</ul>';
  }

  function updateApproval() {
    el('apply').disabled = busy || !record?.preview?.can_apply || record.status !== 'previewed' || !el('approve').checked;
    el('reconcile').disabled = busy || !uncertain;
    el('resume').disabled = busy || !canResume || !el('approve').checked;
  }

  function lockInputs(locked) {
    ['source', 'target', 'board', 'sprint', 'project', 'type', 'extra', 'preview', 'refresh', 'approve'].forEach((id) => { el(id).disabled = locked; });
    el('users').querySelectorAll('input').forEach((input) => { input.disabled = locked; });
  }

  function render(next) {
    record = next;
    const plan = next.preview;
    deps.onMode?.(plan.mode);
    el('approve').checked = false;
    el('users').innerHTML = plan.users.length ? plan.users.map((row, index) => `<tr>
      <td>${escape(row.assignee)}</td>
      <td><input data-ops-user="${index}" aria-label="Optional GPK2 username override for ${escape(row.assignee)}" value="${escape(mappings[row.cloud_account] || row.username || '')}"><p>${row.match_source === 'email' ? 'Automatic email match' : 'Username override'}</p></td>
      <td>${escape(row.action)}${row.issue_key ? ` (${escape(row.issue_key)})` : ''}</td>
      <td>${escape(row.added_points)}</td><td>${escape(row.total_points ?? 'Needs reconciliation')}</td>
      <td>${(row.errors || []).map((error) => `<p>${escape(error)}</p>`).join('')}
      <p>Already included: ${escape((row.already_included || []).join(', ') || 'None')}</p>
      ${storyLinks(row.new_stories)}
      ${row.description ? `<details><summary>Planned description</summary><pre>${escape(row.description)}</pre></details>` : ''}</td>
    </tr>`).join('') : '<tr><td colspan="6">No assigned Cloud work in this sprint.</td></tr>';
    el('users').querySelectorAll('[data-ops-user]').forEach((input) => input.addEventListener('input', () => {
      const row = plan.users[Number(input.dataset.opsUser)];
      if (input.value.trim()) mappings[row.cloud_account] = input.value.trim();
      else delete mappings[row.cloud_account];
      saveMappings();
      invalidate();
    }));
    el('missing').innerHTML = storyLinks(plan.missing_points);
    el('unassigned').innerHTML = storyLinks(plan.unassigned);
    el('status').textContent = `${plan.sprint.name}: ${plan.action_count} eligible change(s), ${plan.missing_points.length} without points. ${plan.mode === 'recommend_only' ? 'Read-only mode.' : 'Review before applying.'}`;
    updateApproval();
  }

  async function loadContext(keepBoard = false) {
    const generation = ++contextGeneration;
    invalidate();
    el('sprint').innerHTML = '';
    try {
      const query = new URLSearchParams({source_instance: el('source').value});
      if (keepBoard && el('board').value) query.set('board_id', el('board').value);
      const data = await deps.api(`/api/sprint-placeholders/context?${query}`);
      if (generation !== contextGeneration) return;
      el('board').innerHTML = '<option value="">Choose a board</option>' + data.boards.map((board) => `<option value="${escape(board.id)}">${escape(board.name)}</option>`).join('');
      if (data.board_id) el('board').value = String(data.board_id);
      el('sprint').innerHTML = data.sprints.map((sprint) => `<option value="${escape(sprint.id)}">${escape(sprint.name)} (${escape(sprint.state)})</option>`).join('');
      el('status').textContent = data.sprints.length ? 'Choose a destination and preview the sprint work.' : 'Choose a Cloud board to load its sprints.';
    } catch (error) {
      if (generation === contextGeneration) { el('status').textContent = error.message; deps.toast(error.message); }
    }
  }

  async function preview() {
    invalidate();
    const generation = previewGeneration;
    try {
      if (!el('source').value || !el('target').value || !el('sprint').value || !el('project').value.trim()) throw new Error('Choose a Cloud sprint and GPK2 connection/project.');
      const parameters = {
        source_instance: el('source').value, instance: el('target').value,
        sprint_id: Number(el('sprint').value), project: el('project').value.trim(),
        issue_type: el('type').value.trim() || 'Story', user_mappings: {...mappings},
        additional_fields: JSON.parse(el('extra').value || '{}'),
      };
      el('preview').disabled = true;
      el('status').textContent = 'Reading Cloud sprint and existing GPK2 descriptions…';
      const next = await deps.api('/api/executions/preview', {method: 'POST', body: JSON.stringify({action: 'sprint_placeholders', parameters})});
      if (generation === previewGeneration) render(next);
    } catch (error) { el('status').textContent = error.message; deps.toast(error.message); }
    finally { el('preview').disabled = false; }
  }

  async function execute(kind) {
    if (!record || busy) return;
    if (kind === 'apply' && (!record.preview.can_apply || !el('approve').checked)) return;
    if (kind === 'resume' && (!recoveryId || !el('approve').checked)) {
      deps.toast('Review recovery observations and tick the approval box before resuming.'); return;
    }
    const id = record.preview_id;
    busy = true;
    lockInputs(true);
    updateApproval();
    try {
      const next = await deps.api(`/api/executions/${encodeURIComponent(id)}/${kind}`, {
        method: 'POST', ...(kind === 'resume' ? {body: JSON.stringify({recovery_id: recoveryId})} : {}),
      });
      if (kind === 'reconcile') {
        recoveryId = next.recovery_id;
        canResume = next.can_resume;
        uncertain = true;
        el('approve').checked = false;
        const observations = next.observations.map((item) => {
          const user = record.preview.users.find((row) => row.marker === item.step_id)?.assignee || 'Placeholder';
          return `${user}: ${item.state}${item.value?.key ? ` (${item.value.key})` : ''}${item.reason ? ` — ${item.reason}` : ''}`;
        });
        el('status').textContent = (next.can_resume ? 'Recovery checked. Review these observations, tick approval, then resume. ' : 'Recovery is blocked; do not repeat the write. ') + observations.join('; ');
      } else {
        record = next;
        el('status').textContent = next.result?.applied ? 'Completed. Refresh the preview after adding any missing Cloud story points.' : (next.result?.reason || next.status);
        uncertain = next.status === 'recovery_required';
        canResume = false;
        el('approve').checked = false;
        await deps.refreshHistory();
      }
    } catch (error) {
      el('status').textContent = `${error.message} Check uncertain results before retrying.`;
      uncertain = true;
      canResume = false;
      record.status = 'recovery_required';
      deps.toast(error.message);
    } finally {
      busy = false;
      lockInputs(false);
      updateApproval();
    }
  }

  function destinationChanged(resetProject = false) {
    invalidate();
    const target = deps.getInstances().find((row) => row.name === el('target').value);
    if (resetProject) el('project').value = target?.default_project || '';
    if (!el('project').value.trim() && target?.default_project) el('project').value = target.default_project;
    loadMappings();
    el('users').innerHTML = '<tr><td colspan="6">Refresh the preview to load users for this destination.</td></tr>';
  }

  function open() {
    const instances = deps.getInstances();
    const previousSource = el('source').value;
    const previousTarget = el('target').value;
    el('source').innerHTML = instances.filter((row) => row.kind === 'cloud').map((row) => `<option value="${escape(row.name)}">${escape(row.name)}</option>`).join('');
    el('target').innerHTML = instances.filter((row) => ['datacenter', 'server'].includes(row.kind)).map((row) => `<option value="${escape(row.name)}">${escape(row.name)}</option>`).join('');
    if (previousSource) el('source').value = previousSource;
    if (previousTarget) el('target').value = previousTarget;
    destinationChanged();
    if (el('source').value) loadContext();
    else el('status').textContent = 'Configure a Cloud connection and a GPK2 Data Center/Server connection first.';
  }

  function bind(dependencies) {
    deps = dependencies;
    el('source').addEventListener('change', () => { loadMappings(); loadContext(); });
    el('target').addEventListener('change', () => destinationChanged(true));
    el('project').addEventListener('input', () => { invalidate(); loadMappings(); });
    el('sprint').addEventListener('change', invalidate);
    el('type').addEventListener('input', invalidate);
    el('extra').addEventListener('input', invalidate);
    el('board').addEventListener('change', () => loadContext(true));
    el('refresh').addEventListener('click', () => loadContext(true));
    el('preview').addEventListener('click', preview);
    el('approve').addEventListener('change', updateApproval);
    el('apply').addEventListener('click', () => execute('apply'));
    el('reconcile').addEventListener('click', () => execute('reconcile'));
    el('resume').addEventListener('click', () => execute('resume'));
  }
  return {bind, open, storyLinks};
})();
