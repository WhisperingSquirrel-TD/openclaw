---
name: stackstone-talk-deck
description: Build self-contained Stackstone HTML talk decks with branded visuals, navigation, progress controls, and appropriate talk, demo, chart, or closing slides.
---

# Stackstone Talk Deck

Builds a single-file HTML presentation in the Stackstone visual style: warm cream/charcoal/amber palette, Playfair Display for headings, DM Sans for labels and body text, full-bleed slides that fade/slide between each other, and navigation via click, arrow keys, space bar (works with presentation remotes), and touch swipe.

The reference build is `references/template.html` — a working deck with every slide type below already implemented. **Copy this file as the starting point for any new deck rather than building from scratch.** Strip out the slides that don't apply and adapt the content.

## Workflow

1. Copy `references/template.html` to the output location and rename it for the new talk.
2. Work out the talk's section structure first (a loose script with timings, if Tom hasn't already provided one).
3. For each section, pick the closest-matching slide type from the catalogue below, duplicate that block, and edit the text.
4. Keep the title slide and closing/contact slide — update the talk title, date, event name, and regenerate the QR code if the destination URL has changed (see "Contact slide" below).
5. Renumber the HTML comments (`<!-- N LABEL -->`) as slides are added/removed — they're just navigation aids for editing, not functional.
6. Test by opening in a browser: click through with arrow keys, check it works at a narrow window width (small presentation screens), and check the QR code scans correctly if present.
7. Save to `/mnt/user-data/outputs/` and present to Tom.

## Design tokens

```css
:root{
  --ch:#3D3A38;   /* charcoal — primary text on light slides */
  --ch2:#2C2A28;  /* deep charcoal — dark slide background base */
  --sl:#5C5652;   /* slate — body text */
  --am:#CA9449;   /* amber — accent, links, highlights */
  --amB:#D4A55A;  /* amber bright — accent on dark slides */
  --amG:rgba(202,148,73,.2); /* amber glow — highlight backgrounds */
  --cr:#F5F3EF;   /* cream — light slide background, text on dark */
  --ww:#FAF9F7;   /* warm white — alternate light background */
  --mt:#8A8480;   /* muted — secondary text */
  --stL:#B8B0A8;  /* stone light — muted text on dark slides */
  --rl:rgba(202,148,73,.4); /* rule line colour */
}
```

Fonts: `Playfair Display` (headings, serif body) + `DM Sans` (labels, UI text, numbers). Both loaded from Google Fonts in the `<head>`.

## Slide background classes

Every slide is a `<div class="s [background-class]">`. Alternate backgrounds to create rhythm — don't run more than two of the same type in a row.

- **`.bc`** — flat cream (`--cr`). Default light slide.
- **`.bw`** — warm gradient (`--ww` to `#EDE8E0`). Slightly warmer alternative to `.bc`, useful for variety.
- **`.bd`** — dark gradient (charcoal to slate) with subtle noise texture. Add `data-d="1"` to the slide div — this flags it as dark for the progress counter and watermark colour logic. Use for section dividers, big stats, and emphasis moments.
- **`.ba`** — amber gradient. Also needs `data-d="1"`. Use sparingly — for section openers or the call-to-action, not more than 2-3 times per deck.

## Slide type catalogue

All slide types live inside `<div class="s [bg-class]">...</div>`. Reference the corresponding numbered slide in `template.html` for exact markup.

### 1. Title slide
Stackstone logo (inline SVG, see "Logo SVG" below), `<h1>` with talk title (use `<span class="ac">` for the accent word), speaker name, event/date in `.mt`. Background `.bd`.

### 2. Simple statement / section opener
`.lb` label, `<h1>` headline (often split across two lines with `<br>`, accent word in `<span class="ac">`), optional `<hr class="rl">`, optional `<h3>` subtext. Works on any background. Section dividers typically use `.bd` or `.ba` with minimal text — just the label and headline.

### 3. Question list
```html
<ol class="ql">
<li><span class="nm">01</span> Question text here?</li>
<li><span class="nm">02</span> Next question?</li>
</ol>
```
Numbered list with amber numerals and rule lines between items. Good for "questions for the room" or enumerated points.

### 4. Big stat
```html
<div class="lb">Context label</div>
<div class="sn">88%</div>
<div class="sc">what the stat <span class="ac">means</span></div>
<div class="sr">Source citation, year</div>
```
`.sn` is a huge number (scales up to ~13rem). `.sc` is the explanatory line underneath in Playfair italic-weight serif. `.sr` is a small muted source citation — always include sources for stats.

For stats with a secondary supporting figure, follow with a `<hr>` rule (amber, 30% opacity, no class needed — inline style) then a `.lb` sub-label and `<p>` — see template slide 19/20 pattern for "the bar chart is one finding, the stats below are another."

### 5. Example card (with trust/caution aside)
```html
<div class="ec">
<div class="lb">01 — Short framing label</div>
<h2>Example title<br>across two lines</h2>
<div class="sn2">Main explanatory paragraph, left-bordered in amber.</div>
<div class="ta">⚠ Caution/trust note — highlighted amber background box.</div>
</div>
```
Used for "here's a practical example, and here's the caveat that goes with it." The `.ta` box auto-prefixes a warning emoji.

### 6. Three/four-item grid
```html
<div class="lb">Section label</div>
<div class="fg">
<div class="fi"><h3>Item title <span class="ac">accent</span></h3><p>Description.</p></div>
<div class="fi">...</div>
<div class="fi">...</div>
</div>
```
`.fg` auto-fits items into columns based on available width (responsive). **For exactly 4 items that must render as a 2×2 grid regardless of width** (rather than auto-fitting to 4-across or 1-across), override with an inline style:
```html
<div class="fg" style="grid-template-columns:repeat(2,1fr);max-width:52rem">
```
This was the fix applied for the "next twelve months" slide — use it whenever a grid has an even number of items that should pair up rather than reflow unpredictably.

### 7. Trust / numbered layer slide
```html
<div class="s bc" style="align-items:flex-start">
<div class="tn">1</div>
<div class="tc" style="padding-left:clamp(2rem,6vw,6rem);padding-top:clamp(3.5rem,7vw,6rem)">
<div class="lb">Question one</div>
<h2>Heading</h2>
<div class="ss"></div>
<p>Body text.</p>
</div>
</div>
```
`.tn` is a huge faint background numeral (positioned absolutely, top-left). `.tc` is the left-aligned content block offset to sit next to/below it. Use for sequential frameworks ("three questions to ask," "three layers of trust").

### 8. Demo / prompt box
```html
<div class="lb">Let me show you</div>
<h2>Headline</h2>
<div class="dp">Prompt or command text<br>on multiple lines<span class="cu"></span></div>
<div class="sp"></div>
<p class="mt">Context line underneath</p>
```
`.dp` renders as a dark monospace terminal-style box with a blinking cursor (`.cu`). Use on `.bd` background for live demo setup slides.

### 9. Perception / proportion bar
```html
<div class="pb"><div class="pos">36%</div><div class="neg">27%</div><div class="und">37%</div></div>
<div class="pb-labels"><span class="pos">Positive</span><span class="neg">Negative</span><span class="und">Unsure</span></div>
```
Three-segment horizontal bar with explicit percentage widths (must sum sensibly — widths are hardcoded per-class, so for a different split you'll need to either reuse 36/27/37 or add new width values inline). Good for sentiment/survey splits.

### 10. Trajectory (sequence of numbers)
```html
<div class="tj">
<div class="yr"><div class="num" style="font-size:...">61%</div><div class="y">2024</div></div>
<div class="arrow">→</div>
<div class="yr"><div class="num" style="font-size:...">76%</div><div class="y">2025</div></div>
<div class="arrow">→</div>
<div class="yr"><div class="num" style="font-size:...">88%</div><div class="y">2026</div></div>
</div>
```
Increase the `font-size` of `.num` for each step to visually emphasise growth (smallest first number, largest last). Use on `.bd`.

### 11. Closing / contact slide

Standard pattern: Stackstone logo SVG, "Thank you" `<h2>`, speaker name in `.ac`, contact email in `.mt`/`.stL`, then a QR code block:

```html
<div class="sp"></div>
<div style="display:flex;flex-direction:column;align-items:center;gap:.6rem">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 41 41" style="width:clamp(90px,12vw,140px);height:auto;background:#F5F3EF;padding:6px;border-radius:6px">
<path fill="#F5F3EF" d="M0,0h41v41H0z"/>
<path fill="#3D3A38" d="[QR PATH DATA]"/>
</svg>
<p style="color:var(--amB);font-family:'DM Sans',sans-serif;font-size:clamp(.85rem,1.4vw,1.05rem);letter-spacing:.03em;font-weight:600">stackstoneconsulting.co.uk/connect</p>
</div>
```

**Generating the QR path data:**
```python
import qrcode
from qrcode.image.svg import SvgPathImage
import re

qr = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
qr.add_data('https://stackstoneconsulting.co.uk/connect')  # update URL as needed
qr.make(fit=True)
img = qr.make_image(image_factory=SvgPathImage)
img.save('/tmp/qr.svg')

with open('/tmp/qr.svg') as f:
    content = f.read()
path = re.search(r'd="([^"]*)"', content).group(1)
viewbox = re.search(r'viewBox="([^"]*)"', content).group(1)
print(viewbox)  # confirm it's "0 0 41 41" — adjust the SVG viewBox above if different
print(path)
```
Install with `pip install qrcode[pil] --break-system-packages` if not already available. Paste the resulting `path` string into the `d=` attribute and update `viewBox` if it differs from `0 0 41 41`.

**The contact destination convention** is a single dedicated page (e.g. `stackstoneconsulting.co.uk/connect`) with one-tap "Connect on LinkedIn" and "Email me" buttons — not a form. Keep the slide to one URL only (don't also spell out the base domain separately — it reads as cluttered).

## Adding visual content (screenshots, charts, photos)

The deck is designed text-first, but slides can carry images. Three patterns:

**A. Full-bleed image slide** — for screenshots, diagrams, or photos that should dominate the slide:
```html
<div class="s bc">
<div class="lb">Context label</div>
<img src="data:image/png;base64,..." style="max-width:90%;max-height:60vh;border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.12);margin-top:1rem">
<p class="mt" style="margin-top:1rem;font-size:clamp(.8rem,1.2vw,1rem)">Caption text</p>
</div>
```
Embed images as base64 data URIs so the deck remains a single portable file — don't reference external file paths. Convert with:
```bash
base64 -w0 image.png
```
then `src="data:image/png;base64,<output>"` (use the correct MIME type for the source format — `image/jpeg`, `image/svg+xml`, etc).

**B. Image alongside text (split layout)** — for a chart with commentary:
```html
<div class="s bw">
<div style="display:flex;align-items:center;gap:clamp(2rem,4vw,4rem);max-width:64rem;width:100%;text-align:left">
  <div style="flex:1">
    <div class="lb">Label</div>
    <h2>Heading</h2>
    <p>Supporting text.</p>
  </div>
  <div style="flex:1">
    <img src="data:image/png;base64,..." style="width:100%;border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.1)">
  </div>
</div>
</div>
```
Add `@media(max-width:700px){ flex-direction:column }` via an inline `<style>` block in `<head>` if the deck needs to support very narrow screens with split layouts — or just avoid split layouts if narrow-screen support is critical, since the rest of the deck is built to stack content vertically by default.

**C. Native SVG charts** — for simple bar/line charts, prefer hand-built inline SVG over images (crisper at any size, matches the palette exactly). Use the design tokens above for fill colours (`--am`, `--sl`, `--stL`, etc — note CSS variables work in inline SVG `fill` attributes via `style="fill:var(--am)"` but not in bare `fill="var(--am)"` attributes, so use `style=` for token colours). The `.pb` (perception bar) and `.tj` (trajectory) components are existing examples of this approach — extend the same pattern for new chart types rather than reaching for an image.

**General rules for visual content:**
- Always pair an image with a `.lb` label and/or short caption so it doesn't sit unexplained.
- Cap image height at roughly `60vh` so it never pushes off-slide on short/wide screens.
- Add a subtle shadow (`box-shadow:0 8px 30px rgba(0,0,0,.1)`) and `border-radius:8px` to screenshots so they feel intentional rather than pasted-in.
- If a screenshot has its own background colour that clashes, consider placing it on `.bc` or `.bw` rather than `.bd`/`.ba`.

## Logo SVG

The Stackstone cairn logo (stacked stones + amber circle) is embedded inline as SVG on the title and closing slides, with a glow filter on the amber piece. Copy the exact markup from `references/template.html` slides 1 and 26 (search for `STACKSTONE` in the file) — it includes a `<filter>` with a unique `id` per instance (`g1`, `g2`, etc — **increment the id if adding more logo instances**, since duplicate SVG filter IDs can cause rendering issues in some browsers).

A small monochrome version of the logo also appears as a `.wm` (watermark) element in the corner of every slide except the first and last — this is shared across the whole deck via the JS (see below), not per-slide.

## Navigation & structure (don't need to rebuild — copy as-is)

The `<script>` block at the end of `template.html` handles:
- Click anywhere (right 70% of screen advances, left 30% goes back)
- Arrow keys / space / page up/down
- Home/End to jump to first/last slide
- `F` to toggle fullscreen
- Touch swipe (mobile/tablet)
- Progress bar (`.pr`) at the bottom
- Slide counter (`.ct`) bottom-right, switches colour for dark slides via `data-d="1"`
- Watermark logo (`.wm`) top-right, hidden on first/last slide, switches colour for dark slides

This script reads `.s` elements in document order — no slide numbering/indexing needed beyond getting the HTML comments right for human navigation. Just keep the script block unchanged when copying the template.

## Responsive sizing

All typography uses `clamp(min, preferred-vw, max)` so the deck scales from small laptop screens up to large projectors without separate breakpoints for most elements. Two explicit breakpoints exist:
- `@media(max-width:600px)` — tighter padding and smaller big-stat numbers for phone-sized previews
- `@media(min-aspect-ratio:2.2/1)` — reduced horizontal padding for ultra-wide displays

If a new slide type needs its own size tuning, follow the existing `clamp()` pattern rather than fixed pixel/rem values — this is what makes the deck work on "I don't know what screen I'll be presenting on."

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
