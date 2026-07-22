import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('C:/Users/14904/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.60.0/node_modules/playwright');
const output = resolve(import.meta.dirname, '..', 'qa');
await mkdir(output, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
});

const report = { desktop: {}, mobile: {}, consoleErrors: [] };
const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await desktop.newPage();
page.on('console', (message) => { if (message.type() === 'error') report.consoleErrors.push(message.text()); });
page.on('pageerror', (error) => report.consoleErrors.push(error.message));

await page.goto('http://127.0.0.1:8765/reader/', { waitUntil: 'networkidle' });
await page.waitForFunction(() => document.querySelectorAll('.book-row').length === 50);
report.desktop.bookCount = await page.locator('.book-row').count();
report.desktop.collectionCount = await page.locator('.collection').count();
report.desktop.title = await page.title();
await page.screenshot({ path: resolve(output, 'desktop-library.png') });

await page.locator('#searchInput').fill('黑贝街');
report.desktop.filteredCount = await page.locator('.book-row').count();
await page.locator('.book-row').first().click();
await page.locator('.page-shell canvas').waitFor({ state: 'visible', timeout: 60000 });
report.desktop.openedTitle = await page.locator('#bookTitle').textContent();
report.desktop.pageCount = Number(await page.locator('#pageCount').textContent());
report.desktop.canvas = await page.locator('.page-shell canvas').evaluate((canvas) => ({ width: canvas.clientWidth, height: canvas.clientHeight }));
await page.locator('#nextPage').click();
await page.waitForFunction(() => document.querySelector('#pageInput')?.value === '2');
report.desktop.nextPage = await page.locator('#pageInput').inputValue();
await page.locator('#scrollMode').click();
await page.waitForFunction(() => document.querySelector('.pages')?.classList.contains('continuous'));
report.desktop.scrollPlaceholders = await page.locator('.page-shell').count();
await page.locator('#themeToggle').click();
report.desktop.theme = await page.locator('html').getAttribute('data-theme');
await page.screenshot({ path: resolve(output, 'desktop-reader.png') });
await desktop.close();

const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
const mobilePage = await mobile.newPage();
mobilePage.on('console', (message) => { if (message.type() === 'error') report.consoleErrors.push(`mobile: ${message.text()}`); });
mobilePage.on('pageerror', (error) => report.consoleErrors.push(`mobile: ${error.message}`));
await mobilePage.goto('http://127.0.0.1:8765/reader/', { waitUntil: 'networkidle' });
await mobilePage.waitForFunction(() => document.querySelectorAll('.book-row').length === 50);
await mobilePage.locator('#openLibrary').click();
await mobilePage.waitForTimeout(350);
report.mobile.drawerOpen = await mobilePage.locator('body').evaluate((body) => body.classList.contains('library-open'));
report.mobile.libraryBox = await mobilePage.locator('#library').boundingBox();
await mobilePage.locator('#searchInput').fill('怪物大师22');
report.mobile.filteredCount = await mobilePage.locator('.book-row').count();
await mobilePage.screenshot({ path: resolve(output, 'mobile-library.png') });
await mobilePage.locator('.book-row').first().click();
await mobilePage.locator('.page-shell canvas').waitFor({ state: 'visible', timeout: 60000 });
report.mobile.drawerClosedAfterOpen = await mobilePage.locator('body').evaluate((body) => !body.classList.contains('library-open'));
report.mobile.viewportOverflow = await mobilePage.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
report.mobile.canvas = await mobilePage.locator('.page-shell canvas').evaluate((canvas) => ({ width: canvas.clientWidth, height: canvas.clientHeight }));
await mobilePage.screenshot({ path: resolve(output, 'mobile-reader.png') });
await mobile.close();

await browser.close();
console.log(JSON.stringify(report, null, 2));

if (report.consoleErrors.length) process.exitCode = 1;
if (report.desktop.bookCount !== 50 || report.desktop.filteredCount !== 1) process.exitCode = 1;
if (!report.mobile.drawerOpen || report.mobile.libraryBox.x < -1 || !report.mobile.drawerClosedAfterOpen || report.mobile.viewportOverflow) process.exitCode = 1;
