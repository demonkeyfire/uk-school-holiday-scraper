from datetime import date
import unittest
from unittest.mock import Mock, call, patch

from bs4 import BeautifulSoup

from scrapers.authorities import src209_wales as scraper


class WalesScraperTests(unittest.TestCase):

    def test_extracts_dates_from_authority_tables(self):
        webpage = """
            <h2>Approved school term dates 2025 to 2026</h2>
            <h2>Anglesey</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr>
                    <td>Autumn Term 2025</td>
                    <td>Monday 01 September</td>
                    <td>Friday 19 December</td>
                </tr>
                <tr>
                    <td>Autumn Half Term 2025</td>
                    <td>Monday 27 October</td>
                    <td>Friday 31 October</td>
                </tr>
            </table>
            <h2>Cardiff</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr>
                    <td>Summer Term 2026</td>
                    <td>Monday 13 April</td>
                    <td>Monday 20 July</td>
                </tr>
            </table>
        """

        records = scraper.extract_page_records(
            BeautifulSoup(webpage, "html.parser")
            ,"2025/26"
            ,date(2026, 11, 20)
        )

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["AUTHORITY"], "Anglesey")
        self.assertEqual(records[0]["EVENT_NAME"], "Autumn Term 2025")
        self.assertEqual(
            records[0]["RAW_DATE_TEXT"]
            ,"Monday 01 September to Friday 19 December"
        )
        self.assertEqual(records[2]["AUTHORITY"], "Cardiff")

    def test_extracts_all_dated_entries_from_term_sections(self):
        webpage = """
            <h2>Approved school term dates 2027 to 2028</h2>
            <h2>Anglesey</h2>
            <h3>Autumn term 2027</h3>
            <p>Term starts: Wednesday 1 September 2027 (schools opening for learners 2 September)</p>
            <p>Half term holiday: Monday 25 October 2027 to Friday 29 October 2027</p>
            <p>Term ends: Wednesday 22 December 2027</p>
            <p>Christmas holiday: Thursday 23 December 2027 to Wednesday 5 January 2028</p>
            <h3>Spring term 2028</h3>
            <p>Term starts: Thursday 6 January 2028</p>
            <p>Half term holiday: Monday 21 February 2028 to Friday 25 February 2028</p>
            <p>Term ends: Friday 7 April 2028</p>
            <p>Easter holiday: Monday 10 April 2028 to Friday 21 April 2028</p>
            <h3>Summer term 2028</h3>
            <p>Term starts: Monday 24 April 2028</p>
            <p>Half term holiday: Monday 29 May 2028 to Friday 2 June 2028</p>
            <p>Term ends: Wednesday 19 July 2028</p>
        """

        records = scraper.extract_page_records(
            BeautifulSoup(webpage, "html.parser")
            ,"2027/28"
            ,date(2026, 11, 20)
        )

        self.assertEqual(len(records), 11)
        self.assertEqual(records[0]["AUTHORITY"], "Anglesey")
        self.assertEqual(
            records[0]["EVENT_NAME"]
            ,"Autumn term 2027 - Term Starts"
        )
        self.assertIn("2 September", records[0]["RAW_DATE_TEXT"])
        self.assertEqual(
            records[-1]["EVENT_NAME"]
            ,"Summer term 2028 - Term Ends"
        )

    def test_scraper_follows_index_and_html_document_links(self):
        source_url = "https://www.gov.wales/school-terms-holidays-and-closures"
        index = """
            <a href="/approved-school-term-dates-2025-2026">
                Approved school term dates 2025 to 2026
            </a>
            <a href="/approved-school-term-dates-2026-2027">
                Approved school term dates 2026 to 2027
            </a>
            <a href="/approved-school-term-dates-2027-2028">
                Approved school term dates 2027 to 2028
            </a>
        """
        landing = """
            <a href="/approved-school-term-dates-2025-2026-html">
                Approved school term dates 2025 to 2026, HTML
            </a>
        """
        table_page = """
            <h2>Anglesey</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr><td>Autumn Term 2025</td><td>Monday 01 September</td>
                    <td>Friday 19 December</td></tr>
            </table>
        """
        page_2026 = """
            <h2>Cardiff</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr><td>Autumn Term 2026</td><td>Tuesday 01 September</td>
                    <td>Friday 18 December</td></tr>
            </table>
        """
        page_2027 = """
            <h2>Newport</h2>
            <h3>Autumn term 2027</h3>
            <p>Term starts: Wednesday 1 September 2027</p>
        """
        responses = []

        for content in (
            index
            ,landing
            ,table_page
            ,page_2026
            ,page_2027
        ):
            response = Mock(content=content.encode())
            response.raise_for_status.return_value = None
            responses.append(response)

        with (
            patch.object(
                scraper
                ,"get_source_url"
                ,return_value=source_url
            )
            ,patch.object(
                scraper.requests
                ,"get"
                ,side_effect=responses
            ) as get_request
        ):
            records = scraper.scrape_wales()

        self.assertEqual(get_request.call_count, 5)
        self.assertEqual(
            list(records["ACADEMIC_YEAR"].drop_duplicates())
            ,["2025/26", "2026/27", "2027/28"]
        )
        self.assertEqual(records["AUTHORITY"].tolist(), ["Anglesey", "Cardiff", "Newport"])

    def test_scraper_can_return_one_authority_for_cardiff_fallback(self):
        source_url = "https://www.gov.wales/school-terms-holidays-and-closures"
        index = """
            <a href="/approved-school-term-dates-2025-2026">
                Approved school term dates 2025 to 2026
            </a>
            <a href="/approved-school-term-dates-2026-2027">
                Approved school term dates 2026 to 2027
            </a>
            <a href="/approved-school-term-dates-2027-2028">
                Approved school term dates 2027 to 2028
            </a>
        """
        page = """
            <h2>Cardiff</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr><td>Autumn Term</td><td>Monday 01 September</td>
                    <td>Friday 19 December</td></tr>
            </table>
            <h2>Newport</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr><td>Autumn Term</td><td>Monday 01 September</td>
                    <td>Friday 19 December</td></tr>
            </table>
        """
        responses = []

        for content in (index, page, page, page):
            response = Mock(content=content.encode())
            response.raise_for_status.return_value = None
            responses.append(response)

        with (
            patch.object(
                scraper
                ,"get_source_url"
                ,return_value=source_url
            )
            ,patch.object(
                scraper.requests
                ,"get"
                ,side_effect=responses
            )
        ):
            records = scraper.scrape_wales_authority("Cardiff")

        self.assertEqual(records["SOURCE_ID"].unique().tolist(), ["SRC209"])
        self.assertEqual(records["AUTHORITY"].unique().tolist(), ["Cardiff"])
        self.assertEqual(
            records["ACADEMIC_YEAR"].drop_duplicates().tolist()
            ,["2025/26", "2026/27", "2027/28"]
        )

    def test_alternative_year_page_is_used_with_index_for_remaining_years(self):
        alternative_url = (
            "https://www.gov.wales/approved-school-term-dates-2026-2027-html#174748"
        )
        index_url = "https://www.gov.wales/school-terms-holidays-and-closures"
        alternative_page = """
            <h2>Approved school term dates 2026 to 2027</h2>
            <h2>Cardiff</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr><td>Autumn Term 2026</td><td>Tuesday 01 September</td>
                    <td>Friday 18 December</td></tr>
            </table>
        """
        index = """
            <a href="/approved-school-term-dates-2025-2026">
                Approved school term dates 2025 to 2026
            </a>
            <a href="/approved-school-term-dates-2026-2027">
                Approved school term dates 2026 to 2027
            </a>
            <a href="/approved-school-term-dates-2027-2028">
                Approved school term dates 2027 to 2028
            </a>
        """
        page_2025 = """
            <h2>Cardiff</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr><td>Autumn Term 2025</td><td>Monday 01 September</td>
                    <td>Friday 19 December</td></tr>
            </table>
        """
        page_2027 = """
            <h2>Cardiff</h2>
            <table>
                <tr><th>Period</th><th>Start</th><th>End</th></tr>
                <tr><td>Autumn Term 2027</td><td>Wednesday 01 September</td>
                    <td>Friday 17 December</td></tr>
            </table>
        """
        responses = []

        for content in (
            alternative_page
            ,index
            ,page_2025
            ,page_2027
        ):
            response = Mock(content=content.encode())
            response.raise_for_status.return_value = None
            responses.append(response)

        def source_url_for(source_id):
            return alternative_url if source_id == "SRC010" else index_url

        with (
            patch.object(
                scraper
                ,"get_source_url"
                ,side_effect=source_url_for
            ) as get_source_url
            ,patch.object(
                scraper.requests
                ,"get"
                ,side_effect=responses
            )
        ):
            records = scraper.scrape_wales_authority(
                "Cardiff"
                ,source_id="SRC010"
            )

        self.assertEqual(
            get_source_url.call_args_list
            ,[call("SRC010"), call("SRC209")]
        )
        self.assertEqual(
            records["ACADEMIC_YEAR"].drop_duplicates().tolist()
            ,["2025/26", "2026/27", "2027/28"]
        )
        self.assertEqual(
            records.set_index("ACADEMIC_YEAR")["SOURCE_ID"].to_dict()
            ,{"2025/26": "SRC209", "2026/27": "SRC010", "2027/28": "SRC209"}
        )


if __name__ == "__main__":
    unittest.main()
