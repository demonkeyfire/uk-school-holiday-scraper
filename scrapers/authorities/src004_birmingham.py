
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Birmingham school-term and holiday events from the published webpage. The output is one
# row per event and academic year, retaining the published date wording.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC004"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

YEAR_PATTERN = re.compile(r"(\d{4})\s+to\s+(\d{4})")
TERM_PATTERN = re.compile(r"^(Autumn|Spring|Summer)\s+term", re.IGNORECASE)

EVENT_PATTERN = re.compile(
    r"(Term starts|Half-term|Term ends)\s*:\s*(.*?)(?=Term starts\s*:|Half-term\s*:|Term ends\s*:|$)"
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

    source_url = get_source_url(SOURCE_ID)

    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    records = []

    # Process each academic-year section independently.
    for heading in soup.find_all("h2"):

        year_match = YEAR_PATTERN.search(heading.get_text(" ", strip = True))

        if year_match is None:
            continue

        academic_year = f"{year_match.group(1)}/{year_match.group(2)[-2:]}"

        # Extract term information until the next academic-year heading.
        for element in heading.next_elements:

            if element is not heading and getattr(element, "name", None) == "h2":
                break

            if getattr(element, "name", None) != "h3":
                continue

            term_match = TERM_PATTERN.search(element.get_text(" ", strip = True))

            if term_match is None:
                continue

            term_name = term_match.group(1).title()

            # Find the text block immediately following the term heading.
            for content in element.next_elements:

                if getattr(content, "name", None) in ["h2", "h3"]:
                    break

                if getattr(content, "name", None) not in ["p", "li"]:
                    continue

                if content.find_parent(["p", "li"]) is not None:
                    continue

                term_text = content.get_text(" ", strip = True)

                for event_match in EVENT_PATTERN.finditer(term_text):

                    event_type = event_match.group(1).lower()
                    raw_date_text = event_match.group(2).strip()

                    if event_type == "term starts":
                        event_name = f"{term_name} term starts"

                    elif event_type == "half-term":
                        event_name = f"{term_name} half-term"

                    else:
                        event_name = f"{term_name} term ends"

                    records.append({"SOURCE_ID"     : SOURCE_ID
                                   ,"ACADEMIC_YEAR" : academic_year
                                   ,"EVENT_NAME"    : event_name
                                   ,"RAW_DATE_TEXT" : raw_date_text
                                   ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

                # Only process the first text block following the term heading.
                break

    return pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)
