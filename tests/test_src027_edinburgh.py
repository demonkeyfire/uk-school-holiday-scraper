import unittest
from unittest.mock import Mock, patch

from scrapers.authorities import src027_edinburgh as scraper


class EdinburghScraperTests(unittest.TestCase):

    def test_finds_academic_year_from_dedicated_heading_not_navigation(self):
        webpage = """
            <main>
              <h1>School term dates</h1>
              <h2>School term dates 2027 / 28</h2>
              <a href="/schools/term-dates">School term dates 2026 / 27</a>
              <a href="/schools/term-dates/3">School term dates 2028 / 29</a>
              <p>Autumn Term starts Wednesday 18 August 2027.</p>
            </main>
        """

        soup = scraper.BeautifulSoup(webpage, "html.parser")
        main_content = soup.find("main")
        heading = None

        for candidate in main_content.find_all(["h1", "h2"]):
            if scraper.get_academic_year(
                candidate.get_text(" ", strip=True)
            ) is not None:
                heading = candidate
                break

        self.assertIsNotNone(heading)
        self.assertEqual(
            scraper.get_academic_year(
                heading.get_text(" ", strip=True)
            )
            ,"2027/28"
        )

    def test_get_academic_year_supports_non_breaking_spaces(self):
        self.assertEqual(
            scraper.get_academic_year(
                "School term dates 2028\u00a0/ 29"
            )
            ,"2028/29"
        )


if __name__ == "__main__":
    unittest.main()
