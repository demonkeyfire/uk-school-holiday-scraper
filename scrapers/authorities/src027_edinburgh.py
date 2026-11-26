
# -------------------------------------------- Overview --------------------------------------------

# Retrieve school term dates and holidays for the City of Edinburgh Council.
# The source publishes each academic year on a separate paginated page.
# The scraper follows the academic-year links and returns one row per event,
# retaining the original date wording and page order.


# --------------------------------------------- Input ----------------------------------------------

import re
from datetime import datetime
from urllib.parse import urljoin, urldefrag

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url


SOURCE_ID = "SRC027"

HEADERS = {
    "User-Agent": "SchoolHolidayResearch/1.0"
}


# ----------------------------------------- Helper Functions ---------------------------------------

def get_page(url, session):
    """Retrieve a page and return its parsed HTML and final URL."""

    response = session.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser"), response.url


def get_academic_year(text):
    """Extract academic year from page text."""

    match = re.search(
        r"School term dates\s+(20\d{2})\s*/\s*(\d{2})",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    start_year = int(match.group(1))
    end_year = int(f"{start_year // 100}{match.group(2)}")

    return f"{start_year}/{str(end_year)[-2:]}"


def find_date(text):
    """
    Find a published date or date range within a text string.

    Supports examples such as:
    - Wednesday 12 August 2026
    - Monday 12 to Monday 19 October 2026
    - Monday 21 December 2026 to Tuesday 5 January 2027
    """

    weekday = (
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
    )

    day = r"\d{1,2}(?:st|nd|rd|th)?"
    month = r"[A-Za-z]+"
    year = r"\d{4}"

    # Date range: first date may omit its month and year
    date_range = (
        rf"(?:{weekday}\s+)?{day}"
        rf"(?:\s+{month})?"
        rf"(?:\s+{year})?"
        rf"\s+to\s+"
        rf"(?:{weekday}\s+)?{day}\s+{month}\s+{year}"
    )

    # Single date
    single_date = (
        rf"(?:{weekday}\s+)?{day}\s+{month}\s+{year}"
    )

    pattern = re.compile(
        rf"(?P<date>{date_range}|{single_date})",
        re.IGNORECASE
    )

    return pattern.search(text)


def extract_event_text(text, date_match):
    """Extract the event description surrounding the date."""

    before_date = text[:date_match.start()].strip()
    after_date = text[date_match.end():].strip()

    before_date = before_date.strip(" ,.-")
    after_date = after_date.strip(" ,.-")

    after_date = re.sub(
        r"\s+inclusive\.?$",
        "",
        after_date,
        flags=re.IGNORECASE
    ).strip()

    # The description may appear before or after the date
    if before_date and after_date:
        return f"{before_date} - {after_date}"

    return before_date or after_date


# -------------------------------------------- Scraper ---------------------------------------------

def scrape_edinburgh():

    # Retrieve the URL selected for the source's current status
    start_url = get_source_url(SOURCE_ID)

    session = requests.Session()

    date_scraped = datetime.now().strftime("%Y-%m-%d")

    records = []
    pages_to_visit = [start_url]
    visited_urls = set()
    academic_years_found = set()

    while pages_to_visit:

        current_url = pages_to_visit.pop(0)

        # Normalise URLs to avoid duplicate requests
        current_url = urldefrag(current_url).url

        if current_url in visited_urls:
            continue

        soup, final_url = get_page(current_url, session)

        final_url = urldefrag(final_url).url

        if final_url in visited_urls:
            continue

        visited_urls.add(final_url)

        main_content = soup.find("main") or soup

        # Identify the academic year from the page heading
        page_heading = main_content.get_text(" ", strip=True)
        academic_year = get_academic_year(page_heading)

        if academic_year is None:
            continue

        academic_years_found.add(academic_year)

        # Extract events in their original page order
        elements = main_content.find_all(
            ["p", "li"]
        )

        page_records = set()

        for element in elements:

            text = element.get_text(" ", strip=True)

            if not text:
                continue

            # Ignore navigation and download links
            if re.search(
                r"download|printable list|next school term dates",
                text,
                re.IGNORECASE
            ):
                continue

            date_match = find_date(text)

            if not date_match:
                continue

            raw_date_text = date_match.group("date").strip()

            event_name = extract_event_text(
                text,
                date_match
            )

            if not event_name:
                continue

            # Avoid duplicate records within the page
            record_key = (
                academic_year,
                event_name,
                raw_date_text
            )

            if record_key in page_records:
                continue

            page_records.add(record_key)

            records.append({
                "SOURCE_ID": SOURCE_ID,
                "ACADEMIC_YEAR": academic_year,
                "AUTHORITY": "Edinburgh",
                "EVENT_NAME": event_name,
                "RAW_DATE_TEXT": raw_date_text,
                "DATE_SCRAPED": date_scraped,
            })

        # Find links to other academic-year pages.
        # Search the entire HTML document because pagination links
        # may sit outside the main content element.

        for link in soup.find_all("a", href=True):

            link_text = link.get_text(" ", strip=True)

            # Identify links containing an academic-year reference
            year_match = re.search(
                r"20\d{2}\s*/\s*\d{2}",
                link_text
            )

            if not year_match:
                continue

            # Only follow links explicitly referring to school term dates
            if "school term dates" not in link_text.lower():
                continue

            next_url = urljoin(final_url, link["href"])
            next_url = urldefrag(next_url).url

            if (
                next_url not in visited_urls
                and next_url not in pages_to_visit
            ):
                pages_to_visit.append(next_url)

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

    # Check that all three expected academic years were retrieved
    expected_years = {
        "2026/27",
        "2027/28",
        "2028/29"
    }

    missing_years = expected_years - academic_years_found

    if missing_years:
        raise ValueError(
            f"Edinburgh scraper did not retrieve all expected academic years. "
            f"Found: {sorted(academic_years_found)}. "
            f"Missing: {sorted(missing_years)}. "
            f"Pages visited: {sorted(visited_urls)}"
        )

    if df.empty:
        raise ValueError(
            "Edinburgh pages were retrieved, but no dated events were extracted."
        )

    return df
