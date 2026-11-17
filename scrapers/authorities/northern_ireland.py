# -------------------------------------------- Overview --------------------------------------------

# Retrieve Northern Ireland school-holiday rows from the published page. The output is one row per
# event and academic year, retaining the source's page order and unparsed date text.



# --------------------------------------------- Input ----------------------------------------------

# Keep imports in this cell so the scraper can be run independently of the notebook library setup.
import re
from datetime import datetime, timezone
import pandas as pd
import requests
from bs4 import BeautifulSoup



# ----------------------------------------- Configuration -----------------------------------------

# Identify the source and provide the request headers used to retrieve its published page.
SOURCE_ID  = "SRC058"
SOURCE_URL = "https://www.education-ni.gov.uk/articles/school-holidays"
HEADERS    = {"User-Agent": "SchoolHolidayResearch/1.0"}

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

    """Return raw school-holiday event rows from the Northern Ireland source page."""

    response = requests.get(SOURCE_URL
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content
                        ,"html.parser")
    records = []

    year_pattern = re.compile(r"School holidays\s+(\d{4})\s*/\s*(\d{4})"
                             ,re.IGNORECASE)
    headings = soup.find_all(re.compile(r"^h[1-6]$"))

    for heading in headings:
        match = year_pattern.search(heading.get_text(" ", strip = True))
        if match is None:
            continue

        academic_year = f"{match.group(1)}/{match.group(2)}"
        table = None

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

        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            event     = cells[0].get_text(" ", strip = True)
            raw_dates = cells[1].get_text(" ", strip = True)

            if event.lower() == "event" or not event or not raw_dates:
                continue

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : academic_year
                           ,"EVENT_NAME"    : event
                           ,"RAW_DATE_TEXT" : raw_dates
                           ,"DATE_SCRAPED"  : datetime.now(timezone.utc).date()})

    return pd.DataFrame.from_records(records
                                    ,columns = OUTPUT_COLUMNS)