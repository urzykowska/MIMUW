import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from wiki_scraper import Scraper

def test_integration():
    filename = "Team_Rocket.html"
    if not os.path.exists(filename):
        print(f"ERROR: file not found {filename}.")

    print(f"Integration test starting on: {filename}")

    # Inicjalizacja Scrapera w trybie offline:
    try:
        scraper = Scraper(
            base_url="http://dummy/",
            phrase="Team Rocket",
            use_local_html_file_instead=True,
            local_file_path=filename
        )
    except Exception as e:
        print(f"Scraper initialization error: {e}")
        sys.exit(1)
    
    # Pobranie summary:
    summary = scraper.get_summary()

    # Fragment otrzymanego streszczenia:
    print(f"\nFragment of the reveived summary: {summary[:80]}...")

    # Analiza otrzymanego streszczenia:
    expected_start = "Team Rocket"
    expected_end_fragment = "Sevii Islands."

    if not summary:
        print("TEST FAILED: Summary is empty")
        sys.exit(1)

    if not summary.startswith(expected_start):
        print(f"TEST FAILED: Text doesn't start with '{expected_start}'.")
        sys.exit(1)

    if expected_end_fragment not in summary:
        print(f"TEST FAILED: Text doesn't contain the expected end fragment: '{expected_end_fragment}'.")
        sys.exit(1)

    words = scraper.count_words()
    if sum(words.values()) < 80:
        print("TEST FAILED: Found too little words.")
        sys.exit(1)

    print("\n------------------------------------------------")
    print("INTEGRATION TEST COMPLETED SUCCESSFULLY (EXIT 0)")
    print("------------------------------------------------")
    sys.exit(0)

if __name__ == '__main__':
    test_integration()