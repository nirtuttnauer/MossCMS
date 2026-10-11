import { readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';

const email = 'docker-smoke@example.test';
const password = 'CI-only-password-for-MossCMS!';

test('production readiness and packaged branding assets', async ({ request }) => {
  expect((await request.get('/ready')).status()).toBe(200);
  for (const [file, mime] of [['moss-symbol-v2.png', 'image/png'], ['moss-arch-v2.webp', 'image/webp']]) {
    const response = await request.get(`/brand/${file}`);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toBe(mime);
    expect(await response.body()).toEqual(readFileSync(new URL(`../web/public/brand/${file}`, import.meta.url)));
    expect((await request.head(`/brand/${file}`)).status()).toBe(200);
  }
  for (const route of ['/brand/missing.png', '/brand/..%2F..%2Fapp/config.py']) {
    expect((await request.get(route)).status()).toBe(404);
  }
});

test('production setup, login and branding on desktop and mobile', async ({ page, context }, testInfo) => {
  const errors = [];
  const failedAssets = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (response.status() >= 400 && /\/(assets|brand)\//.test(response.url())) {
      failedAssets.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on('requestfailed', request => {
    if (/\/(assets|brand)\//.test(request.url())) failedAssets.push(request.url());
  });

  const screenshot = async name => {
    await testInfo.attach(name, { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  };
  const decoded = async selector => {
    await expect.poll(() => page.locator(selector).evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
  };
  const loginLayout = async (name, artworkVisible) => {
    await expect(page.locator('.auth-panel .brand-mark')).toBeVisible();
    await decoded('.auth-panel .brand-mark');
    await decoded('.auth-artwork-image');
    if (artworkVisible) await expect(page.locator('.auth-artwork')).toBeVisible();
    else await expect(page.locator('.auth-artwork')).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect((await page.locator('button[type="submit"]').boundingBox()).height).toBeGreaterThanOrEqual(44);
    await screenshot(name);
  };
  const signedIn = async () => {
    await expect(page.locator('.sidebar .brand-mark')).toBeVisible();
    await decoded('.sidebar .brand-mark');
    await expect(page.locator('.api-status')).toHaveText('API operational');
    expect(await page.evaluate(async () => (await fetch('/auth/me')).status)).toBe(200);
    const session = (await context.cookies()).find(cookie => cookie.name === 'moss_session');
    expect(session).toMatchObject({ secure: true, httpOnly: true });
  };
  const signOut = async () => {
    await page.getByRole('button', { name: 'Sign out', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    expect(await page.evaluate(async () => (await fetch('/auth/me')).status)).toBe(401);
  };
  const signIn = async () => {
    await page.getByLabel('Email', { exact: true }).fill(email);
    await page.getByLabel('Password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await signedIn();
  };

  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Create your workspace' })).toBeVisible();
  await loginLayout('setup-desktop', true);
  await page.getByLabel('Your name', { exact: true }).fill('Docker Smoke Test');
  await page.getByLabel('Workspace name', { exact: true }).fill('Docker Smoke Workspace');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByLabel(/^Setup token/).fill('ci-only-setup-token-not-for-production');
  await page.getByRole('button', { name: 'Create administrator' }).click();
  await signedIn();
  await screenshot('sidebar-desktop');
  await signOut();
  await loginLayout('login-desktop', true);

  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('incorrect-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid email or password.');
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue(email);
  await signIn();
  await signOut();

  await page.setViewportSize({ width: 375, height: 812 });
  await loginLayout('login-mobile', false);
  await page.setViewportSize({ width: 812, height: 375 });
  await loginLayout('login-mobile-landscape', false);
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn();
  expect(errors).toEqual([]);
  expect(failedAssets).toEqual([]);
});
