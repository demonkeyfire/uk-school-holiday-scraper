
# -------------------------------------------- Overview --------------------------------------------
# Summarise calendar file discovery results into one row per authority.
#
# Input:
# data/calendar_file_links.csv
#
# Output:
# data/calendar_file_summary.csv
#
# Output columns:
# SOURCE_ID, HAS_HTML, HAS_PDF, HAS_WORD, HAS_EXCEL, HAS_ICALENDAR


# --------------------------------------------- Imports --------------------------------------------
from pathlib import Path

import pandas as pd


# ---------------------------------------------- Paths ---------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = REPO_ROOT / "data" / "calendar_file_links.csv"
OUTPUT_FILE = REPO_ROOT / "data" / "calendar_file_summary.csv"


# ------------------------------------------- Main Function -----------------------------------------
def run_summary(
    input_file=INPUT_FILE,
    output_file=OUTPUT_FILE
):
    """
    Convert calendar file discovery results into one row per SOURCE_ID.

    Returns
    -------
    pandas.DataFrame
        Boolean availability flags for each source.
    """

    results = pd.read_csv(input_file)

    summaries = []

    for source_id, group in results.groupby("SOURCE_ID", sort=True):

        successful_check = (
            group["DISCOVERY_STATUS"]
            .isin(["LINK_FOUND", "NO_MATCHING_LINKS"])
            .any()
        )

        file_types = set(
            group["FILE_TYPE"]
            .dropna()
            .str.upper()
        )

        summaries.append({
            "SOURCE_ID": source_id,
            "HAS_HTML": successful_check,
            "HAS_PDF": "PDF" in file_types or "PDF_UNCLASSIFIED" in file_types,
            "HAS_WORD": any(
                file_type.startswith("WORD")
                for file_type in file_types
            ),
            "HAS_EXCEL": any(
                file_type.startswith("EXCEL")
                or file_type == "OPEN_DOCUMENT_SPREADSHEET"
                for file_type in file_types
            ),
            "HAS_ICALENDAR": any(
                file_type in {"ICS", "ICAL", "IFB"}
                for file_type in file_types
            ),
        })

    summary = pd.DataFrame(summaries)

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    summary.to_csv(output_file, index=False)

    print(f"Authorities summarised: {len(summary)}")
    print(f"Summary saved to: {output_file}")

    return summary


# --------------------------------------------- Execution -------------------------------------------
def main():
    summary = run_summary()
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
