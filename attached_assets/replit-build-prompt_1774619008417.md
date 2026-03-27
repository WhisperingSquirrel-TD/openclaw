# Replit build prompt — Stackstone Networking Report System
# Hand this to Replit as a single prompt. It knows the existing codebase.

---

I want to extend the existing Stackstone AI Briefing Pack tool into a more powerful
system designed specifically for use at networking events. Do not rebuild from scratch —
extend and improve what exists. Here is exactly what I need.

---

## Overview

The system captures a contact's details at a networking event (name, email, company
website), optionally records the conversation with their consent, and generates a
bespoke, deeply-researched AI opportunity report for that contact. The report is
served as a branded HTML page at a unique URL (/report/[uuid]) and emailed to the
contact as a link. Email sending is handled externally by a Raspberry Pi endpoint
(details below) — the website just calls it.

---

## New route: POST /api/intake

This is the main entry point. It receives:

```json
{
  "firstName": "Sarah",
  "lastName": "Jones",
  "email": "sarah@acmeltd.co.uk",
  "website": "acmeltd.co.uk",
  "transcript": "optional — raw text of recorded conversation"
}
```

### Step 1 — Server-side validation (hard stop)

Reject with 400 if any of the following fail. Return a JSON error listing exactly
what failed — do not guess or proceed with missing data.

- firstName: present, min 2 chars
- lastName: present, min 2 chars
- email: present, valid email format
- website: present, contains a dot, resolves (attempt a HEAD request — if it
  times out in 5s treat as unresolvable and reject)

### Step 2 — Companies House lookup

Use the Companies House public API (no auth required for basic search):
  GET https://api.company-information.service.gov.uk/search/companies?q={company_name}

Derive the company name from the website domain (strip TLD, capitalise).
For example acmeltd.co.uk → "Acme Ltd", stackstoneconsulting.co.uk → "Stackstone Consulting".

From the top result extract:
- Registered company name
- Company number
- SIC code(s) and their descriptions
- Company status (active / dissolved / etc)
- Incorporation date
- Approximate size if available

If the company status is not "active", log a warning but do not block — include a
note in the report. If no match is found, continue without it.

Companies House API key is stored in env var: COMPANIES_HOUSE_API_KEY

### Step 3 — Website deep fetch

Fetch the following pages if they exist (graceful 404 handling, 5s timeout each):
- / (homepage)
- /about (and /about-us)
- /services (and /what-we-do)
- /team (and /our-team)

From the combined HTML extract:
- Page title and meta description
- All visible body text (strip nav, footer boilerplate) — cap at 3000 chars total
- Meta theme-color tag value if present
- The two most prominent hex colour values found in inline styles or linked CSS
  (fetch the primary stylesheet, parse for colour values that appear more than
  3 times, exclude #fff, #ffffff, #000, #000000, and near-whites/near-blacks
  defined as lightness > 90% or < 10% in HSL). If you get a confident single
  dominant brand colour, store it. If ambiguous, store null.
- Any mentions of company size, headcount, founding year, clients, or technologies

### Step 4 — Claude report generation

Make a single Claude API call (claude-opus-4-5, max_tokens 3000).

System prompt:
```
You are a senior AI strategy consultant at Stackstone Consulting, an Oxfordshire-based
AI consultancy. You produce bespoke, intelligent AI opportunity reports for mid-market
UK businesses. Your reports are specific, credible, and immediately useful. You never
write generic content. Every claim must be grounded in the research provided.
Write in UK English. Be direct and confident. No buzzwords.
```

User prompt — build this dynamically from all gathered data:
```
Produce a structured AI opportunity report for the following contact and company.
Return ONLY a valid JSON object — no markdown, no preamble, no explanation.

## Contact
Name: {firstName} {lastName}
Email: {email}
Company website: {website}

## Companies House data
{companies_house_json_or "Not found"}

## Website research
{extracted_website_text}

## Conversation transcript
{transcript_or "No conversation recorded"}

## Required JSON structure
{
  "companyName": "string — confirmed or best-derived company name",
  "sector": "string — specific sector, not generic",
  "companySummary": "string — 2 sentences about what this company actually does, based on the website",
  "executiveSummary": "string — 3 sentences. Address {firstName} directly. Reference something specific from their website or the conversation. State the single most important AI opportunity for them.",
  "sectorContext": "string — 2 paragraphs. What is actually happening with AI in this specific sector right now? What are mid-market companies doing? What is the competitive risk of inaction? Be specific — name real use cases.",
  "primaryOpportunity": {
    "title": "string — give it a name, e.g. 'Automated invoice processing pipeline'",
    "description": "string — 3 paragraphs. What is it, how would it work for a company like theirs, what does it replace or augment, what does success look like?",
    "timeToValue": "string — realistic estimate e.g. '8–12 weeks to first working pilot'",
    "roiIndicator": "string — one sentence on expected ROI or cost impact"
  },
  "quickWins": [
    {
      "title": "string",
      "problem": "string — what specific problem this solves",
      "solution": "string — what the AI implementation looks like",
      "effort": "Low | Medium",
      "timeframe": "string e.g. '2–4 weeks'"
    }
  ],
  "caveats": ["string", "string", "string"],
  "transcriptInsights": "string or null — if a transcript was provided, pull out 1–2 specific things they mentioned that shaped these recommendations. If no transcript, null.",
  "brandColourUsed": "string or null — populated by the server, not Claude"
}

Produce exactly 3 quick wins. All content must be specific to this company and sector.
If the transcript contains specific pain points or priorities, weight the recommendations
toward those. Do not invent facts not supported by the research.
```

Parse the JSON response. If it fails to parse, retry once. If it fails again, return
a 500 with error detail.

Set brandColourUsed from the colour extracted in Step 3 (null if not found).

### Step 5 — Store the report

Save the complete report object to your database/store with:
- id: uuid v4
- createdAt: ISO timestamp
- contact: { firstName, lastName, email, website }
- hasTranscript: boolean
- report: the JSON object from Claude
- brandColour: extracted colour or null

### Step 6 — Notify the Pi to send the email

POST to the Pi's /send-report endpoint:

```json
{
  "to": { "email": "sarah@acmeltd.co.uk", "name": "Sarah Jones" },
  "reportUrl": "https://stackstoneconsulting.co.uk/report/{uuid}",
  "companyName": "Acme Ltd",
  "firstName": "Sarah"
}
```

Headers:
  Authorization: Bearer {INTAKE_SITE_SECRET}
  Content-Type: application/json

Env vars needed: PI_ENDPOINT_URL, INTAKE_SITE_SECRET

This call should be fire-and-forget with a 10s timeout. If it fails, log it but
still return success to the browser — the report page exists regardless.

Return 202 to the browser with { reportUrl, uuid } immediately after Step 5.
The Pi call happens async.

---

## New route: GET /report/[uuid]

Renders the HTML report page. This is what the contact sees when they click the link.

### Layout and design

Use the existing Stackstone brand system: charcoal (#2C2C2E), slate (#48484A),
amber (#D4A017) for rules and accents. Keep the existing header/footer style.

If brandColour is set, use it as a secondary accent throughout the report — section
header left-border, the primary opportunity card background tint, CTA button.
If null, use amber for everything.

### Page sections (in order)

1. Header — Stackstone logo + "AI Opportunity Report" + contact name + date

2. Amber rule line (full width, 3px)

3. Company summary block — company name, sector, a one-line description.
   If Companies House data is present: show company number, SIC, incorporation date
   in a small data strip. This signals that we've done real research.

4. Executive summary — large, prominent. This is the first thing they read.

5. "Your sector and AI" — the sectorContext field, rendered as two paragraphs.

6. Primary opportunity — full-width card with a coloured left border.
   Title as H2, then the three description paragraphs, then time-to-value and
   ROI indicator in a two-column stat strip.

7. Three quick wins — card grid (stack on mobile). Each card: title, problem,
   solution, effort badge (green=Low, amber=Medium), timeframe.

8. What to watch out for — the caveats, rendered as a simple list with a
   warning-tone left border.

9. Transcript insights block — only render if transcriptInsights is not null.
   Subtle callout box: "Based on our conversation..." This is the most personal
   part of the report and should feel that way.

10. PDF download button — triggers window.print() with a print stylesheet that
    removes the nav, header bar, and CTA button, and renders cleanly to A4.
    Label: "Download as PDF"

11. CTA footer — "Ready to take the next step?" with a mailto link to
    tom@stackstoneconsulting.co.uk pre-populated with subject line
    "Following up — AI opportunity for {companyName}"

---

## New route: POST /api/transcribe

Accepts a multipart/form-data upload with an audio field (webm or mp4, max 25MB).
Transcribes using OpenAI Whisper API (model: whisper-1).
Returns { transcript: "string" }.

Env var: OPENAI_API_KEY (for Whisper only — Claude calls use ANTHROPIC_API_KEY)

---

## Updates to the intake form page (existing page, extend it)

Add the following to the existing form:

### Recording section

Between the website field and the submit button, add:

A clearly labelled section: "Record conversation (optional)"

A consent note: "Only record with the contact's permission. Tap to start recording,
tap again to stop. The recording is transcribed and used only to personalise this report."

A single large record button. States:
- Idle: "Start recording" (grey)
- Recording: "Recording... tap to stop" (pulsing red border)
- Done: "Recording saved — transcript ready" (green)
- Error: "Recording failed — continue without it" (amber)

Implementation:
- Use the browser MediaRecorder API (audio/webm)
- On stop, POST the audio blob to /api/transcribe
- Store the returned transcript in a hidden form field
- The form submit should work with or without a transcript
- Do not block form submission if transcription fails — log the error, submit anyway

### Form fields

Replace the existing fields with exactly these (no more, no less):
- First name
- Last name  
- Email
- Company website (hint: "e.g. acmeltd.co.uk — no https needed")
- Hidden: transcript (populated by recording flow)

Remove any other fields that currently exist. The website is the research input —
we do not ask the contact for their sector, size, or pain points. We derive that.

---

## Env vars needed (add to Replit secrets)

ANTHROPIC_API_KEY         — existing
OPENAI_API_KEY            — for Whisper transcription
COMPANIES_HOUSE_API_KEY   — public API, get from developer.company-information.service.gov.uk
PI_ENDPOINT_URL           — full URL of L1's /send-report endpoint on the Pi
INTAKE_SITE_SECRET        — shared secret between site and Pi (you choose this)

---

## Pi endpoint (separate — do not build in Replit)

For reference: the Pi will expose POST /send-report which accepts the payload
described in Step 6 above, verifies the INTAKE_SITE_SECRET, and sends the email
via MS Graph from tom@stackstoneconsulting.co.uk. That endpoint is built separately.

---

## Quality bar

The existing briefing pack is a good starting point but the research pipeline is
shallow. This must feel meaningfully different:

- Companies House data should be visible in the report — it signals real due diligence
- The report should contain at least one sentence that could only have been written
  for this specific company (cite something from their website)
- If a transcript is present, at least one recommendation must reference it directly
- The brand colour extraction must be conservative — if in doubt, do not use it
- The print/PDF output must be clean A4 with no browser chrome artifacts

Do not add authentication, login, or any admin UI. Keep it simple. The report URL
is the access control — it is a long UUID that is not guessable.
