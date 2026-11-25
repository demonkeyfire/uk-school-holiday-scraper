
# -------------------------------------------- Overview --------------------------------------------

# Coordinate the execution of individual authority scrapers and combine their outputs into a single
# DataFrame, while retaining a record of successful and failed scraper runs.



# --------------------------------------------- Imports --------------------------------------------

import pandas as pd

from scrapers.authorities.src001_aberdeenshire                  import scrape_aberdeenshire
from scrapers.authorities.src002_bath_north_east_somerset       import scrape_bath_north_east_somerset
from scrapers.authorities.src003_central_bedfordshire           import scrape_central_bedfordshire
from scrapers.authorities.src004_birmingham                     import scrape_birmingham
from scrapers.authorities.src005_bournemouth_christchurch_poole import scrape_bournemouth_christchurch_poole
from scrapers.authorities.src006_bradford                       import scrape_bradford
from scrapers.authorities.src007_bristol                        import scrape_bristol
from scrapers.authorities.src008_buckinghamshire                import scrape_buckinghamshire
from scrapers.authorities.src009_cambridgeshire                 import scrape_cambridgeshire
from scrapers.authorities.src010_cardiff                        import scrape_cardiff
from scrapers.authorities.src011_cheshire_west_and_chester      import scrape_cheshire_west_and_chester
from scrapers.authorities.src058_northern_ireland               import scrape_northern_ireland
from scrapers.authorities.src209_wales                          import scrape_wales
from scrapers.source_config                                     import SourceBlockedError, SourceNoDataError, get_source_url



# --------------------------------------------- Input ----------------------------------------------

# Register the available authority scrapers using their SOURCE_ID as the key.
SCRAPERS = {"SRC001": scrape_aberdeenshire
           ,"SRC002": scrape_bath_north_east_somerset
           ,"SRC003": scrape_central_bedfordshire
           ,"SRC004": scrape_birmingham
           ,"SRC005": scrape_bournemouth_christchurch_poole
           ,"SRC006": scrape_bradford
           ,"SRC007": scrape_bristol
           ,"SRC008": scrape_buckinghamshire
           ,"SRC009": scrape_cambridgeshire
           ,"SRC010": scrape_cardiff
           ,"SRC011": scrape_cheshire_west_and_chester
           ,"SRC058": scrape_northern_ireland
           ,"SRC209": scrape_wales}

# Define the columns returned by the authority scrapers.
OUTPUT_COLUMNS = ["SOURCE_ID"
                 ,"ACADEMIC_YEAR"
                 ,"AUTHORITY"
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
            get_source_url(source_id)
            data = SCRAPERS[source_id]()

            records.append(data)

            results.append({"SOURCE_ID" : source_id
                           ,"STATUS"    : "SUCCESS"
                           ,"RECORDS"   : len(data)
                           ,"ERROR"     : None})

        except SourceBlockedError as error:
            results.append({"SOURCE_ID" : source_id
                           ,"STATUS"    : "BLOCKED"
                           ,"RECORDS"   : 0
                           ,"ERROR"     : str(error)})

        except SourceNoDataError as error:
            results.append({"SOURCE_ID" : source_id
                           ,"STATUS"    : "NO_DATA"
                           ,"RECORDS"   : 0
                           ,"ERROR"     : str(error)})

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