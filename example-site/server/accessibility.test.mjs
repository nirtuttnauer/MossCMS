// axe-core is an example-site dev dependency. Its license is MPL-2.0.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import axe from 'axe-core';

const RULES = ['button-name', 'label', 'html-has-lang', 'html-lang-valid', 'image-alt', 'link-name'];

function load(name) {
  return readFileSync(new URL(`./fixtures/accessibility/${name}.html`, import.meta.url), 'utf8');
}

async function violationIds(html) {
  const dom = new JSDOM(html, { pretendToBeVisual: true, url: 'https://example.com/' });
  try {
    const result = await axe.run(dom.window.document.documentElement, {
      runOnly: { type: 'rule', values: RULES },
    });
    return result.violations.map(item => item.id);
  } finally {
    axe.teardown();
    dom.window.close();
  }
}

test('axe reports empty buttons, unlabeled fields, missing lang, image alt, and link names', async () => {
  const ids = await violationIds(load('broken'));
  for (const rule of ['button-name', 'label', 'html-has-lang', 'image-alt', 'link-name']) {
    assert.ok(ids.includes(rule), ids.join(','));
  }
});

test('axe reports an invalid html lang value', async () => {
  const ids = await violationIds(load('invalid-lang'));
  assert.ok(ids.includes('html-lang-valid'), ids.join(','));
});

test('axe passes the fixed page', async () => {
  const ids = await violationIds(load('fixed'));
  assert.deepEqual(ids, []);
});
