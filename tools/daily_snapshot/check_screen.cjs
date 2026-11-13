// 배포본 화면 점검 — 오류 · 가로 스크롤 · MARKET NOW 선택 블록 · 금리 탭 이벤트 수집일. 스크린샷을 남긴다.
// 사용: node tools/daily_snapshot/check_screen.cjs <http://127.0.0.1:PORT/index.html> <screenshot.jpg>
const { chromium } = require('playwright');  // 환경에 설치된 playwright(어느 폴더에서나 require 로 찾는다)
(async () => {
const [url, shot] = process.argv.slice(2);
const b = await chromium.launch(); const errs = [];
const p = await b.newPage({ viewport: { width: 1366, height: 900 } });
p.on('pageerror', e => errs.push(e.message));
await p.goto(url); await p.waitForTimeout(3000);
if (shot) await p.screenshot({ path: shot, fullPage: true, type: 'jpeg', quality: 60 });
console.log(JSON.stringify(await p.evaluate(() => ({ now: document.querySelector('[data-testid="ck-now-label"]')?.textContent, rs: document.querySelector('[data-testid="ck-rs"]')?.innerText.slice(0, 300), noregime: document.body.innerText.includes('NO REGIME') }))));
for (const tab of ['금리', '유가', 'AI 센티', '반도체 사이클']) {
  await p.locator(`button:has-text("${tab}")`).first().click(); await p.waitForTimeout(1200);
  console.log(tab, JSON.stringify(await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }))));
}
await p.locator('button:has-text("금리")').first().click(); await p.waitForTimeout(1200);
console.log('events', await p.evaluate(() => document.querySelector('[data-testid="policy-macro-events"]')?.innerText.match(/수집 [0-9-]+/)?.[0]));
console.log('errors', JSON.stringify(errs)); await b.close();
})();
