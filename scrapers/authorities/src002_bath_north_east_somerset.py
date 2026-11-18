
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Bath & North East Somerset school-term dates from the published webpage and its
# printable PDF calendars. PDF calendars provide term dates, bank holidays and periods outside
# published term dates. The webpage remains the fallback where a PDF cannot be processed.



# --------------------------------------------- Imports --------------------------------------------

import re
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

# Identify the source using its unique ID in the central sources.csv register.
SOURCE_ID = "SRC002"

# Define the request headers used when retrieving published content.
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

# Define the columns returned by the scraper.
OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

# Match academic years published in the webpage headings.
YEAR_PATTERN = re.compile(
    r"School year (?P<start_year>\d{4}) to (?P<end_year>\d{4})"
    ,re.IGNORECASE
)

# Match academic years in printable-calendar link text.
PDF_YEAR_PATTERN = re.compile(
    r"(?P<start_year>\d{4})[/-](?P<end_year>\d{2,4})"
)

# Match term date ranges extracted from the PDF.
TERM_PATTERN = re.compile(
    r"\bTerm\s+(?P<term_number>[1-6])\s+"
    r"(?P<start_day>\d{1,2})\s*(?P<start_month>[A-Za-z]+)\s*[–-]\s*"
    r"(?P<end_day>\d{1,2})\s*(?P<end_month>[A-Za-z]+)\s*"
    r"(?P<end_year>\d{4})\b"
    ,re.IGNORECASE
)

# Match bank holiday entries extracted from the PDF.
BANK_HOLIDAY_PATTERN = re.compile(
    r"(?P<event_name>Christmas Day|Boxing Day|New Year's Day|New Year’s Day|"
    r"Good Friday|Easter Monday|May Day|Spring Bank Holiday|Summer Bank Holiday)"
    r"\s*[–-]\s*(?P<day>\d{1,2})(?:st|nd|rd|th)?\s*"
    r"(?P<month>[A-Za-z]+)\s*(?P<year>\d{4})\b"
    ,re.IGNORECASE
)



# ------------------------------------------- Helper Functions -------------------------------------

def clean_text(value):
    """Normalise whitespace in extracted text."""

    return re.sub(r"\s+", " ", str(value)).strip()


def format_date_range(start_date, end_date):
    """Format an inclusive date period with weekday and month names."""

    def format_date(value):
        return f"{value.strftime('%A')} {value.day} {value.strftime('%B %Y')}"

    if start_date == end_date:
        return format_date(start_date)

    return f"{format_date(start_date)} to {format_date(end_date)}"


def get_academic_year(start_year, end_year):
    """Validate and format a consecutive academic-year range."""

    start_year = int(start_year)
    end_year = int(end_year)

    if end_year != start_year + 1:
        raise ValueError(
            f"Academic years must contain consecutive calendar years: "
            f"{start_year}/{end_year}"
        )

    return f"{start_year}/{str(end_year)[-2:]}"


def get_academic_year_bounds(academic_year):
    """Return the first and last dates of an academic year."""

    start_year_text, end_year_text = academic_year.split("/")
    start_year = int(start_year_text)

    return (
        date(start_year, 9, 1)
        ,date(start_year + 1, 8, 31)
    )


def make_record(academic_year, event_name, start_date, end_date, date_scraped):
    """Create a standard output record with temporary dates for sorting."""

    return {
        "SOURCE_ID"     : SOURCE_ID
        ,"ACADEMIC_YEAR" : academic_year
        ,"EVENT_NAME"    : event_name
        ,"RAW_DATE_TEXT" : format_date_range(start_date, end_date)
        ,"DATE_SCRAPED"  : date_scraped
        ,"_START_DATE"   : start_date
        ,"_END_DATE"     : end_date
    }


def validate_date_in_academic_year(value, academic_year, event_name):
    """Raise an error if a date falls outside its academic year."""

    academic_year_start, academic_year_end = get_academic_year_bounds(
        academic_year
    )

    if not academic_year_start <= value <= academic_year_end:
        raise ValueError(
            f"{event_name} date {value} falls outside {academic_year}"
        )


def validate_term_records(term_records, academic_year):
    """Validate term numbers, dates, chronology and overlaps."""

    expected_terms = set(range(1, 7))
    actual_terms = {
        int(record["EVENT_NAME"].split()[-1])
        for record in term_records
    }

    if actual_terms != expected_terms or len(term_records) != 6:
        raise ValueError(
            f"Expected exactly one record for each of the six terms "
            f"in {academic_year}"
        )

    term_records.sort(key=lambda record: record["_START_DATE"])

    previous_end = None

    for record in term_records:

        term_start = record["_START_DATE"]
        term_end = record["_END_DATE"]

        if term_end < term_start:
            raise ValueError(
                f"{record['EVENT_NAME']} ends before it starts"
            )

        validate_date_in_academic_year(
            term_start, academic_year, record["EVENT_NAME"]
        )
        validate_date_in_academic_year(
            term_end, academic_year, record["EVENT_NAME"]
        )

        if previous_end is not None and term_start <= previous_end:
            raise ValueError(
                f"Term dates overlap: {record['EVENT_NAME']}"
            )

        previous_end = term_end


def parse_calendar_text(calendar_text, academic_year, date_scraped):
    """Parse term dates, bank holidays and periods outside published term dates."""

    term_records = []
    bank_holiday_records = []

    # ----------------------------------------- Term Dates -----------------------------------------

    for term_match in TERM_PATTERN.finditer(calendar_text):

        term_number = int(term_match.group("term_number"))
        end_year = int(term_match.group("end_year"))

        start_month = datetime.strptime(
            term_match.group("start_month").title(), "%B"
        ).month

        end_month = datetime.strptime(
            term_match.group("end_month").title(), "%B"
        ).month

        # Infer the start year where a term crosses a calendar-year boundary.
        start_year = end_year - (start_month > end_month)

        start_date = date(
            start_year
            ,start_month
            ,int(term_match.group("start_day"))
        )

        end_date = date(
            end_year
            ,end_month
            ,int(term_match.group("end_day"))
        )

        if end_date < start_date:
            raise ValueError(
                f"Term ends before it starts: {term_match.group(0)!r}"
            )

        term_records.append(
            make_record(
                academic_year
                ,f"Term {term_number}"
                ,start_date
                ,end_date
                ,date_scraped
            )
        )

    # Validate that all six terms were found and that their dates are plausible.
    validate_term_records(term_records, academic_year)

    # --------------------------------------- Bank Holidays ----------------------------------------

    for holiday_match in BANK_HOLIDAY_PATTERN.finditer(calendar_text):

        event_name = clean_text(holiday_match.group("event_name"))

        if not event_name:
            continue

        holiday_date = date(
            int(holiday_match.group("year"))
            ,datetime.strptime(
                holiday_match.group("month").title(), "%B"
            ).month
            ,int(holiday_match.group("day"))
        )

        validate_date_in_academic_year(
            holiday_date, academic_year, event_name
        )

        bank_holiday_records.append(
            make_record(
                academic_year
                ,event_name
                ,holiday_date
                ,holiday_date
                ,date_scraped
            )
        )

    # Reject duplicate bank holiday records rather than silently retaining them.
    bank_holiday_keys = [
        (record["EVENT_NAME"], record["_START_DATE"])
        for record in bank_holiday_records
    ]

    if len(bank_holiday_keys) != len(set(bank_holiday_keys)):
        raise ValueError(
            f"Duplicate bank holiday records found in {academic_year}"
        )

    if len(bank_holiday_records) != 8:
        raise ValueError(
            f"Expected eight bank holidays in {academic_year}; "
            f"found {len(bank_holiday_records)}"
        )

    # ------------------------------------ Periods Outside Terms -----------------------------------

    academic_year_start, academic_year_end = get_academic_year_bounds(
        academic_year
    )

    school_holiday_records = []
    previous_end = academic_year_start - timedelta(days=1)

    for term_record in term_records:

        term_start = term_record["_START_DATE"]
        term_end = term_record["_END_DATE"]

        holiday_start = previous_end + timedelta(days=1)
        holiday_end = term_start - timedelta(days=1)

        if holiday_start <= holiday_end:
            school_holiday_records.append(
                make_record(
                    academic_year
                    ,"School Holiday"
                    ,holiday_start
                    ,holiday_end
                    ,date_scraped
                )
            )

        previous_end = term_end

    # Include the period after the final term, through the end of the academic year.
    if previous_end < academic_year_end:

        holiday_start = previous_end + timedelta(days=1)

        school_holiday_records.append(
            make_record(
                academic_year
                ,"School Holiday"
                ,holiday_start
                ,academic_year_end
                ,date_scraped
            )
        )

    # ------------------------------------------ Output ---------------------------------------------

    records = (
        term_records
        + bank_holiday_records
        + school_holiday_records
    )

    records.sort(
        key=lambda record: (
            record["_START_DATE"]
            ,record["EVENT_NAME"]
        )
    )

    for record in records:
        record.pop("_START_DATE")
        record.pop("_END_DATE")

    return pd.DataFrame.from_records(
        records
        ,columns=OUTPUT_COLUMNS
    )


def find_pdf_calendar_links(soup, page_url):
    """Return unique academic-year and PDF URL pairs from printable-calendar links."""

    calendar_links = {}

    for link in soup.find_all("a", href=True):

        link_text = clean_text(link.get_text(" ", strip=True))

        if "printable calendar" not in link_text.lower():
            continue

        href = link["href"]

        if not href.lower().split("?", 1)[0].endswith(".pdf"):
            continue

        year_match = PDF_YEAR_PATTERN.search(link_text)

        if year_match is None:
            continue

        start_year = int(year_match.group("start_year"))
        end_year_text = year_match.group("end_year")

        if len(end_year_text) == 4:
            end_year = int(end_year_text)
        else:
            end_year = (
                (start_year // 100) * 100
                + int(end_year_text)
            )

            if end_year < start_year:
                end_year += 100

        academic_year = get_academic_year(start_year, end_year)
        pdf_url = urljoin(page_url, href)

        if academic_year in calendar_links:
            if calendar_links[academic_year] != pdf_url:
                raise ValueError(
                    f"Multiple different PDF links found for {academic_year}"
                )
            continue

        calendar_links[academic_year] = pdf_url

    return list(calendar_links.items())


def extract_pdf_calendar(pdf_url, academic_year, date_scraped):
    """Download and extract records from a council-hosted printable calendar PDF."""

    response = requests.get(
        pdf_url
        ,headers=HEADERS
        ,timeout=30
    )
    response.raise_for_status()

    with pdfplumber.open(BytesIO(response.content)) as calendar_pdf:

        # The source calendar's second page contains the term-date summary.
        if len(calendar_pdf.pages) < 2:
            raise ValueError(
                f"The calendar PDF for {academic_year} does not contain page 2"
            )

        calendar_text = calendar_pdf.pages[1].extract_text()

    if not calendar_text:
        raise ValueError(
            f"Could not extract text from page 2 of the {academic_year} calendar PDF"
        )

    return parse_calendar_text(
        calendar_text
        ,academic_year
        ,date_scraped
    )


def extract_webpage_records(soup, academic_year, date_scraped):
    """Extract term start and end records from the webpage table for one academic year."""

    records = []
    matching_heading = None

    for heading in soup.find_all("h2"):

        heading_text = clean_text(heading.get_text(" ", strip=True))
        match = YEAR_PATTERN.search(heading_text)

        if match is None:
            continue

        heading_year = get_academic_year(
            match.group("start_year")
            ,match.group("end_year")
        )

        if heading_year == academic_year:
            matching_heading = heading
            break

    if matching_heading is None:
        return records

    # Locate the first table following the academic-year heading.
    table = None

    for element in matching_heading.next_elements:

        element_name = getattr(element, "name", None)

        if element_name is not None and re.fullmatch(r"h[1-6]", element_name):
            break

        if element_name == "table":
            table = element
            break

    if table is None:
        raise ValueError(
            f"No term-date table found on the webpage for {academic_year}"
        )

    # Extract term start and end dates from the table.
    term_numbers = set()

    for row in table.find_all("tr"):

        cells = row.find_all(["td", "th"])

        if len(cells) < 3:
            continue

        term = clean_text(cells[0].get_text(" ", strip=True))
        start_date = clean_text(cells[1].get_text(" ", strip=True))
        end_date = clean_text(cells[2].get_text(" ", strip=True))

        if term.lower() == "term":
            continue

        if not start_date or not end_date:
            continue

        term_match = re.fullmatch(
            r"(?:Term\s*)?([1-6])"
            ,term
            ,re.IGNORECASE
        )

        if term_match is None:
            raise ValueError(
                f"Unexpected term label in {academic_year}: {term!r}"
            )

        term_number = int(term_match.group(1))

        if term_number in term_numbers:
            raise ValueError(
                f"Duplicate Term {term_number} row in webpage table for {academic_year}"
            )

        term_numbers.add(term_number)

        records.append({
            "SOURCE_ID"     : SOURCE_ID
            ,"ACADEMIC_YEAR" : academic_year
            ,"EVENT_NAME"    : f"Term {term_number} start"
            ,"RAW_DATE_TEXT" : start_date
            ,"DATE_SCRAPED"  : date_scraped
        })

        records.append({
            "SOURCE_ID"     : SOURCE_ID
            ,"ACADEMIC_YEAR" : academic_year
            ,"EVENT_NAME"    : f"Term {term_number} end"
            ,"RAW_DATE_TEXT" : end_date
            ,"DATE_SCRAPED"  : date_scraped
        })

    if term_numbers != set(range(1, 7)):
        raise ValueError(
            f"Expected webpage dates for all six terms in {academic_year}; "
            f"found terms {sorted(term_numbers)}"
        )

    return records



# ------------------------------------------- Main Code --------------------------------------------

def scrape_bath_north_east_somerset():
    """
    Return school-term and holiday events from the Bath & North East Somerset source.

    PDF calendars take precedence for an academic year when they can be downloaded,
    parsed and validated. The webpage term boundaries are retained as a fallback.

    Returns
    -------
    pd.DataFrame
        One row per event, with columns:
            SOURCE_ID
            ACADEMIC_YEAR
            EVENT_NAME
            RAW_DATE_TEXT
            DATE_SCRAPED
    """

    # -------------------------------------- Retrieve Webpage --------------------------------------

    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    response = requests.get(
        source_url
        ,headers=HEADERS
        ,timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.content
        ,"html.parser"
    )

    date_scraped = datetime.now(timezone.utc).date()

    # ---------------------------------- Identify Academic Years -----------------------------------

    academic_years = []

    for heading in soup.find_all("h2"):

        heading_text = clean_text(heading.get_text(" ", strip=True))
        match = YEAR_PATTERN.search(heading_text)

        if match is None:
            continue

        academic_year = get_academic_year(
            match.group("start_year")
            ,match.group("end_year")
        )

        if academic_year in academic_years:
            raise ValueError(
                f"Duplicate academic-year heading found: {academic_year}"
            )

        academic_years.append(academic_year)

    if not academic_years:
        raise ValueError(
            "No academic-year headings were found on the source webpage"
        )

    # ---------------------------------- Extract Webpage Records -----------------------------------

    webpage_records = []

    for academic_year in academic_years:

        year_records = extract_webpage_records(
            soup
            ,academic_year
            ,date_scraped
        )

        webpage_records.extend(year_records)

    # ------------------------------------- Extract PDF Records ------------------------------------

    pdf_records = []
    covered_academic_years = set()

    for academic_year, pdf_url in find_pdf_calendar_links(soup, source_url):

        try:
            pdf_data = extract_pdf_calendar(
                pdf_url
                ,academic_year
                ,date_scraped
            )

        except (
            requests.RequestException
            ,ValueError
            ,pdfplumber.pdfminer.pdfparser.PDFSyntaxError
        ) as error:

            print(
                f"Could not extract PDF for {academic_year}: {error}"
            )
            continue

        if pdf_data.empty:
            print(
                f"PDF returned no records for {academic_year}; "
                "using webpage records instead"
            )
            continue

        covered_academic_years.add(academic_year)
        pdf_records.append(pdf_data)

    # ----------------------------------------- Combine Data ---------------------------------------

    # Remove webpage records only for years where the PDF was successfully processed.
    combined_records = [
        record for record in webpage_records
        if record["ACADEMIC_YEAR"] not in covered_academic_years
    ]

    # Add the validated PDF records.
    for pdf_data in pdf_records:
        combined_records.extend(
            pdf_data.to_dict("records")
        )

    combined = pd.DataFrame.from_records(
        combined_records
        ,columns=OUTPUT_COLUMNS
    )

    if combined.empty:
        raise ValueError(
            "No school-term or holiday records were extracted"
        )

    # Check for duplicate output records.
    duplicate_columns = [
        "SOURCE_ID"
        ,"ACADEMIC_YEAR"
        ,"EVENT_NAME"
        ,"RAW_DATE_TEXT"
    ]

    duplicates = combined.duplicated(
        subset=duplicate_columns
        ,keep=False
    )

    if duplicates.any():
        duplicate_records = combined.loc[
            duplicates, duplicate_columns
        ]

        raise ValueError(
            "Duplicate records found:\n"
            + duplicate_records.to_string(index=False)
        )

    # Keep academic years in chronological order and event records together.
    combined = combined.sort_values(
        ["ACADEMIC_YEAR", "EVENT_NAME", "RAW_DATE_TEXT"]
        ,ignore_index=True
    )

    return combined
