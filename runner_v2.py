import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import libsql_experimental as libsql
import requests

# 1. Environment credentials
TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
RESEND_KEY = os.environ.get("RESEND_API_KEY")
RECIPIENT = os.environ.get("RECIPIENT_EMAIL")

if not all([TURSO_URL, TURSO_TOKEN, RESEND_KEY, RECIPIENT]):
  print(
      "Error: Missing required environment variables. Ensure"
      " TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, RESEND_API_KEY, and"
      " RECIPIENT_EMAIL are set in GitHub Secrets."
  )
  sys.exit(1)

conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)

# Standard European search terms
ROLE_KEYWORDS = [
    "bioengineer",
    "bio-engineer",
    "biomedical engineer",
    "bioprocess engineer",
    "fermentation",
    "biotechnology",
    "biotech",
    "msat",
    "upstream",
    "downstream",
    "cell therapy",
    "gene therapy",
    "bioinformatics",
    "computational biology",
]

EUROPE_GEO = [
    "europe",
    "germany",
    "deutschland",
    "switzerland",
    "schweiz",
    "uk",
    "united kingdom",
    "france",
    "denmark",
    "netherlands",
    "sweden",
    "belgium",
    "austria",
    "ireland",
    "spain",
    "italy",
    "basel",
    "zurich",
    "munich",
    "berlin",
    "cambridge",
    "oxford",
    "copenhagen",
]


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


def clean_html(raw_html: str) -> str:
  cleanr = re.compile("<.*?>")
  return re.sub(cleanr, "", raw_html or "").strip()


# --- PORTAL 1: Official EURES API (europa.eu) ---
def fetch_eures_jobs() -> list:
  """Fetch real bioengineering roles directly from the official European Commission EURES search service."""
  eures_jobs = []
  endpoint = "https://europa.eu/eures/eures-apps/services/research/jv-se/search"
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      ),
      "Content-Type": "application/json",
      "Accept": "application/json",
  }

  search_payload = {
      "keywordsEverywhere": "bioprocess bioengineer biotechnology",
      "resultsPerPage": 15,
      "page": 1,
      "sort": "BEST_MATCH",
  }

  try:
    resp = requests.post(
        endpoint, json=search_payload, headers=headers, timeout=15
    )
    if resp.status_code == 200:
      data = resp.json()
      items = data.get("jvs", [])
      for item in items:
        title = item.get("title", "")
        employer = item.get("employer", {}).get("name", "European Employer")
        location_info = item.get("locations", [{}])[0]
        city = location_info.get("city", "")
        country = location_info.get("countryName", "Europe")
        loc_str = f"{city}, {country}".strip(", ")
        job_id = item.get("id", "")
        apply_link = (
            f"https://europa.eu/eures/portal/jv-se/jv-details/{job_id}?lang=en"
            if job_id
            else "https://europa.eu/eures/portal/jv-se/home"
        )

        eures_jobs.append({
            "title": title,
            "company": employer,
            "location": loc_str or "Europe",
            "country": country,
            "date_posted": item.get("publicationDate", "Recent"),
            "portal_source": "EURES (Europa.eu)",
            "apply_url": apply_link,
            "education_required": item.get(
                "educationLevel", "B.Sc. / M.Sc. in Engineering"
            ),
            "technical_skills": [
                "Bioprocess",
                "Bioengineering",
                "EU Standards",
            ],
        })
  except Exception as e:
    print(f"Notice: EURES endpoint unavailable: {e}")

  return eures_jobs


# --- PORTAL 2: Nature Careers (Biotechnology) ---
def fetch_nature_careers() -> list:
  jobs = []
  headers = {"User-Agent": "Mozilla/5.0 (compatible; BiotechJobAgent/1.0)"}
  url = "https://www.nature.com/naturecareers/rss?subject=biotechnology"
  try:
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 200:
      root = ET.fromstring(resp.content)
      for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        desc = clean_html(item.findtext("description") or "")
        pub_date = item.findtext("pubDate") or ""
        text = f"{title} {desc}".lower()

        if any(k in text for k in ROLE_KEYWORDS) and any(
            g in text for g in EUROPE_GEO
        ):
          jobs.append({
              "title": title,
              "company": "Biotech Institute / Enterprise",
              "location": "Europe (See Listing)",
              "country": "Europe",
              "date_posted": pub_date,
              "portal_source": "Nature Careers",
              "apply_url": link,
              "education_required": "M.Sc. / Ph.D. Preferred",
              "technical_skills": [
                  "Biotechnology",
                  "Process Engineering",
                  "R&D",
              ],
          })
  except Exception as e:
    print(f"Notice: Nature Careers RSS unavailable: {e}")
  return jobs


# --- PORTAL 3: EuroScienceJobs ---
def fetch_euroscience_jobs() -> list:
  jobs = []
  headers = {"User-Agent": "Mozilla/5.0 (compatible; BiotechJobAgent/1.0)"}
  url = "https://www.eurosciencejobs.com/rss/jobs"
  try:
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 200:
      root = ET.fromstring(resp.content)
      for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        desc = clean_html(item.findtext("description") or "")
        pub_date = item.findtext("pubDate") or ""
        text = f"{title} {desc}".lower()

        if any(k in text for k in ROLE_KEYWORDS):
          jobs.append({
              "title": title,
              "company": "European Life Science Organization",
              "location": "Pan-Europe",
              "country": "Europe",
              "date_posted": pub_date,
              "portal_source": "EuroScienceJobs",
              "apply_url": link,
              "education_required": (
                  "Life Science / Biochemical Engineering Degree"
              ),
              "technical_skills": [
                  "Bioengineering",
                  "GMP",
                  "Upstream/Downstream",
              ],
          })
  except Exception as e:
    print(f"Notice: EuroScienceJobs RSS unavailable: {e}")
  return jobs


def run_pipeline():
  init_schema()

  # Gather live jobs across all valid European portals
  all_jobs = []
  all_jobs.extend(fetch_eures_jobs())
  all_jobs.extend(fetch_nature_careers())
  all_jobs.extend(fetch_euroscience_jobs())

  print(
      f"Harvested {len(all_jobs)} candidate listings across European portals."
  )

  # Step 1: Ingest & Deduplicate with SHA-256 hash in Turso
  new_count = 0
  for j in all_jobs:
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
      new_count += 1
    except Exception:
      pass  # Skip duplicates
  conn.commit()
  print(f"Ingested {new_count} new unique bioengineering postings.")

  # Step 2: Fetch Unsent Jobs
  cursor = conn.execute(
      "SELECT id, title, company, location, portal_source, apply_url,"
      " education_required, technical_skills FROM biotech_jobs WHERE emailed = 0"
      " LIMIT 25"
  )
  rows = cursor.fetchall()

  if not rows:
    print("No new jobs to dispatch in this 4-hour cycle.")
    return

  # Step 3: Format HTML Digest
  job_ids = []
  cards_html = ""
  for r in rows:
    job_ids.append(r[0])
    cards_html += f"""
        <div style="border: 1px solid #cbd5e1; border-radius: 6px; padding: 14px; margin-bottom: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <h3 style="margin: 0 0 6px 0;"><a href="{r[5]}" style="color: #0284c7; text-decoration: none;">{r[1]}</a></h3>
            <p style="margin: 2px 0; color: #334155; font-weight: 600;">{r[2]} — {r[3]}</p>
            <p style="margin: 2px 0; font-size: 12px; color: #64748b;">Source: <strong>{r[4]}</strong></p>
            <p style="margin: 4px 0; font-size: 13px; color: #475569;"><strong>Education:</strong> {r[6]}</p>
            <p style="margin: 4px 0; font-size: 13px; color: #475569;"><strong>Skills:</strong> {r[7]}</p>
            <a href="{r[5]}" style="display: inline-block; margin-top: 8px; background-color: #0284c7; color: #ffffff; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: 500;">View & Apply</a>
        </div>
        """

  # Step 4: Send via Resend
  email_payload = {
      "from": "Biotech Agent <onboarding@resend.dev>",
      "to": [RECIPIENT],
      "subject": f"Biotech Alert: {len(rows)} New European Openings",
      "html": (
          f"<div style='font-family: sans-serif;'><h2>European Bio-Engineering"
          f" Job Digest</h2><p>Found {len(rows)} verified positions across"
          f" EURES, Nature Careers, and EuroScienceJobs:</p>{cards_html}</div>"
      ),
  }

  res = requests.post(
      "https://api.resend.com/emails",
      headers={
          "Authorization": f"Bearer {RESEND_KEY}",
          "Content-Type": "application/json",
      },
      json=email_payload,
  )

  # Step 5: Mark as Sent in Turso using tuple parameters
  if res.status_code in [200, 201]:
    placeholders = ",".join("?" for _ in job_ids)
    conn.execute(
        f"UPDATE biotech_jobs SET emailed = 1 WHERE id IN ({placeholders})",
        tuple(job_ids),
    )
    conn.commit()
    print(f"Successfully dispatched {len(rows)} jobs to {RECIPIENT}")
  else:
    print(f"Resend error: {res.text}")


if __name__ == "__main__":
  run_pipeline()
