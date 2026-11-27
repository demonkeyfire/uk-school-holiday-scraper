
# -------------------------------------------- Overview --------------------------------------------
# Retrieve Cornwall school term and holiday dates from published iCalendar files.
#
# Academic years:
#   - 2026/27
#   - 2027/28
#
# ICS files are used as the primary structured source.
#
# Output is one row per calendar event, retaining the event summary and
# original date values in a readable date range.


# --------------------------------------------- Imports --------------------------------------------
import re
from datetime import datetime, date, timedelta

import pandas as pd
import requests

from scrapers.source_config import get_source_url


# ---------------------------------------------- Settings -------------------------------------------
SOURCE_ID = "SRC012"
AUTHORITY = "Cornwall"

USER_AGENT = "SchoolHolidayResearch/1.0"
TIMEOUT = 30

CALENDAR_URLS = {
    "2026/27": (
        "https://www.cornwall.gov.uk/media/aivjyagd/"
        "cornwall-council-term-dates-2026-27.ics"
    ),
    "2027/28": (
        "https://www.cornwall.gov.uk/media/c42hymbo/"
        "cornwall-council-term-dates-2027-28.ics"
    ),
}


# ------------------------------------------ Helper Functions ---------------------------------------
def download_calendar(url):
    """Download an ICS calendar file."""

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return response.text


def unfold_ics_lines(ics_text):
    """
    Unfold ICS lines.

    In iCalendar, a line beginning with a space or tab continues
    the preceding line.
    """

    unfolded = []

    for line in ics_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):

        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    return unfolded


def parse_ics_date(value):
    """
    Parse an ICS date or date-time value.

    Supports:
      YYYYMMDD
      YYYYMMDDTHHMMSS
      YYYYMMDDTHHMMSSZ

    Returns the parsed datetime/date and whether the value is date-only.
    """

    value = value.strip()

    if re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").date(), True

    if re.fullmatch(r"\d{8}T\d{6}Z?", value):
        date_part = value[:8]
        time_part = value[9:15]

        parsed = datetime.strptime(
            date_part + time_part,
            "%Y%m%d%H%M%S"
        )

        return parsed, False

    raise ValueError(f"Unsupported ICS date value: {value}")


def extract_events(ics_text, academic_year):
    """Extract VEVENT records from an ICS calendar."""

    lines = unfold_ics_lines(ics_text)

    events = []
    current_event = None

    for line in lines:

        if line == "BEGIN:VEVENT":
            current_event = {}

        elif line == "END:VEVENT":

            if current_event is not None:
                events.append(current_event)

            current_event = None

        elif current_event is not None and ":" in line:

            property_name, value = line.split(":", 1)

            # Remove ICS property parameters, e.g. DTSTART;VALUE=DATE.
            property_name = property_name.split(";", 1)[0].upper()

            if property_name in {"SUMMARY", "DTSTART", "DTEND"}:
                current_event[property_name] = value.strip()

    records = []

    for event in events:

        summary = event.get("SUMMARY")
        start_value = event.get("DTSTART")
        end_value = event.get("DTEND")

        if not summary or not start_value:
            continue

        start_date, start_is_date = parse_ics_date(start_value)

        if end_value:
            end_date, end_is_date = parse_ics_date(end_value)

            # For all-day ICS events, DTEND is exclusive.
            if start_is_date and end_is_date:
                end_date = end_date - timedelta(days=1)

        else:
            end_date = start_date

        if end_date < start_date:
            raise ValueError(
                f"Invalid date range for event '{summary}' "
                f"in academic year {academic_year}"
            )

        # Keep the original calendar dates, but represent the end
        # date as inclusive for the output date range.
        raw_date_text = (
            f"{start_date.strftime('%Y-%m-%d')} to "
            f"{end_date.strftime('%Y-%m-%d')}"
        )

        records.append({
            "SOURCE_ID": SOURCE_ID,
            "ACADEMIC_YEAR": academic_year,
            "AUTHORITY": AUTHORITY,
            "EVENT_NAME": summary,
            "RAW_DATE_TEXT": raw_date_text,
            "DATE_SCRAPED": datetime.now().strftime("%Y-%m-%d"),
        })

    return records


# ------------------------------------------ Main Scraper -------------------------------------------
def scrape_cornwall():

    # Confirm the authority remains configured in sources.csv.
    get_source_url(SOURCE_ID)

    all_records = []

    for academic_year, calendar_url in CALENDAR_URLS.items():

        ics_text = download_calendar(calendar_url)

        records = extract_events(
            ics_text=ics_text,
            academic_year=academic_year
        )

        if not records:
            raise ValueError(
                f"No calendar events extracted for {academic_year}"
            )

        all_records.extend(records)

    df = pd.DataFrame(all_records)

    # -------------------------------------- Validation ---------------------------------------------
    expected_years = set(CALENDAR_URLS.keys())
    extracted_years = set(df["ACADEMIC_YEAR"].unique())

    missing_years = expected_years - extracted_years

    if missing_years:
        raise ValueError(
            f"Missing expected academic years: {sorted(missing_years)}"
        )

    # Check for duplicate events.
    duplicate_events = df.duplicated(
        subset=["ACADEMIC_YEAR", "EVENT_NAME", "RAW_DATE_TEXT"]
    )

    if duplicate_events.any():
        raise ValueError(
            "Duplicate calendar events found:\n"
            + df.loc[duplicate_events].to_string(index=False)
        )

    return df


# --------------------------------------------- Execution -------------------------------------------
if __name__ == "__main__":

    cornwall_df = scrape_cornwall()

    print(cornwall_df.to_string(index=False))

    print("\nEvents by academic year:")
    print(
        cornwall_df.groupby("ACADEMIC_YEAR")
        .size()
        .to_string()
    )
