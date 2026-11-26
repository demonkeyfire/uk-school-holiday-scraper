import unittest
from unittest.mock import Mock, patch

from scrapers.authorities import src021_dundee as scraper


class DundeeScraperTests(unittest.TestCase):

    def test_extracts_accordion_dates_and_section_context(self):
        webpage = """
            <main>
              <dl>
                <dt>Academic Year 2026-27</dt>
                <dd>
                  <p><strong>Autumn Term</strong></p>
                  <ul>
                    <li>Monday 17 August 2026 - Staff resume</li>
                    <li>Friday 26 March 2027 (Good Friday) - Holiday starts</li>
                  </ul>
                </dd>
              </dl>
            </main>
        """

        response = Mock()
        response.text = webpage
        response.raise_for_status = Mock()

        with (
            patch.object(
                scraper
                ,"get_source_url"
                ,return_value="https://dundee.example/term-dates"
            ) as get_url
            ,patch.object(
                scraper.requests
                ,"get"
                ,return_value=response
            ) as get
        ):
            result = scraper.scrape_dundee()

        get_url.assert_called_once_with("SRC021")
        get.assert_called_once()

        self.assertEqual(result.shape[0], 2)
        self.assertEqual(result.iloc[0]["SOURCE_ID"], "SRC021")
        self.assertEqual(result.iloc[0]["ACADEMIC_YEAR"], "2026/27")
        self.assertEqual(result.iloc[0]["AUTHORITY"], "Dundee")
        self.assertEqual(result.iloc[0]["EVENT_NAME"], "Autumn Term - Staff resume")
        self.assertEqual(
            result.iloc[1]["RAW_DATE_TEXT"]
            ,"Friday 26 March 2027 (Good Friday)"
        )


if __name__ == "__main__":
    unittest.main()
