"""
One-shot scraper: uaex.uada.edu/counties/ + personnel.uada.edu
Outputs: backend/data/county_agents.json

Run: python ingestion/scrape_county_agents.py

Strategy:
  1. Scrape county listing page for all 75 county slugs and office emails/phones.
  2. Query personnel directory per county to find the Staff Chair agent name.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# AR county name -> FIPS (05XXX)
AR_COUNTY_FIPS = {
    "Arkansas": "05001", "Ashley": "05003", "Baxter": "05005", "Benton": "05007",
    "Boone": "05009", "Bradley": "05011", "Calhoun": "05013", "Carroll": "05015",
    "Chicot": "05017", "Clark": "05019", "Clay": "05021", "Cleburne": "05023",
    "Cleveland": "05025", "Columbia": "05027", "Conway": "05029", "Craighead": "05031",
    "Crawford": "05033", "Crittenden": "05035", "Cross": "05037", "Dallas": "05039",
    "Desha": "05041", "Drew": "05043", "Faulkner": "05045", "Franklin": "05047",
    "Fulton": "05049", "Garland": "05051", "Grant": "05053", "Greene": "05055",
    "Hempstead": "05057", "Hot Spring": "05059", "Howard": "05061",
    "Independence": "05063", "Izard": "05065", "Jackson": "05067",
    "Jefferson": "05069", "Johnson": "05071", "Lafayette": "05073",
    "Lawrence": "05075", "Lee": "05077", "Lincoln": "05079",
    "Little River": "05081", "Logan": "05083", "Lonoke": "05085",
    "Madison": "05087", "Marion": "05089", "Miller": "05091",
    "Mississippi": "05093", "Monroe": "05095", "Montgomery": "05097",
    "Nevada": "05099", "Newton": "05101", "Ouachita": "05103",
    "Perry": "05105", "Phillips": "05107", "Pike": "05109",
    "Poinsett": "05111", "Polk": "05113", "Pope": "05115",
    "Prairie": "05117", "Pulaski": "05119", "Randolph": "05121",
    "St. Francis": "05123", "Saline": "05125", "Scott": "05127",
    "Searcy": "05129", "Sebastian": "05131", "Sevier": "05133",
    "Sharp": "05135", "Stone": "05137", "Union": "05139",
    "Van Buren": "05141", "Washington": "05143", "White": "05145",
    "Woodruff": "05147", "Yell": "05149",
}

COUNTIES_INDEX = "https://uaex.uada.edu/counties/default.aspx"
PERSONNEL_URL = "https://personnel.uada.edu/"
HEADERS = {"User-Agent": "AgroAdvisor AR Research Bot (jegedetaiwo95@gmail.com)"}
RATE_LIMIT = 1.0  # seconds between requests


def _get(url: str, timeout: int = 20) -> requests.Response:
    time.sleep(RATE_LIMIT)
    return requests.get(url, headers=HEADERS, timeout=timeout)


def _normalize(name: str) -> str:
    """Strip 'County' suffix, extra whitespace."""
    return re.sub(r"\s+County\s*$", "", name.strip(), flags=re.IGNORECASE).strip()


def _fetch_county_links() -> list[dict]:
    """Return list of {county, href} from counties index page."""
    r = _get(COUNTIES_INDEX)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = _normalize(a.get_text(strip=True))
        # County links look like /counties/<slug>/ or https://uaex.../counties/<slug>/
        if re.search(r"/counties/[a-z\-]+/?$", href) and text:
            full = href if href.startswith("http") else f"https://uaex.uada.edu{href}"
            links.append({"county": text, "href": full})
    # Deduplicate by county name
    seen = set()
    unique = []
    for l in links:
        if l["county"] not in seen:
            seen.add(l["county"])
            unique.append(l)
    return unique


def _scrape_county_page(county_name: str, url: str) -> dict:
    """Scrape a single county office page for phone and email."""
    try:
        r = _get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        main = soup.find(id="maincontent") or soup.find("main") or soup.find("body")
        text = main.get_text(separator="\n") if main else r.text

        # Phone: prefer first phone found
        phone_match = re.search(r"\(?\d{3}\)?[\s\-\.]\d{3}[\-\.]\d{4}", text)
        # Email: prefer office email (county-slug@uada.edu) over personal
        office_email = re.search(
            r"[\w\-]+@uada\.edu",
            text,
            re.IGNORECASE,
        )
        # Normalize whitespace: replace non-breaking spaces with regular spaces
        phone = phone_match.group(0).strip() if phone_match else ""
        phone = phone.replace('\xa0', ' ').strip()
        email = office_email.group(0).strip() if office_email else ""
        email = email.replace('\xa0', ' ').strip()
        return {
            "phone": phone,
            "email": email,
        }
    except Exception as exc:
        print(f"  ERR county page {county_name}: {exc}", file=sys.stderr)
        return {"phone": "", "email": ""}


def _is_name_line(line: str) -> bool:
    """Return True if the line looks like a person's name (2-4 words, letters only)."""
    # Allow mixed case, all caps, middle initials with period
    # Reject lines with digits, colons, slashes, common labels
    if not line or len(line) > 60:
        return False
    skip = {"Phone", "Email", "More Info", "CES", "AES", "Print", "Search",
            "Results", "Menu", "Personnel", "Directory", "Division", "Choose",
            "Keyword", "Category", "County", "Extension"}
    words = line.split()
    if len(words) < 2 or len(words) > 5:
        return False
    if any(kw in line for kw in skip):
        return False
    if re.search(r"[\d:/\\|@]", line):
        return False
    # Each word: uppercase start (or all-caps), no forbidden chars
    if not all(re.match(r"^[A-Za-z][A-Za-z'-\.]*$", w) for w in words):
        return False
    return True


def _fetch_staff_chair(county_name: str) -> str:
    """Query personnel directory and return the Staff Chair agent name."""
    try:
        url = f"{PERSONNEL_URL}?chooseCategory=2&keywordSearch={requests.utils.quote(county_name)}"
        r = _get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Find the "Print Search Results" anchor, then parse person records
        start_idx = next(
            (i for i, l in enumerate(lines) if "Print Search Results" in l), 0
        )
        relevant = lines[start_idx + 1:]

        # Parse blocks: name / title / dept / Phone: / +1 xxx / Email: / email / More Info
        # Priority: Staff Chair > Agriculture agent > any County Extension Agent
        chair_name = ""
        agent_name = ""

        for i in range(len(relevant) - 1):
            name_line = relevant[i]
            title_line = relevant[i + 1] if i + 1 < len(relevant) else ""

            if not _is_name_line(name_line):
                continue

            is_agent = "County Extension Agent" in title_line
            is_chair = "Staff Chair" in title_line
            is_agri = "Agriculture" in title_line

            if is_agent and is_chair:
                if not chair_name:
                    # Normalise all-caps to title case
                    chair_name = name_line.title() if name_line.isupper() else name_line
            elif is_agent and is_agri:
                if not agent_name:
                    agent_name = name_line.title() if name_line.isupper() else name_line
            elif is_agent:
                if not agent_name:
                    agent_name = name_line.title() if name_line.isupper() else name_line

        return chair_name or agent_name
    except Exception as exc:
        print(f"  ERR personnel lookup {county_name}: {exc}", file=sys.stderr)
        return ""


def scrape() -> dict:
    print("Step 1: Fetching county links from index page...")
    county_links = _fetch_county_links()
    print(f"  Found {len(county_links)} county links")

    result = {}

    for lnk in county_links:
        county_name = lnk["county"]
        fips = AR_COUNTY_FIPS.get(county_name)
        if not fips:
            print(f"  SKIP No FIPS for '{county_name}', skipping", file=sys.stderr)
            continue

        print(f"  Scraping {county_name}...", end=" ", flush=True)

        # 1. Get phone/email from county office page
        contact = _scrape_county_page(county_name, lnk["href"])

        # 2. Get agent name from personnel directory
        agent_name = _fetch_staff_chair(county_name)
        # Normalize whitespace: replace non-breaking spaces with regular spaces
        agent_name = agent_name.replace('\xa0', ' ').strip() if agent_name else ""

        result[fips] = {
            "county": county_name,
            "agent_name": agent_name,
            "phone": contact["phone"],
            "email": contact["email"],
        }
        status = "OK" if agent_name else "--"
        print(f"{status} {agent_name or '(no agent found)'}")

    return result


if __name__ == "__main__":
    print("Scraping Arkansas county extension offices...\n")
    data = scrape()

    out_path = Path(__file__).parent.parent / "backend" / "data" / "county_agents.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    populated = sum(1 for v in data.values() if v["agent_name"])
    print(f"\nWrote {len(data)} counties ({populated} with agent_name) -> {out_path}")
