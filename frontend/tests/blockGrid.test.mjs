import { test } from 'node:test';
import assert from 'node:assert/strict';
import { gridBlocks, insertGridAfter, reorderGrid, splitGridRow, mergeGridRow, appendGridBlock, moveGridToRow } from '../app/lib/blockGrid.ts';

const block = (id, position, lane = 'right', section = 's') => ({
  id, section_id: section, type: 'markdown', lane, reading_order: 10,
  content: id, layout: { position_y: position, alignment_group: 'old' }, sources: [],
});

test('legacy visual order is preserved without mutating the document', () => {
  const blocks = [block('b', 400), block('a', 0), block('c', 200)];
  assert.deepEqual(gridBlocks(blocks).map(b => b.id), ['a', 'c', 'b']);
  assert.deepEqual(blocks.map(b => b.id), ['b', 'a', 'c']);
});

test('reorder changes only the requested column and preserves content and identity', () => {
  const blocks = [block('a', 0), block('b', 200), block('c', 400), block('cue', 0, 'left'), block('other', 0, 'right', 'other')];
  const operations = reorderGrid(blocks, 'c', 'a');
  assert.deepEqual(operations.map(op => op.target_id), ['c', 'a', 'b']);
  assert.deepEqual(operations.map(op => op.value.layout.position_y), [0, 10, 20]);
  assert.ok(operations.every(op => op.value.layout.alignment_group === null));
  assert.deepEqual(blocks.map(b => b.content), ['a', 'b', 'c', 'cue', 'other']);
});

test('cross-column, cross-section, summary and cancelled drops are ignored', () => {
  const blocks = [block('a', 0), block('cue', 0, 'left'), block('other', 0, 'right', 'other'), { ...block('summary', 0), type: 'summary' }];
  for (const target of ['cue', 'other', 'summary', 'a', 'missing']) assert.deepEqual(reorderGrid(blocks, 'a', target), []);
});

test('inserting below makes room even with coincident legacy positions', () => {
  const blocks = [block('a', 0), block('b', 0), block('c', 20)];
  const insertion = insertGridAfter(blocks, blocks[0]);
  assert.equal(insertion.position, 10);
  assert.deepEqual(insertion.operations.map(op => op.value.layout.position_y), [0, 20, 30]);
});

test('one-block and empty columns are safe', () => {
  assert.deepEqual(gridBlocks([]), []);
  assert.deepEqual(reorderGrid([block('a', 0)], 'a', 'a'), []);
  assert.equal(insertGridAfter([block('a', 0)], block('a', 0)).position, 10);
});

test('separator splits both columns at selected anchors without altering their order', () => {
  const blocks = [block('a', 0), block('b', 10), block('c', 20), block('q1', 0, 'left'), block('q2', 10, 'left')];
  const document = { composition: {}, blocks };
  const operations = splitGridRow(document, 's', 'start', 'row2', new Set(['b', 'q2']));
  assert.deepEqual(operations[0].value, ['row2']);
  assert.deepEqual(new Set(operations.slice(1).map(op => op.target_id)), new Set(['b', 'c', 'q2']));
  assert.ok(operations.slice(1).every(op => op.value.layout.grid_row === 'row2'));
  assert.deepEqual(blocks.map(b => b.layout.position_y), [0, 10, 20, 0, 10]);
});

test('separator can be inserted between groups and merged without deleting cells', () => {
  const b = { ...block('b', 10), layout: { position_y: 10, grid_row: 'row2' } };
  const document = { composition: { grid_rows: { s: ['row2'] } }, blocks: [block('a', 0), b] };
  assert.deepEqual(splitGridRow(document, 's', 'start', 'middle', new Set())[0].value, ['middle', 'row2']);
  const merged = mergeGridRow(document, 's', 'row2');
  assert.equal(merged[0].value.layout.grid_row, 'start');
  assert.deepEqual(merged[1].value, []);
});

test('append and reorder respect shared visual groups', () => {
  const a = block('a', 0); const b = { ...block('b', 10), layout: { position_y: 10, grid_row: 'row2' } };
  const document = { composition: { grid_rows: { s: ['row2'] } }, blocks: [a, b] };
  const inserted = appendGridBlock(document, 's', 'right', 'start');
  assert.equal(inserted.position, 10);
  assert.equal(inserted.operations[1].value.layout.position_y, 20);
  assert.deepEqual(reorderGrid(document.blocks, 'a', 'b'), []);
});

test('drag into an empty group persists the row and preserves other cells', () => {
  const document = { composition: { grid_rows: { s: ['empty'] } }, blocks: [block('a', 0), block('b', 10), block('cue', 0, 'left')] };
  const operations = moveGridToRow(document, 'a', 'empty');
  assert.deepEqual(operations.map(op => op.target_id), ['b', 'a']);
  assert.equal(operations[1].value.layout.grid_row, 'empty');
  assert.deepEqual(operations.map(op => op.value.layout.position_y), [0, 10]);
  assert.equal(document.blocks[0].layout.grid_row, undefined);
  assert.deepEqual(moveGridToRow(document, 'a', 'missing'), []);
});

test('drag between populated groups supports insertion and moving back', () => {
  const a = block('a', 0);
  const b = { ...block('b', 10), layout: { position_y: 10, grid_row: 'second' } };
  const c = { ...block('c', 20), layout: { position_y: 20, grid_row: 'second' } };
  const document = { composition: { grid_rows: { s: ['second'] } }, blocks: [a, b, c] };
  assert.deepEqual(moveGridToRow(document, 'a', 'second', 'b', true).map(op => op.target_id), ['b', 'a', 'c']);
  const back = moveGridToRow(document, 'c', 'start', 'a');
  assert.deepEqual(back.map(op => op.target_id), ['c', 'a', 'b']);
  assert.equal(back[0].value.layout.grid_row, 'start');
});
