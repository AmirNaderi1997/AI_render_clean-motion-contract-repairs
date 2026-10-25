import test from 'node:test';
import assert from 'node:assert/strict';
import { unsupported, recommendation } from '../src/local/render.ts';
import { localApplicationURL, processingPreferences } from '../src/local/preferences.ts';
test('unsupported effects are never silently rendered or routed',()=>{
  assert.deepEqual(unsupported(['trim','text','hyperframes','ai-broll']),['hyperframes','ai-broll']);
  assert.equal(recommendation(true,30,100,['trim'],false),'device');
  assert.equal(recommendation(true,30,100,['hyperframes'],false),'cloud');
  assert.equal(recommendation(false,30,100,[],true),'lan');
  assert.equal(recommendation(true,121,100,[],true),'lan');
  assert.equal(recommendation(false,30,100,['hyperframes'],true),'cloud');
  assert.equal(recommendation(false,30,100,['text'],true),'cloud');
});
test('settings default to the old online workflow; LAN is not a cloud alias',()=>{
  assert.equal(processingPreferences().mode,'online');
  assert.equal(localApplicationURL('https://192.168.1.10:5187'),'https://192.168.1.10:5187');
  assert.throws(()=>localApplicationURL('https://editor.rafiei.co'));
  assert.equal(localApplicationURL('http://192.168.1.10:5187'),'http://192.168.1.10:5187');
  assert.throws(()=>localApplicationURL('https://user:secret@editor-mac.local'));
});
