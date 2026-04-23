import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, send_from_directory, url_for

load_dotenv()

if not os.getenv("ANTHROPIC_API_KEY"):
    print("[ERROR] ANTHROPIC_API_KEY not set. Add it to .env and restart.")
    raise SystemExit(1)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

REQUIRED_FIELDS = [
    ("company_name", "Company name is required."),
    ("company_url", "Company URL is required."),
    ("industry", "Industry is required."),
    ("proposed_solution", "Proposed solution is required."),
    ("club_description", "Club description is required."),
]


@app.route("/", methods=["GET"])
def index():
    print("[GET] / → 200")
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    from generator import build_html_page, generate_pitch, slugify

    form = request.form
    errors = [msg for field, msg in REQUIRED_FIELDS if not form.get(field, "").strip()]

    if errors:
        print(f"[POST] /generate → 400 (validation: {errors})")
        return render_template("index.html", errors=errors, form_data=form)

    company_name = form["company_name"].strip()
    company_url = form["company_url"].strip()
    if company_url and not company_url.startswith(("http://", "https://")):
        company_url = "https://" + company_url
    industry = form["industry"].strip()
    proposed_solution = form["proposed_solution"].strip()
    email_draft = form.get("email_draft", "").strip()
    club_description = form["club_description"].strip()

    try:
        pitch, scraped = generate_pitch(
            company_name=company_name,
            company_url=company_url,
            industry=industry,
            proposed_solution=proposed_solution,
            email_draft=email_draft,
            club_description=club_description,
        )
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        print("[POST] /generate → 500")
        return render_template("index.html", errors=[str(e)], form_data=form)

    html = build_html_page(pitch, company_name, scraped)
    slug = slugify(company_name)
    filename = f"{slug}-pitch.html"
    (OUTPUT_DIR / filename).write_text(html, encoding="utf-8")

    emails_path = BASE_DIR / "emails.md"
    with open(emails_path, "a", encoding="utf-8") as f:
        f.write(f"\n## {company_name}\n\n")
        f.write(f"**Subject:** {pitch['email_subject']}\n\n")
        f.write(pitch["outreach_email"])
        f.write("\n\n---\n")

    print(f"[POST] /generate → 302 /output/{filename}")
    return redirect(url_for("serve_output", filename=filename))


@app.route("/output/<path:filename>")
def serve_output(filename: str):
    print(f"[GET] /output/{filename} → 200")
    return send_from_directory(str(OUTPUT_DIR), filename)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_ENV") == "development")
