
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Buckinghamshire school-term dates from the council webpage and its linked Excel and PDF
# calendars. Calendar events take precedence on overlapping dates; uncovered webpage dates remain.



# --------------------------------------------- Imports --------------------------------------------

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import re
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook
import pdfplumber

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC008"
ACADEMIC_YEAR = "2025/26"
CALENDAR_FILENAME = "2025_26_academic_year_Term_Dates.xlsx"

HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

ACADEMIC_YEAR_START_MONTH = 9
ACADEMIC_YEAR_END_MONTH = 8

SUPPORTED_PDF_YEARS = {"2026/27", "2027/28"}

TERM_PATTERN = re.compile(
    r"(Autumn|Spring|Summer)\s+term\s+(\d{4})",
    re.IGNORECASE
)

CALENDAR_LINK_PATTERN = re.compile(
    re.escape(CALENDAR_FILENAME) + r"(?:\?|$)",
    re.IGNORECASE
)

PDF_LINK_YEAR_PATTERN = re.compile(
    r"(20\d{2})[\s_-]*(?:to|/|-|_)[\s_-]*(20\d{2})",
    re.IGNORECASE
)

DATE_PATTERN = re.compile(
    r"\b(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?"
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+(\d{4}))?\b",
    re.IGNORECASE
)

CATEGORY_NAMES = {"Inset Day"
                 ,"Bank Holiday"
                 ,"Term Day"
                 ,"Transition Days"
                 ,"Holiday Day"}

MONTH_NUMBERS = {"January"   : 1
                ,"February"  : 2
                ,"March"     : 3
                ,"April"     : 4
                ,"May"       : 5
                ,"June"      : 6
                ,"July"      : 7
                ,"August"    : 8
                ,"September" : 9
                ,"October"   : 10
                ,"November"  : 11
                ,"December" : 12}

EXPECTED_MONTHS = [
    "September"
   ,"October"
   ,"November"
   ,"December"
   ,"January"
   ,"February"
   ,"March"
   ,"April"
   ,"May"
   ,"June"
   ,"July"
   ,"August"
]

PDF_COLOR_TOLERANCE = 0.02

PDF_EVENT_COLORS = {
    "2026/27": {
        (1.0, 0.902, 0.6): "School Holiday",
        (0.408, 0.478, 0.988): "Bank Holiday",
        (1.0, 1.0, 0.0): "Inset Day",
        (0.635, 0.949, 0.941): "Transition Days",
    },
    "2027/28": {
        (0.518, 0.886, 0.565): "School Holiday",
        (0.898, 0.62, 0.863): "Bank Holiday",
        (0.918, 0.196, 0.78): "Inset Day",
        (0.278, 0.831, 0.349): "Transition Days",
    },
}

PDF_TERM_COLORS = {
    "2026/27": (0.706, 0.776, 0.906),
    "2027/28": (0.514, 0.792, 0.922),
}



# ------------------------------------------- Helper Functions -------------------------------------

def get_academic_year_bounds(academic_year):

    """Return the first and last dates of an academic year."""

    match = re.fullmatch(r"(20\d{2})/(\d{2})", academic_year)

    if match is None:
        raise ValueError(f"Invalid academic year: {academic_year}")

    year_start = int(match.group(1))
    year_end = int(f"{str(year_start)[:2]}{match.group(2)}")

    if year_end != year_start + 1:
        raise ValueError(f"Non-consecutive academic year: {academic_year}")

    return (
        date(year_start, ACADEMIC_YEAR_START_MONTH, 1)
        ,date(year_end, ACADEMIC_YEAR_END_MONTH, 31)
    )


def validate_academic_year_dates(dates, academic_year, description):

    """Ensure all supplied dates fall within the specified academic year."""

    year_start, year_end = get_academic_year_bounds(academic_year)

    invalid_dates = [
        value for value in dates
        if value < year_start or value > year_end
    ]

    if invalid_dates:
        raise ValueError(
            f"{description} contains dates outside {academic_year}: "
            f"{sorted(invalid_dates)}"
        )


def get_fill_signature(cell):

    """Return a comparable description of a cell's fill colour."""

    colour = cell.fill.fgColor
    colour_value = getattr(colour, colour.type)

    return (
        cell.fill.fill_type
        ,colour.type
        ,colour_value
        ,colour.tint
    )


def find_calendar_categories(worksheet):

    """Map workbook legend fill colours to their displayed category names."""

    categories = {}

    for row in worksheet.iter_rows():

        for cell in row:

            if not isinstance(cell.value, str) or cell.value.strip() not in CATEGORY_NAMES:
                continue

            if cell.column <= 1:
                raise ValueError(
                    f"Calendar legend category has no preceding colour cell: {cell.value}"
                )

            legend_cell = worksheet.cell(
                row=cell.row
                ,column=cell.column - 1
            )

            signature = get_fill_signature(legend_cell)

            if signature in categories:
                raise ValueError(
                    f"Duplicate calendar legend fill for {cell.value}"
                )

            categories[signature] = cell.value.strip()

    missing_categories = CATEGORY_NAMES.difference(categories.values())

    if missing_categories:
        raise ValueError(
            f"Calendar legend is missing categories: {sorted(missing_categories)}"
        )

    return categories


def find_month_headers(worksheet):

    """Collect calendar month headings and their worksheet positions."""

    months = {}

    for row_number, row in enumerate(worksheet.iter_rows(), start=1):

        month_cells = [
            (cell.column, cell.value.strip().title())
            for cell in row
            if isinstance(cell.value, str)
            and cell.value.strip().title() in MONTH_NUMBERS
        ]

        if month_cells:
            months[row_number] = month_cells

    if not months:
        raise ValueError("No month headings found in the Excel calendar")

    return months


def get_calendar_date(cell, month_headers):

    """Return a cell date, reconstructing day-only Excel values from month headings."""

    if not isinstance(cell.value, (date, datetime)):
        raise ValueError(f"Unexpected calendar date value: {cell.value!r}")

    if cell.value.year != 1900:
        return (
            cell.value.date()
            if isinstance(cell.value, datetime)
            else cell.value
        )

    preceding_rows = [
        row_number
        for row_number in month_headers
        if row_number < cell.row
    ]

    if not preceding_rows:
        raise ValueError(
            f"No month heading found above Excel cell {cell.coordinate}"
        )

    header_row = max(preceding_rows)

    preceding_months = [
        entry
        for entry in month_headers[header_row]
        if entry[0] <= cell.column
    ]

    if not preceding_months:
        raise ValueError(
            f"No month heading found to the left of Excel cell {cell.coordinate}"
        )

    month_name = max(
        preceding_months
        ,key=lambda entry: entry[0]
    )[1]

    month_number = MONTH_NUMBERS[month_name]
    year_start = int(ACADEMIC_YEAR[:4])

    calendar_year = (
        year_start
        if month_number >= ACADEMIC_YEAR_START_MONTH
        else year_start + 1
    )

    return date(calendar_year, month_number, cell.value.day)


def consolidate_dates(dates):

    """Group consecutive dates, bridging only the Friday-to-Monday weekend gap."""

    if not dates:
        return []

    dates = sorted(set(dates))

    periods = []
    period_start = dates[0]
    period_end = dates[0]

    for current_date in dates[1:]:

        difference = (current_date - period_end).days

        is_weekend_gap = (
            difference == 3
            and period_end.weekday() == 4
            and current_date.weekday() == 0
        )

        if difference == 1 or is_weekend_gap:
            period_end = current_date

        else:
            periods.append((period_start, period_end))
            period_start = current_date
            period_end = current_date

    periods.append((period_start, period_end))

    return periods


def format_date_range(start_date, end_date):

    """Format a date period using weekday and month names."""

    def format_date(value):
        return (
            f"{value.strftime('%A')} "
            f"{value.day} "
            f"{value.strftime('%B %Y')}"
        )

    if start_date == end_date:
        return format_date(start_date)

    return f"{format_date(start_date)} to {format_date(end_date)}"


def parse_date_range(raw_date_text, academic_year):

    """Parse the first and last dates in a published date range."""

    matches = list(DATE_PATTERN.finditer(raw_date_text))

    if not matches:
        raise ValueError(
            f"Could not parse Buckinghamshire date text: {raw_date_text!r}"
        )

    year_start = int(academic_year[:4])
    parsed_dates = []

    for match in matches:

        day = int(match.group(1))
        month_name = match.group(2).title()
        month_number = MONTH_NUMBERS[month_name]

        year = (
            int(match.group(3))
            if match.group(3)
            else year_start if month_number >= ACADEMIC_YEAR_START_MONTH
            else year_start + 1
        )

        parsed_dates.append(date(year, month_number, day))

    start_date = parsed_dates[0]
    end_date = parsed_dates[-1]

    if start_date > end_date:
        raise ValueError(
            f"Reversed date range: {raw_date_text!r}"
        )

    validate_academic_year_dates(
        parsed_dates
        ,academic_year
        ,"Webpage date range"
    )

    return start_date, end_date


def merge_calendar_coverage(calendar_records):

    """Merge calendar date periods for overlap checks, including weekend-only gaps."""

    intervals = sorted(
        (record["_START_DATE"], record["_END_DATE"])
        for record in calendar_records
    )

    if not intervals:
        return []

    coverage = []
    coverage_start, coverage_end = intervals[0]

    for current_start, current_end in intervals[1:]:

        difference = (current_start - coverage_end).days

        is_weekend_gap = (
            difference == 3
            and coverage_end.weekday() == 4
            and current_start.weekday() == 0
        )

        if difference <= 1 or is_weekend_gap:
            coverage_end = max(coverage_end, current_end)

        else:
            coverage.append((coverage_start, coverage_end))
            coverage_start = current_start
            coverage_end = current_end

    coverage.append((coverage_start, coverage_end))

    return coverage


def subtract_calendar_coverage(start_date, end_date, coverage):

    """Return parts of a webpage date range not already supplied by calendars."""

    uncovered_periods = [(start_date, end_date)]

    for covered_start, covered_end in coverage:

        remaining_periods = []

        for period_start, period_end in uncovered_periods:

            if covered_end < period_start or covered_start > period_end:
                remaining_periods.append((period_start, period_end))
                continue

            if period_start < covered_start:
                remaining_periods.append((
                    period_start
                    ,covered_start - timedelta(days=1)
                ))

            if covered_end < period_end:
                remaining_periods.append((
                    covered_end + timedelta(days=1)
                    ,period_end
                ))

        uncovered_periods = remaining_periods

        if not uncovered_periods:
            break

    return uncovered_periods


def validate_category_dates(category_dates, academic_year, description):

    """Validate category dates, allowing inset days to overlap term days."""

    date_categories = defaultdict(set)

    for event_name, dates in category_dates.items():

        validate_academic_year_dates(
            dates
            ,academic_year
            ,description
        )

        for calendar_date in dates:
            date_categories[calendar_date].add(event_name)

    conflicting_dates = {}

    for calendar_date, categories in date_categories.items():

        # Inset days can legitimately occur within term periods.
        if categories == {"Inset Day", "Term Day"}:
            continue

        if len(categories) > 1:
            conflicting_dates[calendar_date] = sorted(categories)

    if conflicting_dates:
        raise ValueError(
            f"{description} contains dates assigned to conflicting categories: "
            f"{conflicting_dates}"
        )


def make_calendar_record(event_name, academic_year, start_date, end_date, date_scraped):

    """Create a standard record with internal date bounds for merging."""

    return {
        "SOURCE_ID": SOURCE_ID
        ,"ACADEMIC_YEAR": academic_year
        ,"EVENT_NAME": event_name
        ,"RAW_DATE_TEXT": format_date_range(start_date, end_date)
        ,"DATE_SCRAPED": date_scraped
        ,"_START_DATE": start_date
        ,"_END_DATE": end_date
    }



# ----------------------------------------- Excel Extraction ---------------------------------------

def extract_calendar_records(workbook_content, date_scraped):

    """Extract coloured calendar dates from the 2025/26 Excel calendar."""

    workbook = load_workbook(
        BytesIO(workbook_content)
        ,data_only=True
        ,read_only=False
    )

    try:
        worksheet = workbook.active

        category_fills = find_calendar_categories(worksheet)
        month_headers = find_month_headers(worksheet)

        category_dates = defaultdict(set)

        for row in worksheet.iter_rows():

            for cell in row:

                if not isinstance(cell.value, (date, datetime)):
                    continue

                event_name = category_fills.get(get_fill_signature(cell))

                if event_name is None:
                    continue

                calendar_date = get_calendar_date(cell, month_headers)
                category_dates[event_name].add(calendar_date)

    finally:
        workbook.close()

    validate_category_dates(
        category_dates
        ,ACADEMIC_YEAR
        ,"Excel calendar"
    )

    required_categories = {"Bank Holiday", "Holiday Day", "Term Day"}

    missing_categories = required_categories.difference(category_dates)

    if missing_categories:
        raise ValueError(
            f"Excel calendar has no dates for required categories: "
            f"{sorted(missing_categories)}"
        )

    records = []

    for event_name, dates in category_dates.items():

        for period_start, period_end in consolidate_dates(dates):

            records.append(
                make_calendar_record(
                    event_name
                    ,ACADEMIC_YEAR
                    ,period_start
                    ,period_end
                    ,date_scraped
                )
            )

    print("  Excel calendar extraction:")

    for event_name in sorted(category_dates):
        print(f"    {event_name}: {len(category_dates[event_name])} dates")

    print(f"    Calendar records: {len(records)}")

    return records



# ------------------------------------------ PDF Extraction ----------------------------------------

def find_pdf_calendar_links(soup, page_url):

    """Return academic-year and PDF URL pairs linked from the council page."""

    calendar_links = {}

    for link in soup.find_all("a", href=True):

        link_text = " ".join((
            link.get_text(" ", strip=True)
            ,str(link.get("title", ""))
        ))

        href = str(link["href"])

        year_match = PDF_LINK_YEAR_PATTERN.search(link_text)

        if year_match is None:
            year_match = PDF_LINK_YEAR_PATTERN.search(href)

        if year_match is None:
            continue

        start_year = int(year_match.group(1))
        end_year = int(year_match.group(2))

        if end_year != start_year + 1:
            continue

        academic_year = f"{start_year}/{str(end_year)[-2:]}"

        if academic_year not in SUPPORTED_PDF_YEARS:
            continue

        pdf_url = urljoin(page_url, href)

        if (
            academic_year in calendar_links
            and calendar_links[academic_year] != pdf_url
        ):
            raise ValueError(
                f"Multiple different PDF links found for {academic_year}"
            )

        calendar_links[academic_year] = pdf_url

    return list(sorted(calendar_links.items()))


def match_pdf_event_color(actual_color, expected_color, tolerance=PDF_COLOR_TOLERANCE):

    """Compare PDF fill colours with a small tolerance."""

    if isinstance(expected_color, (int, float)):
        if not isinstance(actual_color, (int, float)):
            return False

        return abs(float(actual_color) - float(expected_color)) <= tolerance

    if not isinstance(actual_color, (tuple, list)) or len(actual_color) != 3:
        return False

    return all(
        abs(float(actual) - float(expected)) <= tolerance
        for actual, expected in zip(actual_color, expected_color)
    )


def identify_pdf_event_color(actual_color, academic_year):

    """Identify a recognised calendar category from a PDF fill colour."""

    event_colors = PDF_EVENT_COLORS[academic_year]

    for expected_color, event_name in event_colors.items():

        if match_pdf_event_color(actual_color, expected_color):
            return event_name

    if match_pdf_event_color(
        actual_color
        ,PDF_TERM_COLORS[academic_year]
    ):
        return "Term Day"

    return None


def find_pdf_month_groups(page, academic_year):

    """Identify and validate the 12 month headings in the PDF calendar."""

    month_headers = []

    for word in page.extract_words():

        month_name = word["text"].title()
        month_number = MONTH_NUMBERS.get(month_name)

        if month_number is None:
            continue

        year_start = int(academic_year[:4])

        year = (
            year_start
            if month_number >= ACADEMIC_YEAR_START_MONTH
            else year_start + 1
        )

        month_headers.append({
            "MONTH": month_name
            ,"NUMBER": month_number
            ,"YEAR": year
            ,"X": (word["x0"] + word["x1"]) / 2
            ,"TOP": word["top"]
        })

    # Group headings into horizontal rows.
    month_groups = []

    for header in sorted(month_headers, key=lambda item: item["TOP"]):

        if (
            not month_groups
            or abs(header["TOP"] - month_groups[-1][0]["TOP"]) > 5
        ):
            month_groups.append([header])

        else:
            month_groups[-1].append(header)

    # Sort each row from left to right.
    for group in month_groups:
        group.sort(key=lambda item: item["X"])

    ordered_months = [
        header["MONTH"]
        for group in month_groups
        for header in group
    ]

    if len(ordered_months) != 12:
        raise ValueError(
            f"Expected 12 PDF month headings for {academic_year}; "
            f"found {len(ordered_months)}: {ordered_months}"
        )

    if ordered_months != EXPECTED_MONTHS:
        raise ValueError(
            f"Unexpected PDF month sequence for {academic_year}: "
            f"{ordered_months}"
        )

    if any(len(group) != 4 for group in month_groups):
        raise ValueError(
            f"Expected four month headings per PDF row for {academic_year}"
        )

    return month_groups


def find_pdf_month_for_date(word_center_x, word_center_y, month_groups):

    """Assign a date number to the month column above its calendar position."""

    preceding_rows = [
        group
        for group in month_groups
        if group[0]["TOP"] <= word_center_y
    ]

    if not preceding_rows:
        return None

    month_row = preceding_rows[-1]

    # Derive horizontal column boundaries from adjacent month-heading centres.
    boundaries = []

    for index, header in enumerate(month_row):

        left_boundary = (
            float("-inf")
            if index == 0
            else (month_row[index - 1]["X"] + header["X"]) / 2
        )

        right_boundary = (
            float("inf")
            if index == len(month_row) - 1
            else (header["X"] + month_row[index + 1]["X"]) / 2
        )

        boundaries.append((left_boundary, right_boundary, header))

    matching_headers = [
        header
        for left_boundary, right_boundary, header in boundaries
        if left_boundary <= word_center_x < right_boundary
    ]

    if len(matching_headers) != 1:
        return None

    return matching_headers[0]


def find_pdf_date_event(word_center_x, word_center_y, page, academic_year):

    """Find the smallest recognised coloured rectangle containing a date number."""

    matching_rectangles = []

    for rectangle in page.rects:

        if not (
            rectangle["x0"] <= word_center_x <= rectangle["x1"]
            and rectangle["top"] <= word_center_y <= rectangle["bottom"]
        ):
            continue

        event_name = identify_pdf_event_color(
            rectangle.get("non_stroking_color")
            ,academic_year
        )

        if event_name is None:
            continue

        area = (
            (rectangle["x1"] - rectangle["x0"])
            * (rectangle["bottom"] - rectangle["top"])
        )

        matching_rectangles.append((area, event_name))

    if not matching_rectangles:
        return None

    matching_rectangles.sort(key=lambda item: item[0])

    smallest_area = matching_rectangles[0][0]

    equally_small = {
        event_name
        for area, event_name in matching_rectangles
        if abs(area - smallest_area) < 0.01
    }

    if len(equally_small) > 1:
        raise ValueError(
            f"Date cell has conflicting PDF category colours: {sorted(equally_small)}"
        )

    return matching_rectangles[0][1]


def extract_pdf_calendar(pdf_content, academic_year, date_scraped):

    """Extract and validate colour-coded calendar dates from a Buckinghamshire PDF."""

    if academic_year not in PDF_EVENT_COLORS:
        raise ValueError(
            f"No PDF calendar colour mapping is configured for {academic_year}"
        )

    with pdfplumber.open(BytesIO(pdf_content)) as calendar_pdf:

        category_dates = defaultdict(set)
        recognised_date_cells = 0
        unclassified_date_cells = 0

        for page_number, page in enumerate(calendar_pdf.pages, start=1):

            print(f"  Processing PDF page {page_number}")

            month_groups = find_pdf_month_groups(
                page
                ,academic_year
            )

            for word in page.extract_words():

                if not re.fullmatch(r"\d{1,2}", word["text"]):
                    continue

                day_number = int(word["text"])

                if not 1 <= day_number <= 31:
                    continue

                word_center_x = (word["x0"] + word["x1"]) / 2
                word_center_y = (word["top"] + word["bottom"]) / 2

                month_header = find_pdf_month_for_date(
                    word_center_x
                    ,word_center_y
                    ,month_groups
                )

                if month_header is None:
                    continue

                try:
                    calendar_date = date(
                        month_header["YEAR"]
                        ,month_header["NUMBER"]
                        ,day_number
                    )

                except ValueError:
                    continue

                event_name = find_pdf_date_event(
                    word_center_x
                    ,word_center_y
                    ,page
                    ,academic_year
                )

                if event_name is None:
                    unclassified_date_cells += 1
                    continue

                category_dates[event_name].add(calendar_date)
                recognised_date_cells += 1

        for word in page.extract_words():

            if not re.fullmatch(r"\d{1,2}", word["text"]):
                continue

            day_number = int(word["text"])

            if not 1 <= day_number <= 31:
                continue

            word_center_x = (word["x0"] + word["x1"]) / 2
            word_center_y = (word["top"] + word["bottom"]) / 2

            month_header = find_pdf_month_for_date(
                word_center_x
                ,word_center_y
                ,month_groups
            )

            if month_header is None:
                continue

            try:
                calendar_date = date(
                    month_header["YEAR"]
                    ,month_header["NUMBER"]
                    ,day_number
                )

            except ValueError:
                continue

            event_name = find_pdf_date_event(
                word_center_x
                ,word_center_y
                ,page
                ,academic_year
            )

            if event_name is None:
                unclassified_date_cells += 1
                continue

            category_dates[event_name].add(calendar_date)
            recognised_date_cells += 1

    validate_category_dates(
        category_dates
        ,academic_year
        ,"PDF calendar"
    )

    # These categories should always be present in a complete calendar.
    required_categories = {"School Holiday", "Bank Holiday", "Term Day"}

    missing_categories = required_categories.difference(category_dates)

    if missing_categories:
        raise ValueError(
            f"PDF calendar {academic_year} is missing required categories: "
            f"{sorted(missing_categories)}"
        )

    all_dates = set().union(*category_dates.values())

    if not all_dates:
        raise ValueError(
            f"No calendar dates were extracted for {academic_year}"
        )

    validate_academic_year_dates(
        all_dates
        ,academic_year
        ,"PDF calendar"
    )

    records = []

    for event_name, dates in category_dates.items():

        for period_start, period_end in consolidate_dates(dates):

            records.append(
                make_calendar_record(
                    event_name
                    ,academic_year
                    ,period_start
                    ,period_end
                    ,date_scraped
                )
            )

    print(f"  PDF calendar extraction: {academic_year}")

    for event_name in sorted(category_dates):
        print(
            f"    {event_name}: "
            f"{len(category_dates[event_name])} dates"
        )

    print(f"    Calendar date cells matched: {recognised_date_cells}")
    print(f"    Unclassified date cells: {unclassified_date_cells}")
    print(f"    Calendar records: {len(records)}")

    return records



# ------------------------------------------- Webpage Extraction -----------------------------------

def extract_webpage_records(soup):

    """Extract school-term and holiday date ranges from the council webpage."""

    website_records = []

    for heading in soup.find_all(["h2", "h3"]):

        heading_text = heading.get_text(" ", strip=True)
        term_match = TERM_PATTERN.search(heading_text)

        if term_match is None:
            continue

        term_name = term_match.group(1).title()
        term_year = int(term_match.group(2))

        year_start = (
            term_year
            if term_name == "Autumn"
            else term_year - 1
        )

        academic_year = f"{year_start}/{str(year_start + 1)[-2:]}"

        for element in heading.next_elements:

            if (
                element is not heading
                and getattr(element, "name", None) in ["h2", "h3"]
            ):
                break

            if getattr(element, "name", None) != "table":
                continue

            for row in element.find_all("tr"):

                cells = row.find_all(["th", "td"])

                if len(cells) < 2:
                    continue

                event_label = cells[0].get_text(" ", strip=True)
                raw_date_text = cells[1].get_text(" ", strip=True)

                if not event_label or not raw_date_text:
                    continue

                if event_label.lower() in ["starts", "half term", "ends"]:
                    event_name = f"{term_name} {event_label.lower()}"

                else:
                    event_name = event_label

                # Validate the source date range without changing its published wording.
                parse_date_range(
                    raw_date_text
                    ,academic_year
                )

                website_records.append({
                    "SOURCE_ID": SOURCE_ID
                    ,"ACADEMIC_YEAR": academic_year
                    ,"EVENT_NAME": event_name
                    ,"RAW_DATE_TEXT": raw_date_text
                    ,"DATE_SCRAPED": datetime.now(timezone.utc).date()
                })

            break

    if not website_records:
        raise ValueError("No school-term records were extracted from the webpage")

    return website_records



# ------------------------------------------- Main Code --------------------------------------------

def scrape_buckinghamshire():

    """
    Retrieve webpage dates and linked Excel/PDF calendars.

    Calendar records take precedence over webpage dates on overlapping dates.
    Webpage-only portions are retained.

    Returns
    -------
    pandas.DataFrame
        Merged school-term and holiday events using the standard scraper output columns.
    """

    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    response = requests.get(
        source_url
        ,headers=HEADERS
        ,timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    date_scraped = datetime.now(timezone.utc).date()

    website_records = extract_webpage_records(soup)

    # ------------------------------------------ Excel Calendar -------------------------------------

    calendar_link = soup.find(
        "a"
        ,href=CALENDAR_LINK_PATTERN
    )

    if calendar_link is None:
        raise ValueError(
            f"Could not find the {CALENDAR_FILENAME} link on {source_url}"
        )

    calendar_url = urljoin(source_url, calendar_link["href"])

    calendar_response = requests.get(
        calendar_url
        ,headers=HEADERS
        ,timeout=30
    )

    calendar_response.raise_for_status()

    if not calendar_response.content.startswith(b"PK"):
        raise ValueError(
            f"The council Excel link did not return an Excel workbook: {calendar_url}"
        )

    calendar_records = extract_calendar_records(
        calendar_response.content
        ,date_scraped
    )

    # ------------------------------------------- PDF Calendars -------------------------------------

    pdf_calendar_records = []

    for academic_year, pdf_url in find_pdf_calendar_links(soup, source_url):

        try:
            pdf_response = requests.get(
                pdf_url
                ,headers=HEADERS
                ,timeout=30
            )

            pdf_response.raise_for_status()

            if not pdf_response.content.startswith(b"%PDF-"):
                raise ValueError(
                    f"The council link for {academic_year} did not return a PDF file"
                )

            extracted_records = extract_pdf_calendar(
                pdf_response.content
                ,academic_year
                ,date_scraped
            )

            # Only accept the PDF records after the extraction function has completed
            # all its structural and date validations.
            if not extracted_records:
                raise ValueError(
                    f"No records extracted from the PDF for {academic_year}"
                )

            pdf_calendar_records.extend(extracted_records)

        except Exception as error:
            print(
                f"Could not extract PDF for {academic_year}: "
                f"{type(error).__name__}: {error}"
            )

    # ------------------------------------------- Merge Records -------------------------------------

    calendar_records.extend(pdf_calendar_records)

    # All calendar categories contribute to coverage, including Term Day.
    # Calendar records therefore replace webpage event labels on overlapping dates.
    calendar_coverage = merge_calendar_coverage(calendar_records)

    resolved_website_records = []

    for record in website_records:

        range_start, range_end = parse_date_range(
            record["RAW_DATE_TEXT"]
            ,record["ACADEMIC_YEAR"]
        )

        uncovered_periods = subtract_calendar_coverage(
            range_start
            ,range_end
            ,calendar_coverage
        )

        for period_start, period_end in uncovered_periods:

            resolved_record = record.copy()

            resolved_record["RAW_DATE_TEXT"] = format_date_range(
                period_start
                ,period_end
            )

            resolved_website_records.append(resolved_record)

    records = calendar_records + resolved_website_records

    # ------------------------------------------ Final Validation -----------------------------------

    if not records:
        raise ValueError("No Buckinghamshire school-holiday records were produced")

    record_keys = [
        (
            record["SOURCE_ID"]
            ,record["ACADEMIC_YEAR"]
            ,record["EVENT_NAME"]
            ,record["RAW_DATE_TEXT"]
        )
        for record in records
    ]

    if len(record_keys) != len(set(record_keys)):
        raise ValueError("Duplicate Buckinghamshire output records detected")

    records.sort(
        key=lambda record: (
            record.get(
                "_START_DATE"
                ,parse_date_range(
                    record["RAW_DATE_TEXT"]
                    ,record["ACADEMIC_YEAR"]
                )[0]
            )
            ,record["EVENT_NAME"]
        )
    )

    # ------------------------------------------ Summary --------------------------------------------

    print("\nBuckinghamshire extraction summary:")

    for academic_year in sorted({
        record["ACADEMIC_YEAR"]
        for record in records
    }):

        year_records = [
            record for record in records
            if record["ACADEMIC_YEAR"] == academic_year
        ]

        calendar_count = sum(
            1 for record in year_records
            if "_START_DATE" in record
        )

        webpage_count = len(year_records) - calendar_count

        print(
            f"  {academic_year}: "
            f"{len(year_records)} records "
            f"({calendar_count} calendar, {webpage_count} webpage)"
        )

    # ------------------------------------------ Output ----------------------------------------------

    for record in records:
        record.pop("_START_DATE", None)
        record.pop("_END_DATE", None)

    return pd.DataFrame.from_records(
        records
        ,columns=OUTPUT_COLUMNS
    )
