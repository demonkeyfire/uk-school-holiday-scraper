
# -------------------------------------------- Overview --------------------------------------------

# Coordinate the execution of individual authority scrapers and combine their outputs into a single
# DataFrame, while retaining a record of successful and failed scraper runs.



# --------------------------------------------- Imports --------------------------------------------

import pandas as pd

from scrapers.authorities.northern_ireland         import scrape_northern_ireland
from scrapers.authorities.aberdeenshire            import scrape_aberdeenshire
from scrapers.authorities.bath_north_east_somerset import scrape_bath_north_east_somerset



# --------------------------------------------- Input ----------------------------------------------

# Register the available authority scrapers using their SOURCE_ID as the key.
SCRAPERS = {"SRC001": scrape_aberdeenshire
           ,"SRC002": scrape_bath_north_east_somerset
           ,"SRC058": scrape_northern_ireland}

# Define the columns returned by the authority scrapers.
OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"EVENT_NAME"
                 ,"RAW_DATE_TEXT"
                 ,"DATE_SCRAPED"]



# ------------------------------------------- Main Code --------------------------------------------

# Execute the selected authority scrapers and combine their outputs into a single DataFrame.
def run_scrapers(source_ids = None):

    """
    Run the registered authority scrapers and combine their outputs.

    Parameters
    ----------
    source_ids : list, optional
        SOURCE_ID values identifying the scrapers to execute. If omitted, all registered scrapers
        are executed.

    Returns
    -------
    tuple
        A combined DataFrame and a summary DataFrame containing the outcome of each scraper.
    """

    # Default to running all registered scrapers when no source IDs are supplied.
    if source_ids is None:
        source_ids = list(SCRAPERS.keys())

    records = []
    results = []

    # Execute each selected scraper independently so one failure does not stop the remaining runs.
    for source_id in source_ids:

        if source_id not in SCRAPERS:
            results.append({"SOURCE_ID" : source_id
                           ,"STATUS"    : "NOT REGISTERED"
                           ,"RECORDS"   : 0
                           ,"ERROR"     : "No scraper registered for this SOURCE_ID"})
            continue

        try:
            data = SCRAPERS[source_id]()

            records.append(data)

            results.append({"SOURCE_ID" : source_id
                           ,"STATUS"    : "SUCCESS"
                           ,"RECORDS"   : len(data)
                           ,"ERROR"     : None})

        except Exception as error:
            results.append({"SOURCE_ID" : source_id
                           ,"STATUS"    : "FAILED"
                           ,"RECORDS"   : 0
                           ,"ERROR"     : str(error)})

    # Combine successful scraper outputs into a single DataFrame.
    if records:
        combined = pd.concat(records
                             ,ignore_index = True)
    else:
        combined = pd.DataFrame(columns = OUTPUT_COLUMNS)

    summary = pd.DataFrame.from_records(results)

    return combined, summary