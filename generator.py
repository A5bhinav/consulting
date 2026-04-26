import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

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
    "Recent news / context about {company_name}:\n---\n{recent_context}\n---\n"
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
    "- If recent news or context is provided above, weave a specific detail from it "
    "into the problem statement — a funding announcement, quarterly result, product "
    "launch, or press story makes the pitch feel timely rather than generic.\n"
    "- Include at least one specific metric, percentage, or timeframe in both "
    "problem_statement and expected_impact. Vague language fails the quality bar: "
    "write '30-90 day post-signup drop-off' not 'retention challenges', "
    "write 'reduce CAC by an estimated 15-20%' not 'lower acquisition costs'.\n"
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

BRAND_PROMPT_TEMPLATE = (
    "You are a brand researcher. Return the visual identity for this company as JSON.\n\n"
    "Company: {company_name}\n"
    "Industry: {industry}\n"
    "Website content:\n---\n{scraped_content}\n---\n\n"
    "Rules:\n"
    "- Use real hex codes if you know them. Examples: Sweetgreen #1B4332, "
    "Stripe #635BFF, Airbnb #FF5A5F, Starbucks #00704A, Spotify #1DB954, "
    "Netflix #E50914, Uber #000000, Lyft #FF00BF, DoorDash #FF3008, "
    "Peloton #D03027, Notion #000000, Figma #F24E1E, Vercel #000000, "
    "Lululemon #000000, Patagonia #1B3A2D, Warby Parker #1F4E79.\n"
    "- primary_color is used as a dark section background — choose a color "
    "with luminance below 0.35 so white text is always readable on it. "
    "If the company's actual brand color is light, darken it significantly.\n"
    "- accent_color is used for CTAs and highlight labels — make it vibrant "
    "and distinct from primary_color. It should match the brand but stand out.\n"
    "- font_name must be a real Google Font that fits the brand tone. "
    "Suggestions by type: tech/modern→'Space Grotesk', "
    "premium/fashion→'Cormorant Garamond', health/wellness→'DM Sans', "
    "food/consumer→'Plus Jakarta Sans', corporate/finance→'IBM Plex Sans', "
    "energetic/sport→'Outfit', default→'Inter'.\n\n"
    "Return ONLY a JSON object, no markdown, no other text:\n"
    "{{\n"
    '  "primary_color": "<hex>",\n'
    '  "accent_color": "<hex>",\n'
    '  "text_on_primary": "<white or dark>",\n'
    '  "font_name": "<Google Font name>"\n'
    "}}"
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


@dataclass
class BrandContext:
    primary_color: str    # hero/about section background
    accent_color: str     # CTAs, section labels, highlights
    text_on_primary: str  # "white" or "dark"
    font_name: str        # Google Font name
    logo_url: str         # clearbit or empty string


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
    cleaned = ""

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
            print(f"[WARN] Cleaned text was: {cleaned[:300]}")
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API error: {e}") from e

    raise RuntimeError(
        f"Claude returned invalid JSON after 2 attempts: {last_error}"
    )


def _get_logo_url(company_url: str) -> str:
    try:
        domain = urlparse(company_url).netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return f"https://logo.clearbit.com/{domain}" if domain else ""
    except Exception:
        return ""


def get_brand_identity(
    company_name: str, industry: str, scraped_content: str, company_url: str
) -> BrandContext:
    default = BrandContext(
        primary_color="#0F172A",
        accent_color="#6366F1",
        text_on_primary="white",
        font_name="Inter",
        logo_url=_get_logo_url(company_url),
    )
    try:
        prompt = BRAND_PROMPT_TEMPLATE.format(
            company_name=company_name,
            industry=industry,
            scraped_content=scraped_content[:1000],
        )
        data = call_claude(prompt)
        return BrandContext(
            primary_color=data.get("primary_color", default.primary_color),
            accent_color=data.get("accent_color", default.accent_color),
            text_on_primary=data.get("text_on_primary", default.text_on_primary),
            font_name=data.get("font_name", default.font_name),
            logo_url=_get_logo_url(company_url),
        )
    except Exception as e:
        print(f"[WARN] Brand identity fetch failed, using defaults: {e}")
        return default


def generate_pitch(
    company_name: str,
    company_url: str,
    industry: str,
    proposed_solution: str,
    email_draft: str,
    club_description: str,
    recent_context: str = "",
) -> tuple[dict, ScrapedContext, BrandContext]:
    scraped = scrape_company(company_url)
    scraped_content = (
        scraped.content
        if scraped.scrape_success
        else f"[Scraping failed: {scraped.error}. Using user-provided description only.]"
    )

    pitch_prompt = PITCH_PROMPT_TEMPLATE.format(
        company_name=company_name,
        industry=industry,
        scraped_content=scraped_content,
        proposed_solution=proposed_solution,
        club_description=club_description,
        email_draft=email_draft or "No draft provided.",
        recent_context=recent_context or "No recent context provided.",
    )

    # Brand and pitch calls are independent — run them in parallel.
    with ThreadPoolExecutor(max_workers=2) as executor:
        brand_future = executor.submit(
            get_brand_identity, company_name, industry, scraped_content, company_url
        )
        pitch_future = executor.submit(call_claude, pitch_prompt)
        brand = brand_future.result()
        pitch = pitch_future.result()

    missing = [k for k in REQUIRED_KEYS if k not in pitch or not pitch[k]]
    if missing:
        raise RuntimeError(f"Claude response missing required keys: {missing}")

    return pitch, scraped, brand


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
    label: str, heading: str, body: str, accent_color: str, bg_slate: bool = False
) -> str:
    bg = "bg-slate-50" if bg_slate else "bg-white"
    return (
        f'<section class="{bg} px-6 py-16 border-b border-slate-100">\n'
        f'  <div class="max-w-4xl mx-auto">\n'
        f'    <p style="color:{accent_color};" '
        f'class="text-xs font-semibold uppercase tracking-widest mb-3">{label}</p>\n'
        f'    <h2 class="text-2xl md:text-3xl font-bold text-slate-900 mb-5">'
        f"{heading}</h2>\n"
        f'    <p class="text-slate-600 text-lg leading-relaxed max-w-3xl">'
        f"{body}</p>\n"
        f"  </div>\n</section>\n"
    )


def _build_hero(
    company_name: str, headline: str, overview: str, brand: BrandContext
) -> str:
    text_cls = "text-white" if brand.text_on_primary == "white" else "text-slate-900"
    muted_cls = (
        "text-slate-300" if brand.text_on_primary == "white" else "text-slate-600"
    )
    logo_filter = "brightness-0 invert" if brand.text_on_primary == "white" else ""
    logo_html = (
        f'    <img src="{brand.logo_url}" alt="{company_name}" '
        f'class="h-10 mb-8 object-contain {logo_filter}" '
        f"onerror=\"this.style.display='none'\" />\n"
        if brand.logo_url
        else ""
    )
    return (
        f'<section style="background:{brand.primary_color};" '
        f'class="px-6 py-20 md:py-28">\n'
        f'  <div class="max-w-4xl mx-auto">\n'
        f"{logo_html}"
        f'    <p style="color:{brand.accent_color};" '
        f'class="text-sm font-semibold uppercase tracking-widest mb-4">'
        f"{company_name}</p>\n"
        f'    <h1 class="text-4xl md:text-5xl font-bold leading-tight mb-6 {text_cls}">'
        f"{headline}</h1>\n"
        f'    <p class="{muted_cls} text-lg max-w-2xl">{overview}</p>\n'
        f"  </div>\n</section>\n"
    )


def _build_cta(cta_body: str, accent_color: str, sender_email: str) -> str:
    return (
        f'<section style="background:{accent_color};" class="px-6 py-16 text-white">\n'
        f'  <div class="max-w-4xl mx-auto text-center">\n'
        f'    <h2 class="text-2xl md:text-3xl font-bold mb-4">'
        f"Ready to take a look?</h2>\n"
        f'    <p class="text-white/80 text-lg mb-8 max-w-2xl mx-auto">'
        f"{cta_body}</p>\n"
        f'    <a href="mailto:{sender_email}" '
        f'style="color:{accent_color};" '
        f'class="inline-block bg-white font-semibold px-8 py-4 rounded-lg '
        f'hover:opacity-90 transition-opacity">Get in touch</a>\n'
        f'    <p class="text-white/50 text-sm mt-5">{sender_email}</p>\n'
        f"  </div>\n</section>\n"
    )


def _build_about(about: str, brand: BrandContext) -> str:
    text_cls = "text-white" if brand.text_on_primary == "white" else "text-slate-900"
    muted_cls = (
        "text-slate-300" if brand.text_on_primary == "white" else "text-slate-600"
    )
    return (
        f'<section style="background:{brand.primary_color};" class="px-6 py-16">\n'
        f'  <div class="max-w-4xl mx-auto">\n'
        f'    <p style="color:{brand.accent_color};" '
        f'class="text-xs font-semibold uppercase tracking-widest mb-3">About Us</p>\n'
        f'    <h2 class="text-2xl md:text-3xl font-bold mb-5 {text_cls}">'
        f"Who we are</h2>\n"
        f'    <p class="{muted_cls} text-lg leading-relaxed max-w-3xl">'
        f"{about}</p>\n"
        f"  </div>\n</section>\n"
    )


def _build_sender_card(
    sender_name: str, sender_email: str, accent_color: str
) -> str:
    initials = "".join(p[0].upper() for p in sender_name.split()[:2])
    return (
        '<section class="bg-white px-6 py-12 border-t border-slate-200">\n'
        '  <div class="max-w-4xl mx-auto">\n'
        f'    <p style="color:{accent_color};" '
        f'class="text-xs font-semibold uppercase tracking-widest mb-5">Reach out</p>\n'
        f'    <div class="flex items-center gap-5">\n'
        f'      <div style="background:{accent_color};" '
        f'class="w-12 h-12 rounded-full flex items-center justify-center '
        f'text-white font-bold text-lg shrink-0">{initials}</div>\n'
        f'      <div>\n'
        f'        <p class="font-semibold text-slate-900 text-base">{sender_name}</p>\n'
        f'        <a href="mailto:{sender_email}" style="color:{accent_color};" '
        f'class="text-sm hover:underline">{sender_email}</a>\n'
        f'      </div>\n'
        f'    </div>\n'
        f'  </div>\n</section>\n'
    )


def build_html_page(
    pitch: dict,
    company_name: str,
    scraped: ScrapedContext,
    brand: BrandContext,
    sender_name: str,
    sender_email: str,
) -> str:
    font_param = brand.font_name.replace(" ", "+")
    fonts = (
        f'<link href="https://fonts.googleapis.com/css2?'
        f"family={font_param}:wght@300;400;500;600;700;800&display=swap"
        f'" rel="stylesheet" />'
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
        f"  <style>body {{ font-family: '{brand.font_name}', 'Inter', sans-serif; }}</style>\n"
        "</head>\n"
        '<body class="bg-white text-slate-800 antialiased">\n'
        f'<div style="height:4px;background:{brand.accent_color};"></div>\n'
    )

    footer = (
        f'<footer style="background:{brand.primary_color};" '
        f'class="px-6 py-8 text-center text-slate-500 text-sm">\n'
        f"  Prepared for {company_name} &middot; Consulting Pitch Tool\n"
        "</footer>\n"
        "</body>\n</html>\n"
    )

    return (
        head
        + _scrape_warning(scraped)
        + _build_hero(company_name, headline, overview, brand)
        + _content_section("The Problem", "What we observed", problem, brand.accent_color)
        + _content_section(
            "Our Solution", "What we'd do", solution, brand.accent_color, bg_slate=True
        )
        + _content_section("Expected Impact", "What changes", impact, brand.accent_color)
        + _build_cta(cta_body, brand.accent_color, sender_email)
        + _build_about(about, brand)
        + _build_sender_card(sender_name, sender_email, brand.accent_color)
        + footer
    )
