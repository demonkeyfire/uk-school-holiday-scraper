import contextlib
from io import BytesIO, StringIO
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pdfplumber

from scrapers.authorities import src003_central_bedfordshire as scraper


PDF_PATH = (
    Path(__file__).resolve().parents[1]
    / "school_calendars"
    / "src003_central_bedfordshire"
    / "2026-2027 school term and holiday dates.pdf"
)


class CentralBedfordshirePdfTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pdf_content = PDF_PATH.read_bytes()

    def test_term_day_count_catches_bad_pdf_range(self):
        with pdfplumber.open(BytesIO(self.pdf_content)) as calendar_pdf:
            page = calendar_pdf.pages[0]
            calendar_text = page.extract_text()
            with contextlib.redirect_stdout(StringIO()):
                event_dates = scraper.extract_calendar_event_dates(
                    page
                    ,"2026/27"
                )

        with self.assertRaisesRegex(
            ValueError
            ,"Expected 35 term weekdays.*found 51"
        ):
            scraper.get_term_periods(
                calendar_text
                ,"2026/27"
                ,event_dates["School Holiday"]
                ,event_dates["Bank Holiday"]
                ,event_dates["Teacher Training Day"]
            )

        corrected_text = calendar_text.replace(
            "2/10/26 - 18/12/26 35"
            ,"2/11/26 - 18/12/26 35"
        )
        term_periods = scraper.get_term_periods(
            corrected_text
            ,"2026/27"
            ,event_dates["School Holiday"]
            ,event_dates["Bank Holiday"]
            ,event_dates["Teacher Training Day"]
        )

        self.assertEqual(len(term_periods), 3)

    def test_pdf_holidays_survive_invalid_term_dates(self):
        source_url = "https://council.example/school-dates"
        pdf_url = "https://council.example/calendar.pdf"
        webpage = f"""
            <h2>2026 to 2027 school year</h2>
            <ul>
                <li>term starts on
                    <strong>Thursday, 3 September 2026</strong>
                </li>
                <li>half-term
                    <strong>Monday, 26 October to Friday, 30 October 2026</strong>
                </li>
                <li>term ends on
                    <strong>Wednesday, 21 July 2027</strong>
                </li>
            </ul>
            <a href="{pdf_url}">Download PDF 2026 to 2027</a>
        """
        page_response = Mock(content=webpage.encode())
        page_response.raise_for_status.return_value = None
        pdf_response = Mock(content=self.pdf_content)
        pdf_response.raise_for_status.return_value = None

        with (
            patch.object(
                scraper
                ,"get_source"
                ,return_value={"SOURCE_URL": source_url}
            )
            ,patch.object(
                scraper.requests
                ,"get"
                ,side_effect=[page_response, pdf_response]
            )
            ,contextlib.redirect_stdout(StringIO())
        ):
            records = scraper.scrape_central_bedfordshire()

        events = set(records["EVENT_NAME"])
        self.assertIn("School Holiday", events)
        self.assertIn("Bank Holiday", events)
        self.assertIn("term starts", events)
        self.assertIn("term ends", events)
        self.assertNotIn("half-term", events)
        self.assertTrue(
            records["RAW_DATE_TEXT"].str.contains("26 October").any()
        )


if __name__ == "__main__":
    unittest.main()
