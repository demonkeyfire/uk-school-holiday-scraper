import unittest
from unittest.mock import patch

from scrapers import source_config
from scrapers.source_config import (
    SourceBlockedError,
    SourceConfigurationError,
    SourceNoDataError,
)


class SourceUrlTests(unittest.TestCase):

    def test_active_source_uses_primary_url(self):
        source = {
            "SOURCE_STATUS": "ACTIVE"
            ,"SOURCE_URL": "https://council.example/primary"
            ,"SOURCE_URL_ALT": "https://council.example/alternative"
        }

        with patch.object(source_config, "get_source", return_value=source):
            self.assertEqual(
                source_config.get_source_url("SRC001")
                ,"https://council.example/primary"
            )

    def test_alternative_source_uses_alternative_url(self):
        source = {
            "SOURCE_STATUS": "ALTERNATIVE"
            ,"SOURCE_URL": "https://council.example/primary"
            ,"SOURCE_URL_ALT": "https://council.example/alternative"
        }

        with patch.object(source_config, "get_source", return_value=source):
            self.assertEqual(
                source_config.get_source_url("SRC001")
                ,"https://council.example/alternative"
            )

    def test_blocked_source_raises_before_a_url_is_returned(self):
        source = {
            "SOURCE_STATUS": "BLOCKED"
            ,"SOURCE_URL": "https://council.example/primary"
            ,"SOURCE_URL_ALT": "https://council.example/alternative"
        }

        with patch.object(source_config, "get_source", return_value=source):
            with self.assertRaises(SourceBlockedError):
                source_config.get_source_url("SRC001")

    def test_no_data_source_raises_before_a_url_is_returned(self):
        source = {
            "SOURCE_STATUS": "NO_DATA"
            ,"SOURCE_URL": "https://council.example/primary"
            ,"SOURCE_URL_ALT": "https://council.example/alternative"
        }

        with patch.object(source_config, "get_source", return_value=source):
            with self.assertRaises(SourceNoDataError):
                source_config.get_source_url("SRC001")

    def test_alternative_source_requires_an_alternative_url(self):
        source = {
            "SOURCE_STATUS": "ALTERNATIVE"
            ,"SOURCE_URL": "https://council.example/primary"
            ,"SOURCE_URL_ALT": None
        }

        with patch.object(source_config, "get_source", return_value=source):
            with self.assertRaises(SourceConfigurationError):
                source_config.get_source_url("SRC001")

    def test_unknown_status_fails_explicitly(self):
        source = {
            "SOURCE_STATUS": "REJECTED"
            ,"SOURCE_URL": "https://council.example/primary"
            ,"SOURCE_URL_ALT": "https://council.example/alternative"
        }

        with patch.object(source_config, "get_source", return_value=source):
            with self.assertRaises(SourceConfigurationError):
                source_config.get_source_url("SRC001")


if __name__ == "__main__":
    unittest.main()
