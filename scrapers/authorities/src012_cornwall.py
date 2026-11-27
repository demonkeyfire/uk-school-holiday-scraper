
# -------------------------------------------- Overview --------------------------------------------
# Retrieve Cornwall school term and holiday dates from the published HTML page.
#
# Extracts:
#   - Autumn, Spring and Summer term dates
#   - Autumn, Spring and Summer half-term dates
#
# Academic years currently published:
#   - 2026/27
#   - 2027/28
#
# Output is one row per event, retaining the original date wording.


# --------------------------------------------- Imports --------------------------------------------
import re
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url


# ---------------------------------------------- Settings -------------------------------------------
SOURCE_ID = "SRC012"
AUTHORITY = "Cornwall"

USER_AGENT = "SchoolHolidayResearch/1.0"
TIMEOUT = 30

EXPECTED_YEARS = {"2026/27", "2027/28"}


# ------------------------------------------ Helper Functions ---------------------------------------
def get_page(url):
    """Retrieve the Cornwall school term dates page."""

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def normalise_academic_year(text):
    """Convert an academic year heading into YYYY/YY format."""

    match = re.search(r"\b(20\d{2})\s*/\s*(\d{2})\b", text)

    if match:
        return f"{match.group(1)}/{match.group(2)}"

    return None


def is_date_range(text):
    """Check whether text contains an English written date range."""

    pattern = (
        r"\b\d{1,2}\s+[A-Za-z]+\b"
        r"\s*[-–]\s*"
        r"\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?\b"
    )

    return bool(re.search(pattern, text))


# ------------------------------------------ Main Scraper -------------------------------------------
def scrape_cornwall():

    url = get_source_url(SOURCE_ID)
    soup = get_page(url)

    records = []
    scraped_date = datetime.now().strftime("%Y-%m-%d")

    # Find academic-year headings.
    year_headings = soup.find_all(
        ["h2", "h3"],
        string=re.compile(r"\b20\d{2}\s*/\s*\d{2}\b")
    )

    for year_heading in year_headings:

        heading_text = year_heading.get_text(" ", strip=True)
        academic_year = normalise_academic_year(heading_text)

        if academic_year not in EXPECTED_YEARS:
            continue

        current_term = None

        # Process content following the academic-year heading,
        # stopping when the next academic-year heading is reached.
        for element in year_heading.find_all_next(
            ["h2", "h3", "h4", "h5", "p", "li"]
        ):

            if element is not year_heading and element.name in ["h2", "h3"]:

                next_year = normalise_academic_year(
                    element.get_text(" ", strip=True)
                )

                if next_year:
                    break

            text = element.get_text(" ", strip=True)

            # Identify the current term heading.
            term_match = re.match(
                r"^(Autumn|Spring|Summer)\s+term\b",
                text,
                flags=re.IGNORECASE
            )

            if term_match and element.name != "li":
                current_term = term_match.group(1).title()
                continue

            # Extract date ranges from list items.
            if element.name != "li" or not is_date_range(text):
                continue

            if current_term is None:
                continue

            # Identify whether this is a half-term or a main term.
            half_term_match = re.search(
                r"\bHalf\s+term\b",
                text,
                flags=re.IGNORECASE
            )

            if half_term_match:
                event_name = f"{current_term} half term"

                # Retain the published date wording, excluding the
                # explanatory "Half term" label and surrounding brackets.
                raw_date_text = re.sub(
                    r"^\(?\s*Half\s+term\s*",
                    "",
                    text,
                    flags=re.IGNORECASE
                ).rstrip(" )")

            else:
                event_name = f"{current_term} term"
                raw_date_text = text

            records.append({
                "SOURCE_ID": SOURCE_ID,
                "ACADEMIC_YEAR": academic_year,
                "AUTHORITY": AUTHORITY,
                "EVENT_NAME": event_name,
                "RAW_DATE_TEXT": raw_date_text,
                "DATE_SCRAPED": scraped_date,
            })

    # -------------------------------------- Validation ---------------------------------------------
    if not records:
        raise ValueError(
            "No term-date records were extracted from the Cornwall page."
        )

    df = pd.DataFrame(records)

    # Check expected academic-year coverage.
    extracted_years = set(df["ACADEMIC_YEAR"].unique())
    missing_years = EXPECTED_YEARS - extracted_years

    if missing_years:
        raise ValueError(
            f"Missing expected academic years: {sorted(missing_years)}"
        )

    # Check that each academic year contains all six expected events.
    expected_events = {
        "Autumn term",
        "Autumn half term",
        "Spring term",
        "Spring half term",
        "Summer term",
        "Summer half term",
    }

    for academic_year in EXPECTED_YEARS:

        actual_events = set(
            df.loc[
                df["ACADEMIC_YEAR"] == academic_year,
                "EVENT_NAME"
            ]
        )

        missing_events = expected_events - actual_events

        if missing_events:
            raise ValueError(
                f"{academic_year} is missing events: "
                f"{sorted(missing_events)}"
            )

    return df


# --------------------------------------------- Execution -------------------------------------------
if __name__ == "__main__":

    cornwall_df = scrape_cornwall()

    print(cornwall_df.to_string(index=False))
