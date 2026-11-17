
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Aberdeenshire school-term and holiday events from the published page.
# The output is one row per event and academic year, retaining the source's date wording.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

# Identify the source using its unique ID in the central sources.csv register.
SOURCE_ID = "SRC001"

# Define the request headers used when retrieving the published page.
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

# Define the columns returned by the scraper.
OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

# Restrict extraction to the academic years currently required.
ACADEMIC_YEARS = {"2026/27"
                 ,"2027/28"
                 ,"2028/29"
                 ,"2029/30"}

# Match a single date or range followed by the event label for each list item.
EVENT_PATTERN = re.compile(r"^("
                          r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"
                          r"(?:\s+to\s+\d{1,2}\s+[A-Za-z]+\s+\d{4})?"
                          r")\s+-\s+(.+)$")



# ------------------------------------------- Main Code --------------------------------------------

# Fetch the published page and convert each academic-year section into a raw event DataFrame.
def scrape_aberdeenshire():

    """
    Return raw school-term and holiday events from the Aberdeenshire source page.

    The source URL is retrieved from the central sources.csv register using SOURCE_ID.

    This scraper preserves the source's publication wording and date span text so downstream
    cleaning can parse and normalise dates consistently.

    Returns
    -------
    pd.DataFrame
        One row per event and academic year, with columns:
            SOURCE_ID
            ACADEMIC_YEAR
            EVENT_NAME
            RAW_DATE_TEXT
            DATE_SCRAPED
    """

    # Retrieve the source metadata, including its URL, from the central source register.
    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    # Retrieve the published page.
    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    # Parse the returned HTML content.
    soup = BeautifulSoup(response.content
                        ,"html.parser")
    records = []

    # Identify academic-year headings, allowing for additional text after the year.
    year_pattern = re.compile(r"(\d{4}/\d{2})")

    for heading in soup.find_all("h2"):
        heading_text = heading.get_text(" ", strip = True)
        match = year_pattern.search(heading_text)

        if match is None:
            continue

        academic_year = match.group(1)

        if academic_year not in ACADEMIC_YEARS:
            continue

        # Extract each event item within the current academic-year section and ignore the rest.
        for element in heading.next_elements:
            if getattr(element, "name", None) == "h2":
                break

            if getattr(element, "name", None) != "li":
                continue

            raw_text = element.get_text(" ", strip = True)
            match = EVENT_PATTERN.match(raw_text)

            if match is None:
                continue

            raw_date_text = match.group(1)
            event_name = match.group(2).strip()

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : event_name
                           ,"RAW_DATE_TEXT" : raw_date_text
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records
                                    ,columns = OUTPUT_COLUMNS)
