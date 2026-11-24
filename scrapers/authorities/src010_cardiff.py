# -------------------------------------------- Overview --------------------------------------------

# Retrieve Cardiff school-term and holiday events from the council, with a Welsh Government fallback.



# --------------------------------------------- Imports --------------------------------------------

import requests

from scrapers.authorities.src209_wales import scrape_wales_authority


# --------------------------------------------- Input ----------------------------------------------

SOURCE_ID = "SRC010"

# ------------------------------------------- Main Code --------------------------------------------

def scrape_cardiff():

    """Retrieve Cardiff school-term dates, falling back to the Welsh Government."""

    try:
        return scrape_wales_authority(
            "Cardiff"
            ,source_id=SOURCE_ID
        )
    except (requests.RequestException, ValueError):
        return scrape_wales_authority("Cardiff")
