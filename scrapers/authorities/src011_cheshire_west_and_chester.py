
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Cheshire West and Chester school-term and holiday rows from the published HTML page.
# The output is one row per event and academic year, retaining the source's page order and
# unparsed date text.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source


# -------------------------------------------- Settings --------------------------------------------

SOURCE_ID = "SRC011"

HEADERS = {
    "User-Agent": "SchoolHolidayResearch/1.0"
}

OUTPUT_COLUMNS = [
    "SOURCE_ID",
    "ACADEMIC_YEAR",
    "EVENT_NAME",
    "RAW_DATE_TEXT",
    "DATE_SCRAPED",
]


# -------------------------------------------- Scraper ---------------------------------------------

def scrape_cheshire_west_and_chester():

    # Retrieve the source URL from the central configuration file.
    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    # Request and parse the webpage.
    response = requests.get(
        source_url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    records = []

    academic_year = None
    season = None

    # Process academic-year headings, seasonal headings and list items in page order.
    for element in soup.find_all(["h2", "h3", "h4", "li"]):

        # -------------------------------- Academic-year headings --------------------------------

        if element.name in ["h2", "h3", "h4"]:

            heading_text = element.get_text(" ", strip=True)

            year_match = re.search(
                r"academic year\s+(\d{4})\s*[-/]\s*(\d{4})",
                heading_text,
                flags=re.IGNORECASE
            )

            if year_match:
                start_year = year_match.group(1)
                end_year = year_match.group(2)

                academic_year = f"{start_year}/{end_year[-2:]}"
                season = None
                continue

            # -------------------------------- Seasonal headings --------------------------------

            season_match = re.match(
                r"^(Autumn|Spring|Summer)\s+\d{4}$",
                heading_text,
                flags=re.IGNORECASE
            )

            if season_match and academic_year:
                season = season_match.group(1).title()
                continue

            # Stop collecting records when the page moves beyond the calendar sections.
            if academic_year:
                academic_year = None
                season = None

        # ------------------------------------ Event rows -----------------------------------------

        elif element.name == "li" and academic_year and season:

            raw_text = element.get_text(" ", strip=True)

            if not raw_text:
                continue

            # Explicitly named holidays, such as:
            # "Half Term: Monday 27 October - Friday 31 October"
            event_match = re.match(
                r"^([^:]+):\s*(.+)$",
                raw_text
            )

            if event_match:
                event_name = event_match.group(1).strip()
                raw_date_text = event_match.group(2).strip()

            # Unlabelled date ranges represent teaching periods within the season.
            else:
                event_name = f"{season} Term"
                raw_date_text = raw_text

            records.append({
                "SOURCE_ID": SOURCE_ID,
                "ACADEMIC_YEAR": academic_year,
                "EVENT_NAME": event_name,
                "RAW_DATE_TEXT": raw_date_text,
                "DATE_SCRAPED": datetime.now(timezone.utc).date(),
            })

    return pd.DataFrame.from_records(
        records,
        columns=OUTPUT_COLUMNS
    )
