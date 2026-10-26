const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function consoleContext(fetch) {
  const element = {};
  const context = vm.createContext({
    document: {querySelector: () => element, getElementById: () => element, querySelectorAll: () => []},
    fetch,
  });
  const script = fs.readFileSync(path.join(__dirname, '../src/engineering_ops/console/static/app.js'), 'utf8');
  vm.runInContext(script.replace(/\ninit\(\);\s*$/, ''), context);
  return context;
}

test('console requests carry the in-memory token and preserve caller headers', async () => {
  let captured;
  const context = consoleContext(async (url, options) => {
    captured = {url, options};
    return {ok: true, json: async () => ({instances: []})};
  });
  await vm.runInContext('state.authToken = "test-token"; api("/api/instances", {headers: {"X-Correlation-ID": "test-request"}})', context);
  assert.equal(captured.options.headers.Authorization, 'Bearer test-token');
  assert.equal(captured.options.headers['Content-Type'], 'application/json');
  assert.equal(captured.options.headers['X-Correlation-ID'], 'test-request');
});

test('console surfaces rejected authentication to the user', async () => {
  const context = consoleContext(async () => ({ok: false, status: 401, json: async () => ({error: 'Authentication required'})}));
  await assert.rejects(vm.runInContext('api("/api/instances")', context), /Authentication required/);
});
