import unittest
from unittest.mock import patch

from scrapers.authorities.aberdeenshire import scrape_aberdeenshire


class FakeResponse:

    def __init__(self, content):
        self.content = content.encode("utf-8")

    def raise_for_status(self):
        pass


class AberdeenshireScraperTests(unittest.TestCase):

    def test_scrape_uses_each_linked_calendar_and_keeps_webpage_only_dates(self):
        source_url = "https://council.example/schooltermdates"
        calendar_data = {
            "2026": ("20260817", "20260819", "17 August 2026 to 20 August 2026"),
            "2027": ("20270823", "20270824", "23 August 2027"),
            "2028": ("20280821", "20280822", "21 August 2028"),
            "2029": ("20290820", "20290821", "20 August 2029"),
        }
        page_sections = []
        responses = {}

        for start_year, (start_date, end_date, web_date) in calendar_data.items():
            academic_year = f"{start_year}/{str(int(start_year) + 1)[-2:]}"
            href = ("/schooltermdates/SchoolTerm/DownloadCalendar?year="
                    f"08%2F01%2F{start_year}%2000%3A00%3A00")
            page_sections.append(
                f'<div role="tabpanel"><h2>{academic_year} school term</h2>'
                f'<a href="{href}">Add to calendar</a>'
                f"<ul><li>{web_date} - In-Service Day</li></ul></div>")
            calendar_url = f"https://council.example{href}"
            responses[calendar_url] = FakeResponse(
                "BEGIN:VCALENDAR\n"
                f"X-WR-CALNAME:Aberdeenshire Council School Dates {academic_year}\n"
                "BEGIN:VEVENT\n"
                f"DTSTART;VALUE=DATE:{start_date}\n"
                f"DTEND;VALUE=DATE:{end_date}\n"
                "SUMMARY:In-Service Day\n"
                "END:VEVENT\n"
                "END:VCALENDAR\n")

        responses[source_url] = FakeResponse("".join(page_sections))

        with patch("scrapers.authorities.aberdeenshire.get_source",
                   return_value={"SOURCE_URL": source_url}), \
             patch("scrapers.authorities.aberdeenshire.requests.get",
                   side_effect=lambda url, **kwargs: responses[url]) as get:
            result = scrape_aberdeenshire()

        self.assertEqual(get.call_count, 5)
        self.assertEqual(set(result["ACADEMIC_YEAR"]), {
            "2026/27", "2027/28", "2028/29", "2029/30"})
        self.assertEqual(len(result), 5)

        first_year = result[result["ACADEMIC_YEAR"] == "2026/27"]
        self.assertEqual(first_year["RAW_DATE_TEXT"].tolist(), [
            "Monday 17 August 2026 to Tuesday 18 August 2026",
            "Wednesday 19 August 2026 to Thursday 20 August 2026",
        ])


if __name__ == "__main__":
    unittest.main()
