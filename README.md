# Consulting Pitch Tool

A local web app that generates a personalized consulting pitch webpage and cold outreach email for a target company. The output reflects real research on the company — not a mail-merged template.

---

## What it does

You fill out a form with:
- Company name and URL
- Industry
- Your proposed solution (2–4 sentences)
- An outreach email draft (optional)
- A short club bio

The tool scrapes the company's homepage and `/about` page, feeds everything to the Claude API, and produces:
1. A polished, self-contained HTML pitch page saved to `output/`
2. A finalized cold outreach email appended to `emails.md`

The quality bar: if the output could have been written without knowing specifically about this company, it fails.

---

## How inputs flow to outputs

```
Form submission
    │
    ▼
app.py — validates fields
    │
    ▼
generator.scrape_company(url)
    │  fetches homepage + /about, strips nav/footer/scripts,
    │  truncates to 3,000 chars → ScrapedContext
    │
    ▼
generator.call_claude(prompt)
    │  PITCH_PROMPT_TEMPLATE filled with all inputs + scraped content
    │  Claude returns JSON with 9 fields
    │
    ▼
generator.build_html_page(pitch, company, scraped)
    │  renders self-contained HTML with Tailwind + Inter font
    │  saved to output/{slug}-pitch.html
    │
    ▼
emails.md  ←  outreach_email field appended
    │
    ▼
Browser redirected to /output/{slug}-pitch.html
```

---

## Why this approach is different from a template

A mail-merge fills in `[COMPANY NAME]` blanks. This tool does something different:

1. **It pulls real language.** The scraper extracts the company's own words — product names, stated priorities, tone — and passes them directly to the AI. The prompt instructs Claude to mirror that language, not substitute generic industry phrases.

2. **The problem section is observed, not invented.** Claude is instructed to reference something specific about how this company operates — something visible from their own site — rather than stating a generic category problem.

3. **The solution is scoped.** The prompt forces a specific deliverable ("a 4-week pricing audit of your SMB tier") rather than a category promise ("pricing optimization").

---

## Design decisions

| Choice | Reason |
|--------|--------|
| Claude API (`claude-sonnet-4-6`) | Best at tone-matching and instruction-following; avoids generic filler phrases better than alternatives |
| Tailwind CSS via CDN | Modern look with no build step; classes stay readable in Python string templates |
| JSON output from Claude | Structured fields let the HTML builder place content precisely; easier to validate than free-form text |
| `requests` + `BeautifulSoup4` | Simple, reliable, no headless browser needed; covers the majority of marketing sites |
| Self-contained HTML output | Pages can be shared as attachments or opened directly — no server required |
| Single `call_claude()` wrapper | One place to change the model, add retries, or swap providers |

---

## Setup

**1. Create a virtual environment**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Add your API key**
```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

**3. Run the app**
```bash
flask run
```

Open `http://127.0.0.1:5000` in your browser.

---

## Generating a pitch page

Fill out the form at `http://127.0.0.1:5000`. Generation takes 15–30 seconds. The output page opens automatically. The outreach email is appended to `emails.md`.

Generated pages are saved to `output/{company-slug}-pitch.html` and can be opened directly in a browser with no server running.

---

## Limitations

- **JavaScript-heavy sites** — the scraper fetches raw HTML. Sites that render content client-side (SPAs) will return sparse content; the tool falls back to user-provided inputs with a visible warning on the output page.
- **Scraper blocks** — some sites detect and block bots. The fallback is the same: generate from user inputs only.
- **No logo fetching** — the page uses text and color only; no company logo is fetched or embedded.
- **Email placeholder link** — the "Get in touch" button on pitch pages links to `mailto:` without a pre-filled address. You would replace this with a real calendar link or email before sending.

---

## Files

| File | Description |
|------|-------------|
| `app.py` | Flask routes: form, generation trigger, output serving |
| `generator.py` | Scraping, Claude API call, HTML page builder |
| `templates/index.html` | Input form |
| `templates/preview.html` | Fallback preview page |
| `output/` | Generated HTML pitch pages |
| `emails.md` | Generated outreach emails, one per company |
| `docs/build-log.md` | Phase-by-phase build log |
