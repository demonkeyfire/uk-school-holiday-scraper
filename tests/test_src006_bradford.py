import unittest
from bs4 import BeautifulSoup

from scrapers.authorities import src006_bradford as scraper


class BradfordCalendarLinkTests(unittest.TestCase):

    def test_finds_word_calendars_for_all_supported_years(self):
        webpage = """
            <a href="/files/Bradford%20Term%20Dates%202025-26.docx">
                2025/26
            </a>
            <a href="/files/Bradford%20Term%20Dates%202025-26.pdf">
                2025/26 PDF
            </a>
            <a href="/files/Bradford%20Term%20Dates%202026-27.docx">
                2026/27
            </a>
            <a href="/files/Bradford%20Term%20Dates%202027-28.docx">
                2027/28
            </a>
        """

        urls = scraper.find_document_urls(
            BeautifulSoup(webpage, "html.parser")
            ,"https://council.example/term-dates"
        )

        self.assertEqual(
            urls
            ,{
                "2025/26": "https://council.example/files/Bradford%20Term%20Dates%202025-26.docx"
                ,"2026/27": "https://council.example/files/Bradford%20Term%20Dates%202026-27.docx"
                ,"2027/28": "https://council.example/files/Bradford%20Term%20Dates%202027-28.docx"
            }
        )

    def test_missing_word_calendar_fails_explicitly(self):
        webpage = """
            <a href="/files/Bradford%20Term%20Dates%2025-26.docx">2025/26</a>
        """

        with self.assertRaisesRegex(ValueError, "2026/27"):
            scraper.find_document_urls(
                BeautifulSoup(webpage, "html.parser")
                ,"https://council.example/term-dates"
            )


if __name__ == "__main__":
    unittest.main()
