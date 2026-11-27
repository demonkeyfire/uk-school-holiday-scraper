
# -------------------------------------------- Overview --------------------------------------------

# Retrieve school term and half-term dates from Knowsley Council.
# The output is one row per published event and academic year.
# Original date wording is retained in RAW_DATE_TEXT.
#
# The page presents dates as text rows separated by a vertical bar,
# rather than using HTML tables.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag

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
    """Convert a heading such as 'School year 2026/2027' to '2026/27'."""

    match = re.search(r"\b(20\d{2})\s*/\s*(20\d{2})\b", text)

    if not match:
        return None

    start_year = int(match.group(1))
    end_year = int(match.group(2))

    if end_year != start_year + 1:
        return None

    return f"{start_year}/{str(end_year)[-2:]}"


def is_academic_year_heading(tag):
    """Identify headings containing an academic-year label."""

    if tag.name not in ["h2", "h3", "h4"]:
        return False

    return normalise_academic_year(
        tag.get_text(" ", strip=True)
    ) is not None


def validate_date_range(date_text):
    """Check that the text contains two written dates."""

    date_pattern = (
        r"(?:"
        r"(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|"
        r"Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
        r"\s+"
        r")?"
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
            f"Could not identify two written dates in: {date_text}"
        )


def is_date_row(tag):
    """Identify a leaf-level HTML element containing a pipe-separated row."""

    if tag.name not in ["p", "div", "li", "tr"]:
        return False

    text = tag.get_text(" ", strip=True)

    if "|" not in text:
        return False

    # Avoid extracting the same row from parent containers.
    for child in tag.find_all(["p", "div", "li", "tr"]):
        if "|" in child.get_text(" ", strip=True):
            return False

    return True


def extract_event_row(text, academic_year):
    """Split a published row into event name and date wording."""

    parts = text.split("|", maxsplit=1)

    if len(parts) != 2:
        return None

    event_name = parts[0].strip()
    date_text = parts[1].strip()

    if not event_name or not date_text:
        return None

    validate_date_range(date_text)

    return {
        "SOURCE_ID": SOURCE_ID,
        "ACADEMIC_YEAR": academic_year,
        "AUTHORITY": AUTHORITY,
        "EVENT_NAME": event_name,
        "RAW_DATE_TEXT": date_text,
        "DATE_SCRAPED": date.today().isoformat(),
    }


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
    current_year = None

    # Process page elements in document order.
    for element in soup.find_all(
        ["h2", "h3", "h4", "p", "div", "li", "tr"]
    ):

        if is_academic_year_heading(element):
            current_year = normalise_academic_year(
                element.get_text(" ", strip=True)
            )
            continue

        if current_year is None:
            continue

        if not is_date_row(element):
            continue

        event = extract_event_row(
            element.get_text(" ", strip=True),
            current_year
        )

        if event is not None:
            events.append(event)

    if not events:
        raise ValueError(
            "No term date rows were extracted from the page."
        )

    results = pd.DataFrame(
        events,
        columns=OUTPUT_COLUMNS
    )

    # Check for duplicate events.
    duplicate_columns = [
        "ACADEMIC_YEAR",
        "EVENT_NAME",
        "RAW_DATE_TEXT"
    ]

    if results.duplicated(subset=duplicate_columns).any():
        raise ValueError("Duplicate events detected.")

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
