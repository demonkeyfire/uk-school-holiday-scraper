# -------------------------------------------- Overview --------------------------------------------

# Retrieve Bristol school-term and holiday events from the council webpage and linked PDF calendars.
# PDF calendar data takes precedence; webpage term rows fill gaps if PDF term dates are invalid.



# --------------------------------------------- Imports --------------------------------------------

import calendar
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import re
from urllib.parse import urljoin

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source_url



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC007"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

YEAR_PATTERN = re.compile(
    r"(\d{4})\s+to\s+(\d{4})"
    ,re.IGNORECASE
)

PDF_LINK_YEAR_PATTERN = re.compile(
    r"(?P<start_year>\d{4})\s+to\s+(?P<end_year>\d{4})"
    ,re.IGNORECASE
)

TERM_DATE_PATTERN = re.compile(
    r"\bTerm\s+(?P<term_number>\d+)\s+From:\s*"
    r"(?P<start_day>\d{1,2})\s+(?P<start_month>[A-Za-z]+)\s+"
    r"(?P<start_year>\d{4})\s+To:\s*"
    r"(?P<end_day>\d{1,2})\s+(?P<end_month>[A-Za-z]+)\s+"
    r"(?P<end_year>\d{4})\s+"
    r"\((?P<term_days>\d+)\s+Days?\)"
    ,re.IGNORECASE
)

MONTH_NUMBERS = {
    month_name.lower(): month_number
    for month_number, month_name in enumerate(calendar.month_name)
    if month_name
}

# Colors used for school and bank holidays in the current Bristol council PDFs.
PDF_CALENDAR_EVENT_COLORS = {
    "2026/27": {
        (0.706, 0.776, 0.906): "School Holiday"
        ,(0.573, 0.816, 0.314): "Bank Holiday"
    }
    ,"2027/28": {
        (0.8, 0.0, 0.0): "School Holiday"
        ,(0.267, 0.447, 0.769): "Bank Holiday"
        ,(0.0, 0.439, 0.753): "Bank Holiday"
    }
}

PDF_COLOR_TOLERANCE = 0.01



# ------------------------------------------- Helper Functions -------------------------------------

def get_academic_year(start_year, end_year):

    """Format and validate a consecutive academic-year range."""

    start_year = int(start_year)
    end_year = int(end_year)

    if end_year != start_year + 1:
        raise ValueError(
            f"Academic years must contain consecutive calendar years: "
            f"{start_year}/{end_year}"
        )

    return f"{start_year}/{str(end_year)[-2:]}"


def get_academic_year_bounds(academic_year):

    """Return the inclusive start and end dates of an academic year."""

    start_year = int(academic_year.split("/")[0])

    return date(start_year, 9, 1), date(start_year + 1, 8, 31)


def make_record(academic_year, event_name, raw_date_text, date_scraped):

    """Build a record using the scraper's shared output schema."""

    return {
        "SOURCE_ID"     : SOURCE_ID
        ,"ACADEMIC_YEAR" : academic_year
        ,"EVENT_NAME"    : event_name
        ,"RAW_DATE_TEXT" : raw_date_text
        ,"DATE_SCRAPED"  : date_scraped
    }


def format_date(value):

    """Format a date using the council's day-month-year style."""

    return f"{value.day} {calendar.month_name[value.month]} {value.year}"


def format_date_range(start_date, end_date):

    """Format one date or an inclusive date range."""

    if start_date == end_date:
        return format_date(start_date)

    return f"{format_date(start_date)} to {format_date(end_date)}"


def find_pdf_calendar_links(soup, page_url):

    """Return academic-year and PDF URL pairs linked from the council page."""

    calendar_links = {}

    for link in soup.find_all("a", href=True):

        link_text = " ".join((
            link.get_text(" ", strip=True)
            ,str(link.get("data-title", ""))
        ))

        if (
            str(link.get("type", "")).lower() != "application/pdf"
            and "pdf" not in link_text.lower()
        ):
            continue

        year_match = PDF_LINK_YEAR_PATTERN.search(link_text)

        if year_match is None:
            continue

        academic_year = get_academic_year(
            year_match.group("start_year")
            ,year_match.group("end_year")
        )
        pdf_url = urljoin(page_url, link["href"])

        if academic_year in calendar_links:

            if calendar_links[academic_year] != pdf_url:
                raise ValueError(
                    f"Multiple different PDF links found for {academic_year}"
                )

            continue

        calendar_links[academic_year] = pdf_url

    return list(calendar_links.items())


def match_pdf_color(actual_color, expected_color):

    """Compare PDF colors while allowing small floating-point differences."""

    if not isinstance(actual_color, (tuple, list)):
        return False

    if len(actual_color) != len(expected_color):
        return False

    try:
        return all(
            abs(actual_value - expected_value) <= PDF_COLOR_TOLERANCE
            for actual_value, expected_value in zip(
                actual_color
                ,expected_color
            )
        )
    except (TypeError, ValueError):
        return False


def identify_pdf_event_color(actual_color, event_colors):

    """Return the event category associated with a PDF fill color."""

    for expected_color, event_name in event_colors.items():

        if match_pdf_color(actual_color, expected_color):
            return event_name

    return None


def find_month_header_groups(page, academic_year):

    """Find and validate the three calendar month headings in each calendar row."""

    start_year = int(academic_year.split("/")[0])
    end_year = start_year + 1
    words = page.extract_words()
    headers = []

    for word_number, word in enumerate(words[:-1]):

        month_number = MONTH_NUMBERS.get(word["text"].lower())

        if month_number is None:
            continue

        expected_year = start_year if month_number >= 9 else end_year

        if words[word_number + 1]["text"] != str(expected_year):
            continue

        headers.append({
            "MONTH" : month_number
            ,"YEAR"  : expected_year
            ,"X"     : (word["x0"] + word["x1"]) / 2
            ,"TOP"   : word["top"]
        })

    groups = []

    for header in sorted(headers, key=lambda item: item["TOP"]):

        if not groups or abs(header["TOP"] - groups[-1][0]["TOP"]) > 3:
            groups.append([header])
        else:
            groups[-1].append(header)

    expected_month_groups = [
        [9, 10, 11]
        ,[12, 1, 2]
        ,[3, 4, 5]
        ,[6, 7, 8]
    ]
    calendar_groups = []

    for group in groups:

        actual_months = [
            item["MONTH"]
            for item in sorted(group, key=lambda item: item["X"])
        ]

        if actual_months in expected_month_groups:
            calendar_groups.append(group)

    if len(calendar_groups) != len(expected_month_groups):
        raise ValueError(
            f"Expected four calendar rows in {academic_year}; "
            f"found {len(calendar_groups)}"
        )

    for group_number, group in enumerate(calendar_groups):
        actual_months = [
            item["MONTH"]
            for item in sorted(group, key=lambda item: item["X"])
        ]

        if actual_months != expected_month_groups[group_number]:
            raise ValueError(
                f"Unexpected month sequence in calendar row "
                f"{group_number + 1} of {academic_year}: {actual_months}"
            )

    return calendar_groups


def extract_calendar_event_dates(page, academic_year):

    """Read colored school- and bank-holiday date cells from a PDF calendar."""

    event_colors = PDF_CALENDAR_EVENT_COLORS.get(academic_year)

    if event_colors is None:
        raise ValueError(
            f"No calendar color mapping is configured for {academic_year}"
        )

    month_groups = find_month_header_groups(page, academic_year)
    start_date, end_date = get_academic_year_bounds(academic_year)
    recognized_rectangles = []

    for rectangle in page.rects:

        event_name = identify_pdf_event_color(
            rectangle.get("non_stroking_color")
            ,event_colors
        )

        if event_name is not None:
            recognized_rectangles.append((rectangle, event_name))

    event_dates = {
        event_name: set()
        for event_name in set(event_colors.values())
    }
    month_date_counts = {}

    for word in page.extract_words():

        if re.fullmatch(r"\d{1,2}", word["text"]) is None:
            continue

        month_rows = [
            group for group in month_groups
            if group[0]["TOP"] <= word["top"]
        ]

        if not month_rows:
            continue

        month_row = month_rows[-1]
        word_center_x = (word["x0"] + word["x1"]) / 2
        month_header = min(
            month_row
            ,key=lambda item: abs(item["X"] - word_center_x)
        )

        if abs(month_header["X"] - word_center_x) > 110:
            continue

        try:
            calendar_date = date(
                month_header["YEAR"]
                ,month_header["MONTH"]
                ,int(word["text"])
            )
        except ValueError:
            continue

        if not start_date <= calendar_date <= end_date:
            continue

        word_center_y = (word["top"] + word["bottom"]) / 2
        matching_rectangles = [
            (rectangle, event_name)
            for rectangle, event_name in recognized_rectangles
            if rectangle["x0"] <= word_center_x <= rectangle["x1"]
            and rectangle["top"] <= word_center_y <= rectangle["bottom"]
        ]

        if not matching_rectangles:
            continue

        rectangle, event_name = min(
            matching_rectangles
            ,key=lambda item: item[0]["width"] * item[0]["height"]
        )

        event_dates[event_name].add(calendar_date)
        month_key = (
            month_header["YEAR"]
            ,month_header["MONTH"]
        )
        month_date_counts[month_key] = (
            month_date_counts.get(month_key, 0) + 1
        )

    bank_holiday_dates = event_dates.get("Bank Holiday", set())

    if len(bank_holiday_dates) != 8:
        raise ValueError(
            f"Expected eight bank holidays in {academic_year}; "
            f"found {len(bank_holiday_dates)}"
        )

    if not event_dates.get("School Holiday"):
        raise ValueError(
            f"No school-holiday dates were extracted for {academic_year}"
        )

    print(f"PDF calendar extraction: {academic_year}")

    for event_name, dates in sorted(event_dates.items()):
        print(f"  {event_name}: {len(dates)} dates")

    print(f"  Calendar date cells matched: {sum(month_date_counts.values())}")

    return event_dates


def group_school_holidays(school_holiday_dates):

    """Group adjacent colored weekdays into inclusive school-holiday periods."""

    closure_dates = sorted(school_holiday_dates)

    if not closure_dates:
        return []

    groups = [[closure_dates[0]]]

    for current_date in closure_dates[1:]:

        previous_date = groups[-1][-1]
        day_gap = (current_date - previous_date).days

        if day_gap == 1 or (
            day_gap == 3
            and previous_date.weekday() == 4
            and current_date.weekday() == 0
        ):
            groups[-1].append(current_date)
        else:
            groups.append([current_date])

    return [
        (group[0], group[-1])
        for group in groups
    ]


def extract_pdf_term_records(calendar_text, academic_year, school_holiday_dates,
                             bank_holiday_dates, date_scraped):

    """Extract and validate the six term ranges and their published day counts."""

    matches = list(TERM_DATE_PATTERN.finditer(calendar_text))

    if [int(match.group("term_number")) for match in matches] != list(range(1, 7)):
        raise ValueError(
            f"Expected six numbered term ranges in {academic_year}; "
            f"found {len(matches)}"
        )

    academic_year_start, academic_year_end = get_academic_year_bounds(
        academic_year
    )
    excluded_dates = school_holiday_dates | bank_holiday_dates
    term_records = []
    previous_end = None

    for match in matches:

        start_month = MONTH_NUMBERS.get(match.group("start_month").lower())
        end_month = MONTH_NUMBERS.get(match.group("end_month").lower())

        if start_month is None or end_month is None:
            raise ValueError(
                f"Unknown month in term dates for {academic_year}"
            )

        start_date = date(
            int(match.group("start_year"))
            ,start_month
            ,int(match.group("start_day"))
        )
        end_date = date(
            int(match.group("end_year"))
            ,end_month
            ,int(match.group("end_day"))
        )

        if not (
            academic_year_start <= start_date <= academic_year_end
            and academic_year_start <= end_date <= academic_year_end
        ):
            raise ValueError(
                f"Term date falls outside {academic_year}: "
                f"{start_date} to {end_date}"
            )

        if end_date < start_date:
            raise ValueError(
                f"Term ends before it starts in {academic_year}: "
                f"{start_date} to {end_date}"
            )

        actual_days = 0
        current_date = start_date

        while current_date <= end_date:

            if (
                current_date.weekday() < 5
                and current_date not in excluded_dates
            ):
                actual_days += 1

            current_date += timedelta(days=1)

        expected_days = int(match.group("term_days"))

        if actual_days != expected_days:
            raise ValueError(
                f"Expected {expected_days} term weekdays in {academic_year} "
                f"from {start_date} to {end_date}; found {actual_days}"
            )

        if previous_end is not None and start_date <= previous_end:
            raise ValueError(
                f"Term date ranges overlap in {academic_year}"
            )

        previous_end = end_date
        raw_date_text = (
            f"{match.group('start_day')} {match.group('start_month')} "
            f"{match.group('start_year')} to "
            f"{match.group('end_day')} {match.group('end_month')} "
            f"{match.group('end_year')} ({expected_days} Days)"
        )

        term_records.append(
            make_record(
                academic_year
                ,f"Term {match.group('term_number')}"
                ,raw_date_text
                ,date_scraped
            )
        )

    return term_records


def extract_pdf_calendar(pdf_url, academic_year, date_scraped):

    """Download a Bristol PDF and return holiday records and any valid term records."""

    response = requests.get(
        pdf_url
        ,headers=HEADERS
        ,timeout=30
    )
    response.raise_for_status()

    if not response.content.startswith(b"%PDF-"):
        raise ValueError(
            f"The council link for {academic_year} did not return a PDF file"
        )

    with pdfplumber.open(BytesIO(response.content)) as calendar_pdf:

        if not calendar_pdf.pages:
            raise ValueError(
                f"The PDF for {academic_year} contains no pages"
            )

        page = calendar_pdf.pages[0]
        calendar_text = page.extract_text() or ""
        event_dates = extract_calendar_event_dates(
            page
            ,academic_year
        )
        bank_holiday_dates = event_dates["Bank Holiday"]
        school_holiday_dates = event_dates["School Holiday"]

        try:
            term_records = extract_pdf_term_records(
                calendar_text
                ,academic_year
                ,school_holiday_dates
                ,bank_holiday_dates
                ,date_scraped
            )
        except ValueError as error:
            print(
                f"Could not extract PDF term dates for {academic_year}: "
                f"{type(error).__name__}: {error}"
            )
            term_records = None

    records = term_records if term_records is not None else []

    records.extend(
        make_record(
            academic_year
            ,"Bank Holiday"
            ,format_date(holiday_date)
            ,date_scraped
        )
        for holiday_date in sorted(bank_holiday_dates)
    )

    records.extend(
        make_record(
            academic_year
            ,"School Holiday"
            ,format_date_range(period_start, period_end)
            ,date_scraped
        )
        for period_start, period_end in group_school_holidays(
            school_holiday_dates
        )
    )

    return (
        pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)
        ,term_records is not None
    )


def extract_webpage_records(soup, date_scraped):

    """Extract event records from the webpage as a fallback for PDF years."""

    records = []

    for heading in soup.find_all("h2"):

        heading_text = heading.get_text(" ", strip=True)
        year_match = YEAR_PATTERN.search(heading_text)

        if year_match is None:
            continue

        academic_year = get_academic_year(
            year_match.group(1)
            ,year_match.group(2)
        )

        for element in heading.next_elements:

            if (
                element is not heading
                and getattr(element, "name", None) == "h2"
            ):
                break

            if getattr(element, "name", None) != "li":
                continue

            event_text = element.get_text(" ", strip=True)

            if ":" not in event_text:
                continue

            event_name, raw_date_text = event_text.split(":", 1)
            event_name = event_name.strip()
            raw_date_text = re.sub(r"\s+", " ", raw_date_text).strip()

            if not event_name or not raw_date_text:
                continue

            records.append(
                make_record(
                    academic_year
                    ,event_name
                    ,raw_date_text
                    ,date_scraped
                )
            )

    return records


def is_webpage_term_record(record):

    """Identify term rows to retain when a PDF calendar's term text is invalid."""

    return re.match(r"^Term\s+\d+\b", record["EVENT_NAME"], re.IGNORECASE) is not None



# ------------------------------------------- Main Code --------------------------------------------

def scrape_bristol():

    source_url = get_source_url(SOURCE_ID)

    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    date_scraped = datetime.now(timezone.utc).date()
    webpage_records = extract_webpage_records(soup, date_scraped)

    webpage_academic_years = {
        record["ACADEMIC_YEAR"]
        for record in webpage_records
    }
    pdf_records = []
    processed_academic_years = set()
    pdf_term_academic_years = set()

    for academic_year, pdf_url in find_pdf_calendar_links(soup, source_url):

        try:
            pdf_data, has_pdf_term_records = extract_pdf_calendar(
                pdf_url
                ,academic_year
                ,date_scraped
            )
        except Exception as error:
            print(
                f"Could not extract PDF for {academic_year}: "
                f"{type(error).__name__}: {error}"
            )
            continue

        if pdf_data.empty:
            print(
                f"PDF returned no records for {academic_year}; "
                "using webpage records instead"
            )
            continue

        processed_academic_years.add(academic_year)

        if has_pdf_term_records:
            pdf_term_academic_years.add(academic_year)

        pdf_records.append(pdf_data)

    combined_records = [
        record for record in webpage_records
        if (
            record["ACADEMIC_YEAR"] not in processed_academic_years
            or (
                record["ACADEMIC_YEAR"] not in pdf_term_academic_years
                and is_webpage_term_record(record)
            )
        )
    ]

    for pdf_data in pdf_records:
        combined_records.extend(
            pdf_data.to_dict("records")
        )

    for academic_year in sorted(
        webpage_academic_years | processed_academic_years
    ):

        if academic_year in pdf_term_academic_years:
            extraction_source = "PDF"
        elif academic_year in processed_academic_years:
            extraction_source = "PDF holidays + webpage terms"
        elif academic_year in webpage_academic_years:
            extraction_source = "Webpage fallback"
        else:
            extraction_source = "No records"

        print(
            f"{academic_year}: {extraction_source}"
        )

    return pd.DataFrame.from_records(
        combined_records
        ,columns=OUTPUT_COLUMNS
    )
