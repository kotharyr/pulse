/* Real browser against the real local backend and a Jira fixture that refuses writes. */
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
  const server = spawn(process.env.PULSE_PYTHON || 'python3', [path.join(__dirname, 'server.py')], {
    cwd: path.join(__dirname, '../..'), env: {...process.env, PULSE_BROWSER_PORT: String(port)}, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let log = '';
  server.stdout.on('data', (chunk) => log += chunk);
  server.stderr.on('data', (chunk) => log += chunk);
  let browser;
  const checks = [];
  try {
    const deadline = Date.now() + 15000;
    while (true) {
      try { if ((await fetch(origin + '/health/live')).ok) break; } catch (_) {}
      if (Date.now() > deadline || server.exitCode !== null) throw new Error('Fixture server did not start: ' + log.slice(-2500));
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    const options = {headless: true};
    if (process.env.PULSE_BROWSER_EXECUTABLE) options.executablePath = process.env.PULSE_BROWSER_EXECUTABLE;
    browser = await chromium.launch(options);
    const context = await browser.newContext();
    await context.route('**/*', (route) => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(origin + '/console');
    assert.equal((await context.request.get(origin + '/api/instances')).status(), 401);
    checks.push('Unauthenticated API access is denied');
    await page.locator('#console-token').fill('pulse-browser-test');
    const instancesLoaded = page.waitForResponse((r) => r.url().endsWith('/api/instances') && r.status() === 200);
    await page.locator('#console-connect').click();
    await instancesLoaded;
    await page.waitForFunction(() => document.querySelector('#instance-select').options.length === 1);
    assert.equal(await page.locator('#console-token').inputValue(), '');
    const storage = await page.evaluate(() => JSON.stringify({local: {...localStorage}, session: {...sessionStorage}}));
    assert.ok(!storage.includes('pulse-browser-test'));
    checks.push('Token entry reconnects without persisting the credential');
    const reviewLoaded = page.waitForResponse((r) => r.url().endsWith('/api/orchestration/engineering-review') && r.status() === 200);
    await page.getByRole('button', {name: 'Prepare Engineering Review', exact: true}).click();
    const review = await (await reviewLoaded).json();
    assert.equal(review.workflow, 'engineering_review');
    assert.ok(review.sections.instances.cloud.sprint_health);
    await page.waitForFunction(() => document.querySelector('#workflow-output').textContent.includes('engineering_review'));
    checks.push('Engineering review renders in the browser');
    await page.locator('[data-view-target="jira-view"]').click();
    await page.locator('#sprint-id').fill('1');
    await page.locator('#next-sprint-id').fill('2');
    await page.locator('#rollover-all').check();
    const previewLoaded = page.waitForResponse((r) => r.url().endsWith('/api/executions/preview') && r.status() === 201);
    await page.locator('#preview-close').click();
    const record = await (await previewLoaded).json();
    await page.waitForFunction(() => document.querySelector('#preview-output').textContent.includes('previewed'));
    assert.equal(await page.locator('#apply-preview').isDisabled(), true);
    checks.push('Sprint preview renders and recommend_only disables Apply');
    const headers = {Authorization: 'Bearer pulse-browser-test'};
    const blocked = await context.request.post(origin + `/api/executions/${record.preview_id}/apply`, {headers});
    assert.equal((await blocked.json()).result.applied, false);
    checks.push('A direct apply request is also blocked by the backend mode');
    // Generate a fresh review so rejection is tested independently of the failed apply.
    const newPreview = page.waitForResponse((r) => r.url().endsWith('/api/executions/preview') && r.status() === 201);
    await page.locator('#preview-close').click();
    const rejectRecord = await (await newPreview).json();
    const rejected = page.waitForResponse((r) => r.url().endsWith('/reject') && r.status() === 200);
    await page.locator('#reject-preview').click();
    assert.equal((await (await rejected).json()).status, 'rejected');
    await page.waitForFunction(() => document.querySelector('#preview-status').textContent === 'Preview rejected');
    const replay = await context.request.post(origin + `/api/executions/${rejectRecord.preview_id}/apply`, {headers});
    assert.equal(replay.status(), 400);
    checks.push('Rejection persists and prevents a later apply');
    assert.deepEqual(errors, []);
    checks.push('No uncaught browser JavaScript errors');
    const output = {passed: true, mode: 'recommend_only', external_jira_mutations: 0, checks};
    const outputPath = path.join(__dirname, '../../.acceptance-results/browser.json');
    fs.mkdirSync(path.dirname(outputPath), {recursive: true});
    fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));
    console.log(JSON.stringify(output, null, 2));
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
  }
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; });
