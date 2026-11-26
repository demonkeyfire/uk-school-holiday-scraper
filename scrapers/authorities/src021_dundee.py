
# -------------------------------------------- Overview --------------------------------------------

# Retrieve school term dates, holidays and school closure dates for Dundee City Council.
# The output is one row per event and academic year, retaining the source's
# original date wording and the order in which events appear on the page.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url


SOURCE_ID = "SRC021"


# -------------------------------------------- Scraper ---------------------------------------------

def scrape_dundee():

    # Retrieve the URL selected for the source's current status
    url = get_source_url(SOURCE_ID)

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
    section = None

    date_scraped = datetime.now().strftime("%Y-%m-%d")

    # Process headings, accordion titles and list items in their original page order
    elements = main_content.find_all(
        ["dt", "h1", "h2", "h3", "h4", "p", "li"]
    )

    for element in elements:

        text = element.get_text(" ", strip=True)

        if not text:
            continue

        # Identify academic year headings, e.g. Academic Year 2026-27
        year_match = re.search(
            r"Academic Year\s+(20\d{2})\s*[-/]\s*(\d{4}|\d{2})",
            text,
            re.IGNORECASE
        )

        if not year_match and element.name in ["dt", "h1", "h2", "h3", "h4"]:
            year_match = re.search(
                r"\b(20\d{2})\s*[-/]\s*(\d{4}|\d{2})\b",
                text,
                re.IGNORECASE
            )

        if year_match and element.name in ["dt", "h1", "h2", "h3", "h4"]:

            start_year = int(year_match.group(1))
            end_year_text = year_match.group(2)
            end_year = (
                int(end_year_text)
                if len(end_year_text) == 4
                else int(f"{start_year // 100}{end_year_text}")
            )

            if end_year != start_year + 1:
                academic_year = None
                section = None
                continue

            academic_year = f"{start_year}/{str(end_year)[-2:]}"
            section = None

            continue

        # Identify the current term or holiday section
        if element.name in ["dt", "h1", "h2", "h3", "h4", "p"]:

            section_match = re.match(
                r"^(Autumn Term|Autumn Holiday|Winter Term|"
                r"Christmas Holiday|Spring Term|Spring Holiday|Summer Term)$",
                text,
                re.IGNORECASE
            )

            if section_match:
                section = section_match.group(1).title()
            elif element.name in ["h1", "h2", "h3", "h4", "dt", "p"]:
                section = None

            continue

        if element.name != "li" or academic_year is None:
            continue

        # Split the published date from the event description.
        date_match = re.match(
            r"^(?P<date>.+?)\s*[-–]\s*(?P<event>.+)$",
            text
        )

        if not date_match:
            continue

        raw_date_text = date_match.group("date").strip()
        event_description = date_match.group("event").strip()

        if not raw_date_text or not event_description:
            continue

        # Retain the section context alongside the event description
        if section:
            event_name = f"{section} - {event_description}"
        else:
            event_name = event_description

        records.append({
            "SOURCE_ID": SOURCE_ID,
            "ACADEMIC_YEAR": academic_year,
            "AUTHORITY": "Dundee",
            "EVENT_NAME": event_name,
            "RAW_DATE_TEXT": raw_date_text,
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
