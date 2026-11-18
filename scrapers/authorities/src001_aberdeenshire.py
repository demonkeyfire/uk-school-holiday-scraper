
# -------------------------------------------- Overview --------------------------------------------

# Retrieve Aberdeenshire school-term and holiday events from the published page and linked calendars.
# Calendar events take precedence on overlapping dates; uncovered webpage dates are retained.



# --------------------------------------------- Imports --------------------------------------------

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.source_config import get_source



# --------------------------------------------- Input ----------------------------------------------

# Identify the source using its unique ID in the central sources.csv register.
SOURCE_ID = "SRC001"

# Define the request headers used when retrieving the published page and calendar files.
HEADERS = {"User-Agent": "SchoolHolidayResearch/1.0"}

# Define the columns returned by the scraper.
OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]

# Restrict extraction to the academic years currently required.
ACADEMIC_YEARS = {"2026/27"
                 ,"2027/28"
                 ,"2028/29"
                 ,"2029/30"}

# Match a single date or range followed by the event label for each list item.
EVENT_PATTERN = re.compile(r"^("
                          r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"
                          r"(?:\s+to\s+\d{1,2}\s+[A-Za-z]+\s+\d{4})?"
                          r")\s+-\s+(.+)$")

# Match academic years in webpage headings and calendar names.
ACADEMIC_YEAR_PATTERN = re.compile(r"\b(\d{4})/(\d{2})\b")
CALENDAR_YEAR_PATTERN = re.compile(r"(\d{4})/(\d{2})\s*$")

# Identify the linked iCalendar download.
CALENDAR_LINK_PATTERN = re.compile(r"/SchoolTerm/DownloadCalendar(?:\?|$)", re.IGNORECASE)

# Match all-day iCalendar date values.
CALENDAR_DATE_PATTERN = re.compile(r"^\d{8}$")



# ------------------------------------------- Helper Functions -------------------------------------

def unfold_calendar_lines(calendar_text):

    """Join iCalendar continuation lines to their preceding property lines."""

    unfolded_lines = []

    for line in calendar_text.splitlines():

        if line.startswith((" ", "\t")):
            if not unfolded_lines:
                raise ValueError("iCalendar begins with a continuation line")

            unfolded_lines[-1] += line[1:]
        else:
            unfolded_lines.append(line)

    return unfolded_lines


def unescape_text(value):

    """Decode escaped text values as defined by the iCalendar text format."""

    return (value.replace(r"\n", "\n")
                 .replace(r"\N", "\n")
                 .replace(r"\,", ",")
                 .replace(r"\;", ";")
                 .replace(r"\\", "\\"))


def parse_calendar_date(value, property_name):

    """Parse an all-day iCalendar date property."""

    if CALENDAR_DATE_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{property_name} must be an all-day YYYYMMDD value, got {value!r}")

    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as error:
        raise ValueError(f"Invalid {property_name} calendar date: {value!r}") from error


def validate_date_parameters(event, property_name):

    """Validate that an iCalendar date property represents an all-day date."""

    parameters = event.get("_PARAMETERS", {}).get(property_name, [])

    if parameters and parameters != ["VALUE=DATE"]:
        raise ValueError(
            f"Unsupported {property_name} parameters: {parameters!r}. "
            "Only VALUE=DATE or no parameters are supported.")


def format_date_range(start_date, end_date):

    """Format an inclusive date period using weekday and month names."""

    def format_date(value):
        return f"{value.strftime('%A')} {value.day} {value.strftime('%B %Y')}"

    if start_date == end_date:
        return format_date(start_date)

    return f"{format_date(start_date)} to {format_date(end_date)}"


def parse_web_date_range(raw_date_text):

    """Parse a webpage single date or inclusive date range."""

    dates = [datetime.strptime(value.strip(), "%d %B %Y").date()
             for value in raw_date_text.split(" to ")]

    if len(dates) not in {1, 2}:
        raise ValueError(f"Invalid webpage date range: {raw_date_text!r}")

    start_date = dates[0]
    end_date = dates[-1]

    if end_date < start_date:
        raise ValueError(f"Webpage date range ends before it starts: {raw_date_text!r}")

    return start_date, end_date


def extract_events(calendar_lines):

    """Return event properties from unfolded iCalendar lines."""

    events = []
    current_event = None

    for line in calendar_lines:

        if line == "BEGIN:VEVENT":
            if current_event is not None:
                raise ValueError("Nested VEVENT in iCalendar document")

            current_event = {"_PARAMETERS": {}}
            continue

        if line == "END:VEVENT":
            if current_event is None:
                raise ValueError("END:VEVENT without a matching BEGIN:VEVENT")

            events.append(current_event)
            current_event = None
            continue

        if current_event is None or ":" not in line:
            continue

        property_definition, value = line.split(":", maxsplit = 1)
        property_parts = property_definition.split(";")
        property_name = property_parts[0].upper()
        parameters = [parameter.upper() for parameter in property_parts[1:]]

        if property_name in {"DTSTART", "DTEND", "SUMMARY"}:

            if property_name in current_event:
                raise ValueError(f"Duplicate {property_name} in iCalendar event")

            current_event[property_name] = unescape_text(value)

            if property_name in {"DTSTART", "DTEND"}:
                current_event["_PARAMETERS"][property_name] = parameters

    if current_event is not None:
        raise ValueError("Unterminated VEVENT in iCalendar document")

    if not events:
        raise ValueError("No VEVENT records found in iCalendar document")

    return events


def extract_calendar_records(calendar_lines, expected_academic_year, date_scraped):

    """Parse calendar events, validating their academic year and date properties."""

    calendar_name = next(
        (line.split(":", maxsplit = 1)[1]
         for line in calendar_lines
         if line.startswith("X-WR-CALNAME:")),
        None)

    if calendar_name is None:
        raise ValueError("iCalendar is missing X-WR-CALNAME")

    academic_year_match = CALENDAR_YEAR_PATTERN.search(calendar_name.strip())

    if academic_year_match is None:
        raise ValueError(f"Could not determine academic year from calendar name: {calendar_name!r}")

    academic_year = f"{academic_year_match.group(1)}/{academic_year_match.group(2)}"

    if academic_year != expected_academic_year:
        raise ValueError(
            f"Calendar year {academic_year} does not match webpage year "
            f"{expected_academic_year}")

    academic_year_start = int(academic_year[:4])
    valid_calendar_years = {academic_year_start, academic_year_start + 1}

    records = []
    seen_events = set()

    for event in extract_events(calendar_lines):

        missing_properties = {"DTSTART", "DTEND", "SUMMARY"}.difference(event)

        if missing_properties:
            raise ValueError(f"Calendar event is missing properties: {sorted(missing_properties)}")

        validate_date_parameters(event, "DTSTART")
        validate_date_parameters(event, "DTEND")

        start_date = parse_calendar_date(event["DTSTART"], "DTSTART")
        exclusive_end_date = parse_calendar_date(event["DTEND"], "DTEND")

        if exclusive_end_date <= start_date:
            raise ValueError(
                f"DTEND must be later than DTSTART for event {event['SUMMARY']!r}")

        end_date = exclusive_end_date - timedelta(days = 1)

        if start_date.year not in valid_calendar_years or end_date.year not in valid_calendar_years:
            raise ValueError(
                f"Calendar event falls outside academic year {academic_year}: "
                f"{event['SUMMARY']!r} ({start_date} to {end_date})")

        event_key = (academic_year, event["SUMMARY"], start_date, end_date)

        if event_key in seen_events:
            raise ValueError(
                f"Duplicate calendar event found: {event['SUMMARY']!r} "
                f"({start_date} to {end_date})")

        seen_events.add(event_key)

        records.append({"SOURCE_ID"     : SOURCE_ID
                       ,"ACADEMIC_YEAR" : academic_year
                       ,"EVENT_NAME"    : event["SUMMARY"]
                       ,"RAW_DATE_TEXT" : format_date_range(start_date, end_date)
                       ,"DATE_SCRAPED"  : date_scraped
                       ,"_START_DATE"   : start_date
                       ,"_END_DATE"     : end_date})

    return records


def merge_calendar_coverage(calendar_records):

    """Combine overlapping or adjacent inclusive calendar date periods."""

    if not calendar_records:
        return []

    periods = sorted((record["_START_DATE"], record["_END_DATE"])
                     for record in calendar_records)
    merged_periods = [periods[0]]

    for current_start, current_end in periods[1:]:
        previous_start, previous_end = merged_periods[-1]

        if current_start <= previous_end + timedelta(days = 1):
            merged_periods[-1] = (previous_start, max(previous_end, current_end))
        else:
            merged_periods.append((current_start, current_end))

    return merged_periods


def subtract_calendar_coverage(start_date, end_date, calendar_coverage):

    """Return portions of a webpage date period not already covered by calendar events."""

    uncovered_periods = []
    current_start = start_date

    for coverage_start, coverage_end in calendar_coverage:

        if coverage_end < current_start:
            continue

        if coverage_start > end_date:
            break

        if coverage_start > current_start:
            uncovered_periods.append((current_start, coverage_start - timedelta(days = 1)))

        current_start = max(current_start, coverage_end + timedelta(days = 1))

        if current_start > end_date:
            break

    if current_start <= end_date:
        uncovered_periods.append((current_start, end_date))

    return uncovered_periods


def get_section_calendar_url(section, source_url, academic_year):

    """Return the calendar download URL linked from an academic-year section."""

    calendar_link = section.find("a", href = CALENDAR_LINK_PATTERN)

    if calendar_link is None:
        raise ValueError(f"Could not find the iCalendar link for {academic_year} on {source_url}")

    return urljoin(source_url, calendar_link["href"])



# ------------------------------------------- Main Code --------------------------------------------

# Fetch the published page, its linked calendars, and merge complementary event dates.
def scrape_aberdeenshire():

    """
    Return school-term and holiday events from the Aberdeenshire page and linked calendars.

    Calendar dates take precedence where the sources overlap. Webpage date portions not covered by
    the calendar are retained, so information published by either source is represented.

    Returns
    -------
    pd.DataFrame
        One row per event and academic year, with columns:
            SOURCE_ID
            ACADEMIC_YEAR
            EVENT_NAME
            RAW_DATE_TEXT
            DATE_SCRAPED
    """

    source = get_source(SOURCE_ID)
    source_url = source["SOURCE_URL"]

    response = requests.get(source_url
                           ,headers = HEADERS
                           ,timeout = 30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content
                        ,"html.parser")
    date_scraped = datetime.now(timezone.utc).date()
    website_records = []
    calendar_records = []
    found_academic_years = set()

    for heading in soup.find_all("h2"):

        heading_text = heading.get_text(" ", strip = True)
        year_match = ACADEMIC_YEAR_PATTERN.search(heading_text)

        if year_match is None:
            continue

        academic_year = f"{year_match.group(1)}/{year_match.group(2)}"

        if academic_year not in ACADEMIC_YEARS:
            continue

        section = heading.find_parent("div", attrs = {"role": "tabpanel"})

        if section is None:
            raise ValueError(f"Could not find webpage section for {academic_year}")

        found_academic_years.add(academic_year)

        for element in section.find_all("li"):

            raw_text = element.get_text(" ", strip = True)
            event_match = EVENT_PATTERN.match(raw_text)

            if event_match is None:
                continue

            raw_date_text = event_match.group(1)
            event_name = event_match.group(2).strip()
            start_date, end_date = parse_web_date_range(raw_date_text)

            website_records.append({"SOURCE_ID"     : SOURCE_ID
                                   ,"ACADEMIC_YEAR" : academic_year
                                   ,"EVENT_NAME"    : event_name
                                   ,"RAW_DATE_TEXT" : raw_date_text
                                   ,"DATE_SCRAPED"  : date_scraped
                                   ,"_START_DATE"   : start_date
                                   ,"_END_DATE"     : end_date})

        calendar_url = get_section_calendar_url(section, source_url, academic_year)

        calendar_response = requests.get(calendar_url
                                        ,headers = HEADERS
                                        ,timeout = 30)
        calendar_response.raise_for_status()

        calendar_text = calendar_response.content.decode("utf-8")
        calendar_lines = unfold_calendar_lines(calendar_text)

        calendar_records.extend(
            extract_calendar_records(calendar_lines
                                    ,academic_year
                                    ,date_scraped))

    missing_years = ACADEMIC_YEARS.difference(found_academic_years)

    if missing_years:
        raise ValueError(f"Could not find webpage sections for academic years: {sorted(missing_years)}")

    calendar_records_by_year = {}

    for record in calendar_records:
        academic_year = record["ACADEMIC_YEAR"]
        calendar_records_by_year.setdefault(academic_year, []).append(record)

    calendar_coverage_by_year = {
        academic_year: merge_calendar_coverage(records)
        for academic_year, records in calendar_records_by_year.items()}

    resolved_website_records = []

    for record in website_records:

        uncovered_periods = subtract_calendar_coverage(
            record["_START_DATE"]
            ,record["_END_DATE"]
            ,calendar_coverage_by_year.get(record["ACADEMIC_YEAR"], []))

        for period_start, period_end in uncovered_periods:

            resolved_record = record.copy()

            if (period_start, period_end) != (record["_START_DATE"], record["_END_DATE"]):
                resolved_record["RAW_DATE_TEXT"] = format_date_range(period_start, period_end)

            resolved_record["_START_DATE"] = period_start
            resolved_record["_END_DATE"] = period_end
            resolved_website_records.append(resolved_record)

    records = calendar_records + resolved_website_records
    records.sort(key = lambda record: (record["_START_DATE"], record["EVENT_NAME"]))

    for record in records:
        record.pop("_START_DATE")
        record.pop("_END_DATE")

    return pd.DataFrame.from_records(records
                                    ,columns = OUTPUT_COLUMNS)
