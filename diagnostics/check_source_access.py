
# -------------------------------------------- Overview --------------------------------------------

# Test all configured authority URLs and identify those blocked by Cloudflare.
# Results are classified by HTTP status and Cloudflare-specific response indicators.
# Includes functionality to update URL_RESPONSE in the source configuration.


# --------------------------------------------- Imports --------------------------------------------

import time
import requests
import pandas as pd

from pathlib import Path
from tqdm.auto import tqdm


# --------------------------------------------- Settings -------------------------------------------

SOURCE_FILE = Path("config/sources.csv")
OUTPUT_FILE = Path("data/cloudflare_blocked_sources.csv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

TIMEOUT = 20
REQUEST_DELAY = 1

CLOUDFLARE_INDICATORS = [
    "just a moment",
    "performing security verification",
    "attention required",
    "cloudflare",
    "cf-chl-",
    "__cf_bm",
]


# ----------------------------------------- Diagnostic Function ------------------------------------

def check_source_urls():

    # Load the source configuration.
    sources = pd.read_csv(SOURCE_FILE)

    results = []

    # Check each configured URL independently, displaying progress.
    for _, source in tqdm(
        sources.iterrows(),
        total=len(sources),
        desc="Checking authority URLs",
        unit="URL"
    ):

        source_id = source["SOURCE_ID"]
        authority = source["AUTHORITY_NAME"]
        url = source["SOURCE_URL"]

        if pd.isna(url) or not str(url).strip():

            results.append({
                "SOURCE_ID": source_id,
                "AUTHORITY": authority,
                "URL": url,
                "HTTP_STATUS": None,
                "RESULT": "NO URL",
                "DETAIL": "No source URL configured",
            })

            continue

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
                allow_redirects=True
            )

            # Examine response headers and page content for Cloudflare indicators.
            response_headers = {
                key.lower(): value.lower()
                for key, value in response.headers.items()
            }

            response_text = response.text[:100_000].lower()

            cloudflare_detected = (
                "cloudflare" in response_headers.get("server", "")
                or "cf-ray" in response_headers
                or any(
                    indicator in response_text
                    for indicator in CLOUDFLARE_INDICATORS
                )
            )

            # Classify the response.
            if cloudflare_detected and response.status_code in [403, 429, 503]:

                result = "CLOUDFLARE_BLOCKED"
                detail = "Cloudflare protection detected"

            elif response.status_code == 403:

                result = "HTTP_403_UNCONFIRMED"
                detail = "Forbidden response; Cloudflare not confirmed"

            elif response.status_code == 429:

                result = "HTTP_429"
                detail = "Too many requests"

            elif response.status_code >= 400:

                result = "HTTP_ERROR"
                detail = f"HTTP {response.status_code}"

            else:

                result = "ACCESSIBLE"
                detail = "Request successful"

            results.append({
                "SOURCE_ID": source_id,
                "AUTHORITY": authority,
                "URL": url,
                "HTTP_STATUS": response.status_code,
                "RESULT": result,
                "DETAIL": detail,
            })

        except requests.exceptions.Timeout:

            results.append({
                "SOURCE_ID": source_id,
                "AUTHORITY": authority,
                "URL": url,
                "HTTP_STATUS": None,
                "RESULT": "TIMEOUT",
                "DETAIL": "Request timed out",
            })

        except requests.exceptions.RequestException as error:

            results.append({
                "SOURCE_ID": source_id,
                "AUTHORITY": authority,
                "URL": url,
                "HTTP_STATUS": None,
                "RESULT": "REQUEST_ERROR",
                "DETAIL": str(error),
            })

        # Avoid sending requests too quickly to authority websites.
        time.sleep(REQUEST_DELAY)

    # Build the results DataFrame.
    results_df = pd.DataFrame(results)

    # Extract confirmed Cloudflare blocks.
    blocked_df = results_df[
        results_df["RESULT"] == "CLOUDFLARE_BLOCKED"
    ].copy()

    # Export the confirmed blocked URLs.
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    blocked_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    return results_df, blocked_df


# -------------------------------------- Update Source Configuration --------------------------------

def update_source_config(results_df):

    # Load the existing source configuration.
    sources = pd.read_csv(SOURCE_FILE)

    # Update URL_RESPONSE using the diagnostic results.
    for _, result in results_df.iterrows():

        mask = sources["SOURCE_ID"] == result["SOURCE_ID"]

        if mask.any():
            sources.loc[mask, "URL_RESPONSE"] = result["RESULT"]

    # Save the updated source configuration.
    sources.to_csv(SOURCE_FILE, index=False)

    return sources


# --------------------------------------------- Run ------------------------------------------------

if __name__ == "__main__":

    results, cloudflare_blocked = check_source_urls()

    print("\n---------------------------------------------")
    print("CLOUDFLARE BLOCKED SOURCES")
    print("---------------------------------------------")

    display(cloudflare_blocked)

    print(f"\nTotal URLs checked: {len(results)}")
    print(f"Cloudflare blocked: {len(cloudflare_blocked)}")
    print(
        "Other HTTP 403 responses:",
        (results["RESULT"] == "HTTP_403_UNCONFIRMED").sum()
    )

    print(f"\nResults saved to: {OUTPUT_FILE}")
