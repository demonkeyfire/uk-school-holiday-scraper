# -------------------------------------------- Overview --------------------------------------------

# Extract Buckinghamshire school dates from the published 2025/26 Excel calendar. The output is
# one row per consecutive date period and calendar category, using the standard scraper schema.



# --------------------------------------------- Imports --------------------------------------------

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC008"
ACADEMIC_YEAR = "2025/26"
CALENDAR_PATH = (Path(__file__).resolve().parents[2]
                 / "school_calendars"
                 / "buckinghamshire"
                 / "2025_26_academic_year_Term_Dates.xlsx")

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

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

    """Group dates separated only by weekends into consecutive calendar periods."""

    if not dates:
        return []

    dates = sorted(set(dates))
    periods = []
    period_start = dates[0]
    period_end = dates[0]

    for current_date in dates[1:]:

        if (current_date - period_end).days <= 3:
            period_end = current_date
        else:
            periods.append((period_start, period_end))
            period_start = current_date
            period_end = current_date

    periods.append((period_start, period_end))

    return periods


def format_date_range(start_date, end_date):

    """Format a date period using the weekday and month wording of the calendar."""

    def format_date(value):
        return f"{value.strftime('%A')} {value.day} {value.strftime('%B %Y')}"

    if start_date == end_date:
        return format_date(start_date)

    return f"{format_date(start_date)} to {format_date(end_date)}"



# ------------------------------------------- Main Code --------------------------------------------

def scrape_buckinghamshire_calendar(calendar_path = CALENDAR_PATH):

    """
    Extract the colour-coded school dates from the Buckinghamshire 2025/26 calendar.

    Consecutive dates of each legend category are consolidated into date ranges. Weekend gaps
    between school weekdays do not split a period.

    Parameters
    ----------
    calendar_path : str or pathlib.Path
        Path to the Excel calendar. Defaults to the workbook stored in this repository.

    Returns
    -------
    pandas.DataFrame
        Calendar events with the standard scraper output columns.
    """

    workbook = load_workbook(calendar_path, data_only = True, read_only = True)

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

                calendar_date = get_calendar_date(cell, month_headers)
                category_dates[event_name].append(calendar_date)

    finally:
        workbook.close()

    date_scraped = datetime.now(timezone.utc).date()
    records = []

    for event_name, dates in category_dates.items():

        for period_start, period_end in consolidate_dates(dates):

            records.append({"SOURCE_ID"     : SOURCE_ID
                           ,"ACADEMIC_YEAR" : ACADEMIC_YEAR
                           ,"EVENT_NAME"    : event_name
                           ,"RAW_DATE_TEXT" : format_date_range(period_start, period_end)
                           ,"DATE_SCRAPED"  : date_scraped
                           ,"_START_DATE"  : period_start})

    records.sort(key = lambda record: (record["_START_DATE"], record["EVENT_NAME"]))

    for record in records:
        del record["_START_DATE"]

    return pd.DataFrame.from_records(records, columns = OUTPUT_COLUMNS)
