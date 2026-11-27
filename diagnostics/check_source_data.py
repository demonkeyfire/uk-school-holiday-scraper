
# -------------------------------------------- Overview --------------------------------------------
# Identify downloadable calendar and document files linked from configured authority websites.
#
# Supported formats:
# ICS, ICAL, PDF, Excel, CSV, Word and OpenDocument spreadsheets.
#
# Output:
# data/calendar_file_links.csv


# --------------------------------------------- Imports --------------------------------------------
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm.auto import tqdm


# ---------------------------------------------- Paths ---------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_FILE = REPO_ROOT / "config" / "sources.csv"
OUTPUT_FILE = REPO_ROOT / "data" / "calendar_file_links.csv"


# --------------------------------------------- Settings -------------------------------------------
USER_AGENT = "SchoolHolidayResearch/1.0"
TIMEOUT = 30
ACTIVE_ONLY = True

FILE_TYPES = {
    ".ics": "ICS",
    ".ical": "ICAL",
    ".ifb": "IFB",
    ".pdf": "PDF",
    ".xlsx": "EXCEL_XLSX",
    ".xls": "EXCEL_XLS",
    ".csv": "CSV",
    ".docx": "WORD_DOCX",
    ".doc": "WORD_DOC",
    ".ods": "OPEN_DOCUMENT_SPREADSHEET",
}

CALENDAR_KEYWORDS = [
    "calendar",
    "term dates",
    "school holidays",
    "download dates",
]


# ---------------------------------------- Link Discovery ------------------------------------------
def identify_file_type(url, link_text):
    """Identify a linked file from its URL extension or link wording."""

    extension = Path(urlparse(url).path.lower()).suffix

    if extension in FILE_TYPES:
        return FILE_TYPES[extension]

    text = link_text.lower()

    if any(keyword in text for keyword in CALENDAR_KEYWORDS):
        return "CALENDAR_LINK_UNCLASSIFIED"

    if "pdf" in text:
        return "PDF_UNCLASSIFIED"

    if "excel" in text or "spreadsheet" in text:
        return "EXCEL_UNCLASSIFIED"

    return None


def inspect_source(source):
    """Inspect one authority page and return discovered file links."""

    source_id = source["SOURCE_ID"]
    authority = source["AUTHORITY_NAME"]
    source_url = source["SOURCE_URL"]

    try:
        response = requests.get(
            source_url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):

            link_text = link.get_text(" ", strip=True)
            file_url = urljoin(response.url, link["href"])

            file_type = identify_file_type(file_url, link_text)

            if file_type and file_url not in seen_urls:

                seen_urls.add(file_url)

                results.append({
                    "SOURCE_ID": source_id,
                    "AUTHORITY_NAME": authority,
                    "SOURCE_URL": source_url,
                    "PAGE_FINAL_URL": response.url,
                    "FILE_TYPE": file_type,
                    "LINK_TEXT": link_text,
                    "FILE_URL": file_url,
                    "DISCOVERY_STATUS": "LINK_FOUND",
                })

        if not results:
            results.append({
                "SOURCE_ID": source_id,
                "AUTHORITY_NAME": authority,
                "SOURCE_URL": source_url,
                "PAGE_FINAL_URL": response.url,
                "FILE_TYPE": None,
                "LINK_TEXT": None,
                "FILE_URL": None,
                "DISCOVERY_STATUS": "NO_MATCHING_LINKS",
            })

        return results

    except Exception as error:

        return [{
            "SOURCE_ID": source_id,
            "AUTHORITY_NAME": authority,
            "SOURCE_URL": source_url,
            "PAGE_FINAL_URL": None,
            "FILE_TYPE": None,
            "LINK_TEXT": None,
            "FILE_URL": None,
            "DISCOVERY_STATUS": f"ERROR: {str(error)}",
        }]


# ------------------------------------------- Main Function -----------------------------------------
def run_check(
    source_file=SOURCE_FILE,
    output_file=OUTPUT_FILE,
    active_only=ACTIVE_ONLY
):
    """
    Check configured authority pages for downloadable calendar files.

    Parameters
    ----------
    source_file : Path or str
        Location of sources.csv.

    output_file : Path or str
        Location where results will be saved.

    active_only : bool
        If True, only inspect sources marked ACTIVE.

    Returns
    -------
    pandas.DataFrame
        One row per discovered file link, or one status row per source
        where no matching links were found or an error occurred.
    """

    source_file = Path(source_file)
    output_file = Path(output_file)

    sources = pd.read_csv(source_file)

    sources["SOURCE_URL"] = sources["SOURCE_URL"].fillna("").str.strip()

    if active_only:
        sources = sources[
            sources["SOURCE_STATUS"].str.upper() == "ACTIVE"
        ]

    sources = sources[sources["SOURCE_URL"] != ""]

    all_results = []

    for _, source in tqdm(
        sources.iterrows(),
        total=len(sources),
        desc="Checking authority pages"
    ):
        all_results.extend(inspect_source(source))

    results = pd.DataFrame(all_results)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_file, index=False)

    links_found = (
        results["DISCOVERY_STATUS"] == "LINK_FOUND"
    ).sum()

    print(f"Sources checked: {len(sources)}")
    print(f"File links discovered: {links_found}")
    print(f"Results saved to: {output_file}")

    return results


# --------------------------------------------- Execution -------------------------------------------
def main():
    results = run_check()

    print("\nDiscovered file links:")

    display_columns = [
        "SOURCE_ID",
        "AUTHORITY_NAME",
        "FILE_TYPE",
        "LINK_TEXT",
        "FILE_URL",
    ]

    print(
        results.loc[
            results["DISCOVERY_STATUS"] == "LINK_FOUND",
            display_columns
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
