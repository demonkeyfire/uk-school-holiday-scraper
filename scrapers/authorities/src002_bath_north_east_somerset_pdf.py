"""Extract Bath & North East Somerset 2025/26 dates from the local council PDF."""

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re

import pandas as pd
import pdfplumber


SOURCE_ID = "SRC002"
ACADEMIC_YEAR = "2025/26"
ACADEMIC_YEAR_START = date(2025, 9, 1)
ACADEMIC_YEAR_END = date(2026, 8, 31)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALENDAR_PATH = (PROJECT_ROOT
                 / "school_calendars"
                 / "bath_north_east_somerset"
                 / "2025-26 Final approved term dates.pdf")

OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

TERM_PATTERN = re.compile(
    r"\bTerm\s+(?P<term_number>[1-6])\s+"
    r"(?P<start_day>\d{1,2})\s*(?P<start_month>[A-Za-z]+)\s*[–-]\s*"
    r"(?P<end_day>\d{1,2})\s*(?P<end_month>[A-Za-z]+)\s*"
    r"(?P<end_year>\d{4})\b"
    ,re.IGNORECASE)

BANK_HOLIDAY_PATTERN = re.compile(
    r"^(?P<event_name>.+?)\s*[–-]\s*"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s*"
    r"(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\b"
    ,re.IGNORECASE)


def format_date_range(start_date, end_date):

    """Format an inclusive date period with weekday and month names."""

    def format_date(value):
        return f"{value.strftime('%A')} {value.day} {value.strftime('%B %Y')}"

    if start_date == end_date:
        return format_date(start_date)

    return f"{format_date(start_date)} to {format_date(end_date)}"


def parse_calendar_text(calendar_text, date_scraped):

    """Parse term and bank-holiday rows, deriving the breaks between terms."""

    term_records = []
    bank_holiday_records = []

    for line in calendar_text.splitlines():
        term_match = TERM_PATTERN.search(line)

        if term_match is not None:
            end_year = int(term_match.group("end_year"))
            start_month = datetime.strptime(
                term_match.group("start_month").title(), "%B").month
            end_month = datetime.strptime(
                term_match.group("end_month").title(), "%B").month
            start_year = end_year - (start_month > end_month)
            start_date = date(start_year
                             ,start_month
                             ,int(term_match.group("start_day")))
            end_date = date(end_year
                           ,end_month
                           ,int(term_match.group("end_day")))

            if end_date < start_date:
                raise ValueError(f"Term ends before it starts: {line!r}")

            term_records.append({"SOURCE_ID"     : SOURCE_ID
                                ,"ACADEMIC_YEAR" : ACADEMIC_YEAR
                                ,"EVENT_NAME"    : f"Term {term_match.group('term_number')}"
                                ,"RAW_DATE_TEXT" : format_date_range(start_date, end_date)
                                ,"DATE_SCRAPED"  : date_scraped
                                ,"_START_DATE"   : start_date
                                ,"_END_DATE"     : end_date})

        bank_holiday_match = BANK_HOLIDAY_PATTERN.match(line.strip())

        if bank_holiday_match is None:
            continue

        holiday_date = date(
            int(bank_holiday_match.group("year"))
            ,datetime.strptime(bank_holiday_match.group("month").title(), "%B").month
            ,int(bank_holiday_match.group("day")))

        bank_holiday_records.append({"SOURCE_ID"     : SOURCE_ID
                                    ,"ACADEMIC_YEAR" : ACADEMIC_YEAR
                                    ,"EVENT_NAME"    : bank_holiday_match.group(
                                        "event_name").strip()
                                    ,"RAW_DATE_TEXT" : format_date_range(
                                        holiday_date, holiday_date)
                                    ,"DATE_SCRAPED"  : date_scraped
                                    ,"_START_DATE"   : holiday_date
                                    ,"_END_DATE"     : holiday_date})

    if {record["EVENT_NAME"] for record in term_records} != {
            f"Term {number}" for number in range(1, 7)}:
        raise ValueError("Expected term dates for all six terms in the PDF")

    if len(bank_holiday_records) != 8:
        raise ValueError(
            f"Expected eight bank holidays in the PDF, found {len(bank_holiday_records)}")

    term_records.sort(key = lambda record: record["_START_DATE"])
    previous_end = ACADEMIC_YEAR_START - timedelta(days = 1)
    school_holiday_records = []

    for term_record in term_records:
        term_start = term_record["_START_DATE"]
        term_end = term_record["_END_DATE"]

        if term_start <= previous_end:
            raise ValueError(f"Term dates overlap: {term_record['EVENT_NAME']}")

        holiday_start = previous_end + timedelta(days = 1)
        holiday_end = term_start - timedelta(days = 1)

        if holiday_start <= holiday_end:
            school_holiday_records.append({"SOURCE_ID"     : SOURCE_ID
                                          ,"ACADEMIC_YEAR" : ACADEMIC_YEAR
                                          ,"EVENT_NAME"    : "School Holiday"
                                          ,"RAW_DATE_TEXT" : format_date_range(
                                              holiday_start, holiday_end)
                                          ,"DATE_SCRAPED"  : date_scraped
                                          ,"_START_DATE"   : holiday_start
                                          ,"_END_DATE"     : holiday_end})

        previous_end = term_end

    if previous_end < ACADEMIC_YEAR_END:
        holiday_start = previous_end + timedelta(days = 1)
        school_holiday_records.append({"SOURCE_ID"     : SOURCE_ID
                                      ,"ACADEMIC_YEAR" : ACADEMIC_YEAR
                                      ,"EVENT_NAME"    : "School Holiday"
                                      ,"RAW_DATE_TEXT" : format_date_range(
                                          holiday_start, ACADEMIC_YEAR_END)
                                      ,"DATE_SCRAPED"  : date_scraped
                                      ,"_START_DATE"   : holiday_start
                                      ,"_END_DATE"     : ACADEMIC_YEAR_END})

    records = term_records + bank_holiday_records + school_holiday_records
    records.sort(key = lambda record: (record["_START_DATE"], record["EVENT_NAME"]))

    for record in records:
        record.pop("_START_DATE")
        record.pop("_END_DATE")

    return pd.DataFrame.from_records(records, columns = OUTPUT_COLUMNS)


def extract_calendar_dates(pdf_path = CALENDAR_PATH, date_scraped = None):

    """Return standard date records extracted from the PDF's term summary page."""

    if date_scraped is None:
        date_scraped = datetime.now(timezone.utc).date()

    with pdfplumber.open(pdf_path) as calendar_pdf:

        if len(calendar_pdf.pages) < 2:
            raise ValueError("The calendar PDF must include its term summary on page 2")

        calendar_text = calendar_pdf.pages[1].extract_text()

    if not calendar_text:
        raise ValueError("Could not extract text from page 2 of the calendar PDF")

    return parse_calendar_text(calendar_text, date_scraped)


def main(argv = None):

    """Write extracted calendar records to a CSV file."""

    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--pdf"
                       ,type = Path
                       ,default = CALENDAR_PATH
                       ,help = "Path to the 2025/26 term dates PDF")
    parser.add_argument("--output"
                       ,type = Path
                       ,help = "CSV destination (defaults to the PDF path with a .csv suffix)")
    arguments = parser.parse_args(argv)
    output_path = arguments.output or arguments.pdf.with_suffix(".csv")
    records = extract_calendar_dates(arguments.pdf)
    records.to_csv(output_path, index = False)
    print(f"Wrote {len(records)} date records to {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
