
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Cambridgeshire school-term and holiday events from the published webpage. The output is
# one row per term or holiday event and academic year, retaining the published date wording.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url



# --------------------------------------------- Input ----------------------------------------------

# Identify the source using its unique ID in the central sources.csv register.
SOURCE_ID = "SRC009"

# Define the request headers used when retrieving the published webpage.
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

# Define the columns returned by the scraper.
OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

# Match academic-year headings containing two consecutive calendar years.
YEAR_PATTERN = re.compile(r"\b(\d{4})\s*-\s*(\d{4})\b")

# Identify term headings.
TERM_PATTERN = re.compile(r"^(Autumn|Spring|Summer)\s+term", re.IGNORECASE)

# Remove the published day count from term-date entries.
DAY_COUNT_PATTERN = re.compile(r"\s*\(\d+\s+days?\)\s*$", re.IGNORECASE)

# Identify month names in published date text.
MONTH_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b"
    ,re.IGNORECASE
)



# ------------------------------------------- Helper Functions -------------------------------------

def clean_text(value):

    """Normalise whitespace in extracted webpage text."""

    return re.sub(r"\s+", " ", value).strip()


def extract_academic_year(heading_text):

    """Extract and validate the academic year from a webpage heading."""

    year_match = YEAR_PATTERN.search(heading_text)

    if year_match is None:
        return None

    start_year = int(year_match.group(1))
    end_year = int(year_match.group(2))

    if end_year != start_year + 1:
        raise ValueError(f"Invalid academic year in heading: {heading_text!r}")

    return f"{start_year}/{str(end_year)[-2:]}"


def extract_event(element, term_name):

    """Extract an event name and its published date text from a list item."""

    event_text = clean_text(element.get_text(" ", strip = True))

    if not event_text:
        return None

    if ":" in event_text:
        event_name, raw_date_text = event_text.split(":", maxsplit = 1)
        event_name = clean_text(event_name)
        raw_date_text = clean_text(raw_date_text)

    else:
        if term_name is None or MONTH_PATTERN.search(event_text) is None:
            return None

        event_name = f"{term_name} term"
        raw_date_text = clean_text(DAY_COUNT_PATTERN.sub("", event_text))

    if not event_name or not raw_date_text:
        return None

    if MONTH_PATTERN.search(raw_date_text) is None:
        return None

    return event_name, raw_date_text



# ------------------------------------------- Main Code --------------------------------------------

def scrape_cambridgeshire():

    """
    Retrieve school-term and holiday events from the Cambridgeshire webpage.

    Returns
    -------
    pandas.DataFrame
        One row per published term or holiday event, using the standard scraper output columns.
    """

    source_url = get_source_url(SOURCE_ID)

    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    records = []
    seen_records = set()
    date_scraped = datetime.now(timezone.utc).date()

    for heading in soup.find_all("h2"):

        heading_text = clean_text(heading.get_text(" ", strip = True))
        academic_year = extract_academic_year(heading_text)

        if academic_year is None:
            continue

        term_name = None

        for element in heading.next_elements:

            if element is not heading and getattr(element, "name", None) == "h2":
                break

            if getattr(element, "name", None) == "h3":

                term_match = TERM_PATTERN.match(
                    clean_text(element.get_text(" ", strip = True)))

                term_name = term_match.group(1).title() if term_match else None
                continue

            if getattr(element, "name", None) != "li":
                continue

            event = extract_event(element, term_name)

            if event is None:
                continue

            event_name, raw_date_text = event

            record = {"SOURCE_ID"     : SOURCE_ID
                     ,"ACADEMIC_YEAR" : academic_year
                     ,"EVENT_NAME"    : event_name
                     ,"RAW_DATE_TEXT" : raw_date_text
                     ,"DATE_SCRAPED"  : date_scraped}

            record_key = (academic_year, event_name, raw_date_text)

            if record_key in seen_records:
                raise ValueError(
                    f"Duplicate event found for {academic_year}: "
                    f"{event_name!r} - {raw_date_text!r}")

            seen_records.add(record_key)
            records.append(record)

    return pd.DataFrame.from_records(records
                                    ,columns = OUTPUT_COLUMNS)
