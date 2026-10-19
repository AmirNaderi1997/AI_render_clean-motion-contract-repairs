import test from 'node:test';
import assert from 'node:assert/strict';
import {movePriority,logQuery} from '../src/ai-models-utils.ts';

test('drag/drop preserves exact IDs and does not mutate the saved order',()=>{
  const before=['Provider/Case:One','Provider/Case:TWO','auto:default'];
  assert.deepEqual(movePriority(before,2,0),['auto:default','Provider/Case:One','Provider/Case:TWO']);
  assert.equal(before[0],'Provider/Case:One');
});
test('invalid reorder is safe',()=>assert.deepEqual(movePriority(['a'],2,0),['a']));
test('log filters use explicit UTC boundaries and encode exact model IDs',()=>{
  const p=new URLSearchParams(logQuery({model:'Provider/Case:One',since:'2026-10-20',until:'2026-10-20',status:''}));
  assert.equal(p.get('model'),'Provider/Case:One');
  assert.equal(p.get('since'),'2026-10-20T00:00:00+00:00');
  assert.equal(p.get('until'),'2026-10-20T23:59:59+00:00');
  assert.equal(p.has('status'),false);
});
