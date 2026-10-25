import test from 'node:test';
import assert from 'node:assert/strict';
import {activateAppUpdate} from '../src/local/pwa.ts';

test('update activates a waiting worker and reloads exactly once',async()=>{
  const container=new EventTarget();
  Object.defineProperty(navigator,'serviceWorker',{value:container,configurable:true});
  const worker=new EventTarget();worker.state='installed';
  worker.postMessage=message=>{
    assert.equal(message,'ACTIVATE_UPDATE');
    queueMicrotask(()=>{worker.state='activated';worker.dispatchEvent(new Event('statechange'));container.dispatchEvent(new Event('controllerchange'));});
  };
  let reloads=0;
  await activateAppUpdate({waiting:worker},()=>reloads++);
  assert.equal(reloads,1);
});
test('stale update card reloads an already activated version instead of hanging',async()=>{
  let checks=0,reloads=0;
  await activateAppUpdate({waiting:null,installing:null,active:{},update:async()=>checks++},()=>reloads++);
  assert.equal(checks,1);assert.equal(reloads,1);
});
test('network failure is reported without reload or deleting browser storage',async()=>{
  let reloads=0;
  await assert.rejects(activateAppUpdate({waiting:null,update:async()=>{throw new Error('offline');}},()=>reloads++),/offline/);
  assert.equal(reloads,0);
});
