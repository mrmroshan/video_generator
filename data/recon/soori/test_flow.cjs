const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = 'D:/MY_PROJECTS/VIDEO MAKER/data/recon/soori';
fs.mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
  });
  const page = await ctx.newPage();

  const shot = async (name) => {
    await page.screenshot({ path: path.join(OUT, name), fullPage: true });
    console.log('  📸 ' + name);
  };

  const dump = async (label) => {
    // Collect a structured DOM map of interactive elements
    const elems = await page.evaluate(() => {
      const out = [];
      const sel = 'button, a, input, textarea, select, [role="button"], [contenteditable="true"]';
      document.querySelectorAll(sel).forEach((el, i) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        out.push({
          i,
          tag: el.tagName.toLowerCase(),
          type: el.getAttribute('type') || '',
          text: (el.innerText || el.value || '').trim().slice(0, 60),
          placeholder: el.getAttribute('placeholder') || '',
          name: el.getAttribute('name') || '',
          id: el.id || '',
          cls: (el.className && typeof el.className === 'string') ? el.className.slice(0, 60) : '',
        });
      });
      return out;
    });
    console.log(`\n=== ${label} === (${elems.length} interactive elements)`);
    elems.forEach(e => console.log(`  [${e.i}] <${e.tag}${e.type ? ' type=' + e.type : ''}> "${e.text || e.placeholder || e.name || e.id}"`));
    fs.writeFileSync(path.join(OUT, `dom_${label.replace(/[^a-z0-9]+/gi, '_')}.json`), JSON.stringify(elems, null, 2));
    return elems;
  };

  console.log('🌐 Opening site...');
  await page.goto('https://sooripostcreator.com/', { waitUntil: 'networkidle', timeout: 45000 });
  await shot('01_landing.png');
  const title = await page.title();
  console.log('Title:', title);

  // Full text of the page
  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '00_full_page_text.txt'), bodyText);
  console.log('\n--- FULL PAGE TEXT ---\n' + bodyText + '\n--- END ---\n');

  const elems1 = await dump('landing');

  // Step 1: News description textarea
  console.log('\n📝 Step 1: Fill news description...');
  const textareas = await page.$$('textarea');
  console.log('textareas found:', textareas.length);
  if (textareas.length > 0) {
    await textareas[0].fill('A new study finds that adults over 50 who walk 20 minutes a day after dinner cut their risk of heart disease by nearly a third, and doctors say the benefit shows up within weeks — no gym, no equipment, just a habit anyone can start tonight.');
    await shot('02_news_filled.png');
  } else {
    console.log('  ⚠️ no textarea found');
  }

  // Look for a "next" / continue button after step 1
  const buttons1 = await page.$$('button');
  console.log('buttons on page:', buttons1.length);
  for (const b of buttons1) {
    const t = (await b.innerText()).trim().slice(0, 40);
    console.log('  button:', JSON.stringify(t));
  }

  // Try to find the headline step
  console.log('\n✍️ Step 2: Headline picker...');
  // Look for headline options / angle buttons
  const angleInfo = await page.evaluate(() => {
    const out = [];
    // Common patterns: radio groups, option cards
    document.querySelectorAll('[class*="headline"], [class*="angle"], [class*="option"], [class*="choice"]').forEach(el => {
      out.push({ cls: el.className, text: (el.innerText || '').trim().slice(0, 100) });
    });
    return out;
  });
  angleInfo.slice(0, 20).forEach(a => console.log('  angle elem:', JSON.stringify(a)));
  await shot('03_headline_step.png');

  // Step 4: templates
  console.log('\n🎨 Step 4: Templates (7 layouts)...');
  const templateInfo = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('[class*="template"], [class*="layout"], [class*="tpl"]').forEach(el => {
      out.push({ cls: el.className, text: (el.innerText || '').trim().slice(0, 80) });
    });
    return out;
  });
  templateInfo.slice(0, 30).forEach(t => console.log('  template elem:', JSON.stringify(t)));
  await shot('04_templates.png');

  // Step 5: size
  console.log('\n📐 Step 5: Size / feed format...');
  const sizeInfo = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('[class*="size"], [class*="format"], [class*="portrait"], [class*="square"]').forEach(el => {
      out.push({ cls: el.className, text: (el.innerText || '').trim().slice(0, 80) });
    });
    return out;
  });
  sizeInfo.slice(0, 20).forEach(s => console.log('  size elem:', JSON.stringify(s)));
  await shot('05_size.png');

  // Grab all script srcs / links to understand the stack
  const stack = await page.evaluate(() => {
    return {
      scripts: [...document.querySelectorAll('script[src]')].map(s => s.src),
      links: [...document.querySelectorAll('link[rel="stylesheet"]')].map(l => l.href),
      meta: [...document.querySelectorAll('meta')].map(m => ({ name: m.name || m.property, content: m.content })).filter(m => m.content),
    };
  });
  fs.writeFileSync(path.join(OUT, 'stack.json'), JSON.stringify(stack, null, 2));
  console.log('\n🔧 Stack:');
  console.log('  scripts:', stack.scripts);
  console.log('  styles:', stack.links);

  await browser.close();
  console.log('\n✅ Recon complete. Artifacts saved to', OUT);
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
