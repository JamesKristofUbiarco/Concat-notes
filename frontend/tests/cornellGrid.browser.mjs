// PLAYWRIGHT_MODULE=/path/to/playwright node tests/cornellGrid.browser.mjs
// Uses an isolated temporary note, removed in finally. Never touches existing notes.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const api = process.env.TEST_API_URL || 'http://localhost:8000';
const web = process.env.TEST_WEB_URL || 'http://localhost:3001';
async function request(path, body, method = body ? 'POST' : 'GET') {
  const response = await fetch(api + path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  assert.ok(response.ok, `${method} ${path}: ${response.status} ${await response.clone().text()}`);
  return response.status === 204 ? null : response.json();
}
let note;
let browser;
let mockServer;
if (process.env.MOCK_API === '1') {
  let fixture;
  mockServer = createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
    if (req.method === 'OPTIONS') { res.end(); return; }
    let input = '';
    for await (const part of req) input += part;
    const body = input ? JSON.parse(input) : {};
    let output = [];
    if (req.url === '/api/note-documents' && req.method === 'POST') {
      const sectionId = randomUUID();
      fixture = { id: randomUUID(), title: body.title, current_revision_id: randomUUID(), revision_number: 1, rendered_markdown: '', document: { composition: {}, sections: [{ id: sectionId, title: 'Sección de prueba', order: 0 }], relations: [], blocks: ['left', 'right'].map((lane, index) => ({ id: randomUUID(), section_id: sectionId, lane, type: 'markdown', content: '', reading_order: index * 10, layout: {}, sources: [] })) } };
      output = fixture;
    } else if (req.url.endsWith('/operations')) {
      assert.equal(body.base_revision_id, fixture.current_revision_id);
      for (const op of body.operations) {
        const b = fixture.document.blocks.find(b => b.id === op.target_id);
        if (op.op === 'replace_block') Object.assign(b, op.value);
        if (op.op === 'move_block') Object.assign(b, op.value);
        if (op.op === 'set_grid_rows') { fixture.document.composition.grid_rows ||= {}; fixture.document.composition.grid_rows[op.target_id] = op.value; }
        if (op.op === 'insert_block' || op.op === 'insert_after') fixture.document.blocks.push({ ...op.block, id: randomUUID(), section_id: op.op === 'insert_after' ? b.section_id : op.target_id, sources: [] });
        if (op.op === 'create_relation') fixture.document.relations.push({ ...op.relation, id: randomUUID() });
      }
      fixture.current_revision_id = randomUUID(); fixture.revision_number++;
      output = { document: fixture };
    } else if (req.url === `/api/note-documents/${fixture?.id}` && req.method === 'GET') output = fixture;
    else if (req.method === 'DELETE') { res.statusCode = 204; res.end(); return; }
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify(output));
  });
  await new Promise(resolve => mockServer.listen(new URL(api).port, resolve));
}
try {
  note = await request('/api/note-documents', { title: 'Prueba temporal grid Cornell' });
  const section = note.document.sections[0].id;
  const cue = note.document.blocks.find(b => b.lane === 'left');
  const detail = note.document.blocks.find(b => b.lane === 'right');
  const result = await request(`/api/note-documents/${note.id}/operations`, {
    base_revision_id: note.current_revision_id, summary: 'Preparar prueba aislada', operations: [
      { op: 'replace_block', target_id: cue.id, value: { ...cue, type: 'markdown', content: 'Pista de prueba', layout: { position_y: 0 } } },
      { op: 'replace_block', target_id: detail.id, value: { ...detail, type: 'markdown', content: 'Primer desarrollo **negrita**', layout: { position_y: 0 } } },
      ...['Segundo desarrollo', 'Tercer desarrollo'].map((content, index) => ({ op: 'insert_block', target_id: section, block: { type: 'markdown', lane: 'right', content, reading_order: 30 + index * 10, layout: { position_y: (index + 1) * 500 } } })),
      { op: 'insert_block', target_id: section, block: { type: 'markdown', lane: 'left', content: 'Otra pista debajo', reading_order: 50, layout: { position_y: 500 } } },
      { op: 'create_relation', relation: { from_block_id: cue.id, to_block_id: detail.id, type: 'explains', style: { connector: true, color: '#818cf8' } } },
    ],
  });
  note = result.document;
  browser = await chromium.launch({ executablePath: process.env.TEST_CHROMIUM_PATH, headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${web}/editor/${note.id}`);
  await page.getByText('Tercer desarrollo', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Alternar asistente', exact: true }).click();
  const cueCell = page.locator('article.group').filter({ hasText: 'Pista de prueba' });
  await cueCell.hover();
  await cueCell.getByRole('button', { name: 'Acciones del bloque', exact: true }).click();
  const menuAction = page.getByRole('button', { name: 'Añadir bloque debajo', exact: true });
  assert.ok(await menuAction.evaluate(button => {
    const r = button.getBoundingClientRect();
    return button.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
  }), 'The cue menu must be above the following cell');
  await page.getByRole('button', { name: 'Cerrar acciones del bloque', exact: true }).click();
  const developments = page.locator('article.group').filter({ hasText: 'desarrollo' });
  assert.equal(await developments.count(), 3);
  const bounds = await developments.evaluateAll(elements => elements.map(el => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, position: getComputedStyle(el).position }; }));
  assert.ok(bounds.every(b => b.position === 'relative'));
  assert.ok(bounds[1].top >= bounds[0].bottom && bounds[2].top >= bounds[1].bottom, 'Blocks must not overlap');
  assert.ok(bounds[1].top - bounds[0].bottom < 20, 'Legacy pixel gaps must not survive');
  const third = page.locator('article.group').filter({ hasText: 'Tercer desarrollo' });
  await third.hover();
  const handle = third.getByRole('button', { name: 'Reordenar bloque', exact: true });
  const source = await handle.boundingBox();
  const first = await developments.first().boundingBox();
  await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
  await page.mouse.down();
  await page.mouse.move(source.x + source.width / 2, first.y + 12, { steps: 15 });
  await page.mouse.up();
  await page.waitForFunction(async ({ api, id }) => {
    const n = await (await fetch(`${api}/api/note-documents/${id}`)).json();
    const ordered = n.document.blocks.filter(b => b.lane === 'right').sort((a,b) => a.layout.position_y - b.layout.position_y);
    return ordered[0].content === 'Tercer desarrollo';
  }, { api, id: note.id });
  const saved = await request(`/api/note-documents/${note.id}`);
  assert.equal(saved.document.relations.length, 1);
  assert.equal(saved.document.relations[0].to_block_id, detail.id);
  await page.reload();
  await page.getByText('Tercer desarrollo', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Alternar asistente', exact: true }).click();
  assert.equal(await page.locator('article.group').filter({ hasText: 'desarrollo' }).first().innerText(), 'Tercer desarrollo');
  const top = page.locator('article.group').filter({ hasText: 'Tercer desarrollo' });
  await top.hover();
  await top.getByRole('button', { name: 'Acciones del bloque', exact: true }).click();
  await page.getByRole('button', { name: 'Añadir bloque debajo', exact: true }).click();
  await page.waitForFunction(async ({ api, id }) => (await (await fetch(`${api}/api/note-documents/${id}`)).json()).document.blocks.length === 6, { api, id: note.id });
  const inserted = await request(`/api/note-documents/${note.id}`);
  const ordered = inserted.document.blocks.filter(b => b.lane === 'right').sort((a,b) => a.layout.position_y - b.layout.position_y);
  assert.equal(ordered[1].content, '');
  assert.equal(inserted.document.relations.length, 1);
  assert.ok(!ordered[1].layout.alignment_group);
  const markdownBeforeSeparator = inserted.rendered_markdown;
  const cueBelow = page.locator('article.group').filter({ hasText: 'Otra pista debajo' });
  const detailBelow = page.locator('article.group').filter({ hasText: 'Primer desarrollo' });
  for (const cell of [cueBelow, detailBelow]) {
    await cell.hover();
    await cell.getByRole('button', { name: 'Seleccionar bloque para vincular', exact: true }).click();
  }
  await page.getByRole('button', { name: 'Separador antes', exact: true }).click();
  await page.waitForFunction(async ({ api, id }) => {
    const n = await (await fetch(`${api}/api/note-documents/${id}`)).json();
    return Object.values(n.document.composition.grid_rows || {}).some(rows => rows.length === 1);
  }, { api, id: note.id });
  await page.getByRole('button', { name: 'Cancelar selección', exact: true }).click();
  const divided = await request(`/api/note-documents/${note.id}`);
  assert.equal(divided.rendered_markdown, markdownBeforeSeparator, 'Visual separator must not change Markdown');
  assert.equal(divided.document.relations.length, 1);
  const cueBounds = await cueBelow.boundingBox();
  const detailBounds = await detailBelow.boundingBox();
  assert.ok(Math.abs(cueBounds.y - detailBounds.y) < 2, 'Both columns must start at the same height after separator');
  await page.getByRole('button', { name: 'Añadir separador de alineación', exact: true }).last().click();
  await page.locator('[data-grid-row]').nth(2).waitFor();
  const emptyGroup = page.locator('[data-grid-row]').nth(2);
  const destination = emptyGroup.locator('[data-grid-lane="left"]');
  await destination.scrollIntoViewIfNeeded();
  await cueBelow.hover();
  const moveHandle = await cueBelow.getByRole('button', { name: 'Reordenar bloque', exact: true }).boundingBox();
  const dropArea = await destination.boundingBox();
  const emptyRowId = await emptyGroup.getAttribute('data-grid-row');
  await page.mouse.move(moveHandle.x + moveHandle.width / 2, moveHandle.y + moveHandle.height / 2);
  await page.mouse.down();
  await page.mouse.move(dropArea.x + dropArea.width / 2, dropArea.y + 30, { steps: 20 });
  await page.mouse.up();
  await page.waitForFunction(async ({ api, id, row }) => {
    const n = await (await fetch(`${api}/api/note-documents/${id}`)).json();
    return n.document.blocks.find(b => b.content === 'Otra pista debajo').layout.grid_row === row;
  }, { api, id: note.id, row: emptyRowId });
  assert.equal((await request(`/api/note-documents/${note.id}`)).document.relations.length, 1);
  await emptyGroup.getByRole('button', { name: 'Eliminar separador de alineación', exact: true }).click();
  await page.waitForFunction(async ({ api, id }) => {
    const n = await (await fetch(`${api}/api/note-documents/${id}`)).json();
    return Object.values(n.document.composition.grid_rows).some(rows => rows.length === 1);
  }, { api, id: note.id });
  await page.reload();
  await page.getByText('Otra pista debajo', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Alternar asistente', exact: true }).click();
  assert.equal(await page.locator('[data-grid-row]').count(), 2, 'Separator persists on reload');
  await page.getByRole('button', { name: 'Eliminar separador de alineación', exact: true }).click();
  await page.waitForFunction(async ({ api, id }) => {
    const n = await (await fetch(`${api}/api/note-documents/${id}`)).json();
    return Object.values(n.document.composition.grid_rows || {}).every(rows => rows.length === 0);
  }, { api, id: note.id });
  const merged = await request(`/api/note-documents/${note.id}`);
  assert.equal(merged.document.blocks.length, 6);
  assert.equal(merged.rendered_markdown, markdownBeforeSeparator);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Desarrollo', exact: true }).click();
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'No horizontal page overflow');
  assert.deepEqual(errors, []);
  console.log('Browser: grid, menus, drag, relations, separators alignment/persistence/removal, unchanged Markdown and mobile passed.');
} finally {
  if (browser) await browser.close();
  if (note) await request(`/api/note-documents/${note.id}`, undefined, 'DELETE');
  if (mockServer) await new Promise(resolve => mockServer.close(resolve));
}
