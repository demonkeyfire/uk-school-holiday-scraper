# -------------------------------------------- Overview --------------------------------------------

# Retrieve Bath & North East Somerset school-term dates from the published page.
# The output is one row per term boundary and academic year, retaining the source's date wording.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

# Identify the source using its unique ID in the central sources.csv register.
SOURCE_ID = "SRC002"

# Define the request headers used when retrieving the published page.
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

# Define the columns returned by the scraper.
OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

# Match academic years published in the page headings.
YEAR_PATTERN = re.compile(r"School year (\d{4}) to (\d{4})"
                         ,re.IGNORECASE)



# ------------------------------------------- Main Code --------------------------------------------

# Fetch the published page and convert each academic-year table into a raw event DataFrame.
def scrape_bath_north_east_somerset():

    """
    Return raw school-term boundary events from the Bath & North East Somerset source page.

    The source URL is retrieved from the central sources.csv register using SOURCE_ID.

    This scraper preserves the published date wording, leaving date parsing and normalisation
    to the downstream processing step.

    Returns
    -------
    pd.DataFrame
        One row per term start or end and academic year, with columns:
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

    # Identify academic-year headings and their associated term tables.
    for heading in soup.find_all("h2"):
        heading_text = heading.get_text(" ", strip = True)
        match = YEAR_PATTERN.search(heading_text)

        if match is None:
            continue

        # Convert the published year range into the standard academic-year format.
        academic_year = f"{match.group(1)}/{match.group(2)[-2:]}"

        # Locate the first table following the current academic-year heading.
        table = None

        for element in heading.next_elements:
            element_name = getattr(element, "name", None)

            # Stop if another heading is encountered before a table.
            if element_name is not None and re.fullmatch(r"h[1-6]", element_name):
                break

            if element_name == "table":
                table = element
                break

        # Report and skip a year section without a table.
        if table is None:
            print(f"No table found: {academic_year}")
            continue

        # Extract term start and end dates from the table.
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])

            if len(cells) < 3:
                continue

            term = cells[0].get_text(" ", strip = True)
            start_date = cells[1].get_text(" ", strip = True)
            end_date = cells[2].get_text(" ", strip = True)

            # Skip the table header and incomplete rows.
            if term.lower() == "term" or not start_date or not end_date:
                continue

            # Create separate records for the start and end of each term.
            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : f"Term {term} start"
                           ,"RAW_DATE_TEXT" : start_date
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : f"Term {term} end"
                           ,"RAW_DATE_TEXT" : end_date
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records
                                    ,columns = OUTPUT_COLUMNS)
