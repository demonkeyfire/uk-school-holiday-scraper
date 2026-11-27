
# -------------------------------------------- Overview --------------------------------------------

# Retrieve school term and half-term dates from Knowsley Council.
# One row per published event and academic year.
# Retains the original date wording from the council page.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url


SOURCE_ID = "SRC042"
AUTHORITY = "Knowsley"

HEADERS = {
    "User-Agent": "SchoolHolidayResearch/1.0"
}

OUTPUT_COLUMNS = [
    "SOURCE_ID",
    "ACADEMIC_YEAR",
    "AUTHORITY",
    "EVENT_NAME",
    "RAW_DATE_TEXT",
    "DATE_SCRAPED",
]


# ------------------------------------------- Functions --------------------------------------------


def normalise_academic_year(text):
    """Convert 2026/2027 into 2026/27."""

    match = re.search(r"\b(20\d{2})\s*/\s*(20\d{2})\b", text)

    if not match:
        return None

    start_year = int(match.group(1))
    end_year = int(match.group(2))

    if end_year != start_year + 1:
        return None

    return f"{start_year}/{str(end_year)[-2:]}"


def is_academic_year_heading(tag):
    """Identify academic-year headings."""

    if tag.name not in ["h2", "h3", "h4"]:
        return False

    return normalise_academic_year(
        tag.get_text(" ", strip=True)
    ) is not None


def validate_date_range(date_text):
    """Check that two written dates are present."""

    date_pattern = (
        r"(?:"
        r"Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|"
        r"Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?"
        r")?\s*"
        r"\d{1,2}(?:st|nd|rd|th)?\s+"
        r"[A-Za-z]+"
        r"(?:\s+20\d{2})?"
    )

    matches = re.findall(
        date_pattern,
        date_text,
        flags=re.IGNORECASE
    )

    if len(matches) < 2:
        raise ValueError(
            f"Could not identify two dates in: {date_text}"
        )


def scrape_knowsley():
    """Scrape Knowsley school term and half-term dates."""

    url = get_source_url(SOURCE_ID)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    events = []
    academic_year = None

    for element in soup.find_all(["h2", "h3", "h4", "tr"]):

        if element.name != "tr":
            if is_academic_year_heading(element):
                academic_year = normalise_academic_year(
                    element.get_text(" ", strip=True)
                )
            continue

        if academic_year is None:
            continue

        event_cell = element.find("th")
        date_cell = element.find("td")

        if event_cell is None or date_cell is None:
            continue

        event_name = event_cell.get_text(" ", strip=True)
        date_text = date_cell.get_text(" ", strip=True)

        if not event_name or not date_text:
            continue

        validate_date_range(date_text)

        events.append({
            "SOURCE_ID": SOURCE_ID,
            "ACADEMIC_YEAR": academic_year,
            "AUTHORITY": AUTHORITY,
            "EVENT_NAME": event_name,
            "RAW_DATE_TEXT": date_text,
            "DATE_SCRAPED": date.today().isoformat(),
        })

    if not events:
        raise ValueError(
            "No term date rows extracted. "
            "Inspect the page HTML and pipe-separated text nodes."
        )

    results = pd.DataFrame(
        events,
        columns=OUTPUT_COLUMNS
    )

    # Remove duplicates caused by nested HTML elements.
    results = results.drop_duplicates(
        subset=[
            "ACADEMIC_YEAR",
            "EVENT_NAME",
            "RAW_DATE_TEXT"
        ]
    ).reset_index(drop=True)

    return results


# --------------------------------------------- Testing --------------------------------------------

if __name__ == "__main__":

    results = scrape_knowsley()

    print(f"Records extracted: {len(results)}")

    print(
        results.groupby("ACADEMIC_YEAR")
        .size()
        .rename("RECORDS")
    )

    print(results.to_string(index=False))
