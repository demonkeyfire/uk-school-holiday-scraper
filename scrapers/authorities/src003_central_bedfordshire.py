
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Central Bedfordshire school-term and holiday events from the council webpage and linked
# PDF calendars. PDF calendar information takes precedence when a calendar can be processed.



# --------------------------------------------- Imports --------------------------------------------

import calendar
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC003"
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

MONTH_NUMBERS = {
    month_name: month_number
    for month_number, month_name in enumerate(calendar.month_name)
    if month_name
}

MONTH_ABBREVIATIONS = {
    month_name[:3].lower(): month_number
    for month_number, month_name in enumerate(calendar.month_name)
    if month_name
}
MONTH_ABBREVIATIONS["sept"] = 9

MONTH_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b"
    ,re.IGNORECASE
)

PDF_LINK_YEAR_PATTERN = re.compile(
    r"(?P<start_year>\d{4})\s+to\s+(?P<end_year>\d{4})"
    ,re.IGNORECASE
)

SLASH_TERM_RANGE_PATTERN = re.compile(
    r"(?P<start_day>\d{1,2})/(?P<start_month>\d{1,2})/(?P<start_year>\d{2,4})"
    r"\s*[–-]\s*"
    r"(?P<end_day>\d{1,2})/(?P<end_month>\d{1,2})/(?P<end_year>\d{2,4})"
)

NAMED_TERM_RANGE_PATTERN = re.compile(
    r"\b(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|"
    r"Thu(?:rs(?:day)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\s+"
    r"(?P<start_day>\d{1,2})\s+(?P<start_month>[A-Za-z]+)\s*[–-]\s*"
    r"(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|"
    r"Thu(?:rs(?:day)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\s+"
    r"(?P<end_day>\d{1,2})\s+(?P<end_month>[A-Za-z]+)"
    r"(?:\s+\d{4})?"
    ,re.IGNORECASE
)

TERM_DURATION_PATTERN = re.compile(
    r"\b(?P<term>Autumn|Spring|Summer)\s+Term\s*[–-]?\s*"
    r"(?P<days>\d+)\s+days?\b"
    ,re.IGNORECASE
)

# Calendar colors used by the council PDFs. Colors represent pupil holidays, bank holidays and,
# in 2026/27, teacher training days.
PDF_CALENDAR_EVENT_COLORS = {
    "2025/26": {
        (0.706, 0.776, 0.906): "School Holiday"
        ,(1.0, 0.898, 0.6): "Bank Holiday"
    }
    ,"2026/27": {
        (0.902, 0.722, 0.718): "School Holiday"
        ,(0.8, 0.6, 1.0): "Bank Holiday"
        ,(0.769, 0.843, 0.608): "Teacher Training Day"
    }
    ,"2027/28": {
        (0.573, 0.816, 0.314): "School Holiday"
        ,(0.8, 0.6, 1.0): "Bank Holiday"
    }
}

# Allow for small differences in PDF colour values.
PDF_COLOR_TOLERANCE = 0.01



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


def make_record(academic_year, event_name, start_date, end_date, date_scraped):

    """Create one standard output record with a private sort date."""

    return {"SOURCE_ID"     : SOURCE_ID
           ,"ACADEMIC_YEAR" : academic_year
           ,"EVENT_NAME"    : event_name
           ,"RAW_DATE_TEXT" : format_date_range(start_date, end_date)
           ,"DATE_SCRAPED"  : date_scraped
           ,"_START_DATE"   : start_date}


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


def validate_academic_year_dates(date_ranges, academic_year):

    """Validate that all supplied date ranges fall within the academic year."""

    academic_year_start, academic_year_end = get_academic_year_bounds(
        academic_year
    )

    for start_date, end_date in date_ranges:

        if end_date < start_date:
            raise ValueError(
                f"Date range ends before it starts: {start_date} to {end_date}"
            )

        if not (
            academic_year_start <= start_date <= academic_year_end
            and academic_year_start <= end_date <= academic_year_end
        ):
            raise ValueError(
                f"Date range falls outside {academic_year}: "
                f"{start_date} to {end_date}"
            )


def validate_term_periods(term_periods, academic_year):

    """Validate the three reconstructed term periods."""

    expected_terms = ["Autumn term", "Spring term", "Summer term"]

    if len(term_periods) != 3:
        raise ValueError(
            f"Expected three term periods in {academic_year}; "
            f"found {len(term_periods)}"
        )

    if [period[0] for period in term_periods] != expected_terms:
        raise ValueError(
            f"Unexpected term sequence in {academic_year}"
        )

    date_ranges = [
        (period[1], period[2])
        for period in term_periods
    ]

    validate_academic_year_dates(date_ranges, academic_year)

    previous_end = None

    for event_name, start_date, end_date in term_periods:

        if end_date < start_date:
            raise ValueError(
                f"{event_name} ends before it starts"
            )

        if previous_end is not None and start_date <= previous_end:
            raise ValueError(
                f"Term periods overlap in {academic_year}: {event_name}"
            )

        previous_end = end_date


def match_pdf_color(actual_color, expected_color, tolerance=PDF_COLOR_TOLERANCE):

    """Compare PDF colors while allowing small floating-point differences."""

    if not isinstance(actual_color, (tuple, list)):
        return False

    if len(actual_color) != len(expected_color):
        return False

    try:
        return all(
            abs(float(actual) - expected) <= tolerance
            for actual, expected in zip(actual_color, expected_color)
        )
    except (TypeError, ValueError):
        return False


def identify_pdf_event_color(actual_color, event_colors):

    """Return the event category associated with a PDF fill color."""

    for expected_color, event_name in event_colors.items():

        if match_pdf_color(actual_color, expected_color):
            return event_name

    return None


def find_pdf_calendar_links(soup, page_url):

    """Return academic-year and PDF URL pairs for linked council calendars."""

    calendar_links = {}

    for link in soup.find_all("a", href=True):

        link_text = clean_text(
            " ".join([
                link.get_text(" ", strip=True)
                ,link.get("title", "")
            ])
        )

        if "pdf" not in link_text.lower():
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


def make_direct_download_url(pdf_url):

    """Add a direct-download parameter to SharePoint sharing links only."""

    parts = urlsplit(pdf_url)

    if "sharepoint.com" not in parts.netloc.lower():
        return pdf_url

    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["download"] = "1"

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def find_month_header_groups(page, academic_year):

    """Find and validate the four calendar month headings in each calendar row."""

    start_year = int(academic_year.split("/")[0])
    end_year = start_year + 1

    words = page.extract_words()
    headers = []

    for word_number, word in enumerate(words[:-1]):

        month_number = MONTH_NUMBERS.get(word["text"].title())

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

    # Each actual calendar row should contain four consecutive months.
    calendar_groups = [
        group for group in groups
        if len(group) >= 3
    ]

    expected_month_groups = [
        [9, 10, 11, 12]
        ,[1, 2, 3, 4]
        ,[5, 6, 7, 8]
    ]

    if len(calendar_groups) != 3:
        raise ValueError(
            f"Expected three calendar rows in {academic_year}; "
            f"found {len(calendar_groups)}"
        )

    for group_number, group in enumerate(calendar_groups):

        if len(group) != 4:
            raise ValueError(
                f"Expected four month headings in calendar row "
                f"{group_number + 1} of {academic_year}; found {len(group)}"
            )

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

    """Read colored date cells from the PDF's 12-month calendar."""

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

        # The PDFs sometimes draw the same colored day cell as nested rectangles.
        # Select the smallest matching rectangle, as in the original implementation.
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

    # Validate the number of bank holidays found in the calendar.
    bank_holiday_count = len(event_dates.get("Bank Holiday", set()))

    if bank_holiday_count != 8:
        raise ValueError(
            f"Expected eight bank holidays in {academic_year}; "
            f"found {bank_holiday_count}"
        )

    if not event_dates.get("School Holiday"):
        raise ValueError(
            f"No school-holiday dates were extracted for {academic_year}"
        )

    # Report extracted date counts for manual checking.
    print(f"PDF calendar extraction: {academic_year}")

    for event_name, dates in sorted(event_dates.items()):
        print(f"  {event_name}: {len(dates)} dates")

    print(f"  Calendar date cells matched: {sum(month_date_counts.values())}")

    return event_dates


def get_term_periods(calendar_text, academic_year, school_holiday_dates,
                     bank_holiday_dates, teacher_training_dates):

    """Read term periods from PDF text, or infer them from the published day counts."""

    start_year = int(academic_year.split("/")[0])
    end_year = start_year + 1
    date_ranges = []

    # --------------------------------------- Explicit Date Ranges ---------------------------------

    for match in SLASH_TERM_RANGE_PATTERN.finditer(calendar_text):

        start_range_year = int(match.group("start_year"))
        end_range_year = int(match.group("end_year"))

        if start_range_year < 100:
            start_range_year += 2000

        if end_range_year < 100:
            end_range_year += 2000

        date_ranges.append((
            date(
                start_range_year
                ,int(match.group("start_month"))
                ,int(match.group("start_day"))
            )
            ,date(
                end_range_year
                ,int(match.group("end_month"))
                ,int(match.group("end_day"))
            )
        ))

    # ---------------------------------------- Named Date Ranges -----------------------------------

    if not date_ranges:

        def parse_short_month(value):

            month_number = MONTH_ABBREVIATIONS.get(value[:4].lower())

            if month_number is None:
                month_number = MONTH_ABBREVIATIONS.get(value[:3].lower())

            if month_number is None:
                raise ValueError(
                    f"Unknown month in term date: {value!r}"
                )

            return month_number

        for match in NAMED_TERM_RANGE_PATTERN.finditer(calendar_text):

            start_month = parse_short_month(match.group("start_month"))
            end_month = parse_short_month(match.group("end_month"))

            term_start_year = (
                start_year if start_month >= 9 else end_year
            )

            term_end_year = (
                end_year if end_month < 9 else start_year
            )

            date_ranges.append((
                date(
                    term_start_year
                    ,start_month
                    ,int(match.group("start_day"))
                )
                ,date(
                    term_end_year
                    ,end_month
                    ,int(match.group("end_day"))
                )
            ))

    # -------------------------------------- Validate Date Ranges ----------------------------------

    if date_ranges:

        if len(date_ranges) != 6:
            raise ValueError(
                f"Expected six term date ranges in {academic_year}; "
                f"found {len(date_ranges)}"
            )

        date_ranges.sort(key=lambda item: item[0])

        validate_academic_year_dates(
            date_ranges
            ,academic_year
        )

        # Check that the six ranges are chronologically ordered and do not overlap.
        previous_end = None

        for start_date, end_date in date_ranges:

            if previous_end is not None and start_date <= previous_end:
                raise ValueError(
                    f"Term date ranges overlap in {academic_year}"
                )

            previous_end = end_date

        # The six date ranges represent two periods for each of the three terms.
        term_names = ["Autumn term", "Spring term", "Summer term"]
        term_records = []

        for term_number, term_name in enumerate(term_names):

            first_range = date_ranges[term_number * 2]
            second_range = date_ranges[term_number * 2 + 1]

            term_records.append((
                term_name
                ,first_range[0]
                ,second_range[1]
            ))

    print(f"  Extracted term periods for {academic_year}:")

        validate_term_periods(
            term_records
            ,academic_year
        )

        return term_records

    # --------------------------------------- Term Duration Fallback -------------------------------

    duration_matches = list(
        TERM_DURATION_PATTERN.finditer(calendar_text)
    )

    term_durations = {}

    for match in duration_matches:

        term_name = match.group("term").title()
        term_days = int(match.group("days"))

        if term_name in term_durations:
            raise ValueError(
                f"Duplicate {term_name} term duration found in {academic_year}"
            )

        if term_days <= 0:
            raise ValueError(
                f"Invalid {term_name} term duration in {academic_year}"
            )

        term_durations[term_name] = term_days

    if set(term_durations) != {"Autumn", "Spring", "Summer"}:
        raise ValueError(
            f"Could not extract term date ranges or day counts for {academic_year}"
        )

    academic_year_start, academic_year_end = get_academic_year_bounds(
        academic_year
    )

    # Exclude all calendar dates that are not pupil attendance days.
    excluded_dates = (
        school_holiday_dates
        | bank_holiday_dates
        | teacher_training_dates
    )

    term_weekdays = []
    current_date = academic_year_start

    while current_date <= academic_year_end:

        if (
            current_date.weekday() < 5
            and current_date not in excluded_dates
        ):
            term_weekdays.append(current_date)

        current_date += timedelta(days=1)

    expected_term_days = sum(term_durations.values())

    if len(term_weekdays) != expected_term_days:
        raise ValueError(
            f"Expected {expected_term_days} term weekdays in {academic_year}; "
            f"found {len(term_weekdays)}"
        )

    term_records = []
    offset = 0

    for term_name in ["Autumn", "Spring", "Summer"]:

        term_days = term_weekdays[
            offset:offset + term_durations[term_name]
        ]

        if not term_days:
            raise ValueError(
                f"No reconstructed attendance dates found for {term_name} "
                f"in {academic_year}"
            )

        term_records.append((
            f"{term_name} term"
            ,term_days[0]
            ,term_days[-1]
        ))

        offset += term_durations[term_name]

    validate_term_periods(
        term_records
        ,academic_year
    )

    return term_records


def group_school_holidays(school_holiday_dates, academic_year):

    """Group colored school-holiday weekdays into inclusive break periods."""

    closure_dates = sorted(school_holiday_dates)

    if not closure_dates:
        return []

    groups = [[closure_dates[0]]]

    for current_date in closure_dates[1:]:

        previous_date = groups[-1][-1]
        day_gap = (current_date - previous_date).days

        # Combine consecutive dates, or Friday and Monday separated by a weekend.
        if day_gap == 1 or (
            day_gap == 3
            and previous_date.weekday() == 4
            and current_date.weekday() == 0
        ):
            groups[-1].append(current_date)
        else:
            groups.append([current_date])

    year_start, year_end = get_academic_year_bounds(academic_year)
    periods = []

    for group in groups:

        period_start = group[0]
        period_end = group[-1]

        period_start = max(period_start, year_start)
        period_end = min(period_end, year_end)

        periods.append((period_start, period_end))

    return periods


def extract_pdf_calendar(pdf_url, academic_year, date_scraped):

    """Download a council PDF and return its term, holiday and training-day records."""

    response = requests.get(
        make_direct_download_url(pdf_url)
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
        calendar_text = page.extract_text()

        if not calendar_text:
            raise ValueError(
                f"Could not extract text from the {academic_year} PDF"
            )

        event_dates = extract_calendar_event_dates(
            page
            ,academic_year
        )

        school_holiday_dates = event_dates.get("School Holiday", set())
        bank_holiday_dates = event_dates.get("Bank Holiday", set())
        teacher_training_dates = event_dates.get("Teacher Training Day", set())

        term_periods = get_term_periods(
            calendar_text
            ,academic_year
            ,school_holiday_dates
            ,bank_holiday_dates
            ,teacher_training_dates
        )

    # ----------------------------------------- Term Records ---------------------------------------

    records = [
        make_record(
            academic_year
            ,event_name
            ,start_date
            ,end_date
            ,date_scraped
        )
        for event_name, start_date, end_date in term_periods
    ]

    # -------------------------------------- Bank Holiday Records ----------------------------------

    records.extend(
        make_record(
            academic_year
            ,"Bank Holiday"
            ,holiday_date
            ,holiday_date
            ,date_scraped
        )
        for holiday_date in sorted(bank_holiday_dates)
    )

    # ---------------------------------- Teacher Training Records ----------------------------------

    records.extend(
        make_record(
            academic_year
            ,"Teacher Training Day"
            ,training_date
            ,training_date
            ,date_scraped
        )
        for training_date in sorted(teacher_training_dates)
    )

    # ------------------------------------- School Holiday Records ---------------------------------

    records.extend(
        make_record(
            academic_year
            ,"School Holiday"
            ,period_start
            ,period_end
            ,date_scraped
        )
        for period_start, period_end in group_school_holidays(
            school_holiday_dates
            ,academic_year
        )
    )

    return pd.DataFrame.from_records(
        records
        ,columns=OUTPUT_COLUMNS + ["_START_DATE"]
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

            date_elements = [
                date_element for date_element in element.find_all("strong")
                if MONTH_PATTERN.search(
                    date_element.get_text(" ", strip=True)
                )
            ]

            if not date_elements:
                continue

            raw_dates = [
                clean_text(date_element.get_text(" ", strip=True))
                for date_element in date_elements
            ]

            event_name = element.get_text(" ", strip=True)

            for raw_date in raw_dates:
                event_name = event_name.replace(raw_date, "", 1)

            event_name = re.sub(
                r"\s+"
                , " "
                ,event_name
            ).strip(" ,:-")

            event_name = re.sub(
                r"\s+\b(on|is|from)\s*$"
                ,""
                ,event_name
                ,flags=re.IGNORECASE
            )

            if not event_name:
                continue

            records.append({
                "SOURCE_ID"     : SOURCE_ID
                ,"ACADEMIC_YEAR" : academic_year
                ,"EVENT_NAME"    : event_name
                ,"RAW_DATE_TEXT" : " | ".join(raw_dates)
                ,"DATE_SCRAPED"  : date_scraped
                ,"_START_DATE"   : pd.NaT
            })

    return records



# ------------------------------------------- Main Code --------------------------------------------

def scrape_central_bedfordshire():

    """
    Retrieve school-term and holiday events from Central Bedfordshire Council.

    PDF calendars take precedence for academic years whose linked PDFs can be processed.
    Webpage records are retained as a fallback for other years.
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

    # ---------------------------------- Extract Webpage Records -----------------------------------

    webpage_records = extract_webpage_records(
        soup
        ,date_scraped
    )

    webpage_academic_years = {
        record["ACADEMIC_YEAR"]
        for record in webpage_records
    }

    # ------------------------------------- Extract PDF Records ------------------------------------

    pdf_records = []
    processed_academic_years = set()

    for academic_year, pdf_url in find_pdf_calendar_links(soup, source_url):

        try:
            pdf_data = extract_pdf_calendar(
                pdf_url
                ,academic_year
                ,date_scraped
            )

        except Exception as error:

            # A failed PDF should not prevent the webpage fallback from being used.
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
        pdf_records.append(pdf_data)

    # ----------------------------------------- Combine Data ---------------------------------------

    # Retain webpage records only where a PDF was not successfully processed.
    combined_records = [
        record for record in webpage_records
        if record["ACADEMIC_YEAR"] not in processed_academic_years
    ]

    # Add the successfully extracted PDF records.
    for pdf_data in pdf_records:
        combined_records.extend(
            pdf_data.to_dict("records")
        )

    combined = pd.DataFrame.from_records(
        combined_records
        ,columns=OUTPUT_COLUMNS + ["_START_DATE"]
    )

    if combined.empty:
        raise ValueError(
            "No school-term or holiday records were extracted"
        )

    # ------------------------------------- Validate Output -----------------------------------------

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
        raise ValueError(
            "Duplicate records found:\n"
            + combined.loc[
                duplicates, duplicate_columns
            ].to_string(index=False)
        )

    # -------------------------------------- Extraction Summary ------------------------------------

    for academic_year in sorted(
        webpage_academic_years | processed_academic_years
    ):

        if academic_year in processed_academic_years:
            extraction_source = "PDF"
        elif academic_year in webpage_academic_years:
            extraction_source = "Webpage fallback"
        else:
            extraction_source = "No records"

        print(
            f"{academic_year}: {extraction_source}"
        )

    # --------------------------------------- Sort and Return --------------------------------------

    combined["_START_DATE"] = pd.to_datetime(
        combined["_START_DATE"]
        ,errors="coerce"
    )

    combined = combined.sort_values(
        ["ACADEMIC_YEAR", "_START_DATE", "EVENT_NAME", "RAW_DATE_TEXT"]
        ,ignore_index=True
    )

    return combined[OUTPUT_COLUMNS]
