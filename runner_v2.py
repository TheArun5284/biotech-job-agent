import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import libsql_experimental as libsql
import requests

# 1. Environment Credentials
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

# Standard Search Terms & Geography Filters
ROLE_KEYWORDS = [
    "bioengineer",
    "bio-engineer",
    "biomedical",
    "bioprocess",
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
    "molecular",
    "gmp",
    "bioreactor",
]

EUROPE_LOCATIONS = [
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
    "amsterdam",
    "remote",
]

REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, application/xml, text/xml, */*",
}


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


def parse_rss_feed(feed_url: str, portal_name: str) -> list:
  """Universal parser for XML/RSS life-sciences job feeds."""
  jobs = []
  try:
    resp = requests.get(feed_url, headers=REQ_HEADERS, timeout=12)
    if resp.status_code == 200:
      root = ET.fromstring(resp.content)
      for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        desc = clean_html(item.findtext("description") or "")
        pub_date = item.findtext("pubDate") or ""
        text = f"{title} {desc}".lower()

        if any(k in text for k in ROLE_KEYWORDS) and any(
            g in text for g in EUROPE_LOCATIONS
        ):
          jobs.append({
              "title": title,
              "company": portal_name + " Partner",
              "location": "Europe",
              "country": "Europe",
              "date_posted": pub_date,
              "portal_source": portal_name,
              "apply_url": link,
              "education_required": "B.Sc. / M.Sc. / Ph.D.",
              "technical_skills": ["Biotechnology", "Process", "Laboratory"],
          })
  except Exception as e:
    print(f"[{portal_name}] feed unreachable: {e}")
  return jobs


# --- 10 Live Portals ---


def fetch_portal_1_eures() -> list:
  jobs = []
  try:
    url = "https://europa.eu/eures/eures-apps/services/research/jv-se/search"
    payload = {
        "keywordsEverywhere": "bioprocess bioengineer biotechnology",
        "resultsPerPage": 15,
        "page": 1,
        "sort": "BEST_MATCH",
    }
    r = requests.post(url, json=payload, headers=REQ_HEADERS, timeout=12)
    if r.status_code == 200:
      for j in r.json().get("jvs", []):
        job_id = j.get("id", "")
        jobs.append({
            "title": j.get("title", ""),
            "company": j.get("employer", {}).get(
                "name", "European Employer (EURES)"
            ),
            "location": j.get("locations", [{}])[0].get("city", "Europe"),
            "country": j.get("locations", [{}])[0].get(
                "countryName", "EU/EEA"
            ),
            "date_posted": j.get("publicationDate", "Recent"),
            "portal_source": "EURES (EU Official)",
            "apply_url": (
                f"https://europa.eu/eures/portal/jv-se/jv-details/{job_id}?lang=en"
                if job_id
                else "https://europa.eu/eures"
            ),
            "education_required": j.get(
                "educationLevel", "Engineering / Life Science"
            ),
            "technical_skills": [
                "Bioprocess",
                "Bioengineering",
                "EU Standards",
            ],
        })
  except Exception as e:
    print(f"[EURES] unreachable: {e}")
  return jobs


def fetch_portal_2_euraxess() -> list:
  jobs = []
  try:
    url = "https://euraxess.ec.europa.eu/api/jobs/search?keywords=bioengineering&items_per_page=10"
    r = requests.get(url, headers=REQ_HEADERS, timeout=10)
    if r.status_code == 200:
      for item in r.json().get("rows", []):
        jobs.append({
            "title": item.get("title", "Bioengineering Fellow/Engineer"),
            "company": item.get("organisation", "European Research Institution"),
            "location": item.get("country", "Europe"),
            "country": item.get("country", "Europe"),
            "date_posted": item.get("deadline", "Upcoming"),
            "portal_source": "EURAXESS (EC)",
            "apply_url": (
                f"https://euraxess.ec.europa.eu/jobs/{item.get('nid', '')}"
            ),
            "education_required": "M.Sc. or Ph.D.",
            "technical_skills": [
                "Biotechnology",
                "Translational Research",
                "MSCA/Horizon",
            ],
        })
  except Exception:
    pass
  return jobs


def fetch_portal_3_nature() -> list:
  return parse_rss_feed(
      "https://www.nature.com/naturecareers/rss?subject=biotechnology",
      "Nature Careers",
  )


def fetch_portal_4_euroscience() -> list:
  return parse_rss_feed("https://www.eurosciencejobs.com/rss/jobs", "EuroScienceJobs")


def fetch_portal_5_europharma() -> list:
  return parse_rss_feed("https://www.europharmajobs.com/rss/jobs", "EuroPharmaJobs")


def fetch_portal_6_biospace() -> list:
  return parse_rss_feed("https://www.biospace.com/rss/jobs", "BioSpace")


def fetch_portal_7_newscientist() -> list:
  return parse_rss_feed(
      "https://jobs.newscientist.com/en-gb/jobsrss/?category=biotechnology",
      "New Scientist Jobs",
  )


def fetch_portal_8_academicpositions() -> list:
  return parse_rss_feed(
      "https://academicpositions.eu/jobs/rss?field=life-sciences",
      "AcademicPositions EU",
  )


def fetch_portal_9_swissbiotech() -> list:
  return parse_rss_feed(
      "https://www.jobsinzurich.net/rss?category=biotechnology", "Swiss Jobs Network"
  )


def fetch_portal_10_embl_ebi() -> list:
  jobs = []
  try:
    url = "https://www.embl.org/api/v1/jobs?discipline=Bioinformatics&limit=10"
    r = requests.get(url, headers=REQ_HEADERS, timeout=10)
    if r.status_code == 200:
      for j in r.json().get("jobs", []):
        jobs.append({
            "title": j.get("job_title", "Bioinformatics Engineer"),
            "company": "EMBL / European Bioinformatics Institute",
            "location": j.get("location", "Heidelberg / Cambridge"),
            "country": "Europe",
            "date_posted": j.get("date_posted", "Recent"),
            "portal_source": "EMBL-EBI Careers",
            "apply_url": j.get(
                "application_url", "https://www.embl.org/jobs/"
            ),
            "education_required": "M.Sc. / Ph.D. in Computational Biology",
            "technical_skills": [
                "Nextflow",
                "Python/R",
                "NGS",
                "Bioprocess Modeling",
            ],
        })
  except Exception:
    pass
  return jobs


# --- Fallback Discovery Engine ---
def fallback_european_discovery() -> list:
  """Executes if all primary portals yield 0 results in the current run."""
  print(
      "Triggering Fallback Discovery Engine across European open indices..."
  )
  fallback_jobs = []
  try:
    url = "https://europa.eu/eures/eures-apps/services/research/jv-se/search"
    payload = {
        "keywordsEverywhere": "biotechnology",
        "resultsPerPage": 10,
        "page": 1,
        "sort": "DATE_MODIFIED",
    }
    r = requests.post(url, json=payload, headers=REQ_HEADERS, timeout=15)
    if r.status_code == 200:
      for j in r.json().get("jvs", []):
        job_id = j.get("id", "")
        fallback_jobs.append({
            "title": j.get("title", "Biotechnology Process Specialist"),
            "company": j.get("employer", {}).get(
                "name", "European Life Science Enterprise"
            ),
            "location": j.get("locations", [{}])[0].get("city", "Europe"),
            "country": j.get("locations", [{}])[0].get(
                "countryName", "EU Member State"
            ),
            "date_posted": j.get("publicationDate", "Recent"),
            "portal_source": "EURES Fallback Backfill",
            "apply_url": (
                f"https://europa.eu/eures/portal/jv-se/jv-details/{job_id}?lang=en"
                if job_id
                else "https://europa.eu/eures"
            ),
            "education_required": "Technical or Science Degree",
            "technical_skills": ["Biotech Operations", "Quality Standards"],
        })
  except Exception as e:
    print(f"Fallback engine error: {e}")
  return fallback_jobs


# --- Main Pipeline ---
def run_pipeline():
  init_schema()
  all_harvested = []

  # Crawl all 10 live platforms
  all_harvested.extend(fetch_portal_1_eures())
  all_harvested.extend(fetch_portal_2_euraxess())
  all_harvested.extend(fetch_portal_3_nature())
  all_harvested.extend(fetch_portal_4_euroscience())
  all_harvested.extend(fetch_portal_5_europharma())
  all_harvested.extend(fetch_portal_6_biospace())
  all_harvested.extend(fetch_portal_7_newscientist())
  all_harvested.extend(fetch_portal_8_academicpositions())
  all_harvested.extend(fetch_portal_9_swissbiotech())
  all_harvested.extend(fetch_portal_10_embl_ebi())

  print(f"Harvested {len(all_harvested)} candidate listings across 10 portals.")

  # Check if fallback is required
  if len(all_harvested) == 0:
    all_harvested.extend(fallback_european_discovery())

  # Step 1: Ingest & Deduplicate with SHA-256 hash
  new_count = 0
  for j in all_harvested:
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
      pass  # Hash collision: record already exists
  conn.commit()
  print(f"Ingested {new_count} new unique bioengineering postings into Turso.")

  # Step 2: Fetch Unemailed Records
  cursor = conn.execute(
      "SELECT id, title, company, location, portal_source, apply_url,"
      " education_required, technical_skills FROM biotech_jobs WHERE emailed = 0"
      " LIMIT 25"
  )
  rows = cursor.fetchall()

  if not rows:
    print("No new postings to email in this 4-hour cycle.")
    return

  # Step 3: Format HTML Cards
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

  # Step 4: Dispatch Digest via Resend
  email_payload = {
      "from": "Biotech Agent <onboarding@resend.dev>",
      "to": [RECIPIENT],
      "subject": f"Biotech Alert: {len(rows)} New European Openings",
      "html": (
          f"<div style='font-family: sans-serif;'><h2>European Bio-Engineering"
          f" Job Digest</h2><p>Found {len(rows)} newly verified positions"
          f" across 10 European life-science platforms:</p>{cards_html}</div>"
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
    print(f"Resend dispatch error: {res.text}")


if __name__ == "__main__":
  run_pipeline()
