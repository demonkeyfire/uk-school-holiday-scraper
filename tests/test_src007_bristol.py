import contextlib
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from scrapers.authorities import src007_bristol as scraper


PDF_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "school_calendars"
    / "src007_bristol"
)


class BristolPdfTests(unittest.TestCase):

    def run_scraper(self, fail_first_pdf_terms=False):
        source_url = "https://council.example/school-dates"
        pdf_urls = [
            "/files/documents/2026"
            ,"/files/documents/2027"
        ]
        webpage = f"""
            <h2>2026 to 2027</h2>
            <ul><li>Term 1: web term 1 for 2026</li></ul>
            <a type="application/pdf" href="{pdf_urls[0]}">
                PDF term planner 2026 to 2027
            </a>
            <h2>2027 to 2028</h2>
            <ul><li>Term 1: web term 1 for 2027</li></ul>
            <a type="application/pdf" href="{pdf_urls[1]}">
                PDF term planner 2027 to 2028
            </a>
        """
        page_response = Mock(content=webpage.encode())
        page_response.raise_for_status.return_value = None
        pdf_responses = [
            Mock(content=(
                PDF_DIRECTORY / "BCC School Term Dates 2026 2027.pdf"
            ).read_bytes())
            ,Mock(content=(
                PDF_DIRECTORY / "BCC School Term Dates 2027 2028.pdf"
            ).read_bytes())
        ]

        for pdf_response in pdf_responses:
            pdf_response.raise_for_status.return_value = None

        original_term_parser = scraper.extract_pdf_term_records

        def term_parser(calendar_text, academic_year, school_holiday_dates,
                        bank_holiday_dates, date_scraped):
            if fail_first_pdf_terms and academic_year == "2026/27":
                raise ValueError("Invalid term date text")

            return original_term_parser(
                calendar_text
                ,academic_year
                ,school_holiday_dates
                ,bank_holiday_dates
                ,date_scraped
            )

        with (
            patch.object(
                scraper
                ,"get_source_url"
                ,return_value=source_url
            )
            ,patch.object(
                scraper.requests
                ,"get"
                ,side_effect=[page_response] + pdf_responses
            )
            ,patch.object(
                scraper
                ,"extract_pdf_term_records"
                ,side_effect=term_parser
            )
            ,contextlib.redirect_stdout(StringIO())
        ):
            return scraper.scrape_bristol()

    def test_linked_pdfs_supply_terms_and_colored_holidays(self):
        records = self.run_scraper()

        self.assertEqual(
            len(records[records["EVENT_NAME"].str.startswith("Term ")])
            ,12
        )
        self.assertEqual(
            len(records[records["EVENT_NAME"] == "Bank Holiday"])
            ,16
        )
        self.assertEqual(
            len(records[records["EVENT_NAME"] == "School Holiday"])
            ,17
        )
        self.assertIn(
            "(37 Days)"
            ,records.loc[
                (records["ACADEMIC_YEAR"] == "2026/27")
                & (records["EVENT_NAME"] == "Term 1")
                ,"RAW_DATE_TEXT"
            ].iloc[0]
        )

    def test_pdf_holidays_remain_when_term_dates_fail(self):
        records = self.run_scraper(fail_first_pdf_terms=True)
        first_year_terms = records[
            (records["ACADEMIC_YEAR"] == "2026/27")
            & records["EVENT_NAME"].str.startswith("Term ")
        ]

        self.assertEqual(len(first_year_terms), 1)
        self.assertEqual(
            first_year_terms.iloc[0]["RAW_DATE_TEXT"]
            ,"web term 1 for 2026"
        )
        self.assertTrue(
            (
                (records["ACADEMIC_YEAR"] == "2026/27")
                & (records["EVENT_NAME"] == "School Holiday")
            ).any()
        )
        self.assertTrue(
            (
                (records["ACADEMIC_YEAR"] == "2026/27")
                & (records["EVENT_NAME"] == "Bank Holiday")
            ).any()
        )


if __name__ == "__main__":
    unittest.main()
