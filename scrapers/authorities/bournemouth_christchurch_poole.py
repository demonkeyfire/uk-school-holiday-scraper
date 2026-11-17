
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Bournemouth, Christchurch and Poole school-term and holiday events from the published
# webpage. The output is one row per event and academic year, retaining the published date wording.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC005"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

YEAR_PATTERN = re.compile(r"From\s+(\d{4})\s+to\s+(\d{4})", re.IGNORECASE)



# ------------------------------------------- Main Code --------------------------------------------

def scrape_bournemouth_christchurch_poole():

    """
    Retrieve school-term and holiday events from the BCP webpage.

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

        year_match = YEAR_PATTERN.search(heading.get_text(" ", strip = True))

        if year_match is None:
            continue

        academic_year = f"{year_match.group(1)}/{year_match.group(2)[-2:]}"

        # Extract events until the next academic-year heading.
        for element in heading.next_elements:

            if element is not heading and getattr(element, "name", None) == "h2":
                break

            if getattr(element, "name", None) not in ["p", "li"]:
                continue

            # Avoid processing nested text blocks more than once.
            if element.find_parent(["p", "li"]) is not None:
                continue

            event_text = element.get_text(" ", strip = True)

            if ":" not in event_text:
                continue

            event_name, raw_date_text = event_text.split(":", 1)

            event_name = re.sub(r"\s+", " ", event_name).strip()
            raw_date_text = re.sub(r"\s+", " ", raw_date_text).strip()

            if not event_name or not raw_date_text:
                continue

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : event_name
                           ,"RAW_DATE_TEXT" : raw_date_text
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)
