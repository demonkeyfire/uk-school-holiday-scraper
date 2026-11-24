import unittest
from unittest.mock import call, patch

import pandas as pd

from scrapers.authorities import src010_cardiff as scraper
from scrapers.source_config import SourceBlockedError


class CardiffScraperTests(unittest.TestCase):

    def test_uses_its_registered_source_and_returns_records(self):
        records = pd.DataFrame(
            [{"SOURCE_ID": "SRC010", "AUTHORITY": "Cardiff"}]
        )

        with patch.object(
            scraper
            ,"scrape_wales_authority"
            ,return_value=records
        ) as scrape_authority:
            result = scraper.scrape_cardiff()

        scrape_authority.assert_called_once_with(
            "Cardiff"
            ,source_id="SRC010"
        )
        self.assertIs(result, records)

    def test_unusable_cardiff_source_falls_back_to_wales_index(self):
        fallback_records = pd.DataFrame(
            [{"SOURCE_ID": "SRC209", "AUTHORITY": "Cardiff"}]
        )

        with patch.object(
            scraper
            ,"scrape_wales_authority"
            ,side_effect=[ValueError("No dates found"), fallback_records]
        ) as scrape_authority:
            result = scraper.scrape_cardiff()

        self.assertEqual(
            scrape_authority.call_args_list
            ,[
                call("Cardiff", source_id="SRC010")
                ,call("Cardiff")
            ]
        )
        self.assertIs(result, fallback_records)

    def test_blocked_cardiff_source_does_not_fall_back(self):
        with patch.object(
            scraper
            ,"scrape_wales_authority"
            ,side_effect=SourceBlockedError("SRC010 is blocked")
        ) as scrape_authority:
            with self.assertRaises(SourceBlockedError):
                scraper.scrape_cardiff()

        scrape_authority.assert_called_once_with(
            "Cardiff"
            ,source_id="SRC010"
        )


if __name__ == "__main__":
    unittest.main()
