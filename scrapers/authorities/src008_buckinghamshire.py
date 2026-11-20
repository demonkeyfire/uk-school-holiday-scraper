# -------------------------------------------- Overview --------------------------------------------

# Retrieve Buckinghamshire school-term dates from the council webpage and its linked Excel calendar.
# Calendar events take precedence on overlapping dates; uncovered webpage dates are retained.



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

TERM_PATTERN = re.compile(r"(Autumn|Spring|Summer)\s+term\s+(\d{4})", re.IGNORECASE)
CALENDAR_LINK_PATTERN = re.compile(re.escape(CALENDAR_FILENAME) + r"(?:\?|$)", re.IGNORECASE)
PDF_LINK_YEAR_PATTERN = re.compile(
    r"(20\d{2})[\s_-]*(?:to|/|-|_)[\s_-]*(20\d{2})",
    re.IGNORECASE
)
PDF_EVENT_COLORS = {
    "2026/27": {
        (1.0, 0.902, 0.6): "School Holiday",
        (0.408, 0.478, 0.988): "Bank Holiday",
        (1.0, 1.0, 0.0): "Inset Day",
        (0.635, 0.949, 0.941): "Transition Day",
    },
    "2027/28": {
        (0.518, 0.886, 0.565): "School Holiday",
        (0.898, 0.62, 0.863): "Bank Holiday",
        (0.918, 0.196, 0.78): "Inset Day",
        (0.278, 0.831, 0.349): "Transition Day",
    },
}
DATE_PATTERN = re.compile(
    r"\b(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?"
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+(\d{4}))?\b"
    ,re.IGNORECASE)

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
                ,"December"  : 12}



# ------------------------------------------- Helper Functions -------------------------------------

def get_fill_signature(cell):

    """Return a comparable description of a cell's fill colour."""

    colour = cell.fill.fgColor
    colour_value = getattr(colour, colour.type)

    return (cell.fill.fill_type
           ,colour.type
           ,colour_value
           ,colour.tint)


def find_calendar_categories(worksheet):

    """Map the workbook's legend fill colours to their displayed category names."""

    categories = {}

    for row in worksheet.iter_rows():

        for cell in row:

            if not isinstance(cell.value, str) or cell.value.strip() not in CATEGORY_NAMES:
                continue

            legend_cell = worksheet.cell(row = cell.row, column = cell.column - 1)
            categories[get_fill_signature(legend_cell)] = cell.value.strip()

    missing_categories = CATEGORY_NAMES.difference(categories.values())

    if missing_categories:
        raise ValueError(f"Calendar legend is missing categories: {sorted(missing_categories)}")

    return categories


def find_month_headers(worksheet):

    """Collect the calendar month headings and their positions."""

    months = {}

    for row_number, row in enumerate(worksheet.iter_rows(), start = 1):

        month_cells = [(cell.column, cell.value.strip())
                       for cell in row
                       if isinstance(cell.value, str) and cell.value.strip() in MONTH_NUMBERS]

        if month_cells:
            months[row_number] = month_cells

    return months


def get_calendar_date(cell, month_headers):

    """Return a cell date, reconstructing day-only Excel values from its month heading."""

    if cell.value.year != 1900:
        return cell.value.date() if isinstance(cell.value, datetime) else cell.value

    header_row = max(row_number for row_number in month_headers if row_number < cell.row)
    month_name = max(
        (entry for entry in month_headers[header_row] if entry[0] <= cell.column)
        ,key = lambda entry: entry[0])[1]
    month_number = MONTH_NUMBERS[month_name]
    year_start = int(ACADEMIC_YEAR[:4])
    calendar_year = year_start if month_number >= 9 else year_start + 1

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
        is_weekend_gap = (difference == 3
                          and period_end.weekday() == 4
                          and current_date.weekday() == 0)

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
        return f"{value.strftime('%A')} {value.day} {value.strftime('%B %Y')}"

    if start_date == end_date:
        return format_date(start_date)

    return f"{format_date(start_date)} to {format_date(end_date)}"


def parse_date_range(raw_date_text, academic_year):

    """Parse the first and last dates in a published date range."""

    matches = list(DATE_PATTERN.finditer(raw_date_text))

    if not matches:
        raise ValueError(f"Could not parse Buckinghamshire date text: {raw_date_text!r}")

    year_start = int(academic_year[:4])
    parsed_dates = []

    for match in matches:

        day = int(match.group(1))
        month_name = match.group(2).title()
        month_number = MONTH_NUMBERS[month_name]
        year = (int(match.group(3))
                if match.group(3)
                else year_start if month_number >= 9 else year_start + 1)
        parsed_dates.append(date(year, month_number, day))

    return parsed_dates[0], parsed_dates[-1]


def merge_calendar_coverage(calendar_records):

    """Merge calendar date periods for overlap checks, including weekend-only gaps."""

    intervals = sorted((record["_START_DATE"], record["_END_DATE"])
                       for record in calendar_records)

    if not intervals:
        return []

    coverage = []
    coverage_start, coverage_end = intervals[0]

    for current_start, current_end in intervals[1:]:

        difference = (current_start - coverage_end).days
        is_weekend_gap = (difference == 3
                          and coverage_end.weekday() == 4
                          and current_start.weekday() == 0)

        if difference <= 1 or is_weekend_gap:
            coverage_end = max(coverage_end, current_end)
        else:
            coverage.append((coverage_start, coverage_end))
            coverage_start = current_start
            coverage_end = current_end

    coverage.append((coverage_start, coverage_end))

    return coverage


def subtract_calendar_coverage(start_date, end_date, coverage):

    """Return the parts of a website date range not already supplied by the calendar."""

    uncovered_periods = [(start_date, end_date)]

    for covered_start, covered_end in coverage:

        remaining_periods = []

        for period_start, period_end in uncovered_periods:

            if covered_end < period_start or covered_start > period_end:
                remaining_periods.append((period_start, period_end))
                continue

            if period_start < covered_start:
                remaining_periods.append((period_start, covered_start - timedelta(days = 1)))

            if covered_end < period_end:
                remaining_periods.append((covered_end + timedelta(days = 1), period_end))

        uncovered_periods = remaining_periods

        if not uncovered_periods:
            break

    return uncovered_periods


def extract_calendar_records(workbook_content, date_scraped):

    """Extract colored calendar dates as standard records with private interval bounds."""

    workbook = load_workbook(BytesIO(workbook_content), data_only = True, read_only = False)

    try:
        worksheet = workbook.active
        category_fills = find_calendar_categories(worksheet)
        month_headers = find_month_headers(worksheet)
        category_dates = defaultdict(list)

        for row in worksheet.iter_rows():

            for cell in row:

                if not isinstance(cell.value, (date, datetime)):
                    continue

                event_name = category_fills.get(get_fill_signature(cell))

                if event_name is None:
                    continue

                category_dates[event_name].append(get_calendar_date(cell, month_headers))

    finally:
        workbook.close()

    records = []

    for event_name, dates in category_dates.items():

        for period_start, period_end in consolidate_dates(dates):

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : ACADEMIC_YEAR
                           ,"EVENT_NAME"    : event_name
                           ,"RAW_DATE_TEXT" : format_date_range(period_start, period_end)
                           ,"DATE_SCRAPED"  : date_scraped
                           ,"_START_DATE"  : period_start
                           ,"_END_DATE"    : period_end})

    return records


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
        academic_year = f"{start_year}/{str(end_year)[-2:]}"

        if academic_year not in ("2026/27", "2027/28"):
            continue

        pdf_url = urljoin(page_url, href)

        if academic_year in calendar_links and calendar_links[academic_year] != pdf_url:
            raise ValueError(f"Multiple different PDF links found for {academic_year}")

        calendar_links[academic_year] = pdf_url

    return list(calendar_links.items())


def match_pdf_event_color(actual_color, expected_color, tolerance=0.02):

    """Compare PDF fill colors with a small tolerance."""

    if isinstance(actual_color, (int, float)) and isinstance(expected_color, (int, float)):
        return abs(float(actual_color) - float(expected_color)) <= tolerance

    if isinstance(expected_color, (int, float)):
        return False

    if not isinstance(actual_color, (tuple, list)) or len(actual_color) != 3:
        return False

    return all(
        abs(float(actual) - float(expected)) <= tolerance
        for actual, expected in zip(actual_color, expected_color)
    )


def extract_pdf_calendar(pdf_content, academic_year, date_scraped):

    """Extract color-coded calendar dates from a Buckinghamshire PDF."""

    event_colors = PDF_EVENT_COLORS.get(academic_year)

    if event_colors is None:
        raise ValueError(f"No PDF calendar color mapping is configured for {academic_year}")

    # The Term Day colors differ from the holiday categories and are stable per PDF layout.
    term_colors = {
        "2026/27": (0.706, 0.776, 0.906),
        "2027/28": (0.514, 0.792, 0.922),
    }

    with pdfplumber.open(BytesIO(pdf_content)) as calendar_pdf:
        if not calendar_pdf.pages:
            raise ValueError(f"The PDF for {academic_year} contains no pages")

        page = calendar_pdf.pages[0]
        month_headers = []

        for word in page.extract_words():
            month_name = word["text"].title()
            month_number = MONTH_NUMBERS.get(month_name)

            if month_number is None:
                continue

            year_start = int(academic_year[:4])
            year = year_start if month_number >= 9 else year_start + 1
            month_headers.append({
                "MONTH": month_name,
                "NUMBER": month_number,
                "YEAR": year,
                "X": (word["x0"] + word["x1"]) / 2,
                "TOP": word["top"],
            })

        month_groups = []

        for header in sorted(month_headers, key=lambda item: item["TOP"]):
            if not month_groups or abs(header["TOP"] - month_groups[-1][0]["TOP"]) > 5:
                month_groups.append([header])
            else:
                month_groups[-1].append(header)

        category_dates = defaultdict(set)

        for word in page.extract_words():
            if not re.fullmatch(r"\d{1,2}", word["text"]):
                continue

            word_center_x = (word["x0"] + word["x1"]) / 2
            word_center_y = (word["top"] + word["bottom"]) / 2

            month_row = [
                group for group in month_groups
                if group[0]["TOP"] <= word_center_y
            ]

            if not month_row:
                continue

            month_header = min(
                month_row[-1],
                key=lambda item: abs(item["X"] - word_center_x)
            )

            try:
                calendar_date = date(
                    month_header["YEAR"]
                    ,month_header["NUMBER"]
                    ,int(word["text"])
                )
            except ValueError:
                continue

            for rectangle in page.rects:
                if not (
                    rectangle["x0"] <= word_center_x <= rectangle["x1"]
                    and rectangle["top"] <= word_center_y <= rectangle["bottom"]
                ):
                    continue

                actual_color = rectangle.get("non_stroking_color")

                event_name = next((
                    name for color, name in event_colors.items()
                    if match_pdf_event_color(actual_color, color)
                ), None)

                if event_name is None:
                    if match_pdf_event_color(actual_color, term_colors[academic_year]):
                        event_name = "Term Day"

                if event_name is not None:
                    category_dates[event_name].add(calendar_date)

                break

    records = []

    for event_name, dates in category_dates.items():
        for period_start, period_end in consolidate_dates(sorted(dates)):
            records.append({
                "SOURCE_ID": SOURCE_ID
                ,"ACADEMIC_YEAR": academic_year
                ,"EVENT_NAME": event_name
                ,"RAW_DATE_TEXT": format_date_range(period_start, period_end)
                ,"DATE_SCRAPED": date_scraped
                ,"_START_DATE": period_start
                ,"_END_DATE": period_end
            })

    return records



# ------------------------------------------- Main Code --------------------------------------------

def scrape_buckinghamshire():

    """
    Retrieve webpage dates and the color-coded dates from its linked 2025/26 calendar.

    The calendar is authoritative when a website date overlaps it. Website-only portions are
    retained as date ranges, preventing duplicate coverage while keeping uncaptured dates.

    Returns
    -------
    pandas.DataFrame
        Merged school-term and holiday events using the standard scraper output columns.
    """

    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]
    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    date_scraped = datetime.now(timezone.utc).date()
    website_records = []

    for heading in soup.find_all(["h2", "h3"]):

        heading_text = heading.get_text(" ", strip = True)
        term_match = TERM_PATTERN.search(heading_text)

        if term_match is None:
            continue

        term_name = term_match.group(1).title()
        term_year = int(term_match.group(2))
        year_start = term_year if term_name == "Autumn" else term_year - 1
        academic_year = f"{year_start}/{str(year_start + 1)[-2:]}"

        for element in heading.next_elements:

            if element is not heading and getattr(element, "name", None) in ["h2", "h3"]:
                break

            if getattr(element, "name", None) != "table":
                continue

            for row in element.find_all("tr"):

                cells = row.find_all(["th", "td"])

                if len(cells) < 2:
                    continue

                event_label = cells[0].get_text(" ", strip = True)
                raw_date_text = cells[1].get_text(" ", strip = True)

                if not event_label or not raw_date_text:
                    continue

                if event_label.lower() in ["starts", "half term", "ends"]:
                    event_name = f"{term_name} {event_label.lower()}"
                else:
                    event_name = event_label

                website_records.append({"SOURCE_ID"     : SOURCE_ID
                                       ,"ACADEMIC_YEAR" : academic_year
                                       ,"EVENT_NAME"    : event_name
                                       ,"RAW_DATE_TEXT" : raw_date_text
                                       ,"DATE_SCRAPED"  : date_scraped})

            break

    calendar_link = soup.find("a", href = CALENDAR_LINK_PATTERN)

    if calendar_link is None:
        raise ValueError(f"Could not find the {CALENDAR_FILENAME} link on {source_url}")

    calendar_url = urljoin(source_url, calendar_link["href"])
    calendar_response = requests.get(calendar_url
                                    ,headers = HEADERS
                                    ,timeout = 30)
    calendar_response.raise_for_status()
    calendar_records = extract_calendar_records(calendar_response.content, date_scraped)
    pdf_calendar_records = []

    for academic_year, pdf_url in find_pdf_calendar_links(soup, source_url):

        try:
            pdf_response = requests.get(pdf_url
                                       ,headers = HEADERS
                                       ,timeout = 30)
            pdf_response.raise_for_status()

            if not pdf_response.content.startswith(b"%PDF-"):
                raise ValueError(
                    f"The council link for {academic_year} did not return a PDF file"
                )

            pdf_calendar_records.extend(
                extract_pdf_calendar(pdf_response.content
                                    ,academic_year
                                    ,date_scraped)
            )

        except Exception as error:
            print(
                f"Could not extract PDF for {academic_year}: "
                f"{type(error).__name__}: {error}"
            )

    calendar_records.extend(pdf_calendar_records)
    calendar_coverage = merge_calendar_coverage(calendar_records)
    resolved_website_records = []

    for record in website_records:

        range_start, range_end = parse_date_range(record["RAW_DATE_TEXT"]
                                                 ,record["ACADEMIC_YEAR"])
        uncovered_periods = subtract_calendar_coverage(range_start
                                                     ,range_end
                                                     ,calendar_coverage)

        for period_start, period_end in uncovered_periods:

            resolved_record = record.copy()
            resolved_record["RAW_DATE_TEXT"] = format_date_range(period_start, period_end)
            resolved_website_records.append(resolved_record)

    records = calendar_records + resolved_website_records
    records.sort(key = lambda record: (record.get("_START_DATE")
                                       or parse_date_range(record["RAW_DATE_TEXT"]
                                                           ,record["ACADEMIC_YEAR"])[0]
                                       ,record["EVENT_NAME"]))

    for record in records:
        record.pop("_START_DATE", None)
        record.pop("_END_DATE", None)

    return pd.DataFrame.from_records(records, columns = OUTPUT_COLUMNS)
