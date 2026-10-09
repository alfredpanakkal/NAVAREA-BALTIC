#!/usr/bin/env python3
"""
baltic_scraper.py — Sjöfartsverket VHF Navigational Warnings Scraper
Harvests active Swedish and Baltic Sea navigational warnings from the Swedish Maritime Administration portal:
https://navvarn.sjofartsverket.se/en/Navigationsvarningar/VHF
"""

import sys
import re
import html
import requests
import urllib3
from bs4 import BeautifulSoup

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Disable SSL warnings if any
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://navvarn.sjofartsverket.se/en/Navigationsvarningar/VHF"

def clean_text(text: str) -> str:
    """Normalize text and whitespace."""
    if not text:
        return ""
    text = html.unescape(text)
    # Normalize CRLF and non-breaking spaces
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\xa0', ' ')
    return text.strip()

def scrape_baltic_warnings(output_filename="navarea_baltic_warnings.txt"):
    print("=" * 60)
    print("⚓ Sjofartsverket Baltic Navigational Warnings Scraper")
    print("=" * 60)
    print(f"Fetching live bulletins from {URL}...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,sv;q=0.8"
    }

    try:
        response = requests.get(URL, headers=headers, timeout=30, verify=False)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error while fetching {URL}: {e}")
        sys.exit(1)

    soup = BeautifulSoup(response.text, "html.parser")
    warnings_container = soup.find(id="warnings_by_area")

    if not warnings_container:
        print("❌ Could not locate '#warnings_by_area' in the page DOM.")
        sys.exit(1)

    area_divs = warnings_container.find_all("div", class_="nav-area-div")
    print(f"Found {len(area_divs)} navigational area sections.")

    # Dictionary to collect and deduplicate warnings
    # Key: normalized header text e.g. "SWEDISH NAV WARN 168/26"
    collected_warnings = {}

    for area_div in area_divs:
        h5 = area_div.find("h5")
        area_name = clean_text(h5.get_text()) if h5 else "Unknown Area"

        # Find all p tags inside this area
        paragraphs = area_div.find_all("p")
        for p in paragraphs:
            p_text = clean_text(p.get_text())
            if not p_text or "No current warnings in the area" in p_text:
                continue

            # Extract <b> header (e.g. SWEDISH NAV WARN 168/26 or BALTIC SEA NAV WARN 026/25)
            b_tag = p.find("b")
            if not b_tag:
                continue

            header_raw = clean_text(b_tag.get_text())
            # Collapse multiple spaces or newlines in header
            header_clean = " ".join(header_raw.split())

            # Extract date line: text before <b>
            # In HTML: "080056 UTC OCT <br /> <b>SWEDISH NAV WARN 168/26</b>"
            date_match = re.search(r'(\d{6}\s+UTC\s+[A-Z]{3})', p.text)
            date_str = date_match.group(1) if date_match else ""

            # Extract body text from <span style="white-space: pre-line">
            span_tag = p.find("span")
            if span_tag:
                body_clean = clean_text(span_tag.get_text())
            else:
                # Fallback: remove header and date from p text
                body_clean = p_text.replace(header_raw, "").replace(date_str, "").strip()

            if not body_clean:
                continue

            # Standardize key
            key = header_clean

            if key not in collected_warnings:
                collected_warnings[key] = {
                    "header": header_clean,
                    "date_str": date_str,
                    "body": body_clean,
                    "areas": [area_name]
                }
            else:
                if area_name not in collected_warnings[key]["areas"]:
                    collected_warnings[key]["areas"].append(area_name)

    print(f"Total unique warnings extracted: {len(collected_warnings)}")

    # Write out to structured text file
    with open(output_filename, "w", encoding="utf-8") as f:
        for warn in collected_warnings.values():
            areas_str = ", ".join(warn["areas"])
            f.write(f"--- {warn['header']} [{areas_str}] ---\n")
            if warn["date_str"]:
                f.write(f"{warn['date_str']}\n")
            f.write(f"{warn['body']}\n\n")

    print(f"✅ Successfully wrote {len(collected_warnings)} warnings to '{output_filename}'.")
    return collected_warnings

if __name__ == "__main__":
    scrape_baltic_warnings()
