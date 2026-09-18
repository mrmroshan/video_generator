# Soori Lifestyle Post Creator — Capability Recon & Feature Test

Target: https://sooripostcreator.com/
Goal: Drive the full flow end-to-end with Playwright, generate a test post, and document every feature/step so we can replicate it in our own tool (D:/MY_PROJECTS/VIDEO MAKER).

## What this tool does (from initial scrape)
A 5-step Facebook post creator for a 45-80 lifestyle audience:
1. News description → paste a story (or generate via Claude/ChatGPT/Gemini, free, no key)
2. Pick a headline (4 angles)
3. The picture (generate a brief, then generate photo — runs on Pollinations, free)
4. Template (7 layouts)
5. Size (Feed format — portrait/square)

## Your task
1. Write and run a Playwright script (Chromium, headless) that:
   - Opens https://sooripostcreator.com/
   - Maps the full DOM: every step, button, input, select, radio, textarea
   - Walks the flow with a realistic test story (e.g. a lifestyle/health news item for a 45-80 audience)
   - Clicks through all 7 template layouts (screenshot each)
   - Tests both size options (portrait + square), screenshot each
   - Generates the headline via the 4-angle picker
   - Captures the image-generation step (Pollinations) — note if it actually returns an image or needs manual paste
   - Records the final "post" output — download the image, screenshot the result
2. Save ALL screenshots to D:/MY_PROJECTS/VIDEO MAKER/data/recon/soori/ (numbered, e.g. 01_landing.png, 02_headline.png, etc.)
3. Write a capabilities document to D:/MY_PROJECTS/VIDEO MAKER/data/recon/soori/CAPABILITIES.md covering:
   - Full step-by-step flow
   - Every UI element and its function
   - The 7 template layouts (describe each: what text/image positions, fonts, colors, logo placement)
   - The 4 headline angles (what each emphasizes)
   - Size options + guidance text
   - The image pipeline (Pollinations → how the brief maps to the image)
   - How headline/caption text is assembled into the final post
   - What we can replicate in our video generator (which parts map to our script→scene→broll→render pipeline, which are post-specific and new)

## Technical notes
- Node + Playwright 1.63 + Chromium already installed.
- Use `require('playwright')` in a CommonJS .cjs script, or ESM — your choice.
- Run from D:/MY_PROJECTS/VIDEO MAKER.
- Save the playwright script itself to D:/MY_PROJECTS/VIDEO MAKER/data/recon/soori/test_flow.cjs so we can re-run it.
- The site may require network; if a step needs an account or key, note it and skip gracefully — do NOT guess credentials.
- Be thorough and concrete in CAPABILITIES.md — this is a blueprint for us to clone the tool.
