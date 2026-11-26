
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Dorset school-term and holiday rows from the published HTML page.
# The output is one row per event and academic year, retaining the source's page order and
# unparsed date text.


# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source


# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC019"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.google.com/",
}

OUTPUT_COLUMNS = [
    "SOURCE_ID",
    "ACADEMIC_YEAR",
    "AUTHORITY",
    "EVENT_NAME",
    "RAW_DATE_TEXT",
    "DATE_SCRAPED",
]


# -------------------------------------------- Scraper ---------------------------------------------

def scrape_dorset():

    # Retrieve the source URL from the central configuration file.
    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    # Request and parse the webpage.
    response = requests.get(
        source_url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    records = []
    academic_year = None

    # Process headings and their associated content in page order.
    for element in soup.find_all(["h2", "h3", "h4", "p", "li", "tr"]):

        text = element.get_text(" ", strip=True)

        if not text:
            continue

        # -------------------------------- Academic-year headings --------------------------------

        year_match = re.search(
            r"(?:academic\s+year\s+)?(20\d{2})\s*[/\-]\s*(20\d{2})",
            text,
            flags=re.IGNORECASE
        )

        if element.name in ["h2", "h3", "h4"] and year_match:

            start_year = year_match.group(1)
            end_year = year_match.group(2)

            academic_year = f"{start_year}/{end_year[-2:]}"
            continue

        if academic_year is None:
            continue

        # ------------------------------------ Event content --------------------------------------

        # Ignore generic navigation and introductory text that does not contain a date.
        if not re.search(
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b",
            text,
            flags=re.IGNORECASE
        ):
            continue

        # Use a table row's first cell as the event name where available.
        if element.name == "tr":
            cells = element.find_all(["th", "td"], recursive=False)

            if len(cells) < 2:
                continue

            event_name = cells[0].get_text(" ", strip=True)
            raw_date_text = " | ".join(
                cell.get_text(" ", strip=True)
                for cell in cells[1:]
            )

        else:
            # Separate a labelled event from its date text when a colon is present.
            event_match = re.match(
                r"^([^:]+):\s*(.+)$",
                text
            )

            if event_match:
                event_name = event_match.group(1).strip()
                raw_date_text = event_match.group(2).strip()
            else:
                event_name = "School Term / Holiday"
                raw_date_text = text

        if not raw_date_text:
            continue

        records.append({
            "SOURCE_ID": SOURCE_ID,
            "ACADEMIC_YEAR": academic_year,
            "AUTHORITY": "Dorset",
            "EVENT_NAME": event_name,
            "RAW_DATE_TEXT": raw_date_text,
            "DATE_SCRAPED": datetime.now(timezone.utc).date(),
        })

    # Raise a clear error if the page structure changes or no dates are found.
    if not records:
        raise ValueError(
            "No school term or holiday dates were extracted from the Dorset webpage."
        )

    return pd.DataFrame.from_records(
        records,
        columns=OUTPUT_COLUMNS
    )
