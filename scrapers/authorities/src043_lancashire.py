
# -------------------------------------------- Overview --------------------------------------------

# Retrieve school term and holiday framework dates from Lancashire County Council.
#
# The output is one row per published event and academic year.
#
# Events include:
#   - Term starts
#   - Half terms
#   - Term ends
#   - May Day
#
# Each labelled event is extracted separately.
# Original published date wording is retained in RAW_DATE_TEXT.
#
# Individual school INSET days are not included because schools choose these
# independently.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url


SOURCE_ID = "SRC043"
AUTHORITY = "Lancashire"

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


def parse_event_line(text, term_name):
    """Extract one event label and its associated date wording."""

    text = re.sub(r"\s+", " ", text).strip()

    match = re.match(
        r"^(Starts|Half\s*term|Ends|May\s*Day)\s*:\s*(.+)$",
        text,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    event_type = re.sub(
        r"\s+",
        " ",
        match.group(1).strip()
    ).title()

    date_text = match.group(2).strip()

    # Remove 'on' from the beginning of the date text.
    date_text = re.sub(
        r"^on\s+",
        "",
        date_text,
        flags=re.IGNORECASE
    ).strip()

    if not date_text:
        return None

    event_name = f"{term_name} - {event_type}"

    return event_name, date_text


def is_term_heading(element):
    """Identify headings such as Autumn Term 2025."""

    if element.name not in ["h2", "h3", "h4"]:
        return False

    return bool(
        re.search(
            r"\b(?:Autumn|Spring|Summer)\s+Term\b",
            element.get_text(" ", strip=True),
            flags=re.IGNORECASE
        )
    )


def scrape_lancashire():
    """Scrape Lancashire school term and holiday dates."""

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
    current_term = None

    # Process individual HTML elements in document order.
    for element in soup.find_all(
        ["h2", "h3", "h4", "p", "li"]
    ):

        text = element.get_text(" ", strip=True)

        # Academic-year heading.
        academic_year = normalise_academic_year(text)

        if academic_year:
            current_year = academic_year
            current_term = None
            continue

        # Term heading.
        if is_term_heading(element):
            current_term = text
            continue

        if current_year is None or current_term is None:
            continue

        # Extract one event from this individual element.
        parsed = parse_event_line(text, current_term)

        if parsed is None:
            continue

        event_name, date_text = parsed

        events.append({
            "SOURCE_ID": SOURCE_ID,
            "ACADEMIC_YEAR": current_year,
            "AUTHORITY": AUTHORITY,
            "EVENT_NAME": event_name,
            "RAW_DATE_TEXT": date_text,
            "DATE_SCRAPED": date.today().isoformat(),
        })

    if not events:
        raise ValueError(
            "No term date events extracted. "
            "Check the page HTML structure."
        )

    results = pd.DataFrame(
        events,
        columns=OUTPUT_COLUMNS
    )

    # Remove duplicate events if the page contains repeated HTML elements.
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

    results = scrape_lancashire()

    print(f"Records extracted: {len(results)}")

    print(
        results.groupby("ACADEMIC_YEAR")
        .size()
        .rename("RECORDS")
    )

    print(results.to_string(index=False))
