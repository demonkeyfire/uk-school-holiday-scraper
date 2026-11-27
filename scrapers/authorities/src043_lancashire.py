
# -------------------------------------------- Overview --------------------------------------------

# Retrieve school term and holiday framework dates from Lancashire County Council.
# The output is one row per published date event and academic year.
#
# Events include:
#   - Term starts
#   - Half terms
#   - Term ends
#   - May Day
#
# The original published date wording is retained in RAW_DATE_TEXT.
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


def is_academic_year_heading(tag):
    """Identify academic-year headings."""

    if tag.name not in ["h2", "h3", "h4"]:
        return False

    return normalise_academic_year(
        tag.get_text(" ", strip=True)
    ) is not None


def is_term_heading(tag):
    """Identify headings such as Autumn Term 2026."""

    if tag.name not in ["h2", "h3", "h4"]:
        return False

    text = tag.get_text(" ", strip=True)

    return bool(
        re.search(
            r"\b(?:Autumn|Spring|Summer)\s+Term\b",
            text,
            flags=re.IGNORECASE
        )
    )


def parse_event_line(text, term_name):
    """Extract an event label and its original date wording."""

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

    # Remove minor wording variations without altering the date itself.
    date_text = re.sub(
        r"^(?:on\s+)",
        "",
        date_text,
        flags=re.IGNORECASE
    ).strip()

    if not date_text:
        return None

    # Require at least one complete written date.
    date_pattern = (
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
        r"\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s+"
        r"[A-Za-z]+\s+20\d{2}"
    )

    if not re.search(date_pattern, date_text, flags=re.IGNORECASE):
        raise ValueError(
            f"Could not identify a complete date in: {date_text}"
        )

    event_name = f"{term_name} - {event_type}"

    return event_name, date_text


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

    # Process headings and text blocks in document order.
    for element in soup.find_all(
        ["h2", "h3", "h4", "p", "li"]
    ):

        # Academic-year heading.
        if is_academic_year_heading(element):
            current_year = normalise_academic_year(
                element.get_text(" ", strip=True)
            )
            current_term = None
            continue

        # Term heading.
        if is_term_heading(element):
            current_term = element.get_text(" ", strip=True)
            continue

        if current_year is None or current_term is None:
            continue

        text = element.get_text(" ", strip=True)

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
            "Check the page headings and date text structure."
        )

    results = pd.DataFrame(
        events,
        columns=OUTPUT_COLUMNS
    )

    # Remove duplicate rows if the page contains repeated HTML elements.
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
