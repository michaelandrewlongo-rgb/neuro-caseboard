/* Cycle-2 manual-equivalent checks that axe can't do: semantics, reduced-motion, keyboard focus.
   NODE_PATH=web/node_modules node gui-council/verify.cjs */
const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5174'
const shots = path.join(__dirname, 'shots', 'verify')
fs.mkdirSync(shots, { recursive: true })

;(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] })
  const out = []

  // 1. Semantics + keyboard (normal motion)
  let ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  let page = await ctx.newPage()
  await page.goto(BASE + '/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(600)
  const h1 = await page.$eval('h1', (el) => el.textContent?.trim()).catch(() => null)
  const h1Tag = await page.$eval('h1', (el) => el.tagName).catch(() => null)
  const skip = await page.$('a[href="#main"]')
  const mainEl = await page.$('main#main')
  out.push(['home <h1> present', h1Tag === 'H1', `<${h1Tag}> "${h1}"`])
  out.push(['skip link present', !!skip, ''])
  out.push(['main#main landmark', !!mainEl, ''])
  // keyboard: first Tab should land on the skip link
  await page.keyboard.press('Tab')
  const firstFocus = await page.evaluate(() => {
    const a = document.activeElement
    return a ? `${a.tagName}:${(a.getAttribute('href') || a.textContent || '').trim().slice(0, 20)}` : 'none'
  })
  out.push(['first Tab = skip link', firstFocus.startsWith('A:#main') || firstFocus.includes('#main'), firstFocus])
  await ctx.close()

  // 2. Reduced motion: BlurText renders static (single text node, no per-letter spans)
  ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' })
  page = await ctx.newPage()
  await page.goto(BASE + '/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(600)
  const blurSpanCount = await page.$$eval('.blur-text > span', (els) => els.length).catch(() => -1)
  const blurText = await page.$eval('.blur-text', (el) => el.textContent?.trim()).catch(() => null)
  out.push(['reduced-motion: BlurText static (0 child spans)', blurSpanCount === 0, `${blurSpanCount} spans, text="${blurText}"`])
  await page.screenshot({ path: path.join(shots, 'reduced-motion-home.jpg'), fullPage: true, type: 'jpeg', quality: 65 })

  // reduced-motion loader: role=status + aria-busy present, then screenshot
  await page.goto(BASE + '/ask', { waitUntil: 'networkidle' })
  await page.fill('input[type="text"]', 'blood supply of the lateral medulla')
  await page.click('button[type="submit"]')
  await page.waitForTimeout(1200)
  const statusRole = await page.$('[role="status"][aria-busy="true"]')
  const srOnly = await page.$eval('[role="status"] .sr-only', (el) => el.textContent?.trim().slice(0, 40)).catch(() => null)
  out.push(['loader role=status+aria-busy', !!statusRole, ''])
  out.push(['loader has sr-only summary', !!srOnly, srOnly || ''])
  await page.screenshot({ path: path.join(shots, 'reduced-motion-ask-loading.jpg'), fullPage: true, type: 'jpeg', quality: 65 })
  await ctx.close()

  await browser.close()

  console.log('\n=== Cycle 2 verification ===')
  let allPass = true
  for (const [name, pass, detail] of out) {
    if (!pass) allPass = false
    console.log(`  ${pass ? '✓' : '✗ FAIL'}  ${name}${detail ? '  — ' + detail : ''}`)
  }
  console.log(allPass ? '\nALL CHECKS PASS' : '\nSOME CHECKS FAILED')
  process.exit(allPass ? 0 : 1)
})().catch((e) => { console.error('FATAL', e); process.exit(2) })
