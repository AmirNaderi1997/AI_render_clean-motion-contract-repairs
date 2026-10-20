import test from 'node:test';
import assert from 'node:assert/strict';
import {editorMediaPolicy,editorMediaTimeout,editorMediaChain} from './editor-media-policy.js';
test('Editor media has one candidate and minimum response budgets',async()=>{
  await editorMediaPolicy({headers:{'x-editorgpt-media-single-attempt':'1','x-editorgpt-media-timeout-ms':'900000'}},async()=>{
    await Promise.resolve();
    assert.deepEqual(editorMediaChain([1,2,3]),[1]);
    assert.equal(editorMediaTimeout('image',60000),900000);
  });
  editorMediaPolicy({headers:{'x-editorgpt-media-single-attempt':'1'}},()=>{
    assert.equal(editorMediaTimeout('image',60000),150000);
    assert.equal(editorMediaTimeout('audio',60000),200000);
    assert.equal(editorMediaTimeout('video',60000),300000);
  });
  assert.equal(editorMediaTimeout('image',60000),60000);
  assert.deepEqual(editorMediaChain([1,2,3]),[1,2,3]);
});
