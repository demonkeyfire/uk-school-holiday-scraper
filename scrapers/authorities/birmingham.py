
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Birmingham school-term and holiday events from the published webpage. The output is one
# row per event and academic year, retaining the published date wording.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC004"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

YEAR_PATTERN = re.compile(r"(\d{4})\s+to\s+(\d{4})")
TERM_PATTERN = re.compile(r"^(Autumn|Spring|Summer)\s+Term", re.IGNORECASE)

EVENT_PATTERN = re.compile(
    r"^(Term starts|Half-term|Term ends)\s*:\s*(.+)$"
    ,re.IGNORECASE
)



# ------------------------------------------- Main Code --------------------------------------------

def scrape_birmingham():

    """
    Retrieve school-term and holiday events from the Birmingham webpage.

    Returns
    -------
    pandas.DataFrame
        One row per published event, using the standard scraper output columns.
    """

    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    records = []

    # Process each academic-year section independently.
    for heading in soup.find_all("h2"):

        heading_text = heading.get_text(" ", strip = True)
        year_match = YEAR_PATTERN.search(heading_text)

        if year_match is None:
            continue

        academic_year = f"{year_match.group(1)}/{year_match.group(2)[-2:]}"
        current_term = None

        # Extract events until the next academic-year heading.
        for element in heading.next_elements:

            if element is not heading and getattr(element, "name", None) == "h2":
                break

            # Identify the term associated with subsequent events.
            if getattr(element, "name", None) == "h3":

                term_match = TERM_PATTERN.search(
                    element.get_text(" ", strip = True)
                )

                if term_match:
                    current_term = term_match.group(1).title()

                continue

            if getattr(element, "name", None) not in ["p", "li"]:
                continue

            # Avoid processing a paragraph twice if it is nested inside a list item.
            if element.name == "p" and element.find_parent("li") is not None:
                continue

            event_text = element.get_text(" ", strip = True)
            event_match = EVENT_PATTERN.match(event_text)

            if event_match is None or current_term is None:
                continue

            event_type = event_match.group(1).lower()
            raw_date_text = event_match.group(2).strip()

            if event_type == "term starts":
                event_name = f"{current_term} term starts"

            elif event_type == "half-term":
                event_name = f"{current_term} half-term"

            else:
                event_name = f"{current_term} term ends"

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : event_name
                           ,"RAW_DATE_TEXT" : raw_date_text
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)
