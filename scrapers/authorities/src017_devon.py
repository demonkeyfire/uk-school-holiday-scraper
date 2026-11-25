
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Devon school-term and holiday rows from the published HTML page.
# The output is one row per event and academic year, retaining the source's page order
# and unparsed date text.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source


# -------------------------------------------- Settings --------------------------------------------

SOURCE_ID = "SRC017"

HEADERS = {
    "User-Agent": "SchoolHolidayResearch/1.0"
}

OUTPUT_COLUMNS = [
    "SOURCE_ID",
    "ACADEMIC_YEAR",
    "EVENT_NAME",
    "RAW_DATE_TEXT",
    "DATE_SCRAPED",
]


# -------------------------------------------- Scraper ---------------------------------------------

def scrape_devon():

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
    date_scraped = datetime.now(timezone.utc).date()

    # Each academic year is introduced by a heading followed by a dates table.
    for heading in soup.find_all(["h2", "h3"]):

        heading_text = heading.get_text(" ", strip=True)

        year_match = re.search(
            r"Recommended term dates for\s+(\d{4})\s*/\s*(\d{2,4})",
            heading_text,
            flags=re.IGNORECASE
        )

        if not year_match:
            continue

        start_year = year_match.group(1)
        end_year = year_match.group(2)

        academic_year = f"{start_year}/{end_year[-2:]}"

        # Locate the table immediately following the academic-year heading.
        table = heading.find_next("table")

        if table is None:
            continue

        # Check that the table belongs to this heading rather than a later section.
        next_heading = table.find_next(["h2", "h3"])

        if next_heading and re.search(
            r"Recommended term dates for",
            next_heading.get_text(" ", strip=True),
            flags=re.IGNORECASE
        ):
            pass

        # Process each table row in its published order.
        for row in table.find_all("tr"):

            cells = row.find_all(["th", "td"], recursive=False)

            if len(cells) < 2:
                continue

            event_name = cells[0].get_text(" ", strip=True)
            raw_date_text = cells[1].get_text(" ", strip=True)

            if not event_name or not raw_date_text:
                continue

            # Retain the event label and date wording as published.
            records.append({
                "SOURCE_ID": SOURCE_ID,
                "ACADEMIC_YEAR": academic_year,
                "EVENT_NAME": event_name,
                "RAW_DATE_TEXT": raw_date_text,
                "DATE_SCRAPED": date_scraped,
            })

    return pd.DataFrame.from_records(
        records,
        columns=OUTPUT_COLUMNS
    )
