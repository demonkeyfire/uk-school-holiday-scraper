
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Lancashire school term and holiday dates.
# Each term section may contain multiple events in one text block, so the scraper
# splits the section using the published event labels rather than relying on HTML
# elements to separate the events.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from scrapers.source_config import get_source_url


SOURCE_ID = "SRC043"

EVENT_LABELS = {
    "starts": "Starts",
    "half term": "Half Term",
    "ends": "Ends",
    "may day": "May Day",
}


# -------------------------------------------- Helpers ---------------------------------------------

def is_term_heading(text):
    """Identify Autumn, Spring or Summer term headings."""

    return bool(
        re.search(
            r"\b(Autumn|Spring|Summer)\s+Term\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def get_term_details(text):
    """Return the term name and year from a term heading."""

    match = re.search(
        r"\b(Autumn|Spring|Summer)\s+Term\b\s*(20\d{2})?",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None, None

    term_name = match.group(1).title()
    term_year = int(match.group(2)) if match.group(2) else None

    return term_name, term_year


def academic_year_from_term(term_name, term_year):
    """Infer the academic year from the term and its calendar year."""

    if term_year is None:
        return None

    if term_name == "Autumn":
        start_year = term_year
    else:
        start_year = term_year - 1

    return f"{start_year}/{str(start_year + 1)[-2:]}"


def extract_section_text(heading):
    """
    Collect all text after a term heading until the next term heading
    or academic-year heading.

    Navigating text nodes avoids processing the same content multiple
    times through nested parent and child elements.
    """

    text_parts = []

    for element in heading.next_elements:

        if isinstance(element, Tag) and element.name in [
            "h1", "h2", "h3", "h4", "h5", "h6"
        ]:
            heading_text = element.get_text(" ", strip=True)

            if is_term_heading(heading_text):
                break

            if re.search(
                r"\b20\d{2}\s*(?:/|to|-)\s*(?:20)?\d{2}\b",
                heading_text,
                flags=re.IGNORECASE,
            ):
                break

        if isinstance(element, NavigableString):
            value = str(element).strip()

            if value:
                text_parts.append(value)

    return " ".join(text_parts)


def split_events(section_text, term_name):
    """Split a combined term section into individual labelled events."""

    label_pattern = re.compile(
        r"(?<!\w)(Starts|Half\s*term|Ends|May\s*Day)\s*:",
        flags=re.IGNORECASE,
    )

    matches = list(label_pattern.finditer(section_text))
    events = []

    for i, match in enumerate(matches):

        start = match.end()

        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(section_text)

        date_text = section_text[start:end].strip()

        # Remove separators left between events, but retain the published
        # wording of the date itself.
        date_text = date_text.strip(" ;|")

        if not date_text:
            continue

        label_key = re.sub(r"\s+", " ", match.group(1).lower())
        event_type = EVENT_LABELS[label_key]

        events.append({
            "EVENT_NAME": f"{term_name} Term - {event_type}",
            "RAW_DATE_TEXT": date_text,
        })

    return events


# --------------------------------------------- Scraper --------------------------------------------

def scrape_lancashire():

    url = get_source_url(SOURCE_ID)

    response = requests.get(
        url,
        headers={
            "User-Agent": "SchoolHolidayResearch/1.0"
        },
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    records = []
    current_academic_year = None

    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

    for heading in headings:

        heading_text = heading.get_text(" ", strip=True)

        # Update academic year if the page contains an explicit year heading.
        year_match = re.search(
            r"\b(20\d{2})\s*(?:/|to|-)\s*(?:20)?(\d{2})\b",
            heading_text,
        )

        if year_match and not is_term_heading(heading_text):

            start_year = int(year_match.group(1))
            current_academic_year = (
                f"{start_year}/{str(start_year + 1)[-2:]}"
            )

            continue

        if not is_term_heading(heading_text):
            continue

        term_name, term_year = get_term_details(heading_text)

        # Prefer the academic year inferred from the term heading.
        academic_year = academic_year_from_term(term_name, term_year)

        if academic_year is None:
            academic_year = current_academic_year

        if academic_year is None:
            continue

        section_text = extract_section_text(heading)

        events = split_events(section_text, term_name)

        for event in events:

            records.append({
                "SOURCE_ID": SOURCE_ID,
                "ACADEMIC_YEAR": academic_year,
                "AUTHORITY": "Lancashire",
                "EVENT_NAME": event["EVENT_NAME"],
                "RAW_DATE_TEXT": event["RAW_DATE_TEXT"],
                "DATE_SCRAPED": datetime.now().date(),
            })

    df = pd.DataFrame(records)

    if df.empty:
        raise ValueError(
            "No events extracted. Inspect the page headings and term section text."
        )

    df = df.drop_duplicates(
        subset=[
            "SOURCE_ID",
            "ACADEMIC_YEAR",
            "EVENT_NAME",
            "RAW_DATE_TEXT",
        ]
    ).reset_index(drop=True)

    return df
