
# -------------------------------------------- Overview --------------------------------------------

# Retrieve school term dates and holidays for Dudley Council.
# The output is one row per event and academic year, retaining the source's
# original date wording and the order in which events appear on the page.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source


SOURCE_ID = "SRC020"


# -------------------------------------------- Scraper ---------------------------------------------

def scrape_dudley():

    # Retrieve source URL from central configuration
    source = get_source(SOURCE_ID)
    url = source["SOURCE_URL"]

    headers = {
        "User-Agent": "SchoolHolidayResearch/1.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Restrict extraction to the main page content where possible
    main_content = soup.find("main") or soup

    records = []
    academic_year = None
    term = None

    date_scraped = datetime.now().strftime("%Y-%m-%d")

    # Process headings and content in their original page order
    elements = main_content.find_all(
        ["h2", "h3", "li", "p"]
    )

    for element in elements:

        text = element.get_text(" ", strip=True)

        if not text:
            continue

        # Identify academic year headings, e.g. 2026-27 or 2026 -27
        if element.name == "h2":

            year_match = re.search(
                r"\b(20\d{2})\s*[-/]\s*(\d{2})\b",
                text
            )

            if year_match:
                start_year = int(year_match.group(1))
                end_year = year_match.group(2)

                academic_year = f"{start_year}/{end_year}"
                term = None

            continue

        # Identify term headings
        if element.name == "h3":

            if re.search(r"Autumn Term", text, re.IGNORECASE):
                term = "Autumn"

            elif re.search(r"Spring Term", text, re.IGNORECASE):
                term = "Spring"

            elif re.search(r"Summer Term", text, re.IGNORECASE):
                term = "Summer"

            else:
                term = None

            continue

        if academic_year is None:
            continue

        # Extract event rows from list items
        if element.name == "li":

            # Split the event label from the original date wording
            parts = re.split(
                r"\s*[-–]\s*",
                text,
                maxsplit=1
            )

            if len(parts) != 2:
                continue

            event_label = parts[0].strip()
            raw_date_text = parts[1].strip()

            if not raw_date_text:
                continue

            # Standardise the event name while retaining the term context
            if re.search(
                r"^term\s*start",
                event_label,
                re.IGNORECASE
            ):
                event_name = "Term Start"

            elif re.search(
                r"^term\s*end",
                event_label,
                re.IGNORECASE
            ):
                event_name = "Term End"

            elif re.search(
                r"^half\s*term",
                event_label,
                re.IGNORECASE
            ):
                event_name = "Half Term"

            else:
                # Other listed dates are bank holidays on this page
                event_name = f"Bank Holiday - {event_label}"

            if term:
                event_name = f"{term} Term - {event_name}"

            records.append({
                "SOURCE_ID": SOURCE_ID,
                "ACADEMIC_YEAR": academic_year,
                "AUTHORITY": "Dudley",
                "EVENT_NAME": event_name,
                "RAW_DATE_TEXT": raw_date_text,
                "DATE_SCRAPED": date_scraped,
            })

        # Primary Liaison Week is published as a paragraph rather than a list item
        elif element.name == "p":

            if re.match(
                r"Primary Liaison Week\s*[-–]",
                text,
                re.IGNORECASE
            ):

                parts = re.split(
                    r"\s*[-–]\s*",
                    text,
                    maxsplit=1
                )

                if len(parts) == 2:
                    records.append({
                        "SOURCE_ID": SOURCE_ID,
                        "ACADEMIC_YEAR": academic_year,
                        "AUTHORITY": "Dudley",
                        "EVENT_NAME": "Primary Liaison Week",
                        "RAW_DATE_TEXT": parts[1].strip(),
                        "DATE_SCRAPED": date_scraped,
                    })

    # Create dataframe using the standard project output schema
    output_columns = [
        "SOURCE_ID",
        "ACADEMIC_YEAR",
        "AUTHORITY",
        "EVENT_NAME",
        "RAW_DATE_TEXT",
        "DATE_SCRAPED",
    ]

    df = pd.DataFrame(records, columns=output_columns)

    return df
