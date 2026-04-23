import json
import os
import re
from dataclasses import dataclass
from typing import Optional

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

PITCH_PROMPT_TEMPLATE = (
    "You are writing a consulting pitch for a real company. Your output must feel "
    "like it was written by someone who already analyzed this company deeply — "
    "not generated from a template.\n\n"
    "Company Name: {company_name}\n"
    "Industry: {industry}\n"
    "Company Website Content (scraped):\n---\n{scraped_content}\n---\n"
    "Our Proposed Solution: {proposed_solution}\n"
    "Our Club / Team Description: {club_description}\n"
    "Outreach Email Draft: {email_draft}\n\n"
    "Instructions:\n"
    "- Use the company's own language from the scraped content. Mirror their "
    "terminology, product names, and stated priorities.\n"
    "- The problem must reference something specific about how this company "
    "operates — not a general industry trend.\n"
    "- The solution must name a specific deliverable (e.g., 'a 4-week pricing "
    "audit of your SMB tier'), not a category.\n"
    "- Avoid all of: 'in today's competitive landscape', 'leverage synergies', "
    "'best-in-class', 'holistic approach', 'empower', 'robust', "
    "'innovative solutions'.\n"
    "- Write as if you have already analyzed this company and are presenting "
    "findings — not pitching in the abstract.\n"
    "- The outreach email must open with something specific about the company — "
    "no greeting, no pleasantry.\n"
    "- The outreach email must be 4-6 sentences, no bullet points, under 150 words.\n"
    "- The call to action must be a single, low-friction ask "
    "(15-minute call or quick reply).\n\n"
    "Your entire response must be a single JSON object — no markdown fences, "
    "no explanation, no text before or after. Use exactly this structure:\n\n"
    "{{\n"
    '  "page_headline": "...",\n'
    '  "company_overview": "...",\n'
    '  "problem_statement": "...",\n'
    '  "our_solution": "...",\n'
    '  "expected_impact": "...",\n'
    '  "call_to_action": "...",\n'
    '  "about_us": "...",\n'
    '  "email_subject": "...",\n'
    '  "outreach_email": "..."\n'
    "}}\n\n"
    "Every value must be a non-empty string. Do not include any text outside "
    "the JSON object."
)

REQUIRED_KEYS = [
    "page_headline",
    "company_overview",
    "problem_statement",
    "our_solution",
    "expected_impact",
    "call_to_action",
    "about_us",
    "email_subject",
    "outreach_email",
]

SCRAPE_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConsultingPitchBot/1.0)"}


@dataclass
class ScrapedContext:
    url: str
    title: str
    meta_description: str
    content: str
    scrape_success: bool
    error: Optional[str] = None


def _extract_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2"])]
    paragraphs = [
        p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)
    ]
    return " | ".join(headings[:10]) + "\n" + "\n".join(paragraphs[:20])


def scrape_company(url: str) -> ScrapedContext:
    pages = [url, url.rstrip("/") + "/about"]
    parts: list[str] = []
    title = ""
    meta_description = ""

    for page_url in pages:
        try:
            resp = requests.get(page_url, headers=SCRAPE_HEADERS, timeout=8)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            if not title:
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else ""

            if not meta_description:
                meta = soup.find("meta", attrs={"name": "description"})
                meta_description = meta.get("content", "") if meta else ""

            parts.append(_extract_text(soup))
        except requests.RequestException as e:
            print(f"[WARN] Could not scrape {page_url}: {e}")

    if not parts:
        return ScrapedContext(
            url=url,
            title="",
            meta_description="",
            content="",
            scrape_success=False,
            error="All scrape attempts failed",
        )

    combined = "\n\n".join(parts)[:3000]
    return ScrapedContext(
        url=url,
        title=title,
        meta_description=meta_description,
        content=combined,
        scrape_success=True,
    )


def _extract_json(raw: str) -> str:
    """Strip markdown fences and extract the first {...} block."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    # If there's prose before the JSON object, find the first {
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]
    return raw


def call_claude(prompt: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    last_error: Exception = RuntimeError("unknown")

    for attempt in range(2):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
            print(f"[DEBUG] Claude raw response (attempt {attempt + 1}): {raw[:200]}")
            cleaned = _extract_json(raw)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_error = e
            print(f"[WARN] JSON parse failed on attempt {attempt + 1}: {e}")
            print(f"[WARN] Cleaned text was: {cleaned[:300] if 'cleaned' in dir() else 'N/A'}")
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API error: {e}") from e

    raise RuntimeError(
        f"Claude returned invalid JSON after 2 attempts: {last_error}"
    )


def generate_pitch(
    company_name: str,
    company_url: str,
    industry: str,
    proposed_solution: str,
    email_draft: str,
    club_description: str,
) -> tuple[dict, ScrapedContext]:
    scraped = scrape_company(company_url)
    if scraped.scrape_success:
        scraped_content = scraped.content
    else:
        scraped_content = (
            f"[Scraping failed: {scraped.error}. "
            "Using user-provided description only.]"
        )

    prompt = PITCH_PROMPT_TEMPLATE.format(
        company_name=company_name,
        industry=industry,
        scraped_content=scraped_content,
        proposed_solution=proposed_solution,
        club_description=club_description,
        email_draft=email_draft or "No draft provided.",
    )

    pitch = call_claude(prompt)
    missing = [k for k in REQUIRED_KEYS if k not in pitch or not pitch[k]]
    if missing:
        raise RuntimeError(f"Claude response missing required keys: {missing}")

    return pitch, scraped


def slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug


def _v(pitch: dict, key: str) -> str:
    return pitch.get(key) or f"[{key} unavailable]"


def _scrape_warning(scraped: ScrapedContext) -> str:
    if scraped.scrape_success:
        return ""
    cls = (
        "bg-yellow-50 border border-yellow-200 text-yellow-800 "
        "px-4 py-3 text-sm text-center"
    )
    msg = "Website could not be scraped — content generated from provided inputs only."
    return f'<div class="{cls}">{msg}</div>\n'


def _content_section(
    label: str, heading: str, body: str, bg_slate: bool = False
) -> str:
    bg = "bg-slate-50" if bg_slate else "bg-white"
    lbl_cls = (
        "text-indigo-500 text-xs font-semibold uppercase tracking-widest mb-3"
    )
    return (
        f'<section class="{bg} px-6 py-16 border-b border-slate-100">\n'
        f'  <div class="max-w-4xl mx-auto">\n'
        f'    <p class="{lbl_cls}">{label}</p>\n'
        f'    <h2 class="text-2xl md:text-3xl font-bold text-slate-900 mb-5">'
        f"{heading}</h2>\n"
        f'    <p class="text-slate-600 text-lg leading-relaxed max-w-3xl">'
        f"{body}</p>\n"
        f"  </div>\n</section>\n"
    )


def _build_hero(company_name: str, headline: str, overview: str) -> str:
    return (
        '<section class="bg-[#0F172A] text-white px-6 py-20 md:py-28">\n'
        '  <div class="max-w-4xl mx-auto">\n'
        f'    <p class="text-indigo-400 text-sm font-semibold uppercase '
        f'tracking-widest mb-4">{company_name}</p>\n'
        f'    <h1 class="text-4xl md:text-5xl font-bold leading-tight mb-6">'
        f"{headline}</h1>\n"
        f'    <p class="text-slate-300 text-lg max-w-2xl">{overview}</p>\n'
        "  </div>\n</section>\n"
    )


def _build_cta(cta_body: str) -> str:
    btn_cls = (
        "inline-block bg-white text-indigo-600 font-semibold "
        "px-8 py-4 rounded-lg hover:bg-indigo-50 transition-colors"
    )
    return (
        '<section class="px-6 py-16 bg-indigo-600 text-white">\n'
        '  <div class="max-w-4xl mx-auto text-center">\n'
        '    <h2 class="text-2xl md:text-3xl font-bold mb-4">'
        "Ready to take a look?</h2>\n"
        f'    <p class="text-indigo-100 text-lg mb-8 max-w-2xl mx-auto">'
        f"{cta_body}</p>\n"
        f'    <a href="mailto:" class="{btn_cls}">Get in touch</a>\n'
        "  </div>\n</section>\n"
    )


def _build_about(about: str) -> str:
    lbl_cls = (
        "text-indigo-400 text-xs font-semibold uppercase tracking-widest mb-3"
    )
    return (
        '<section class="px-6 py-16 bg-[#0F172A] text-white">\n'
        '  <div class="max-w-4xl mx-auto">\n'
        f'    <p class="{lbl_cls}">About Us</p>\n'
        '    <h2 class="text-2xl md:text-3xl font-bold mb-5">Who we are</h2>\n'
        f'    <p class="text-slate-300 text-lg leading-relaxed max-w-3xl">'
        f"{about}</p>\n"
        "  </div>\n</section>\n"
    )


def build_html_page(
    pitch: dict, company_name: str, scraped: ScrapedContext
) -> str:
    fonts = (
        '<link href="https://fonts.googleapis.com/css2?'
        "family=Inter:wght@300;400;500;600;700;800&display=swap"
        '" rel="stylesheet" />'
    )
    headline = _v(pitch, "page_headline")
    overview = _v(pitch, "company_overview")
    problem = _v(pitch, "problem_statement")
    solution = _v(pitch, "our_solution")
    impact = _v(pitch, "expected_impact")
    cta_body = _v(pitch, "call_to_action")
    about = _v(pitch, "about_us")

    head = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, '
        'initial-scale=1.0" />\n'
        f"  <title>{headline}</title>\n"
        '  <script src="https://cdn.tailwindcss.com"></script>\n'
        f"  {fonts}\n"
        "  <style>body { font-family: 'Inter', sans-serif; }</style>\n"
        "</head>\n"
        '<body class="bg-white text-slate-800 antialiased">\n'
    )

    footer = (
        '<footer class="px-6 py-8 bg-slate-900 text-center '
        'text-slate-500 text-sm">\n'
        f"  Prepared for {company_name} &middot; Consulting Pitch Tool\n"
        "</footer>\n"
        "</body>\n</html>\n"
    )

    return (
        head
        + _scrape_warning(scraped)
        + _build_hero(company_name, headline, overview)
        + _content_section("The Problem", "What we observed", problem)
        + _content_section("Our Solution", "What we'd do", solution, bg_slate=True)
        + _content_section("Expected Impact", "What changes", impact)
        + _build_cta(cta_body)
        + _build_about(about)
        + footer
    )
