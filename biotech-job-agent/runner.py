import hashlib
import json
import os
import sys
import libsql_experimental as libsql
import requests

# 1. Connect to Turso Cloud SQLite
TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
RESEND_KEY = os.environ.get("RESEND_API_KEY")
RECIPIENT = os.environ.get("RECIPIENT_EMAIL")

if not all([TURSO_URL, TURSO_TOKEN, RESEND_KEY, RECIPIENT]):
    print("Error: Missing required environment variables.")
    sys.exit(1)

conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)


def init_schema():
    conn.execute("""
        CREATE TABLE IF NOT EXISTS biotech_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_hash TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT NOT NULL,
            country TEXT,
            date_posted TEXT,
            portal_source TEXT NOT NULL,
            apply_url TEXT NOT NULL,
            education_required TEXT,
            technical_skills TEXT,
            emailed INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def compute_hash(company: str, title: str, location: str) -> str:
    seed = (
        f"{company.strip().lower()}|{title.strip().lower()}|{location.strip().lower()}"
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def fetch_live_jobs() -> list:
    """Fetch jobs from target endpoints (EURES / RapidAPI / Specialized feeds).

    Replace the mock payload below with live HTTP requests to your chosen endpoints.
    """
    return [
        {
            "title": "Bioprocess Downstream Engineer",
            "company": "Lonza AG",
            "location": "Visp, Switzerland",
            "country": "Switzerland",
            "date_posted": "2026-10-20",
            "portal_source": "EURES",
            "apply_url": "https://www.lonza.com/careers",
            "education_required": "M.Sc. in Biochemical Engineering",
            "technical_skills": ["Chromatography", "UF/DF", "GMP"],
        }
    ]


def run_pipeline():
    init_schema()

    # Step 1: Scrape & Ingest
    jobs = fetch_live_jobs()
    new_jobs_count = 0

    for j in jobs:
        j_hash = compute_hash(j["company"], j["title"], j["location"])
        try:
            conn.execute(
                """
                INSERT INTO biotech_jobs (
                    job_hash, title, company, location, country,
                    date_posted, portal_source, apply_url,
                    education_required, technical_skills
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    j_hash,
                    j["title"],
                    j["company"],
                    j["location"],
                    j.get("country", "Europe"),
                    j.get("date_posted", ""),
                    j["portal_source"],
                    j["apply_url"],
                    j.get("education_required", "Not specified"),
                    json.dumps(j.get("technical_skills", [])),
                ),
            )
            new_jobs_count += 1
        except Exception:
            pass  # Already exists (hash collision ignored)
    conn.commit()

    # Step 2: Query Unemailed Records
    cursor = conn.execute(
        "SELECT id, title, company, location, apply_url, education_required, technical_skills FROM biotech_jobs WHERE emailed = 0 LIMIT 30"
    )
    rows = cursor.fetchall()

    if not rows:
        print("No new jobs to dispatch today.")
        return

    # Step 3: Build HTML Digest
    job_ids = []
    cards_html = ""
    for r in rows:
        job_ids.append(r[0])
        cards_html += f"""
        <div style="border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; margin-bottom: 10px; font-family: sans-serif;">
            <h3 style="margin: 0 0 6px 0;"><a href="{r[4]}" style="color: #0284c7; text-decoration: none;">{r[1]}</a></h3>
            <p style="margin: 2px 0; color: #334155;"><strong>{r[2]}</strong> — {r[3]}</p>
            <p style="margin: 2px 0; font-size: 13px; color: #475569;">Degree: {r[5]} | Skills: {r[6]}</p>
            <a href="{r[4]}" style="display: inline-block; margin-top: 6px; background-color: #0284c7; color: white; padding: 4px 8px; border-radius: 4px; text-decoration: none; font-size: 12px;">Apply</a>
        </div>
        """

    # Step 4: Dispatch via Resend API
    email_payload = {
        "from": "Biotech Agent <onboarding@resend.dev>",
        "to": [RECIPIENT],
        "subject": f"Biotech Job Digest: {len(rows)} New Roles Found",
        "html": f"<h2>European Biotech Daily Digest</h2>{cards_html}",
    }

    res = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_KEY}",
            "Content-Type": "application/json",
        },
        json=email_payload,
    )

    if res.status_code in [200, 201]:
        placeholders = ",".join("?" for _ in job_ids)
        conn.execute(
            f"UPDATE biotech_jobs SET emailed = 1 WHERE id IN ({placeholders})",
            job_ids,
        )
        conn.commit()
        print(f"Successfully sent {len(rows)} jobs to {RECIPIENT}")
    else:
        print(f"Failed to send email: {res.text}")


if __name__ == "__main__":
    run_pipeline()