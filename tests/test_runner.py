import unittest
from unittest.mock import Mock, patch

from scrapers import runner
from scrapers.source_config import SourceBlockedError, SourceNoDataError


class RunnerSourceStatusTests(unittest.TestCase):

    def test_blocked_source_is_not_invoked_and_is_reported_as_blocked(self):
        scraper = Mock()

        with (
            patch.dict(runner.SCRAPERS, {"SRC001": scraper})
            ,patch.object(
                runner
                ,"get_source_url"
                ,side_effect=SourceBlockedError("SRC001 is blocked")
            )
        ):
            records, summary = runner.run_scrapers(["SRC001"])

        scraper.assert_not_called()
        self.assertTrue(records.empty)
        self.assertEqual(summary.iloc[0]["STATUS"], "BLOCKED")
        self.assertEqual(summary.iloc[0]["RECORDS"], 0)

    def test_no_data_source_is_not_invoked_and_is_reported_as_no_data(self):
        scraper = Mock()

        with (
            patch.dict(runner.SCRAPERS, {"SRC001": scraper})
            ,patch.object(
                runner
                ,"get_source_url"
                ,side_effect=SourceNoDataError("SRC001 has no authority-wide dates")
            )
        ):
            records, summary = runner.run_scrapers(["SRC001"])

        scraper.assert_not_called()
        self.assertTrue(records.empty)
        self.assertEqual(summary.iloc[0]["STATUS"], "NO_DATA")
        self.assertEqual(summary.iloc[0]["RECORDS"], 0)


if __name__ == "__main__":
    unittest.main()
