"""UA Extension PDF scraper — downloads rice/soybean/poultry PDFs."""
import os
import re
import time
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.uaex.uada.edu"
SEARCH_URLS = [
    "https://www.uaex.uada.edu/farm-ranch/crops-commercial-horticulture/rice/",
    "https://www.uaex.uada.edu/farm-ranch/crops-commercial-horticulture/soybean/default.aspx",
    "https://www.uaex.uada.edu/farm-ranch/animals-forages/poultry/commercial.aspx",
    "https://www.uaex.uada.edu/farm-ranch/animals-forages/poultry/hobby-small-flocks.aspx",
    "https://www.uaex.uada.edu/farm-ranch/animals-forages/poultry/processing.aspx",
]

OUTPUT_DIR = Path(__file__).parent / "raw_pdfs"
OUTPUT_DIR.mkdir(exist_ok=True)

CROP_PREFIX_MAP = {
    "rice": "rice",
    "soybean": "soybeans",
    "poultry": "poultry",
}

HEADERS = {
    "User-Agent": "AgroAdvisor AR Research Bot (jegedetaiwo95@gmail.com)",
}

RATE_LIMIT_SECONDS = 1.5


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "_", text).strip("_")[:80]


def scrape_page(url: str, crop_prefix: str) -> list[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Failed to fetch {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            full_url = urljoin(url, href)
            pdf_links.append((full_url, a.get_text(strip=True)))

    downloaded = []
    for pdf_url, link_text in pdf_links:
        filename = crop_prefix + "_" + _slugify(link_text or Path(urlparse(pdf_url).path).stem)
        out_path = OUTPUT_DIR / f"{filename}.pdf"

        if out_path.exists():
            print(f"  Already exists: {out_path.name}")
            downloaded.append(str(out_path))
            continue

        try:
            time.sleep(RATE_LIMIT_SECONDS)
            pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=20, stream=True)
            pdf_resp.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in pdf_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"  Downloaded: {out_path.name}")
            downloaded.append(str(out_path))
        except Exception as e:
            print(f"  Failed {pdf_url}: {e}")

    return downloaded


def run_scraper() -> None:
    total = []
    for url in SEARCH_URLS:
        for crop_key, prefix in CROP_PREFIX_MAP.items():
            if crop_key in url:
                print(f"\nScraping {url}")
                downloaded = scrape_page(url, prefix)
                total.extend(downloaded)
                break

    print(f"\nTotal PDFs in raw_pdfs/: {len(list(OUTPUT_DIR.glob('*.pdf')))}")
    print(f"Downloaded this run: {len(total)}")


if __name__ == "__main__":
    run_scraper()
