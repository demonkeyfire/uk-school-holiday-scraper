
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Leeds school term dates and holidays from the council website.
# The page publishes dates in tables with the columns:
# Term or holiday | Starts | Ends
#
# Output is one row per event, retaining the published date wording.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url


SOURCE_ID = "SRC044"


# -------------------------------------------- Helpers ---------------------------------------------

def normalise_academic_year(text):
    """Convert a year heading into YYYY/YY format."""

    match = re.search(
        r"\b(20\d{2})\s*(?:-|/|to)\s*(20\d{2}|\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    start_year = int(match.group(1))
    end_text = match.group(2)

    if len(end_text) == 2:
        end_year = (start_year // 100) * 100 + int(end_text)

        if end_year < start_year:
            end_year += 100
    else:
        end_year = int(end_text)

    return f"{start_year}/{str(end_year)[-2:]}"


def clean_cell_text(cell):
    """Extract clean text from a table cell."""

    return re.sub(
        r"\s+",
        " ",
        cell.get_text(" ", strip=True)
    ).strip()


def extract_table_events(table, academic_year):
    """Extract individual event rows from a Leeds dates table."""

    events = []

    for row in table.find_all("tr"):

        cells = row.find_all(["td", "th"], recursive=False)

        if len(cells) < 3:
            continue

        values = [clean_cell_text(cell) for cell in cells[:3]]

        event_name, start_date, end_date = values

        # Ignore table headers and incomplete rows.
        if (
            event_name.lower() in ["term or holiday", "term", "holiday"]
            or start_date.lower() == "starts"
            or end_date.lower() == "ends"
        ):
            continue

        if not event_name or not start_date or not end_date:
            continue

        events.append({
            "SOURCE_ID": SOURCE_ID,
            "ACADEMIC_YEAR": academic_year,
            "AUTHORITY": "Leeds",
            "EVENT_NAME": event_name,
            "RAW_DATE_TEXT": f"Starts: {start_date}; Ends: {end_date}",
            "DATE_SCRAPED": datetime.now().date(),
        })

    return events


# --------------------------------------------- Scraper --------------------------------------------

def scrape_leeds():

    url = get_source_url(SOURCE_ID)

    response = requests.get(
        url,
        headers={
            "User-Agent": "SchoolHolidayResearch/1.0"
        },
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    records = []
    current_academic_year = None

    # Process headings and tables in document order so that each table
    # inherits the academic year from its preceding year heading.
    for element in soup.find_all([
        "h1", "h2", "h3", "h4", "h5", "h6", "table"
    ]):

        if element.name != "table":

            heading_text = element.get_text(" ", strip=True)
            academic_year = normalise_academic_year(heading_text)

            if academic_year:
                current_academic_year = academic_year

            continue

        if current_academic_year is None:
            continue

        records.extend(
            extract_table_events(element, current_academic_year)
        )

    df = pd.DataFrame(records)

    if df.empty:
        raise ValueError(
            "No events extracted. Check the page headings and table structure."
        )

    df = df.drop_duplicates(
        subset=[
            "SOURCE_ID",
            "ACADEMIC_YEAR",
            "EVENT_NAME",
            "RAW_DATE_TEXT",
        ]
    ).reset_index(drop=True)

    return df
