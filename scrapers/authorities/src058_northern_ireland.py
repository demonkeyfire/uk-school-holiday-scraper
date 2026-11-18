
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Northern Ireland school-holiday rows from the published page. The output is one row per
# event and academic year, retaining the source's page order and unparsed date text.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

# Identify the source using its unique ID in the central sources.csv register.
SOURCE_ID = "SRC058"

# Define the request headers used when retrieving the published page.
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

# Keep the extracted column order explicit so an empty result still has a stable schema.
OUTPUT_COLUMNS = ("SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED")



# ------------------------------------------- Main Code --------------------------------------------

# Request the official page and parse each academic-year section's first table, stopping at the next
# heading so rows are not accidentally attributed to a neighbouring year.
def scrape_northern_ireland():

    """
    Return raw school-holiday event rows from the Northern Ireland source page.

    The source URL is retrieved from the central sources.csv register using SOURCE_ID.

    This scraper preserves the published ordering and raw date text, leaving all date parsing to the
    downstream normalisation step.

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

    # Retrieve the official page.
    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    # Parse the returned HTML content.
    soup = BeautifulSoup(response.content
                        ,"html.parser")
    records = []

    # Identify headings containing academic-year labels.
    year_pattern = re.compile(r"School holidays\s+(\d{4})\s*/\s*(\d{4})"
                             ,re.IGNORECASE)
    headings = soup.find_all(re.compile(r"^h[1-6]$"))

    for heading in headings:
        match = year_pattern.search(heading.get_text(" ", strip = True))
        if match is None:
            continue

        academic_year = f"{match.group(1)}/{match.group(2)}"
        table = None

        # Locate the first table within the current academic-year section.
        for element in heading.next_elements:
            element_name = getattr(element, "name", None)

            if element_name is not None and re.fullmatch(r"h[1-6]", element_name):
                break

            if element_name == "table":
                table = element
                break

        # Report and skip a year section without a table so source-page layout changes are visible.
        if table is None:
            print(f"No table found: {academic_year}")
            continue

        # Extract event names and their corresponding raw date text.
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            event = cells[0].get_text(" ", strip = True)
            raw_dates = cells[1].get_text(" ", strip = True)

            # Skip table headers and empty rows.
            if event.lower() == "event" or not event or not raw_dates:
                continue

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : event
                           ,"RAW_DATE_TEXT" : raw_dates
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records
                                    ,columns = OUTPUT_COLUMNS)
