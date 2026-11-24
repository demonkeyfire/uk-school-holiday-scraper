
# -------------------------------------------- Overview --------------------------------------------

# Load and retrieve source metadata from the central source register so scraping modules do not
# duplicate URLs, authorities and other configuration details.



# --------------------------------------------- Imports --------------------------------------------

import pandas as pd


class SourceBlockedError(RuntimeError):

    """Raised when a source is marked BLOCKED in the source register."""


class SourceConfigurationError(RuntimeError):

    """Raised when a source status or its corresponding URL is invalid."""



# --------------------------------------------- Input ----------------------------------------------

# The canonical metadata source that defines every scraper's configuration.
SOURCES_PATH = "config/sources.csv"



# ------------------------------------------- Main Code --------------------------------------------

# Return the central source register so downstream scrapers can resolve metadata consistently.
def load_sources():

    """
    Return the source register as a pandas DataFrame.

    This keeps scraper configuration in one place and avoids scattering source metadata across
    individual modules.
    """

    sources = pd.read_csv(SOURCES_PATH)

    return sources


# Retrieve a single source record by SOURCE_ID and fail clearly when it is missing.
def get_source(source_id):

    """
    Return the matching source record for a given SOURCE_ID.

    This is intended for lookup-only access by scraping modules that need a single source's
    metadata. The function raises a clear error so callers can fail fast when a source is not
    registered.

    Parameters
    ----------
    source_id : str
        Unique source identifier, e.g. 'MY_SOURCE'.

    Returns
    -------
    pd.Series
        The matching row from the central source register.

    Raises
    ------
    ValueError
        Raised when `source_id` does not exist in `config/sources.csv`.
    """

    sources = load_sources()
    source = sources.loc[sources["SOURCE_ID"].eq(source_id), :].copy()

    if source.empty:
        raise ValueError(f"Unknown SOURCE_ID: {source_id}")

    return source.iloc[0]


# Select the URL that is permitted by the source's status in the central register.
def get_source_url(source_id):

    """
    Return the URL selected by SOURCE_STATUS for a given source.

    ACTIVE sources use SOURCE_URL, ALTERNATIVE sources use SOURCE_URL_ALT, and BLOCKED sources
    raise SourceBlockedError so callers can skip scraping without making a request.
    """

    source = get_source(source_id)
    status = str(source["SOURCE_STATUS"]).strip().upper()

    if status == "BLOCKED":
        raise SourceBlockedError(f"{source_id} is marked BLOCKED in {SOURCES_PATH}")

    url_column = {
        "ACTIVE": "SOURCE_URL"
        ,"ALTERNATIVE": "SOURCE_URL_ALT"
    }.get(status)

    if url_column is None:
        raise SourceConfigurationError(
            f"Unsupported SOURCE_STATUS {status!r} for {source_id}"
        )

    source_url = source[url_column]

    if pd.isna(source_url) or not str(source_url).strip():
        raise SourceConfigurationError(
            f"{source_id} has no URL in {url_column} for SOURCE_STATUS {status}"
        )

    return str(source_url).strip()
