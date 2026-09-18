const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = 'D:/MY_PROJECTS/VIDEO MAKER/data/recon/soori';
fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const shot = async n => { await page.screenshot({ path: path.join(OUT, n), fullPage: true }); console.log('  📸 ' + n); };

  console.log('🌐 Load...');
  await page.goto('https://sooripostcreator.com/', { waitUntil: 'networkidle', timeout: 45000 });

  // Step 1: fill story
  const ta = await page.$$('textarea');
  await ta[0].fill('A new study finds that adults over 50 who walk 20 minutes a day after dinner cut their risk of heart disease by nearly a third, and doctors say the benefit shows up within weeks.');
  await sleep(300);

  // Step 2: skip to manual headline entry
  console.log('\n✍️ Step 2: manual headline entry (bypass Claude API)');
  await page.getByRole('button', { name: /Skip — I'll write my own/i }).click();
  await sleep(500);
  await shot('11_manual_headline_form.png');

  // Fill manual headlines textarea
  const manualTa = await page.$$('textarea');
  // Find the one with placeholder about "four headlines"
  const manual = await page.getByPlaceholder(/four headlines/i);
  if (await manual.count()) {
    await manual.fill(`1. The 20-Minute Walk That Could Add Years to Your Life\n2. After Dinner, Do This For Your Heart\n3. Doctors Stunned by What a Simple Walk Can Do\n4. No Gym. No Cost. Just a Walk — and Your Heart Will Thank You`);
    await sleep(300);
    await shot('12_manual_headlines_filled.png');
    await page.getByRole('button', { name: /use-manual|Use this|Use headlines/i }).click().catch(() => {});
    await sleep(500);
  } else {
    console.log('  ⚠️ manual headline textarea not found, dumping textareas:');
    for (let i = 0; i < (await page.$$('textarea')).length; i++) {
      const t = (await page.$$('textarea'))[i];
      console.log(`    [${i}] placeholder=`, await t.getAttribute('placeholder'));
    }
  }
  await shot('13_headlines_accepted.png');

  // Step 2b: pick headline (4 angles) — look for angle options
  console.log('\n✍️ Step 2b: pick headline angle');
  const angleBtns = await page.evaluate(() => {
    return [...document.querySelectorAll('button')].map(b => (b.innerText || '').trim()).filter(t => t && t.length < 120);
  });
  console.log('  visible buttons:', JSON.stringify(angleBtns.filter(t => !/Next|Skip|Download|Start over|Browse|Copy|Use this|Generate|Save|MP4|JPG|PNG|Write|Draft|chat|poll|Débat|frame|Question|bar|Kicker|Big/i.test(t)).slice(0, 20), null, 2));
  await shot('14_headline_angles.png');

  // Step 3: picture — generate brief + photo
  console.log('\n🖼️ Step 3: picture');
  const nextPic = await page.getByRole('button', { name: /Next: the picture/i });
  if (await nextPic.count()) {
    await nextPic.click();
    await sleep(500);
    await shot('15_picture_step.png');
    const genBtn = await page.getByRole('button', { name: /Generate the photo/i });
    if (await genBtn.count()) {
      await genBtn.click();
      try { await page.waitForSelector('img', { timeout: 40000 }); console.log('  ✅ image generated (Pollinations)'); }
      catch { console.log('  ⚠️ no image after 40s'); }
      await shot('16_photo.png');
    }
  }

  // Step 4: templates — click all 7 and screenshot
  console.log('\n🎨 Step 4: 7 templates');
  const nextTpl = await page.getByRole('button', { name: /Next: template/i });
  if (await nextTpl.count()) { await nextTpl.click(); await sleep(500); }
  await shot('17_template_step.png');

  const tplButtons = await page.evaluate(() => {
    return [...document.querySelectorAll('button')].map(b => (b.innerText || '').trim()).filter(t => /poll|Débat|frame|Question|bar|Kicker|Big|Yellow|Caption|Panel|Badge|gold|black|navy|tricolor/i.test(t));
  });
  console.log('  template buttons:', JSON.stringify(tplButtons, null, 2));

  // Click each template button by index
  const allButtons = await page.$$('button');
  let tplCount = 0;
  for (const b of allButtons) {
    const txt = (await b.innerText()).trim();
    if (/poll|Débat|frame|Question|bar|Kicker|Big|Yellow|Caption|Panel/i.test(txt) && txt.length < 60) {
      await b.click().catch(() => {});
      await sleep(500);
      tplCount++;
      await shot(`20_template_${tplCount}.png`);
      console.log(`  template ${tplCount}: "${txt}"`);
    }
  }

  // Step 5: sizes
  console.log('\n📐 Step 5: sizes');
  const nextSize = await page.getByRole('button', { name: /Next: size/i });
  if (await nextSize.count()) { await nextSize.click(); await sleep(400); }
  const sq = await page.getByRole('button', { name: /1:1 square/i });
  if (await sq.count()) { await sq.click(); await sleep(400); await shot('30_size_square.png'); }
  const pt = await page.getByRole('button', { name: /3:4 portrait/i });
  if (await pt.count()) { await pt.click(); await sleep(400); await shot('31_size_portrait.png'); }

  // Final
  await shot('40_final_preview.png');

  // Download PNG
  const dl = await page.getByRole('button', { name: /Download PNG/i });
  if (await dl.count()) {
    try {
      const [download] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }).catch(() => null), dl.click()]);
      if (download) { const dest = path.join(OUT, 'final_post.png'); await download.saveAs(dest); console.log('  ✅ downloaded final_post.png (' + fs.statSync(dest).size + ' bytes)'); }
    } catch (e) { console.log('  ⚠️ download failed:', e.message.split('\n')[0]); }
  }

  await browser.close();
  console.log('\n✅ E2E (manual path) complete.');
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
