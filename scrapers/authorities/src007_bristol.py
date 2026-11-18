
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Bristol school-term dates from the published webpage. The output is one row per term
# and academic year, retaining the published date wording.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC007"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

YEAR_PATTERN = re.compile(r"(\d{4})\s+to\s+(\d{4})", re.IGNORECASE)



# ------------------------------------------- Main Code --------------------------------------------

def scrape_bristol():

    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    records = []

    for heading in soup.find_all("h2"):
        heading_text = heading.get_text(" ", strip = True)
        year_match = YEAR_PATTERN.search(heading_text)

        if year_match is None:
            continue

        academic_year = f"{year_match.group(1)}/{year_match.group(2)[-2:]}"

        for element in heading.next_elements:

            if element is not heading and getattr(element, "name", None) == "h2":
                break

            if getattr(element, "name", None) != "li":
                continue

            event_text = element.get_text(" ", strip = True)

            if ":" not in event_text:
                continue

            event_name, raw_date_text = event_text.split(":", 1)

            event_name = event_name.strip()
            raw_date_text = re.sub(r"\s+", " ", raw_date_text).strip()

            if not event_name or not raw_date_text:
                continue

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : event_name
                           ,"RAW_DATE_TEXT" : raw_date_text
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)
