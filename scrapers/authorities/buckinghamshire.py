
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Buckinghamshire school-term and holiday events from the published webpage. The output
# is one row per event and academic year, retaining the published date wording.
#
# NOTE: The 2025/26 webpage section currently contains only the summer term dates. The scraper
# extracts the information published rather than attempting to fill the missing terms.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC008"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

YEAR_PATTERN = re.compile(r"(\d{4})\s*(?:/|to)\s*(\d{2,4})", re.IGNORECASE)
TERM_PATTERN = re.compile(r"(Autumn|Spring|Summer)\s+term\s+(\d{4})", re.IGNORECASE)



# ------------------------------------------- Main Code --------------------------------------------

def scrape_buckinghamshire():

    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    records = []

    for heading in soup.find_all(["h2", "h3"]):

        heading_text = heading.get_text(" ", strip = True)
        term_match = TERM_PATTERN.search(heading_text)

        if term_match is None:
            continue

        term_name = term_match.group(1).title()
        term_year = int(term_match.group(2))

        # Autumn terms begin the academic year; spring and summer terms belong to the
        # academic year that started in the preceding calendar year.
        year_start = term_year if term_name == "Autumn" else term_year - 1
        academic_year = f"{year_start}/{str(year_start + 1)[-2:]}"

        # Find the table associated with this term heading, stopping at the next heading.
        table = None

        for element in heading.next_elements:

            if element is not heading and getattr(element, "name", None) in ["h2", "h3"]:
                break

            if getattr(element, "name", None) == "table":
                table = element
                break

        if table is None:
            continue

        for row in table.find_all("tr"):

            cells = row.find_all(["th", "td"])

            if len(cells) < 2:
                continue

            event_label = cells[0].get_text(" ", strip = True)
            raw_date_text = cells[1].get_text(" ", strip = True)

            if not event_label or not raw_date_text:
                continue

            if event_label.lower() in ["starts", "half term", "ends"]:
                event_name = f"{term_name} {event_label.lower()}"
            else:
                event_name = event_label

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : event_name
                           ,"RAW_DATE_TEXT" : raw_date_text
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)
