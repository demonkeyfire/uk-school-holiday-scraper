
# -------------------------------------------- Overview --------------------------------------------
# Retrieve Falkirk school term dates, holidays and staff development days
# from the published HTML page.
#
# Extracts:
#   - School terms
#   - School holidays
#   - Staff development days
#   - Local holidays
#
# Academic years are assigned from the event start date.
#
# Output is one row per event, retaining the original published date text.


# --------------------------------------------- Imports --------------------------------------------
import re
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url


# ---------------------------------------------- Settings -------------------------------------------
SOURCE_ID = "SRC030"
AUTHORITY = "Falkirk"

USER_AGENT = "SchoolHolidayResearch/1.0"
TIMEOUT = 30


# ------------------------------------------ Helper Functions ---------------------------------------
def get_page(url):
    """Retrieve the Falkirk school dates page."""

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def parse_date(date_text):
    """
    Parse a published English date.

    Supports formats such as:
      Mon, 26 October 2026
      Monday, 26 October 2026
      26 October 2026
      Monday, 26th October 2026
    """

    if not date_text:
        return None

    text = date_text.strip()

    # Remove ordinal suffixes.
    text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text)

    formats = [
        "%a, %d %B %Y",
        "%A, %d %B %Y",
        "%d %B %Y",
    ]

    for date_format in formats:

        try:
            return datetime.strptime(text, date_format).date()

        except ValueError:
            continue

    raise ValueError(f"Unable to parse date: {date_text}")


def get_academic_year(start_date):
    """
    Assign academic year based on the event start date.

    August-December -> academic year starts in the same calendar year.
    January-July -> academic year starts in the previous calendar year.
    """

    if start_date.month >= 8:
        start_year = start_date.year
    else:
        start_year = start_date.year - 1

    return f"{start_year}/{str(start_year + 1)[-2:]}"


def get_table_after_heading(soup, heading_text):
    """Find the first table following a matching page heading."""

    for heading in soup.find_all(["h2", "h3"]):

        if heading_text.lower() in heading.get_text(" ", strip=True).lower():
            return heading.find_next("table")

    raise ValueError(
        f"Could not find a table following heading: {heading_text}"
    )


def extract_table_events(table, event_type):
    """Extract event rows from a Falkirk dates table."""

    records = []

    if table is None:
        raise ValueError(f"Could not locate the {event_type} table.")

    for row in table.find_all("tr"):

        cells = row.find_all(["th", "td"], recursive=False)

        if len(cells) < 3:
            continue

        # Skip header rows.
        if any(cell.name == "th" for cell in cells):
            continue

        event_name = cells[0].get_text(" ", strip=True)
        start_text = cells[1].get_text(" ", strip=True)
        end_text = cells[2].get_text(" ", strip=True)

        if not event_name or not start_text:
            continue

        start_date = parse_date(start_text)

        if end_text:
            end_date = parse_date(end_text)

            if end_date < start_date:
                raise ValueError(
                    f"End date precedes start date for {event_name}: "
                    f"{start_text} - {end_text}"
                )

        academic_year = get_academic_year(start_date)

        # Retain the original date wording.
        if end_text:
            raw_date_text = f"{start_text} - {end_text}"
        else:
            raw_date_text = start_text

        records.append({
            "SOURCE_ID": SOURCE_ID,
            "ACADEMIC_YEAR": academic_year,
            "AUTHORITY": AUTHORITY,
            "EVENT_NAME": event_name,
            "RAW_DATE_TEXT": raw_date_text,
            "DATE_SCRAPED": datetime.now().strftime("%Y-%m-%d"),
        })

    return records


# ------------------------------------------ Main Scraper -------------------------------------------
def scrape_falkirk():

    url = get_source_url(SOURCE_ID)
    soup = get_page(url)

    # Find the two published tables.
    term_table = get_table_after_heading(
        soup,
        "School term dates"
    )

    holiday_table = get_table_after_heading(
        soup,
        "School holidays and staff development days"
    )

    # Extract both sets of events.
    term_records = extract_table_events(
        term_table,
        "school term dates"
    )

    holiday_records = extract_table_events(
        holiday_table,
        "school holidays and staff development days"
    )

    records = term_records + holiday_records

    if not records:
        raise ValueError(
            "No school term or holiday records were extracted."
        )

    df = pd.DataFrame(records)

    # -------------------------------------- Validation ---------------------------------------------
    if df["RAW_DATE_TEXT"].isna().any():
        raise ValueError("One or more records have missing date text.")

    if df["ACADEMIC_YEAR"].isna().any():
        raise ValueError("One or more records have no academic year.")

    # Check for duplicate events.
    duplicate_events = df.duplicated(
        subset=[
            "ACADEMIC_YEAR",
            "EVENT_NAME",
            "RAW_DATE_TEXT"
        ]
    )

    if duplicate_events.any():
        raise ValueError(
            "Duplicate events found:\n"
            + df.loc[duplicate_events].to_string(index=False)
        )

    return df


# --------------------------------------------- Execution -------------------------------------------
if __name__ == "__main__":

    falkirk_df = scrape_falkirk()

    print(falkirk_df.to_string(index=False))

    print("\nEvents by academic year:")
    print(
        falkirk_df.groupby("ACADEMIC_YEAR")
        .size()
        .to_string()
    )
