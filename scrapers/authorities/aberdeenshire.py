# -------------------------------------------- Overview --------------------------------------------

# Retrieve Aberdeenshire school-term and holiday events from the published page.
# The output is one row per event and academic year, retaining the source's date wording.


# --------------------------------------------- Imports ---------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup


# -------------------------------------------- Configuration ----------------------------------------

SOURCE_ID = "SRC001"

SOURCE_URL = (
    "https://www.aberdeenshire.gov.uk/schools/school-info/school-term-dates/"
)

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

ACADEMIC_YEARS = {
    "2026/27",
    "2027/28",
    "2028/29",
    "2029/30",
}

# Matches either a single date or a date range, followed by an event name.
EVENT_PATTERN = re.compile(
    r"^("
    r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"
    r"(?:\s+to\s+\d{1,2}\s+[A-Za-z]+\s+\d{4})?"
    r")\s+-\s+(.+)$"
)


# ----------------------------------------------- Scraper -------------------------------------------

def scrape_aberdeenshire():
    """Return raw school-term and holiday events from the Aberdeenshire source page."""

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    records = []

    # Identify academic-year headings.
    year_pattern = re.compile(r"^\d{4}/\d{2}$")

    for heading in soup.find_all("h2"):

        academic_year = heading.get_text(" ", strip=True)

        if not year_pattern.fullmatch(academic_year):
            continue

        if academic_year not in ACADEMIC_YEARS:
            continue

        # Extract list items belonging to this academic-year section.
        for element in heading.next_elements:

            # Stop when the next academic-year heading is reached.
            if (
                getattr(element, "name", None) == "h2"
            ):
                break

            if getattr(element, "name", None) != "li":
                continue

            raw_text = element.get_text(" ", strip=True)

            match = EVENT_PATTERN.match(raw_text)

            # Ignore navigation items and anything that is not a dated event.
            if match is None:
                continue

            raw_date_text = match.group(1)
            event_name = match.group(2).strip()

            records.append({
                "SOURCE_ID": SOURCE_ID,
                "ACADEMIC_YEAR": academic_year,
                "EVENT_NAME": event_name,
                "RAW_DATE_TEXT": raw_date_text,
                "DATE_SCRAPED": datetime.now(timezone.utc).date()
            })

    return pd.DataFrame.from_records(
        records,
        columns=OUTPUT_COLUMNS
    )
