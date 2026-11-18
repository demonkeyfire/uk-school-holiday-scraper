
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Bradford school holiday dates from the published DOCX academic calendars. The calendar
# uses cell shading to distinguish bank holidays, other holidays and likely Eid dates.
#
# The output contains one row per consecutive holiday period and category, retaining the date
# range reconstructed from the calendar.
#
# NOTE: The calendars identify five INSET days, but individual schools determine these dates.



# --------------------------------------------- Imports --------------------------------------------

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

import pandas as pd
import requests
from docx import Document
from docx.oxml.ns import qn



# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC006"
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

DOCUMENT_URLS = {"2025/26": "https://bso.bradford.gov.uk/userfiles/file/IMT/SchoolHolidays/Bradford%20Term%20Dates%202025-26.docx"
                ,"2026/27": "https://bso.bradford.gov.uk/userfiles/file/IMT/Bradford%20Term%20Dates%202026-27.docx"
                ,"2027/28": "https://bso.bradford.gov.uk/userfiles/file/IMT/SchoolHolidays/Bradford%20Term%20Dates%202027-28.docx"}

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

MONTHS = {"January": 1
         ,"February": 2
         ,"March": 3
         ,"April": 4
         ,"May": 5
         ,"June": 6
         ,"July": 7
         ,"August": 8
         ,"September": 9
         ,"October": 10
         ,"November": 11
         ,"December": 12}

HOLIDAY_COLOURS = {"9999FF": "Bank Holidays"
                  ,"66FF33": "Other Holidays"
                  ,"FFC000": "Likely date for Eid"}



# ------------------------------------------- Helper Functions -------------------------------------

def get_cell_shading(cell):

    shading = cell._tc.tcPr.find(qn("w:shd"))

    if shading is None:
        return None

    colour = shading.get(qn("w:fill"))

    if colour is None:
        return None

    return colour.upper()


def get_academic_year_numbers(academic_year):

    start_year, end_year = academic_year.split("/")
    start_year = int(start_year)
    end_year = (start_year // 100) * 100 + int(end_year[-2:])

    return start_year, end_year


def format_date_range(start_date, end_date):

    def format_date(value):
        return f"{value.strftime('%A')} {value.day} {value.strftime('%B %Y')}"

    if start_date == end_date:
        return format_date(start_date)

    return f"{format_date(start_date)} to {format_date(end_date)}"


def consolidate_dates(dates):

    if not dates:
        return []

    dates = sorted(set(dates))
    periods = []

    period_start = dates[0]
    period_end = dates[0]

    for current_date in dates[1:]:

        difference = (current_date - period_end).days

        # The calendar only displays weekdays. A Friday-to-Monday gap therefore represents
        # consecutive shaded weekdays with the weekend between them.

        if difference <= 3:
            period_end = current_date

        else:
            periods.append((period_start, period_end))
            period_start = current_date
            period_end = current_date

    periods.append((period_start, period_end))

    return periods



# ------------------------------------------- Main Code --------------------------------------------

def scrape_bradford():

    records = []
    date_scraped = datetime.now(timezone.utc).date()

    for academic_year, document_url in DOCUMENT_URLS.items():

        response = requests.get(document_url
                               ,headers = HEADERS
                               ,timeout = 30)
        response.raise_for_status()

        document = Document(BytesIO(response.content))

        if not document.tables:
            raise ValueError(f"No calendar table found for {academic_year}")

        table = document.tables[0]
        start_year, end_year = get_academic_year_numbers(academic_year)

        holiday_dates = defaultdict(list)

        # Each calendar section starts with a row containing the month names. The following row
        # contains weekday headings, followed by five rows containing the calendar dates.

        for header_row_number, header_row in enumerate(table.rows):

            month_columns = defaultdict(list)

            for column_number, cell in enumerate(header_row.cells):

                month_name = cell.text.strip()

                if month_name in MONTHS:
                    month_columns[month_name].append(column_number)

            if not month_columns:
                continue

            for month_name, columns in month_columns.items():

                month_number = MONTHS[month_name]

                if month_number >= 9:
                    calendar_year = start_year
                else:
                    calendar_year = end_year

                for row_number in range(header_row_number + 2
                                       ,min(header_row_number + 7, len(table.rows))):

                    date_row = table.rows[row_number]

                    for column_number in columns:

                        cell = date_row.cells[column_number]
                        day_text = cell.text.strip()

                        if not day_text.isdigit():
                            continue

                        colour = get_cell_shading(cell)

                        if colour not in HOLIDAY_COLOURS:
                            continue

                        calendar_date = date(calendar_year
                                            ,month_number
                                            ,int(day_text))

                        event_name = HOLIDAY_COLOURS[colour]
                        holiday_dates[event_name].append(calendar_date)

        # Consolidate consecutive shaded weekdays into date ranges.

        for event_name, dates in holiday_dates.items():

            for period_start, period_end in consolidate_dates(dates):

                records.append({"SOURCE_ID"     : SOURCE_ID
                               ,"ACADEMIC_YEAR" : academic_year
                               ,"EVENT_NAME"    : event_name
                               ,"RAW_DATE_TEXT" : format_date_range(period_start, period_end)
                               ,"DATE_SCRAPED"  : date_scraped})

    output = pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)

    if not output.empty:
        output = output.sort_values(["ACADEMIC_YEAR"
                                    ,"RAW_DATE_TEXT"]).reset_index(drop = True)

    return output
