
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Central Bedfordshire school-term and holiday events from the published webpage. The
# output is one row per event and academic year, retaining the published date wording.
#
# NOTE: The council also publishes PDF calendars for 2025/26, 2026/27 and 2027/28. These are
# intentionally excluded for now because the PDF formats require separate extraction logic.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC003"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

YEAR_PATTERN = re.compile(r"(\d{4})\s+to\s+(\d{4})")

MONTH_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b"
    ,re.IGNORECASE
)



# ------------------------------------------- Main Code --------------------------------------------

def scrape_central_bedfordshire():

    """
    Retrieve school-term and holiday events from the Central Bedfordshire webpage.

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

        # Extract events until the next academic-year heading.
        for element in heading.next_elements:

            if element is not heading and getattr(element, "name", None) == "h2":
                break

            if getattr(element, "name", None) != "li":
                continue

            # Dates are published in bold elements within each list item.
            date_elements = [
                date for date in element.find_all("strong")
                if MONTH_PATTERN.search(date.get_text(" ", strip = True))
            ]

            if not date_elements:
                continue

            raw_dates = [date.get_text(" ", strip = True) for date in date_elements]

            # Remove the date text to retain the event description.
            event_name = element.get_text(" ", strip = True)

            for raw_date in raw_dates:
                event_name = event_name.replace(raw_date, "", 1)

            event_name = re.sub(r"\s+", " ", event_name).strip(" ,:-")

            # Remove dangling connecting words left after removing the dates.
            event_name = re.sub(r"\s+\b(on|is|from)\s*$", "", event_name, flags = re.IGNORECASE)

            if not event_name:
                continue

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : event_name
                           ,"RAW_DATE_TEXT" : " | ".join(raw_dates)
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records, columns = OUTPUT_COLUMNS)
