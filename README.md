# UK School Holiday Scraper

A modular Python framework for scraping and standardising UK school holiday and term dates from local authority websites.

## Overview

School holiday and term-date information is published across multiple UK local authority websites, often in different formats and structures. Central repositories, such as Housemait and Term Dates, make this information easier to access, but the dates they publish do not always match the information available on the relevant council websites.

This project aims to collect school holiday and term-date information directly from local authority sources, preserving the original published date text and its source provenance. The resulting dataset will provide a consistent foundation for analysis, comparison with existing repositories, and downstream data engineering workflows.

The project also aims to identify discrepancies between aggregated datasets and official council publications, helping establish a more reliable and traceable source of school holiday information.

## Objectives

* **Collect authoritative data:** Scrape school holiday and term-date information directly from UK local authority websites.
* **Assess data accuracy:** Enable comparisons between official council publications and existing central repositories.
* **Standardise extracted records:** Produce a consistent dataset while retaining the original published date text.
* **Maintain source traceability:** Link every extracted record to its originating source through a unique identifier.
* **Build reusable extraction methods:** Support multiple website structures through shared scraper functions and source-specific logic.
* **Enable downstream use:** Provide a foundation for further analysis, automated data collection and productionisation.

## Output Schema

The scraper produces a tabular dataset with the following fields:

| Field           | Description                                                             |
| --------------- | ----------------------------------------------------------------------- |
| `SOURCE_ID`     | Unique identifier for the source, linked to the source register.        |
| `ACADEMIC_YEAR` | Academic year associated with the event, where identifiable.            |
| `EVENT_NAME`    | Name or description of the school holiday or term-date event.           |
| `RAW_DATE_TEXT` | Date information as published by the source, before date normalisation. |
| `DATE_SCRAPED`  | Date on which the source was scraped, in `YYYY-MM-DD` format.           |

Raw date text is retained to preserve the original published information and support subsequent date parsing and validation.

## Project Structure

```text
uk-school-holiday-scraper/
├── config/
│   └── sources.csv
├── scrapers/
│   ├── authorities/
│   ├── extractors/
│   └── registry.py
├── utils/
├── tests/
├── requirements.txt
├── main.py
└── README.md
```

* `config/`: source register containing source identifiers, URLs and metadata.
* `scrapers/authorities/`: source-specific scraper functions.
* `scrapers/extractors/`: reusable extraction logic for common website formats.
* `scrapers/registry.py`: maps source identifiers to scraper functions.
* `utils/`: shared utilities for validation and date processing.
* `tests/`: tests for extraction logic and output validation.
* `main.py`: entry point for running selected scrapers.

## Running the Scraper

The project is currently developed and tested in Kaggle notebooks.

1. Clone the repository.
2. Install the required Python dependencies.
3. Configure the source identifiers to run.
4. Execute the main script or import the scraper modules into a notebook.

Example:

```bash
git clone https://github.com/<your-username>/uk-school-holiday-scraper.git
cd uk-school-holiday-scraper
pip install -r requirements.txt
python main.py
```

The repository URL and execution instructions should be updated as the project structure is finalised.

## Source Coverage

Sources are maintained in a separate source register. Each source is assigned a unique `SOURCE_ID`, allowing the extracted dataset to be joined back to the source metadata.

Not all sources necessarily use the same publishing format. The framework is intended to accommodate different source types, including HTML tables, structured HTML content and downloadable documents, as support is implemented and tested.

## Data Quality and Limitations

* Source websites may change their layout or URLs, causing extraction failures.
* Some authorities publish dates for individual schools rather than a single authority-wide calendar.
* Date formats and event descriptions may vary between sources.
* A successful scrape does not guarantee that all published dates have been captured.
* Extracted data should be validated before being used in downstream analysis.

## Development Status

This project is under active development. Source coverage, extraction methods and validation checks will evolve as additional websites are assessed and supported.

## Contributing

Contributions are welcome, particularly for:

* Supporting additional local authorities.
* Improving reusable extraction methods.
* Adding tests and data-quality checks.
* Identifying changes to existing source websites.

Please include the relevant `SOURCE_ID`, source URL and example of the published date format when proposing a new scraper or reporting an extraction issue.

## Disclaimer

This project collects publicly available school holiday and term-date information for research and analytical purposes. Extracted information should be checked against the relevant local authority's official publication before being relied upon.

The project is not affiliated with any UK local authority or government department.
