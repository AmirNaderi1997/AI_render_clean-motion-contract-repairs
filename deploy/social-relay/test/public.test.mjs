import test from 'node:test';
import assert from 'node:assert/strict';
import {isPublicAddress, isPublicUrl} from '../api/_public.mjs';

test('private, loopback, link-local and reserved addresses are refused', () => {
  for (const a of ['127.0.0.1', '10.1.2.3', '172.16.0.1', '172.31.255.255', '192.168.1.1', '169.254.169.254', '0.0.0.0', '100.64.0.1', '224.0.0.1', '::1', 'fd00::1', 'fe80::1', '::ffff:10.0.0.1']) {
    assert.equal(isPublicAddress(a), false, a);
  }
});

test('public addresses are allowed', () => {
  for (const a of ['8.8.8.8', '185.158.133.1', '172.32.0.1', '2606:4700:4700::1111', '::ffff:8.8.8.8']) assert.equal(isPublicAddress(a), true, a);
});

test('only plain http(s) urls to public hosts pass', async () => {
  assert.equal(await isPublicUrl('http://127.0.0.1/admin'), false);
  assert.equal(await isPublicUrl('file:///etc/passwd'), false);
  assert.equal(await isPublicUrl('https://user:pass@8.8.8.8/'), false);
  assert.equal(await isPublicUrl('not a url'), false);
  assert.equal(await isPublicUrl('https://8.8.8.8/x'), true);
});
