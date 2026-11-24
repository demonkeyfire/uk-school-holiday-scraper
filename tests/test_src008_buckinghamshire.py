from datetime import date
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

from scrapers.authorities import src008_buckinghamshire as scraper


PDF_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "school_calendars"
    / "src008_buckinghamshire"
)


class BuckinghamshirePdfTests(unittest.TestCase):

    def test_pdf_links_and_records_for_both_future_years(self):
        source_url = "https://council.example/school-dates"
        webpage = """
            <a href="/2026/School_Term_Dates_2026_to_2027_PDF.pdf">
                School term dates 2026 to 2027 PDF
            </a>
            <a href="/2027/Bucks_final_term_dates_2027_2028.pdf">
                Bucks final term dates 2027 2028
            </a>
        """
        links = scraper.find_pdf_calendar_links(
            BeautifulSoup(webpage, "html.parser")
            ,source_url
        )

        self.assertEqual(
            [academic_year for academic_year, _ in links]
            ,["2026/27", "2027/28"]
        )

        pdf_cases = [
            ("2026/27", "School_Term_Dates_2026_to_2027_PDF.pdf")
            ,("2027/28", "Bucks_final_term_dates_2027_2028.pdf")
        ]

        for academic_year, filename in pdf_cases:
            records = scraper.extract_pdf_calendar(
                (PDF_DIRECTORY / filename).read_bytes()
                ,academic_year
                ,date.today()
            )

            self.assertTrue(records)
            self.assertTrue(
                all(record["ACADEMIC_YEAR"] == academic_year for record in records)
            )

    def test_2026_27_weekend_cells_are_not_school_holidays(self):
        records = scraper.extract_pdf_calendar(
            (
                PDF_DIRECTORY
                / "School_Term_Dates_2026_to_2027_PDF.pdf"
            ).read_bytes()
            ,"2026/27"
            ,date.today()
        )
        school_holidays = [
            record for record in records
            if record["EVENT_NAME"] == "School Holiday"
        ]

        self.assertTrue(school_holidays)

        for record in school_holidays:
            for match in scraper.DATE_PATTERN.finditer(record["RAW_DATE_TEXT"]):
                holiday_date = date(
                    int(match.group(3))
                    ,scraper.MONTH_NUMBERS[match.group(2).title()]
                    ,int(match.group(1))
                )

                self.assertLess(
                    holiday_date.weekday()
                    ,5
                    ,record["RAW_DATE_TEXT"]
                )

    def test_scraper_uses_pdf_responses_for_future_years(self):
        source_url = "https://council.example/school-dates"
        webpage = f"""
            <h2>2026 to 2027 school year</h2>
            <table><tr><th>Term starts</th><td>Tuesday 1 September 2026</td></tr></table>
            <a href="/2025_26_academic_year_Term_Dates.xlsx">
                2025/26 Excel calendar
            </a>
            <a href="/2026/School_Term_Dates_2026_to_2027_PDF.pdf">
                PDF term dates 2026 to 2027
            </a>
            <a href="/2027/Bucks_final_term_dates_2027_2028.pdf">
                PDF term dates 2027 to 2028
            </a>
        """
        page_response = Mock(content=webpage.encode())
        page_response.raise_for_status.return_value = None
        excel_response = Mock(
            content=(
                PDF_DIRECTORY / "2025_26_academic_year_Term_Dates.xlsx"
            ).read_bytes()
        )
        excel_response.raise_for_status.return_value = None

        pdf_responses = []

        for filename in (
            "School_Term_Dates_2026_to_2027_PDF.pdf"
            ,"Bucks_final_term_dates_2027_2028.pdf"
        ):
            response = Mock(
                content=(PDF_DIRECTORY / filename).read_bytes()
            )
            response.raise_for_status.return_value = None
            pdf_responses.append(response)

        with (
            patch.object(
                scraper
                ,"get_source_url"
                ,return_value=source_url
            )
            ,patch.object(
                scraper.requests
                ,"get"
                ,side_effect=[page_response, excel_response, *pdf_responses]
            )
        ):
            records = scraper.scrape_buckinghamshire()

        self.assertIn("2026/27", set(records["ACADEMIC_YEAR"]))
        self.assertIn("2027/28", set(records["ACADEMIC_YEAR"]))


if __name__ == "__main__":
    unittest.main()
