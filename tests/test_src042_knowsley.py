import unittest
from unittest.mock import Mock, patch

from scrapers.authorities import src042_knowsley as scraper


class KnowsleyTermDateTests(unittest.TestCase):

    def test_extracts_table_rows_for_each_academic_year(self):
        webpage = """
            <h2>School year 2026/2027</h2>
            <table>
                <tr>
                    <th>Autumn term 2026</th>
                    <td>Tuesday 1 September – Friday 18 December</td>
                </tr>
                <tr>
                    <th>Half term</th>
                    <td>Monday 26 October – Friday 30 October</td>
                </tr>
            </table>
            <h2>School year 2027/2028</h2>
            <table>
                <tr>
                    <th>Spring term 2028</th>
                    <td>Tuesday 4 January – Friday 7 April</td>
                </tr>
            </table>
        """
        response = Mock(content=webpage.encode())
        response.raise_for_status.return_value = None

        with (
            patch.object(scraper, "get_source_url", return_value="https://council.example/term-dates"),
            patch.object(scraper.requests, "get", return_value=response),
        ):
            results = scraper.scrape_knowsley()

        self.assertEqual(
            results["ACADEMIC_YEAR"].tolist(),
            ["2026/27", "2026/27", "2027/28"],
        )
        self.assertEqual(
            results["EVENT_NAME"].tolist(),
            ["Autumn term 2026", "Half term", "Spring term 2028"],
        )
        self.assertEqual(
            results["RAW_DATE_TEXT"].tolist(),
            [
                "Tuesday 1 September – Friday 18 December",
                "Monday 26 October – Friday 30 October",
                "Tuesday 4 January – Friday 7 April",
            ],
        )


if __name__ == "__main__":
    unittest.main()
