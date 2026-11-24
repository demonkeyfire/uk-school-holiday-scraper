# -------------------------------------------- Overview --------------------------------------------

# Retrieve school-term dates for all Welsh local authorities from the Welsh Government pages.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC209"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"AUTHORITY"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

ACADEMIC_YEARS = ("2025/26", "2026/27", "2027/28")

YEAR_PATTERN = re.compile(
    r"\b(?P<start_year>20\d{2})\s*(?:to|/|-)\s*(?P<end_year>20\d{2})\b"
    ,re.IGNORECASE
)

EVENT_PATTERN = re.compile(
    r"^(Term starts|Half term holiday|Term ends|Christmas holiday|Easter holiday)"
    r"\s*:\s*(.+)$"
    ,re.IGNORECASE
)

TERM_PATTERN = re.compile(
    r"^(Autumn|Spring|Summer)\s+term(?:\s+20\d{2})?$"
    ,re.IGNORECASE
)



# ------------------------------------------- Helper Functions -------------------------------------

def clean_text(value):

    """Normalise whitespace in extracted webpage text."""

    return re.sub(r"\s+", " ", value).strip()


def extract_academic_year(text):

    """Return a canonical academic year from a page title or link label."""

    match = YEAR_PATTERN.search(text)

    if match is None:
        return None

    start_year = int(match.group("start_year"))
    end_year = int(match.group("end_year"))

    if end_year != start_year + 1:
        return None

    return f"{start_year}/{str(end_year)[-2:]}"


def find_academic_year_links(soup, base_url):

    """Find the three approved-term-date pages linked from the Welsh Government index."""

    links = {}

    for anchor in soup.find_all("a", href=True):
        label = clean_text(anchor.get_text(" ", strip=True))

        if "approved school term dates" not in label.lower():
            continue

        academic_year = extract_academic_year(label)

        if academic_year in ACADEMIC_YEARS:
            links[academic_year] = urljoin(base_url, anchor["href"])

    return links


def find_html_document_link(soup, base_url, academic_year):

    """Find the HTML data document linked from a year-specific landing page."""

    for anchor in soup.find_all("a", href=True):
        label = clean_text(anchor.get_text(" ", strip=True))
        href = anchor["href"]

        if (
            extract_academic_year(label) == academic_year
            and "html" in f"{label} {href}".lower()
        ):
            return urljoin(base_url, href)

    return None


def make_record(academic_year, authority, event_name, raw_date_text, date_scraped):

    """Create one output record with source provenance and authority."""

    return {
        "SOURCE_ID": SOURCE_ID
        ,"ACADEMIC_YEAR": academic_year
        ,"AUTHORITY": authority
        ,"EVENT_NAME": event_name
        ,"RAW_DATE_TEXT": raw_date_text
        ,"DATE_SCRAPED": date_scraped
    }


def extract_page_records(soup, academic_year, date_scraped):

    """Extract authority tables or dated term entries from a year-specific page."""

    records = []
    authority = None
    term_section = None

    for element in soup.find_all(["h2", "h3", "table", "p"]):
        if element.name == "h2":
            heading = clean_text(element.get_text(" ", strip=True))
            authority = (
                None
                if heading.lower() in {"in this page", "teacher training (inset) day closures"}
                or extract_academic_year(heading) is not None
                else heading
            )
            term_section = None
            continue

        if element.name == "h3":
            heading = clean_text(element.get_text(" ", strip=True))
            term_section = heading if TERM_PATTERN.match(heading) else None
            continue

        if authority is None:
            continue

        if element.name == "table":
            for row in element.find_all("tr"):
                cells = [
                    clean_text(cell.get_text(" ", strip=True))
                    for cell in row.find_all(["th", "td"])
                ]

                if len(cells) < 3 or cells[0].lower() == "period":
                    continue

                period, start_date, end_date = cells[:3]

                if not period or not start_date or not end_date:
                    continue

                records.append(make_record(
                    academic_year
                    ,authority
                    ,period
                    ,f"{start_date} to {end_date}"
                    ,date_scraped
                ))

            continue

        event_match = EVENT_PATTERN.match(
            clean_text(element.get_text(" ", strip=True)))

        if event_match is None:
            continue

        event_name = event_match.group(1).title()

        if term_section is not None:
            event_name = f"{term_section} - {event_name}"

        records.append(make_record(
            academic_year
            ,authority
            ,event_name
            ,clean_text(event_match.group(2))
            ,date_scraped
        ))

    return records



# ------------------------------------------- Main Code --------------------------------------------

def scrape_wales_authority(authority, source_id=SOURCE_ID):

    """Retrieve dates for one Welsh local authority from a supported Welsh dates page."""

    return _scrape_wales(authority, source_id)


def scrape_wales():

    """Retrieve term dates for all Welsh local authorities from the Welsh Government."""

    return _scrape_wales()


def _scrape_wales(authority=None, source_id=SOURCE_ID):

    """Retrieve term dates for all or one Welsh local authority from the selected page."""

    source_url = get_source_url(source_id)

    response = requests.get(
        source_url
        ,headers=HEADERS
        ,timeout=30
    )
    response.raise_for_status()

    index_soup = BeautifulSoup(response.content, "html.parser")
    year_links = find_academic_year_links(index_soup, source_url)
    page_soups = {source_url: index_soup}

    if not year_links:
        academic_year = extract_academic_year(source_url)

        if academic_year not in ACADEMIC_YEARS:
            raise ValueError(
                f"No supported Welsh academic-year links found at {source_url}"
            )

        year_links[academic_year] = source_url

    year_source_ids = {
        academic_year: source_id
        for academic_year in year_links
    }
    missing_years = set(ACADEMIC_YEARS) - set(year_links)

    if missing_years and source_id != SOURCE_ID:
        index_url = get_source_url(SOURCE_ID)
        index_response = requests.get(
            index_url
            ,headers=HEADERS
            ,timeout=30
        )
        index_response.raise_for_status()
        index_soup = BeautifulSoup(index_response.content, "html.parser")
        additional_links = find_academic_year_links(index_soup, index_url)

        for academic_year in missing_years:
            if academic_year in additional_links:
                year_links[academic_year] = additional_links[academic_year]
                year_source_ids[academic_year] = SOURCE_ID

        missing_years = set(ACADEMIC_YEARS) - set(year_links)

    if missing_years:
        raise ValueError(
            f"Missing Welsh Government year links: {', '.join(sorted(missing_years))}"
        )

    date_scraped = datetime.now(timezone.utc).date()
    records = []

    for academic_year in ACADEMIC_YEARS:
        page_url = year_links[academic_year]
        page_soup = page_soups.get(page_url)

        if page_soup is None:
            page_response = requests.get(
                page_url
                ,headers=HEADERS
                ,timeout=30
            )
            page_response.raise_for_status()
            page_soup = BeautifulSoup(page_response.content, "html.parser")

        year_records = extract_page_records(
            page_soup
            ,academic_year
            ,date_scraped
        )

        if authority is not None:
            year_records = [
                record for record in year_records
                if record["AUTHORITY"].casefold() == authority.casefold()
            ]

        if not year_records:
            document_url = find_html_document_link(
                page_soup
                ,page_url
                ,academic_year
            )

            if document_url is not None:
                document_response = requests.get(
                    document_url
                    ,headers=HEADERS
                    ,timeout=30
                )
                document_response.raise_for_status()

                year_records = extract_page_records(
                    BeautifulSoup(document_response.content, "html.parser")
                    ,academic_year
                    ,date_scraped
                )

                if authority is not None:
                    year_records = [
                        record for record in year_records
                        if record["AUTHORITY"].casefold() == authority.casefold()
                    ]

        if not year_records:
            authority_label = f" for {authority}" if authority is not None else ""
            raise ValueError(
                f"No Welsh school dates extracted{authority_label} for {academic_year} "
                f"from {page_url}"
            )

        for record in year_records:
            record["SOURCE_ID"] = year_source_ids[academic_year]

        records.extend(year_records)

    return pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)
