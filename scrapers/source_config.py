
# -------------------------------------------- Overview --------------------------------------------

# Load and retrieve source metadata from the central sources.csv register.
# This keeps source URLs and authority information in one place, rather than hardcoding them
# in individual scraping modules.



# --------------------------------------------- Imports ---------------------------------------------

import pandas as pd



# -------------------------------------------- Configuration ---------------------------------------

# Path to the central source register.
SOURCES_PATH = "config/sources.csv"



# ---------------------------------------------- Functions -----------------------------------------

def load_sources():
    """
    Load the source register into a pandas DataFrame.

    Returns:
        pd.DataFrame: All source records from sources.csv.
    """

    sources = pd.read_csv(SOURCES_PATH)

    return sources


def get_source(source_id):
    """
    Retrieve a single source record using its SOURCE_ID.

    Args:
        source_id (str): Unique identifier for the source.

    Returns:
        pd.Series: The matching source record.

    Raises:
        ValueError: If the SOURCE_ID does not exist in the source register.
    """

    # Load the source register.
    sources = load_sources()

    # Filter the register to the requested source ID.
    source = sources.loc[
        sources["SOURCE_ID"] == source_id
    ]

    # Check that the requested source ID exists.
    if source.empty:
        raise ValueError(f"Unknown SOURCE_ID: {source_id}")

    # Return the matching source record.
    return source.iloc[0]
