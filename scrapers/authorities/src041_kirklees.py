
# -------------------------------------------- Overview --------------------------------------------
# Retrieve Kirklees school term and holiday dates from the published HTML page.
#
# Extracts:
#   - Term start and end dates
#   - Half-term holidays
#   - Christmas, Easter and summer holidays
#   - Dates to remember, including May Day and election days
#
# Academic years are identified from the page headings.
#
# Output is one row per event, retaining the original published date wording.


# --------------------------------------------- Imports --------------------------------------------
import re
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url


# ---------------------------------------------- Settings -------------------------------------------
SOURCE_ID = "SRC041"
AUTHORITY = "Kirklees"

USER_AGENT = "SchoolHolidayResearch/1.0"
TIMEOUT = 30

EXPECTED_YEARS = {"2026/27", "2027/28"}


# ------------------------------------------ Helper Functions ---------------------------------------
def get_page(url):
    """Retrieve the Kirklees school term dates page."""

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def normalise_academic_year(text):
    """Convert a year heading into YYYY/YY format."""

    match = re.search(
        r"\b(20\d{2})\s+to\s+(20\d{2})\b",
        text,
        flags=re.IGNORECASE
    )

    if match:
        start_year = int(match.group(1))
        end_year = int(match.group(2))

        if end_year != start_year + 1:
            raise ValueError(
                f"Unexpected academic-year heading: {text}"
            )

        return f"{start_year}/{str(end_year)[-2:]}"

    return None


def extract_event_text(text):
    """
    Split a published bullet point into event name and date wording.

    Example:
        Term starts: Tuesday 1 September 2026.

    Returns:
        ("Term starts", "Tuesday 1 September 2026")
    """

    if ":" not in text:
        return None, None

    event_name, date_text = text.split(":", 1)

    event_name = event_name.strip()
    date_text = date_text.strip()

    # Remove the trailing explanatory note from election-day entries.
    date_text = re.split(
        r"\.\s+Schools used as a polling station",
        date_text,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    date_text = date_text.rstrip(".").strip()

    if not event_name or not date_text:
        return None, None

    return event_name, date_text


def validate_date_text(date_text):
    """Check that the published text contains at least one written date."""

    pattern = (
        r"\b(?:"
        r"Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|"
        r"Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?"
        r",?\s+"
        r")?"
        r"\d{1,2}(?:st|nd|rd|th)?\s+"
        r"[A-Za-z]+"
        r"(?:\s+\d{4})?\b"
    )

    if not re.search(pattern, date_text, flags=re.IGNORECASE):
        raise ValueError(
            f"Could not identify a written date in: {date_text}"
        )


# ------------------------------------------ Main Scraper -------------------------------------------
def scrape_kirklees():

    url = get_source_url(SOURCE_ID)
    soup = get_page(url)

    records = []
    scraped_date = datetime.now().strftime("%Y-%m-%d")

    current_year = None
    current_section = None

    # Process headings and list items in their published page order.
    for element in soup.find_all(["h3", "h4", "li"]):

        text = element.get_text(" ", strip=True)

        # Academic-year heading.
        if element.name == "h3":

            academic_year = normalise_academic_year(text)

            if academic_year:
                current_year = academic_year
                current_section = None

            continue

        # Ignore content outside the expected academic years.
        if current_year not in EXPECTED_YEARS:
            continue

        # Term or dates-to-remember heading.
        if element.name == "h4":

            current_section = text.strip()
            continue

        if element.name != "li" or current_section is None:
            continue

        event_name, raw_date_text = extract_event_text(text)

        if not event_name:
            continue

        validate_date_text(raw_date_text)

        # Include the term heading to distinguish repeated event names.
        if current_section.lower() != "dates to remember":
            event_name = f"{current_section} - {event_name}"

        records.append({
            "SOURCE_ID": SOURCE_ID,
            "ACADEMIC_YEAR": current_year,
            "AUTHORITY": AUTHORITY,
            "EVENT_NAME": event_name,
            "RAW_DATE_TEXT": raw_date_text,
            "DATE_SCRAPED": scraped_date,
        })

    # -------------------------------------- Validation ---------------------------------------------
    if not records:
        raise ValueError(
            "No school term or holiday records were extracted."
        )

    df = pd.DataFrame(records)

    extracted_years = set(df["ACADEMIC_YEAR"].unique())
    missing_years = EXPECTED_YEARS - extracted_years

    if missing_years:
        raise ValueError(
            f"Missing expected academic years: {sorted(missing_years)}"
        )

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

    kirklees_df = scrape_kirklees()

    print(kirklees_df.to_string(index=False))

    print("\nEvents by academic year:")
    print(
        kirklees_df.groupby("ACADEMIC_YEAR")
        .size()
        .to_string()
    )
