/* Capture REAL result reading-surfaces (slow engine calls) for the before/after report.
   NODE_PATH=web/node_modules node gui-council/capture-results.cjs */
const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5174'
const shots = path.join(__dirname, 'shots', 'results')
fs.mkdirSync(shots, { recursive: true })

const JOBS = [
  { name: 'cards-result', route: '/cards', q: 'cavernous sinus contents', timeout: 90000 },
  { name: 'ask-result', route: '/ask', q: 'blood supply of the lateral medulla', timeout: 180000 },
  { name: 'build-result', route: '/build', q: 'right carotid endarterectomy', timeout: 300000 },
]

;(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] })
  for (const j of JOBS) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 })
    const page = await ctx.newPage()
    try {
      await page.goto(BASE + j.route, { waitUntil: 'networkidle' })
      await page.fill('input[type="text"]', j.q)
      await page.click('button[type="submit"]')
      // result arrives when the loading status region detaches
      await page.waitForSelector('[role="status"][aria-busy="true"]', { state: 'detached', timeout: j.timeout })
      await page.waitForTimeout(1200)
      await page.screenshot({ path: path.join(shots, j.name + '.jpg'), fullPage: true, type: 'jpeg', quality: 62, scale: 'css' })
      console.log(`  ✓ ${j.name} captured`)
    } catch (e) {
      await page.screenshot({ path: path.join(shots, j.name + '-timeout.jpg'), fullPage: true, type: 'jpeg', quality: 62 }).catch(() => {})
      console.log(`  ✗ ${j.name}: ${e.message.split('\n')[0]}`)
    }
    await ctx.close()
  }
  await browser.close()
  console.log('DONE → ' + shots)
})().catch((e) => { console.error('FATAL', e); process.exit(1) })
