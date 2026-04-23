# Consulting Pitch Tool — Execution Plan

## What We're Building

A local web app that takes in a company name, URL, industry, proposed solution, outreach email draft, and club description — then generates a polished, personalized consulting pitch webpage and a matching cold outreach email. The output should feel like we already did real work for the company, not like a mail-merged template.

**Final deliverables:**
- The tool (Flask web app)
- 2–3 generated pitch pages for real companies
- 2–3 matching outreach emails
- A one-page system explanation

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python + Flask | Simple, local, easy to demo |
| AI | Claude API (`claude-opus-4-6` or `claude-sonnet-4-6`) | Best at tone-matching, avoids generic output |
| Scraping | `requests` + `BeautifulSoup4` | Pull real language from company websites |
| Frontend styling | Tailwind CSS via CDN | Modern, fast, no build step |
| Output format | Self-contained HTML file | Shareable as a link or attachment |
| Email generation | Claude API (same call or second prompt) | Consistent with page content |

---

## Phase 1: Project Setup

**Goal:** Get a working skeleton before writing any real logic.

- [ ] Create project folder structure:
  ```
  pitch-tool/
  ├── app.py               # Flask app
  ├── generator.py         # AI + scraping logic
  ├── templates/
  │   ├── index.html       # Input form
  │   └── preview.html     # Shows generated page inline
  ├── output/              # Saved HTML pitch pages
  ├── .env                 # API key (never committed)
  ├── requirements.txt
  └── README.md
  ```
- [ ] Install dependencies: `flask`, `anthropic`, `requests`, `beautifulsoup4`, `python-dotenv`
- [ ] Set up `.env` with `ANTHROPIC_API_KEY`
- [ ] Confirm Flask app runs on `localhost:5000`

---

## Phase 2: Input Form

**Goal:** A clean browser form that collects all the inputs needed to generate a pitch.

**Fields to collect:**
1. **Company name** — e.g., "Sweetgreen"
2. **Company website URL** — e.g., "https://www.sweetgreen.com"
3. **Industry** — e.g., "Fast-casual restaurant / food tech"
4. **Our proposed solution** — 2–4 sentences describing what we'd help them do
5. **Outreach email draft** — paste the email we plan to send (or key points)
6. **About our club** — 1 short paragraph describing who we are

Design notes:
- Clean, minimal form. White background, subtle border, one column.
- Button: "Generate Pitch Page"
- On submit: show a loading state, then redirect to the generated page

---

## Phase 3: Company Research (Scraper)

**Goal:** Pull real content from the company's website so the AI has actual material to work with — not just our description.

**Logic (`generator.py`):**
1. Accept the company URL as input
2. Fetch the homepage and `/about` page (handle errors gracefully)
3. Extract: page title, meta description, all `<p>` text, `<h1>`/`<h2>` headings
4. Strip boilerplate (nav, footer, cookie banners) using tag filtering
5. Truncate to ~3,000 characters to stay within prompt limits
6. Return as a clean string: `scraped_context`

**Edge cases to handle:**
- Site blocks scrapers → fall back to user-provided description only
- JS-rendered sites → extract what's available from raw HTML, note limitation
- Very long pages → truncate intelligently (prioritize headings + first paragraphs)

---

## Phase 4: AI Content Generation

**Goal:** Turn all inputs + scraped context into a structured pitch, section by section.

### Prompt Design

Use a single, carefully structured prompt. Pass in:
- Company name, industry
- Scraped website content
- Our proposed solution
- Outreach email draft
- Club description

Ask Claude to return a JSON object with these fields:
```json
{
  "company_overview": "...",
  "problem_statement": "...",
  "our_solution": "...",
  "expected_impact": "...",
  "call_to_action": "...",
  "about_us": "...",
  "page_headline": "...",
  "email_subject": "...",
  "outreach_email": "..."
}
```

### Key prompt instructions to include:
- "Use the company's own language and priorities from the scraped content"
- "The problem should feel observed, not invented — reference specific things about how they operate"
- "The solution should be specific to this company's size, industry, and stage"
- "Avoid phrases like 'in today's competitive landscape' or 'leverage synergies'"
- "Write as if you've already analyzed this company and are presenting findings"
- "The email should reference the webpage naturally, as if it's a follow-up to real work"

---

## Phase 5: Page Generation

**Goal:** Take the JSON from Claude and render it as a polished, self-contained HTML page.

### Page sections (in order):
1. **Hero / Header** — Company logo (fetched via favicon or placeholder), headline, one-line hook
2. **Company Overview** — 2–3 sentences grounded in their real business
3. **The Problem** — Specific, observed, uncomfortable to ignore
4. **Our Solution** — Clear, scoped, credible. Not "we will help you grow."
5. **Expected Impact** — Concrete metrics or outcomes where possible (even estimates)
6. **Call to Action** — One clear next step. A calendar link placeholder or email button.
7. **About Us** — Club background, who we are, why we're qualified

### Design specs:
- Font: Inter (via Google Fonts)
- Color palette: Navy `#0F172A` + White + one accent (default: `#6366F1` indigo)
- Tailwind CSS via CDN for layout and spacing
- Mobile-responsive
- No stock photo placeholders — text and color only
- Save as `output/{company-name}-pitch.html`

---

## Phase 6: Email Generation

**Goal:** Output a cold outreach email that pairs naturally with the page.

The email should:
- Open with something specific about the company (not "I hope this email finds you well")
- Reference that we put something together for them specifically
- Link to the pitch page (use a placeholder URL)
- Be 4–6 sentences max. No bullet points.
- End with a single, low-friction ask (15-min call, quick reply)

This comes out of the same Claude call as the page content (the `outreach_email` field in the JSON).

---

## Phase 7: Demo Companies

**Goal:** Generate 2–3 polished examples using real companies to submit as proof the tool works.

### Candidate companies to research and select from:

**Option A — Regional/mid-market brand with operational gaps**
Look for: regional grocery chains, regional banks, mid-size retail with no loyalty program, local restaurant groups with 10+ locations

**Option B — Consumer startup with data/personalization opportunity**
Look for: DTC brands with obvious retention problems, subscription companies with churn signals, food/wellness brands scaling fast

**Option C — B2B company with sales or pricing inefficiency**
Look for: SaaS companies with opaque pricing, logistics companies with manual quoting, professional services firms with no digital presence

### What makes a good demo company:
- Problem is visible from outside (their website, reviews, or growth stage implies it)
- Specific enough that our solution can't apply to anyone else
- Real enough that a real person at that company would feel seen reading the page

---

## Phase 8: System Explanation

**Goal:** A concise one-pager that explains how the tool works.

**Contents:**
- What it does and why it's different from a template
- How inputs flow through to outputs (simple diagram or prose)
- The scraping + AI synthesis approach and why it matters
- Design decisions (why Claude, why Tailwind, why JSON output)
- Limitations and what we'd improve with more time

**Format:** Markdown, saved as `README.md`. Clean enough to submit directly.

---

## Execution Order

```
Phase 1: Setup              → 30 min
Phase 2: Input form         → 45 min
Phase 3: Scraper            → 1 hour
Phase 4: AI prompting       → 1.5 hours (most iteration here)
Phase 5: Page generation    → 1.5 hours
Phase 6: Email output       → 30 min
Phase 7: Demo companies     → 1 hour (research + generate + review)
Phase 8: System explanation → 30 min
─────────────────────────────────────
Total estimate              → ~7 hours
```

---

## Quality Bar

Before submitting, each generated page must pass this check:

- [ ] Could this page have been written without knowing specifically about this company? (If yes, rewrite.)
- [ ] Does the problem section reference something real and specific about how they operate?
- [ ] Does the solution section name a specific deliverable, not a category?
- [ ] Is the email under 150 words and free of filler phrases?
- [ ] Does the page look like it came from a real firm, not a student project?

---

## Files to Submit

| File | Description |
|---|---|
| `app.py` | Flask app — routes and form handling |
| `generator.py` | Scraping + Claude API logic |
| `templates/index.html` | Input form |
| `output/company1-pitch.html` | Demo page 1 |
| `output/company2-pitch.html` | Demo page 2 |
| `output/company3-pitch.html` | Demo page 3 |
| `emails.md` | 3 outreach emails, one per company |
| `README.md` | System explanation |
