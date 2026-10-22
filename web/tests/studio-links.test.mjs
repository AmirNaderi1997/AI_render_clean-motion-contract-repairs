import test from 'node:test';
import assert from 'node:assert/strict';
import {readableLink} from '../src/studio/links.ts';

test('Persian encyclopedia URL has readable subject without a product claim',()=>{
  const url='https://fa.wikipedia.org/wiki/'+encodeURIComponent('تحلیل جنگ ایران');
  assert.equal(readableLink(url),'تحلیل جنگ ایران — ویکی‌پدیا');
  assert.equal(readableLink(url,{[url]:'عنوان واقعی مقاله'}),'عنوان واقعی مقاله');
});
test('links retain safe short fallback labels for malformed encoding and query strings',()=>{
  assert.equal(readableLink('https://example.com/%E0%A4%A?token=private'),'example.com');
  assert.equal(readableLink('https://example.com/'),'example.com');
  assert.equal(readableLink('not a url'),'لینک منبع');
});
