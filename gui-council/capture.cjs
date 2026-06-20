/* GUI Council capture+audit harness.
   Screenshots every surface at 1280w and 390w (default state) plus a loading-state
   shot for each async route, and runs axe-core (WCAG 2.0/2.1/2.2 A+AA + best-practice)
   on each. Reusable every cycle for before/after evidence.

   Run from the worktree with web/node_modules on NODE_PATH (CJS resolves it):
     NODE_PATH=web/node_modules LABEL=baseline node gui-council/capture.cjs
   Env: BASE_URL (default http://127.0.0.1:5174), LABEL (subdir), OUT_DIR. */
const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')
const AxePkg = require('@axe-core/playwright')
const AxeBuilder = AxePkg.default || AxePkg.AxeBuilder || AxePkg

const BASE = process.env.BASE_URL || 'http://127.0.0.1:5174'
const OUT = process.env.OUT_DIR || path.resolve(__dirname)
const LABEL = process.env.LABEL || 'baseline'
const shotsDir = path.join(OUT, 'shots', LABEL)
const axeDir = path.join(OUT, 'axe', LABEL)
fs.mkdirSync(shotsDir, { recursive: true })
fs.mkdirSync(axeDir, { recursive: true })

const ROUTES = [
  { name: 'home', path: '/' },
  { name: 'ask', path: '/ask' },
  { name: 'build', path: '/build' },
  { name: 'cards', path: '/cards' },
]
const WIDTHS = [1280, 390]
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']
const HINTS = {
  ask: 'blood supply of the lateral medulla',
  build: 'right carotid endarterectomy',
  cards: 'cavernous sinus contents',
}

function summarize(results) {
  const byImpact = { critical: 0, serious: 0, moderate: 0, minor: 0, null: 0 }
  for (const v of results.violations) {
    const k = v.impact || 'null'
    byImpact[k] += v.nodes ? v.nodes.length : 1
  }
  return byImpact
}

async function capture(browser, { tag, url, width, prep }) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 })
  const page = await context.newPage()
  const consoleErrors = []
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message))
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 }).catch((e) => consoleErrors.push('goto: ' + e.message))
  await page.waitForTimeout(700)
  if (prep) await prep(page, consoleErrors)
  await page.screenshot({ path: path.join(shotsDir, tag + '.jpg'), fullPage: true, type: 'jpeg', quality: 65, scale: 'css' })
  let sum = null
  try {
    const axe = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze()
    fs.writeFileSync(path.join(axeDir, tag + '.json'), JSON.stringify({ violations: axe.violations }, null, 2))
    sum = summarize(axe)
  } catch (e) { consoleErrors.push('axe: ' + e.message) }
  await context.close()
  return { tag, sum, consoleErrors }
}

;(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] })
  const rows = []
  for (const width of WIDTHS) {
    for (const route of ROUTES) {
      rows.push(await capture(browser, { tag: `${route.name}-${width}`, url: BASE + route.path, width }))
    }
  }
  for (const route of ['ask', 'build', 'cards']) {
    rows.push(await capture(browser, {
      tag: `${route}-1280-loading`, url: BASE + '/' + route, width: 1280,
      prep: async (page, errs) => {
        await page.fill('input[type="text"]', HINTS[route]).catch((e) => errs.push('fill: ' + e.message))
        await page.click('button[type="submit"]').catch((e) => errs.push('click: ' + e.message))
        await page.waitForTimeout(1300) // loader is up; slow response not back yet
      },
    }))
  }
  await browser.close()

  console.log('\n=== AXE violations (failing-node count by impact) + console state ===')
  for (const r of rows) {
    const s = r.sum
    const sstr = s ? `crit ${s.critical} | serious ${s.serious} | mod ${s.moderate} | minor ${s.minor}` : 'AXE FAILED'
    console.log(`  ${r.tag.padEnd(22)} ${sstr}` + (r.consoleErrors.length ? `  ⚠ console(${r.consoleErrors.length})` : '  ✓ console clean'))
  }
  console.log('\n=== Unique violation rules per surface (1280 default) ===')
  for (const route of ROUTES) {
    const f = path.join(axeDir, `${route.name}-1280.json`)
    if (fs.existsSync(f)) {
      const j = JSON.parse(fs.readFileSync(f))
      const ids = j.violations.map((v) => `${v.id}(${v.impact}×${v.nodes.length})`)
      console.log(`  ${route.name}: ${ids.join(', ') || 'none'}`)
    }
  }
  const anyErr = rows.filter((r) => r.consoleErrors.length)
  if (anyErr.length) {
    console.log('\n=== Console error detail ===')
    for (const r of anyErr) { console.log(`  [${r.tag}]`); r.consoleErrors.forEach((e) => console.log('     ' + e)) }
  }
  console.log('\nDONE → shots:', shotsDir, '| axe:', axeDir)
})().catch((e) => { console.error('FATAL', e); process.exit(1) })
