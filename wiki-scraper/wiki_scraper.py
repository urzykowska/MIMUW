from bs4 import BeautifulSoup
import requests
import argparse
import pathlib
import pandas as pd
import json
from collections import Counter, deque
import os
import matplotlib.pyplot as plt
import time

# Jeśli wordfreq nie jest zainstalowany, przy próbie uzycia argumentu --analyze-relative-word-frequency
# pojawi się błąd.
try:
    from wordfreq import word_frequency, top_n_list
    WORDFREQ_AVAILABLE = True
except ImportError:
    WORDFREQ_AVAILABLE = False

BULBAPEDIA_URL = "https://bulbapedia.bulbagarden.net/wiki/"
BULBAPEDIA_CONTENT = "mw-content-text" # Selektor w Bulbapedii dla treści


class Scraper:
    # Inicjalizacja scrapera dla konkretnej frazy:
    def __init__(self, base_url, phrase, use_local_html_file_instead=False, local_file_path=None):
        self.base_url = base_url # podstawowy adres URL wiki
        self.phrase = phrase # szukana fraza
        self.use_local_html_file_instead = use_local_html_file_instead # flaga = czy uzywać pliku lokalnego
        self.local_file_path = local_file_path # ściezka do pliku lokalnego, jeśli use_local_html_file_instead = true
        self._soup = None # obiekt BeautifulSoup, scrapowana strona
    
    # Metoda pobierająca treść strony, zwracająca obiekt BeautifulSoup
    def get_soup(self):
        # Strona została pobrana juz wcześniej - nie trzeba tego robić ponownie:
        if self._soup: 
            return self._soup 
        
        # Używanie pliku lokalnego:
        if self.use_local_html_file_instead:
            if not self.local_file_path: # Brak ścieżki do pliku
                raise ValueError("Error: No filepath was provided.")
            try:
                with open(self.local_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self._soup = BeautifulSoup(content, 'html.parser')
            except FileNotFoundError: # Nie znaleziono pliku
                print("Error: File not found.")
                return None
        
        # Strona pobierana z internetu:
        else:
            # Zamieniamy spacje na podłogi, zeby móc uzyć frazy w URL
            correct_phrase = self.phrase.replace(" ", "_")
            # Ostateczne URL:
            url = f"{self.base_url}{correct_phrase}"
            try:
                response = requests.get(url)
                response.raise_for_status() # sprawdź status strony, żeby nie kontynuować w przypadku błędu
                self._soup = BeautifulSoup(response.text, 'html.parser')
            except:
                print("Error fetching the webpage " + url)
                return None
        
        return self._soup
    
    # Metoda obsługująca argument --summary:
    def get_summary(self):
        # Pobieramy obiekt soup:
        soup = self.get_soup()
        if not soup:
            return "Page not found or error occured."
        
        # Szukamy pierwszego DIVa z tekstem:
        content = soup.find('div', id=BULBAPEDIA_CONTENT)

        # Znaleźliśmy szukany DIV:
        if content:
            # Szukamy wszystkich paragrafów w znalezionym DIVie:
            paragraphs = content.find_all('p') 
            # Przechodzimy po wszystkich paragrafach (pierwszy paragraf może być pusty):
            for p in paragraphs:
                # Czyścimy tekst ze znaczników, usuwamy białe znaki:
                text = p.get_text().strip()
                # Zwracamy pierwszy niepusty paragraf:
                if text:
                    return text
        
        # Nie znaleziono tekstu:
        return "No summary paragraph found"
    
    # Metoda obsługująca argument --table:
    def get_table(self, number, first_row_is_header):
        soup = self.get_soup()
        if not soup:
            return "Page not found or error occured."
        
        # Znajdujemy wszystkie tabele:
        tables = soup.find_all('table')

        # Sprawdzamy poprawność argumentu number:
        if number < 1 or number > len(tables):
            print(f"Error: Table number {number} not found.")
            return
        
        target_table = tables[number-1] # znaleziona tabela

        # Interesuje nas tylko tekst w komórkach, bez znaczników HTML.
        table_data = []
        # Znajdujemy wszystkie wiersze w tabeli:
        rows = target_table.find_all('tr') # tr - wiersz tabeli

        for row in rows:
            # Pobieramy wszystkie komórki z wiersza (td - zwykła komórka, th - nagłówek)
            cols = row.find_all(['td', 'th'])
            # Pobieramy tekst, usuwamy spacje z początku/końca:
            cols = [ele.get_text(strip=True) for ele in cols]
            # Dodajemy wiersz, jeśli nie jest pusty:
            if cols:
                table_data.append(cols)

        # Tabela nie została utworzona
        if not table_data:
            print("Table is empty or could not be parsed.")
            return
        
        # Tworzenie DataFrame pandas
        # Wyrównywanie wierszy:
        max_cols = max(len(row) for row in table_data) # najdłuższy wiersz
        table_data = [row + [''] * (max_cols - len(row)) for row in table_data]

        if first_row_is_header:
            # Pierwszy wiersz traktowany jako nagłówki:
            headers = table_data[0]
            data = table_data[1:]
            df = pd.DataFrame(data, columns=headers)
        else:
            # Brak nagłówków kolumn
            df = pd.DataFrame(table_data)

        # Zapis do pliku "szukana fraza.csv"
        csv_filename = f"{self.phrase}.csv"
        try:
            df.to_csv(csv_filename, index=False) 
            print(f"Table saved to file: {csv_filename}")
        except:
            print("Error saving file.")
        
        # Wypisanie w formie tabeli ile razy dana wartość wystąpiła:
        print(f"\nValue frequency in table {number} (excluding headers):")

        # Spłaszczenie danych do jednej serii, aby zliczyć wystąpienia:
        all_values = df.values.flatten()

        # Filtrowanie pustych stringów:
        all_values = [v for v in all_values if v != '']

        # Zliczanie wartości:
        value_counts = pd.Series(all_values).value_counts().reset_index()
        value_counts.columns = ['Value', 'Count']

        # Wypisanie tabeli:
        print(value_counts.to_string(index=False))


    # Metoda częściowo obsługująca argument --count_words - pobieramy treść strony i tworzymy z niej
    # słownik ze słowami i liczbą ich wystąpień.
    def count_words(self):
        soup = self.get_soup()
        if not soup:
            return None
        
        # Główny kontener treści: 
        content_div = soup.find('div', id=BULBAPEDIA_CONTENT)

        if not content_div:
            print("Error: Could not find content div")
            return None
        
        # Usuwanie tagów <script> i <style>:
        for script in content_div(["script", "style"]):
            script.decompose()

        # Pobieranie czystego tekstu, oddzielając elementy spacją:
        text = content_div.get_text(separator=' ')

        # Podział na słowa, usuwanie znaków interpunkcyjnych:
        raw_words = text.split()
        clean_words = [] # lista słów

        for word in raw_words:
            # Usuwamy interpunkcję z początku i końca słowa
            word_stripped = word.strip('.,!?;:"()[]{}<>-\\/...—×•&$%^*')
            if word_stripped:
                clean_words.append(word_stripped.lower())
        
        # Zwracamy słownik ze słowami i z liczbą ich wystąpień:
        return Counter(clean_words)
    
    # Metoda obsługująca argument --analyze-relative-word-frequency:
    def analyze_frequency(self, mode, count, chart_path=None, lang='en'):
        # Wczytaj dane z pliku word-counts.json:
        json_filename = "word-counts.json"
        if not os.path.exists(json_filename):
            # Nie odnaleziono pliku word-counts.json.
            print(f"Error: {json_filename} not found. Run --count-words first.")
            return
        
        with open(json_filename, 'r', encoding='utf-8') as f:
            # wiki_data - slownik {"słowo": liczba_wystapien}
            wiki_data = json.load(f)
        
        if not wiki_data:
            # Słownik wiki_data jest pusty:
            print("Error: No data in word-counts.json.")
            return
        
        # Przygotuj DataFrame z danymi z Wiki:
        # Dane mają postać listy par krotek: (słowo, liczba wystąpień)
        df_wiki = pd.DataFrame(list(wiki_data.items()), columns=['word', 'wiki_raw'])

        # Normalizacja danych Wiki
        wiki_max = df_wiki['wiki_raw'].max() # słowo, które wystąpiło najwięcej razy
        # Dzielimy przez max, zeby mieć skalę 0-1:
        df_wiki['wiki_norm'] = df_wiki['wiki_raw'] / wiki_max

        # Pobieranie danych językowych z wordfreq:
        if not WORDFREQ_AVAILABLE:
            # Biblioteka wordfreq nie jest dostępna
            print("Error: wordfreq library is not installed.")
            return
        
        # Przygotowanie danych w zalezności od trybu:
        final_df = None

        if mode == 'article':
            # Posortowanie po częstotliwości na wiki
            # Bierzemy top N słow z wiki:
            top_wiki = df_wiki.sort_values(by='wiki_raw', ascending=False).head(count).copy()

            # Pobieramy częstotliwość występowania słowa "the" w języku - najczęstsze słowo w angielskim
            max_lang_freq = word_frequency('the', lang)

            # Dla kazdego słowa w tabeli:
            # 1. Pobieramy jego częstotliwość w języku angielskim (word_frequency(w, lang))
            # 2. Dzielimy ją przez częstotliwość najczęstszego słowa (jeśli częstotliwość występowania słowa > 0)
            top_wiki['lang_norm'] = top_wiki['word'].apply(
                lambda w: word_frequency(w, lang) / max_lang_freq if word_frequency(w, lang) > 0 else None
            )

            final_df = top_wiki

        elif mode == 'language':
            # Pobieramy top N najczęstszych słów w języku:
            top_lang_words = top_n_list(lang, count)
        
            # Tworzymy DataFrame z N najczęstszymi słowami w języku
            df_lang = pd.DataFrame(top_lang_words, columns=['word'])
            
            # Liczymy ich normalizowaną częstotliwość (0-1)
            max_lang_freq = word_frequency('the', lang)
            df_lang['lang_norm'] = df_lang['word'].apply(lambda w: word_frequency(w, lang) / max_lang_freq)
            
            # Łączymy z danymi wiki
            # Słowa z języka, których nie ma na wiki, będą miały luki
            final_df = pd.merge(df_lang, df_wiki[['word', 'wiki_norm']], on='word', how='left')

        else:
            print("Unknown mode.")
            return
        
        # Formatowanie i wypisanie tabeli:
        display_df = final_df.copy()
        display_df = display_df[['word', 'wiki_norm', 'lang_norm']]
        display_df.columns = ['word', 'frequency in the article', 'frequency in wiki language']
    
        # Wypisz tabelę
        print(display_df.to_string(index=False))

        # Rysowanie wykresu:
        if chart_path:
            create_chart(display_df, chart_path)
    
    # Funkcja znajdująca wszystkie linki w artykule:
    def get_valid_links(self):
        soup = self.get_soup()
        if not soup:
            return []

        # Szukamy linków tylko w głównym DIVie
        content_div = soup.find('div', id=BULBAPEDIA_CONTENT)
        if not content_div:
            # Nie udało się pobrać DIVa z treścią (lub go nie ma) - zwracamy pustą listę 
            return []

        links = [] # lista linków
        # Szukamy wszystkich znaczników <a> z atrybutem href
        for a_tag in content_div.find_all('a', href=True):
            href = a_tag['href']
            # Ignorujemy linki do plików, dyskusji itp
            if href.startswith('/wiki/') and ':' not in href:
                # Wyciągamy frazę z URL, np. "/wiki/Team_Rocket" -> "Team Rocket"
                # Usuwamy prefiks (/wiki/)
                raw_phrase = href[6:]
                # Zamieniamy podłogi na spacje
                clean_phrase = raw_phrase.replace('_', ' ')
                links.append(clean_phrase)
        return links


# Klasa, której zadaniem jest wejście na stronę startową, pobranie z niej danych, 
# znalezienie linków do kolejnych stron i odwiedzenie ich aż do osiągnięcia określonej głębokości.
class WikiCrawler:
    def __init__(self, start_phrase, max_depth, wait_time, base_url):
        # start_phrase - fraza, od której zaczynamy
        # max_depth - maksymalna głębokość poszukiwań (0 - tylko strona startowa)
        # wait_time - czas, jaki program ma odczekać między zapytaniami
        # base_url - adres bazowy wikipedii
        self.start_phrase = start_phrase
        self.max_depth = max_depth
        self.wait_time = wait_time
        self.base_url = base_url
        self.visited = set() # Zbiór odwiedzonych fraz, aby nie zapętlić się

    # Chodzenie po stronach (BFS)
    def run(self):
        # Kolejka przechowuje krotki: (fraza, aktualna_głębokość)
        queue = deque([(self.start_phrase, 0)])

        # Pętla działa dopóki są jakieś strony do odwiedzenia
        while queue:
            # Pobieramy pierwszy element z kolejki:
            current_phrase, current_depth = queue.popleft()

            # Jeśli już byliśmy na tej stronie, pomijamy:
            if current_phrase in self.visited:
                continue
            
            # Oznaczamy jako odwiedzoną:
            self.visited.add(current_phrase)
            
            # Informacja dla uzytkownika:
            print(f"[{current_depth}/{self.max_depth}] Processing: {current_phrase}") 

            # Tworzymy scraper dla bieżącej frazy:
            scraper = Scraper(self.base_url, current_phrase)
            
            # Pobieramy i zliczamy słowa:
            word_counts = scraper.count_words()
            
            if word_counts:
                # Aktualizujemy plik JSON
                update_word_counts_json(word_counts)
                print(f"   -> Saved {sum(word_counts.values())} words.")
                
                # Jeśli nie osiągnęliśmy limitu głębokości, szukamy linków
                if current_depth < self.max_depth:
                    links = scraper.get_valid_links()
                    new_links_count = 0
                    for link_phrase in links:
                        if link_phrase not in self.visited:
                            # Dodajemy do kolejki z głębokością + 1
                            queue.append((link_phrase, current_depth + 1))
                            new_links_count += 1
                    print(f"   -> Found {new_links_count} new links to queue.")
            else:
                print("   -> Failed to extract text.")

            # Czekamy t sekund przed kolejnym żądaniem (chyba że to koniec kolejki)
            if queue:
                time.sleep(self.wait_time)


# Funkcja służąca do zapisywania wyników z --count-words i --auto-count-words: jej celem jest 
# wczytanie starego pliku JSON, dodanie do niego nowych zliczeń słów i zapisanie całości z powrotem.
def update_word_counts_json(new_counts, filename="word-counts.json"):
    # new_counts - słownik z nowymi słowami
    total_counts = {}
    
    # Jeśli plik istnieje, wczytaj istniejące dane:
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                total_counts = json.load(f)
        except:
            # Nie udało się otworzyć pliku:
            print("JSON file corrupted, starting fresh.")
            total_counts = {}
        
    # Zaktualizuj licznik:
    for word, count in new_counts.items():
        current_val = total_counts.get(word, 0) # obecna wartość dla słowa
        total_counts[word] = current_val + count # dodajemy nową liczbę słów do poprzedniej

    # Zapisz z powrotem do pliku:
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(total_counts, f, ensure_ascii=False, indent=4)
        print(f"Successfully updated {filename}")
    except IOError as e:
        print(f"Error saving JSON: {e}") 


# Rysowanie wykresu dla funkcji --analyze-relative-word-frequency:
def create_chart(df, path):
    # df - obiekt pandas.DataFrame
    # path - ścieżka, pod którą ma zostać zapisany plik z wykresem

    # Słowa - etykiety na osi X: 
    plot_data = df.set_index('word')
    
    # Rysowanie wykresu słupkowego:
    ax = plot_data.plot(kind='bar', figsize=(10, 6), width=0.8)
    
    plt.title("Frequency of some words on Wiki vs Language")
    plt.ylabel("Normalized Frequency")
    plt.xlabel("Words")
    plt.legend(["Wiki", "Language"])
    plt.tight_layout()
    
    # Zapis do pliku
    try:
        plt.savefig(path)
        print(f"Chart saved to {path}")
    except Exception as e:
        print(f"Error saving chart: {e}")
    finally:
        plt.close()


def main():
    # === Konfiguracja parsera argumentów ===
    parser = argparse.ArgumentParser(
        prog='wiki_scraper',
        prefix_chars='--'
    )

    # --summary "szukana fraza"
    parser.add_argument("--summary", type=str, action="store")
    
    # --table "szukana fraza" --number n [--first-row-is-header]"
    table_group = parser.add_argument_group()
    table_group.add_argument("--table", action="store", type=str)
    table_group.add_argument("--number", action="store", type=int)
    table_group.add_argument("--first-row-is-header", action="store_true")

    # --count-words "szukana fraza"
    parser.add_argument("--count-words", action="store", type=str)

    # --analyze-relative-word-frequency --mode "tryb" --count n [--chart "ścieżka/do/pliku.png"]
    analysis_group = parser.add_argument_group()
    analysis_group.add_argument("--analyze-relative-word-frequency", action="store_true")
    analysis_group.add_argument("--mode", action="store", type=str)
    analysis_group.add_argument("--count", action="store", type=int)
    analysis_group.add_argument("--chart", action="store", type=pathlib.Path)

    # --auto-count-words "początkowa szukana fraza" --depth n --wait t
    auto_count_group = parser.add_argument_group()
    auto_count_group.add_argument("--auto-count-words", action="store", type=str)
    auto_count_group.add_argument("--depth", action="store", type=int)
    auto_count_group.add_argument("--wait", action="store", type=int)

    args = parser.parse_args()

    # == Sprawdzanie poprawności argumentów ==
    # Podano --table, nie podano --number:
    if args.table and args.number is None:
        parser.error("--number is required after --table.")
    # Podano --number, nie podano --table
    if args.number and args.table is None:
        parser.error("--number can't be used without --table.")
    # Podano --first-row-is-header, nie podano --table:
    if args.first_row_is_header and args.table is None:
        parser.error("--first-row-is-header can't be used without --table.")

    # Podano --analyze-relative-word-frequency:
    if args.analyze_relative_word_frequency:
        # Podano tryb - sprawdzanie poprawności trybu:
        if args.mode:
            if args.mode != "article" and args.mode != "language":
                parser.error("Wrong arguments in --mode. Usage: --mode article or --mode language.")
        # Nie podano trybu:
        else:
            parser.error("--mode is required after --analyze-relative-word-frequency.")
        if args.count is None:
            parser.error("--count is required after --analyze-relative-word-frequency.")
    # Nie podano --analyze-relative-word-frequency:
    else:
        # Sprawdzanie, czy nie zostały podane argumenty, które powinny zostać podane z --analyze-relative-word-frequency:
        if args.mode: # Podano --mode
            parser.error("--mode can't be used without --analyze-relative-word-frequency.")
        if args.count: # Podano --count
            parser.error("--count can't be used without --analyze-relative-word-frequency.")
        if args.chart: # Podano --chart
            parser.error("--chart can't be used without --analyze-relative-word-frequency.")

    # Podano --auto-count-words:
    if args.auto_count_words:
        if args.depth is None: # Nie podano --depth
            parser.error("--depth is required after --auto-count-words.")
        if args.wait is None: # Nie podano --wait
            parser.error("--wait is required after --auto-count-words.")
    # Nie podano --auto-count-words:
    else:
        if args.depth: # Podano --depth
            parser.error("--depth can't be used without --auto-count-words.")
        if args.wait: # Podano --wait
            parser.error("--wait can't be used without --auto-count-words.")

    # == Obsługa argumentów ==

    if args.summary:
        scraper = Scraper(BULBAPEDIA_URL, phrase=args.summary) 
        result = scraper.get_summary()
        print(result)

    if args.table:
        scraper = Scraper(BULBAPEDIA_URL, phrase=args.table)
        scraper.get_table(args.number, args.first_row_is_header)
    
    if args.count_words:
        print(f"Counting words for: {args.count_words}...")
        scraper = Scraper(BULBAPEDIA_URL, phrase=args.count_words)
        words_count = scraper.count_words()
        if words_count:
            update_word_counts_json(words_count)
            print(f"Found {sum(words_count.values())} words in the article.")
        else:
            print("No words found or page extraction failed.")

    if args.analyze_relative_word_frequency:
        print(f"Analyzing frequency in mode: {args.mode}...")
        # Metoda analyze_frequency w klasie Scraper nie wymaga podania frazy, bo operujemy
        # na istniejącym pliku. Fraza podana ponizej jest sztuczna, nie odnosi się do zadnego
        # istniejącego pliku ani strony.
        scraper = Scraper(BULBAPEDIA_URL, phrase="analysis_mode")
        scraper.analyze_frequency(
            mode=args.mode,
            count=args.count,
            chart_path = args.chart
        )

    if args.auto_count_words:
        print(f"Starting auto-crawler from: '{args.auto_count_words}' with depth {args.depth}")
        crawler = WikiCrawler(
            start_phrase=args.auto_count_words,
            max_depth=args.depth,
            wait_time=args.wait,
            base_url=BULBAPEDIA_URL
        )
        crawler.run()


if __name__ == '__main__':
    main()
