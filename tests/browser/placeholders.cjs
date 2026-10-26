const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function main() {
  const port = await freePort();
  const origin = `http://127.0.0.1:${port}`;
  const fixture = spawn(process.env.PULSE_PYTHON || 'python3', [path.join(__dirname, 'placeholder_server.py')], {
    cwd: path.join(__dirname, '../..'), env: {...process.env, PULSE_BROWSER_PORT: String(port)}, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let log = '';
  fixture.stdout.on('data', (chunk) => log += chunk);
  fixture.stderr.on('data', (chunk) => log += chunk);
  let browser;
  try {
    const deadline = Date.now() + 20000;
    while (true) {
      try { if ((await fetch(origin + '/health/live')).ok) break; } catch (_) {}
      if (Date.now() > deadline || fixture.exitCode !== null) throw new Error('Fixture failed to start: ' + log.slice(-2000));
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({headless: true, ...(process.env.PULSE_BROWSER_EXECUTABLE ? {executablePath: process.env.PULSE_BROWSER_EXECUTABLE} : {})});
    const context = await browser.newContext({viewport: {width: 1440, height: 1100}});
    await context.route('**/*', (route) => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(origin + '/console');
    await page.locator('#console-token').fill('placeholder-browser-test');
    const connected = page.waitForResponse((response) => response.url().endsWith('/api/instances') && response.ok());
    await page.locator('#console-connect').click();
    await connected;
    await page.waitForFunction(() => document.querySelector('#instance-select').options.length === 2);
    await page.locator('[data-view-target="sprint-ops-view"]').click();
    await page.waitForFunction(() => document.querySelector('#ops-sprint').options.length === 1);
    assert.equal(await page.locator('#ops-sprint option').textContent(), 'Sprint Amber (active)');

    async function preview() {
      const pending = page.waitForResponse((response) => response.url().endsWith('/api/executions/preview') && response.status() === 201);
      await page.locator('#ops-preview').click();
      const record = await (await pending).json();
      await page.waitForFunction(() => !document.querySelector('#ops-preview').disabled);
      return record;
    }
    async function apply() {
      await page.locator('#ops-approve').check();
      const pending = page.waitForResponse((response) => response.url().endsWith('/apply'));
      await page.locator('#ops-apply').click();
      const result = await (await pending).json();
      assert.equal(result.status, 'succeeded');
      await page.waitForFunction(() => document.querySelector('#ops-status').textContent.startsWith('Completed.'));
      return result;
    }

    const first = await preview();
    assert.equal(first.preview.users[0].action, 'create');
    assert.equal(first.preview.users[0].username, 'alice@common.example.invalid');
    assert.equal(first.preview.users[0].match_source, 'email');
    assert.equal(await page.locator('#ops-missing a').getAttribute('href'), 'https://cloud.example.invalid/jira/browse/SBG-2');
    assert.equal(first.preview.users[0].total_points, 3);
    assert.equal(await page.locator('#ops-apply').isDisabled(), true);
    await page.locator('#ops-approve').check();
    assert.equal(await page.locator('#ops-apply').isEnabled(), true);
    await page.locator('#ops-type').fill('Task');
    assert.equal(await page.locator('#ops-apply').isDisabled(), true);
    assert.equal(await page.locator('#ops-approve').isChecked(), false);
    await page.locator('#ops-type').fill('Story');
    await preview();
    await apply();
    await context.request.post(origin + '/__test/points');
    const second = await preview();
    assert.equal(second.preview.users[0].action, 'update');
    assert.equal(second.preview.users[0].total_points, 8);
    assert.equal(second.preview.missing_points.length, 0);
    await apply();
    const third = await preview();
    assert.equal(third.preview.action_count, 0);
    assert.equal(third.preview.users[0].action, 'unchanged');
    assert.equal(await page.locator('#ops-apply').isDisabled(), true);
    const state = await (await context.request.get(origin + '/__test/state')).json();
    assert.deepEqual(state.calls, [['create', 'GPK-1'], ['update', 'GPK-1']]);
    assert.equal(Object.keys(state.issues).length, 1);
    assert.equal(state.issues['GPK-1'].fields.customfield_10001, 8);
    assert.equal(state.issues['GPK-1'].fields.description.split('[SBG-1|').length - 1, 1);
    assert.deepEqual(errors, []);
    const result = {passed: true, external_jira_mutations: 0, checks: [
      'Named board/sprint and destination selection', 'Missing-point stories link to Cloud',
      'Automatic common-email matching and reviewed approval', 'Input edits invalidate approval',
      'First run creates one 3-point placeholder', 'Newly pointed story updates same placeholder to 8',
      'Further run is unchanged with no duplicate creation', 'No uncaught browser errors',
    ]};
    const output = path.join(__dirname, '../../.acceptance-results');
    fs.mkdirSync(output, {recursive: true});
    await page.screenshot({path: path.join(output, 'sprint-placeholders.png'), fullPage: true});
    fs.writeFileSync(path.join(output, 'sprint-placeholders.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally {
    if (browser) await browser.close();
    fixture.kill('SIGTERM');
  }
}
main().catch((error) => { console.error(error.stack); process.exitCode = 1; });
