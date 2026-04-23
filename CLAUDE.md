# Consulting Pitch Tool — Claude Development Guide

This file is the authoritative guide for all AI-assisted development on this codebase. Read it fully before writing any code. Follow every protocol exactly.

---

## 1. Project Overview

This tool generates a custom consulting pitch webpage and a matching cold outreach email for a target company. A consultant fills out a form with the company's name, URL, industry, our proposed solution, a draft of the outreach email, and a short club bio. The tool scrapes the company's website, passes everything to the Claude API, and produces a polished, self-contained HTML pitch page plus a finalized outreach email — both personalized enough that it feels like real work was already done.

**The quality bar:** If the output could have been written without knowing specifically about that company, it fails. Generic language is a bug.

---

## 2. Project Structure

```
pitch-tool/
├── app.py                  # Flask app — routes and form handling
├── generator.py            # Scraping + Claude API logic
├── templates/
│   ├── index.html          # Input form (served at /)
│   └── preview.html        # Inline preview of generated page
├── output/                 # Saved self-contained HTML pitch pages
├── emails.md               # Generated outreach emails, one per company
├── .env                    # API keys — never committed
├── .env.example            # Documents required env vars
├── requirements.txt        # Python dependencies
├── README.md               # System explanation (submission deliverable)
├── plan.md                 # Phased execution plan
└── CLAUDE.md               # This file
```

---

## 3. Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+ / Flask |
| AI | Anthropic Claude API (`claude-sonnet-4-6` default) |
| Scraping | `requests` + `BeautifulSoup4` |
| Frontend styling | Tailwind CSS via CDN (no build step) |
| Output | Self-contained `.html` files saved to `output/` |
| Config | `python-dotenv` for env var loading |

**Dependency versions are pinned in `requirements.txt`.** Do not upgrade a library mid-project without testing all generated pages end-to-end.

---

## 4. Environment Variables

Required in `.env` (documented in `.env.example`):

```
ANTHROPIC_API_KEY=sk-ant-...
FLASK_SECRET_KEY=some-random-string
FLASK_ENV=development
```

Rules:
- Never log the value of any env var, even in debug output.
- Access all env vars through a single `config.py` loader once there are more than 3 vars — do not scatter `os.getenv()` calls across files.
- `.env` is gitignored. If it does not exist, the app must print a clear error and exit rather than silently failing.

---

## 5. Testing and Validation Loop

**This loop must be followed for every file you write. Do not exit the loop until all validation checks pass.**

```
WRITE → SYNTAX CHECK → LINT → RUN → VALIDATE → (pass: log + continue) | (fail: fix + restart loop)
```

**Step 1 — Write**
Write the complete file. No `# TODO` comments for logic that must exist for the current chunk to work. Stubs are allowed only for features explicitly deferred to a later chunk.

**Step 2 — Syntax check**
```bash
python -m py_compile app.py generator.py
```
Fix all syntax errors before proceeding. The loop does not advance with any syntax error present.

**Step 3 — Lint**
```bash
flake8 app.py generator.py --max-line-length=100
```
Fix all errors. Warnings may be left with an inline comment explaining why.

**Step 4 — Run**
Start the dev server and confirm it starts without crashing:
```bash
flask run
```
Then manually submit the form with a known test input (use Sweetgreen as the default test case — it's one of our demo companies). Confirm the page generates and saves to `output/`.

**Step 5 — Validate**
Run through the chunk's validation gate checklist. Each item must explicitly pass. If any item fails, note which one, fix the code, and restart from Step 1 for the changed files.

### Error handling rules

- Never silently swallow exceptions. Every `except` block must either log the error with `print(f"[ERROR] {e}")` or re-raise.
- The scraper failing must not crash the app. If a company URL cannot be scraped, fall back to generating from user-provided inputs only and surface a visible warning in the output page.
- Claude API errors must surface a user-readable error message in the browser, not a 500 stack trace.
- Never use bare `except:`. Always catch specific exceptions or `except Exception as e`.
- If a function reaches a branch that should be unreachable, raise `NotImplementedError("not implemented: <description>")` so failures are loud.

---

## 6. Code Conventions

### Python

- Python 3.11+. Use f-strings, not `.format()` or `%`.
- Type hints on all function signatures. No bare `Any` unless unavoidable and commented.
- Functions longer than 40 lines should be split. Each function does one thing.
- `generator.py` is the only file that calls the Claude API or makes HTTP requests. `app.py` orchestrates; it does not contain business logic.
- All Claude API calls go through a single `call_claude(prompt: str) -> dict` wrapper function. Do not scatter `anthropic.Anthropic()` calls across the file.

### Flask routes (`app.py`)

- Two routes only: `GET /` (form) and `POST /generate` (generation + redirect to saved page).
- Validate all form inputs before passing to `generator.py`. Missing required fields return the form with an inline error message, not a 400 JSON response.
- Log the method, path, and outcome for every request: `print(f"[{method}] {path} → {status}")`.
- Saved HTML files are served via Flask's `send_from_directory`. Do not expose the filesystem directly.

### Scraper (`generator.py`)

- Fetch homepage and `/about` page only. Do not crawl further.
- Set a `User-Agent` header on all requests: `"Mozilla/5.0 (compatible; ConsultingPitchBot/1.0)"`.
- Hard timeout: 8 seconds per request. Use `requests.get(..., timeout=8)`.
- Strip all `<script>`, `<style>`, `<nav>`, `<footer>`, and `<header>` tags before extracting text.
- Truncate extracted text to 3,000 characters. Prioritize `<h1>`, `<h2>`, and the first `<p>` of each section.
- Return a `ScrapedContext` dataclass, not a raw string.

### Claude API prompt (`generator.py`)

- The prompt is defined as a single module-level constant `PITCH_PROMPT_TEMPLATE`. It is a Python f-string template filled at call time.
- The prompt must explicitly instruct Claude to return valid JSON and nothing else. Parse with `json.loads()`. If parsing fails, retry once, then raise.
- The prompt must include anti-generic instructions. Required phrases (update as needed):
  - `"Use the company's own language from the scraped content."`
  - `"The problem must reference something specific about how this company operates — not a general industry trend."`
  - `"Avoid: 'in today's competitive landscape', 'leverage synergies', 'best-in-class', 'holistic approach'."`
- Expected JSON keys from Claude (all required — treat missing keys as a generation failure):
  ```
  page_headline, company_overview, problem_statement, our_solution,
  expected_impact, call_to_action, about_us, email_subject, outreach_email
  ```

### HTML output

- All generated pages are self-contained single `.html` files. No external dependencies except Tailwind CDN and Google Fonts CDN.
- Tailwind CSS classes only — no inline `style=` attributes, no `<style>` blocks with custom CSS.
- Color palette: navy `#0F172A` background for hero, white body, accent `#6366F1` (indigo) for CTAs and highlights.
- Font: Inter via Google Fonts.
- Every page must have an empty-state fallback for each section in case Claude returns an empty string for that field.
- Saved to `output/{company-name-slugified}-pitch.html`. Slugify with lowercase + hyphens, strip special characters.

### File naming

- Python source files: `snake_case.py`
- HTML templates: `snake_case.html`
- Generated output files: `{company-slug}-pitch.html`
- No spaces in any filename anywhere in the project.

---

## 7. Build Log Protocol

The build log lives at `docs/build-log.md`. It is append-only. **Update it once and only once per phase, immediately after that phase's validation gate fully passes.**

Do not update the build log mid-phase or speculatively. Only update when every item on the phase's checklist passes.

### Entry format

Append a new section at the TOP of the build log (most recent first):

```markdown
## Phase N — [Phase Name] — Completed [YYYY-MM-DD]

### What was built
- Built `app.py` — Flask routes for form rendering and generation trigger
- Built `generator.py` — scraper and Claude API wrapper
- [etc.]

### Validation gate — all passed
- ✅ Flask starts without errors
- ✅ Form submits and generates output for Sweetgreen test case
- ✅ Scraped content appears in output (not just user inputs)
- [etc.]

---

### Up next — Phase [N+1]: [Phase Name]
[One line describing the primary goal of the next phase]
```

Do not modify previous entries. If a previous phase had a gap, create a patch entry labeled `Phase N.1 — Patch — [date]`.

---

## 8. Working Order Within a Phase

When starting a new phase:

1. **Read this file** in full.
2. **Read `docs/build-log.md`** to confirm current state and which phase is next.
3. **Read `plan.md`** to confirm scope and deliverables for this phase.
4. **List every file you will create or modify** before writing any of them.
5. **Write in dependency order**: config and types first, then scraper, then Claude wrapper, then Flask routes, then templates.
6. **Run the validation loop** as you complete each file — not just at the end of the phase.
7. **Update the build log** only after the full phase validation gate passes.
8. **Do not start Phase N+1** until Phase N's build log entry is written.

---

## 9. Quality Gate for Generated Pages

Before any generated page is accepted as a demo deliverable, it must pass every item:

- [ ] The problem statement references something specific and observable about this company — not a generic industry trend.
- [ ] The solution names a concrete deliverable, not a category (e.g., "a pricing audit of your SMB tier" not "pricing optimization").
- [ ] No forbidden phrases appear anywhere in the output: "in today's competitive landscape," "leverage synergies," "best-in-class," "holistic," "empower," "robust," "innovative solutions."
- [ ] The outreach email is under 150 words.
- [ ] The outreach email opens with something specific about the company — not a greeting or pleasantry.
- [ ] The page looks correct on a 1280px wide browser window.
- [ ] The page has no broken layout, no unstyled fallback text, and no visible placeholder content.
- [ ] The scraped company content is visibly reflected somewhere in the output (company's own language, specific product names, etc.).

If any item fails, the generation prompt must be revised and the page regenerated. Do not manually patch the HTML.

---

## 10. Demo Companies

The three demo companies must span different industries and have externally visible problems. Document each company here once chosen:

| Slot | Company | Industry | Core Problem |
|------|---------|----------|-------------|
| 1 | TBD | TBD | TBD |
| 2 | TBD | TBD | TBD |
| 3 | TBD | TBD | TBD |

**Selection criteria:**
- Problem is visible from their public website, reviews, or growth stage
- Solution is specific enough that it cannot apply to a different company unchanged
- Company is real and reachable (someone could actually receive this email)
- Avoid Fortune 500s (too generic a pitch) and companies with fewer than ~50 employees (too niche)

---

## 11. Phases Reference

| Phase | Description | Key Output |
|-------|-------------|------------|
| 1 | Project setup | Folder structure, deps installed, Flask skeleton running |
| 2 | Input form | `templates/index.html`, form submission to `/generate` |
| 3 | Scraper | `generator.py` scrape functions, `ScrapedContext` dataclass |
| 4 | AI prompt | `PITCH_PROMPT_TEMPLATE`, `call_claude()`, JSON parsing |
| 5 | Page generation | HTML builder, Tailwind layout, `output/` file saving |
| 6 | Email output | `outreach_email` field wired through to `emails.md` |
| 7 | Demo companies | 3 pitch pages + 3 emails passing the quality gate |
| 8 | System explanation | `README.md` complete and submission-ready |

---

## 12. Invariants That Must Never Break

1. **The scraper failing never crashes the app.** If scraping fails for any reason, the app continues with user-provided inputs only and logs a warning.
2. **Claude API errors surface to the user.** Never return a 500 with a stack trace. Always return a user-readable message in the browser.
3. **Generated output is never manually edited.** If the output is wrong, fix the prompt and regenerate. Manual HTML patches are forbidden — they make the tool's quality non-reproducible.
4. **Every output file is self-contained.** No generated page may depend on a local file path, a running server, or any external resource except Tailwind CDN and Google Fonts CDN.
5. **No API key is ever written to an output file or logged to the console.**
6. **The quality gate is not skipped for demo pages.** All three demo pages must pass every item in Section 9 before being submitted.

---

## 13. Quick Reference

### Install dependencies
```bash
pip install -r requirements.txt
```

### Run the dev server
```bash
flask run
```

### Syntax check
```bash
python -m py_compile app.py generator.py
```

### Lint
```bash
flake8 app.py generator.py --max-line-length=100
```

### Generate a test page (Sweetgreen — default test case)
Fill the form at `http://localhost:5000` with:
- Company: Sweetgreen
- URL: https://www.sweetgreen.com
- Industry: Fast-casual restaurant / food tech
- Solution: (your pitch)
- Email draft: (your draft)
- About us: (club bio)

### View generated pages
Open any file in `output/` directly in a browser. No server needed.
