const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function harness(api) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {value: '', checked: false, disabled: false,
      textContent: '', innerHTML: '', handlers: {},
      addEventListener(kind, fn) { this.handlers[kind] = fn; }, querySelectorAll() { return []; }});
    return elements.get(id);
  }
  const context = vm.createContext({URL, document: {getElementById: element},
    localStorage: {getItem: () => null, setItem() {}},
    dependencies: {api, toast() {}, refreshHistory: async () => {}, getInstances: () => []}});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/engineering_ops/console/static/sprint-ops.js'), 'utf8'), context);
  vm.runInContext('sprintOps.bind(dependencies)', context);
  element('ops-source').value = 'cloud'; element('ops-target').value = 'gpk2';
  element('ops-project').value = 'GPK'; element('ops-sprint').value = '42';
  element('ops-type').value = 'Story';
  return {context, el: (id) => element('ops-' + id)};
}

const record = {preview_id: 'review', status: 'previewed', preview: {can_apply: true, mode: 'safe_apply',
  sprint: {name: 'Sprint Amber'}, action_count: 1, missing_points: [], unassigned: [],
  users: [{assignee: 'Alice', username: 'alice@example.invalid', match_source: 'email', action: 'create',
    errors: [], new_stories: [], already_included: [], added_points: 3, total_points: 3}]}};

test('automatic email workflow submits no required user mappings and requires reviewed approval', async () => {
  let submitted;
  const {el} = harness(async (_, options) => { submitted = JSON.parse(options.body); return record; });
  await el('preview').handlers.click();
  assert.deepEqual(submitted.parameters.user_mappings, {});
  assert.equal(el('apply').disabled, true);
  el('approve').checked = true;
  el('approve').handlers.change();
  assert.equal(el('apply').disabled, false);
  el('type').handlers.input();
  assert.equal(el('apply').disabled, true);
  assert.equal(el('approve').checked, false);
});

test('recommend_only cannot be applied through the Console even when approval is checked', async () => {
  const calls = [];
  const {el} = harness(async (url) => {
    calls.push(url);
    return {...record, preview: {...record.preview, can_apply: false, mode: 'recommend_only'}};
  });
  await el('preview').handlers.click();
  el('approve').checked = true;
  el('approve').handlers.change();
  await el('apply').handlers.click();
  assert.equal(el('apply').disabled, true);
  assert.deepEqual(calls, ['/api/executions/preview']);
});

test('an old preview response cannot authorize changed inputs', async () => {
  let resolve;
  const {el} = harness(() => new Promise((done) => { resolve = done; }));
  const pending = el('preview').handlers.click();
  el('project').value = 'OTHER';
  el('project').handlers.input();
  resolve(record);
  await pending;
  el('approve').checked = true;
  el('approve').handlers.change();
  assert.equal(el('apply').disabled, true);
});

test('story links escape text and reject script URLs', () => {
  const {context} = harness(async () => record);
  const html = vm.runInContext(`sprintOps.storyLinks([
    {key: '<script>', summary: '<img src=x>', assignee: 'Alice', url: 'https://cloud.example.invalid/browse/SBG-1'},
    {key: 'SBG-2', summary: 'bad', url: 'javascript:alert(1)'}])`, context);
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(html.includes('&lt;img src=x&gt;'));
  assert.ok(!html.includes('href="javascript:'));
  assert.ok(!html.includes('<script>'));
});
