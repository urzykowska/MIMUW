import unittest
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from wiki_scraper import Scraper

class TestWikiScraper(unittest.TestCase):
    def setUp(self):
        # Przygotowanie środowiska:
        self.test_file = "test_page.html"
        html_content = """
        <html>
        <body>
            <div id="mw-content-text">
                <p> This is the first paragraph. </p>
                <p> This is the second paragraph. </p>
                <a href="/wiki/Pikachu">Pikachu</a>
                <a href="/wiki/File:Image.png">Image (invalid)</a>
                <a href="https://google.com"Google (invalid)</a>
                <a href="/wiki/Charmander">Charmander</a>
            </div>
        </body>
        </html>
        """

        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(html_content)

    def tearDown(self):
        # Sprzątanie po teście:
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
    
    # Test pobierania pierwszego paragrafu (summary)
    def test_get_summary(self):
        scraper = Scraper(
            base_url="http://dummy",
            phrase="Test",
            use_local_html_file_instead=True,
            local_file_path=self.test_file
        )
        result=scraper.get_summary()
        self.assertEqual(result, "This is the first paragraph.")

    # Test pobierania linków (powinien ignorować pliki i linki zewnętrzne)
    def test_get_valid_links(self):
        scraper = Scraper(
            base_url="http://dummy",
            phrase="Test",
            use_local_html_file_instead=True,
            local_file_path=self.test_file
        )
        links = scraper.get_valid_links()
        # Sprawdzamy, czy znalazł poprawne:
        self.assertIn("Pikachu", links)
        self.assertIn("Charmander", links)
        # Sprawdzamy, czy odrzucił błędne:
        self.assertNotIn("File:Image.png", links)
        self.assertNotIn("google.com", links)

    # Test zliczania słów
    def test_count_words(self):
        scraper = Scraper(
            base_url="http://dummy",
            phrase="Test",
            use_local_html_file_instead=True,
            local_file_path=self.test_file
        )
        counts = scraper.count_words()
        self.assertEqual(counts["paragraph"], 2)
        self.assertEqual(counts["first"], 1)

    # Test zachowania, gdy plik nie istnieje
    def test_file_not_found(self):
        scraper = Scraper(
            base_url="http://dummy",
            phrase="Test",
            use_local_html_file_instead=True,
            local_file_path="non_existent_file.html"
        )
        # Metoda get_summary powinna zwrócić błąd
        result = scraper.get_summary()
        self.assertIn("Page not found", result)

if __name__ == '__main__':
    unittest.main()
