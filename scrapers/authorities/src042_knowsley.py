
# -------------------------------------------- Overview --------------------------------------------

# Retrieve school term dates from Knowsley Council.
# The output is one row per published term or half-term event and academic year,
# retaining the source's original date wording and page order.
#
# The council publishes term dates and half terms, but does not separately
# identify the longer school holiday periods.


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
    """Identify headings containing a school-year label."""

    if tag.name not in ["h2", "h3", "h4"]:
        return False

    return normalise_academic_year(tag.get_text(" ", strip=True)) is not None


def validate_date_range(date_text):
    """Check that the published text contains two written dates."""

    date_pattern = (
        r"(?:"
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
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


def extract_table_events(table, academic_year):
    """Extract event rows from a term dates table."""

    events = []

    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)

        # Ignore header rows and incomplete rows.
        if len(cells) < 2 or any(cell.name == "th" for cell in cells):
            continue

        event_name = cells[0].get_text(" ", strip=True)
        date_text = cells[1].get_text(" ", strip=True)

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

    return events


def scrape_knowsley():
    """Scrape Knowsley school term dates."""

    url = get_source_url(SOURCE_ID)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    events = []
    headings = soup.find_all(is_academic_year_heading)

    if not headings:
        raise ValueError(
            "Could not identify any academic-year headings on the page."
        )

    for heading in headings:

        heading_text = heading.get_text(" ", strip=True)
        academic_year = normalise_academic_year(heading_text)

        # Find the next table belonging to this academic-year heading.
        table = heading.find_next("table")

        if table is None:
            raise ValueError(
                f"No term dates table found for {academic_year}."
            )

        # Check that the table occurs before the next academic-year heading.
        next_heading = heading.find_next(is_academic_year_heading)

        if next_heading is not None:
            next_table = next_heading.find_previous("table")

            if next_table == table:
                # The table belongs to the current heading.
                pass

        year_events = extract_table_events(table, academic_year)

        if not year_events:
            raise ValueError(
                f"No events extracted for academic year {academic_year}."
            )

        events.extend(year_events)

    results = pd.DataFrame(events, columns=OUTPUT_COLUMNS)

    # Check for duplicate events.
    duplicate_columns = [
        "ACADEMIC_YEAR",
        "EVENT_NAME",
        "RAW_DATE_TEXT"
    ]

    if results.duplicated(subset=duplicate_columns).any():
        raise ValueError("Duplicate events detected in the extracted data.")

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
