# import json
# import time
# from playwright.sync_api import sync_playwright
# from bs4 import BeautifulSoup
#
# class BusinessLogicAnalyzer:
#     def __init__(self, base_url, directories_file, output_file):
#         self.base_url = base_url.rstrip("/")
#         self.output_file = output_file
#         self.interactions = {}
#
#         # Load discovered directories from directories.json
#         with open(directories_file, "r") as f:
#             self.site_data = json.load(f)
#             self.urls = self.site_data.get("urls", [])  # Ensure URLs are loaded
#             self.api_endpoints = self.site_data.get("api_endpoints", [])
#
#     def extract_forms_and_buttons(self, page_content, url):
#         """Extracts forms, input fields, and buttons"""
#         soup = BeautifulSoup(page_content, "html.parser")
#         forms = soup.find_all("form")
#         buttons = soup.find_all("button")
#         inputs = soup.find_all("input")
#
#         self.interactions[url] = {
#             "forms": len(forms),
#             "buttons": len(buttons),
#             "inputs": [inp.get("name") for inp in inputs if inp.get("name")],
#         }
#
#     def analyze(self):
#         """Crawl discovered URLs and analyze business logic elements"""
#         with sync_playwright() as p:
#             browser = p.chromium.launch(headless=False)
#             page = browser.new_page()
#
#             for url in self.urls:
#                 try:
#                     print(f"[+] Analyzing: {url}")
#                     page.goto(url, wait_until="domcontentloaded")
#                     time.sleep(2)
#
#                     content = page.content()
#                     self.extract_forms_and_buttons(content, url)
#
#                 except Exception as e:
#                     print(f"[!] Error analyzing {url}: {e}")
#
#             browser.close()
#
#         # Store business logic analysis data separately
#         output_data = {
#             "urls": self.urls,
#             "api_endpoints": self.api_endpoints,
#             "interactions": self.interactions
#         }
#
#         with open(self.output_file, "w") as f:
#             json.dump(output_data, f, indent=4)
#
#         print(f"\n[+] Business logic data saved in {self.output_file}")
#         return output_data
#
# if __name__ == "__main__":
#     analyzer = BusinessLogicAnalyzer(
#         "https://slaying.ddns.net",
#         "directories.json",  # Read input from directories.json
#         "available.json"  # Save output to business_logic.json
#     )
#     analyzer.analyze()

import json
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

class BusinessLogicAnalyzer:
    def __init__(self, base_url, directories_file="directories.json", output_file="available.json"):
        self.base_url = base_url.rstrip("/")
        self.directories_file = directories_file
        self.output_file = output_file
        self.interactions = {}

        # Load discovered URLs
        with open(directories_file, "r") as f:
            self.site_data = json.load(f)
            self.urls = set(self.site_data.get("urls", []))
            self.api_endpoints = set(self.site_data.get("api_endpoints", []))

    def load_existing_data(self):
        """Load existing interactions to prevent redundant reanalysis."""
        try:
            with open(self.output_file, "r") as f:
                data = json.load(f)
                return data.get("interactions", {})
        except FileNotFoundError:
            return {}

    def save_data(self):
        """Append new interactions to the existing data."""
        existing_interactions = self.load_existing_data()
        existing_interactions.update(self.interactions)

        updated_data = {
            "urls": list(self.urls),
            "api_endpoints": list(self.api_endpoints),
            "interactions": existing_interactions
        }

        with open(self.output_file, "w") as f:
            json.dump(updated_data, f, indent=4)

        print(f"[+] Updated business logic in {self.output_file}")

    def extract_forms_and_buttons(self, page_content, url):
        """Extract forms, input fields, and buttons dynamically."""
        soup = BeautifulSoup(page_content, "html.parser")
        forms = soup.find_all("form")
        buttons = soup.find_all("button")
        inputs = soup.find_all("input")

        self.interactions[url] = {
            "forms": len(forms),
            "buttons": len(buttons),
            "inputs": [inp.get("name") for inp in inputs if inp.get("name")],
        }

    def analyze(self):
        """Analyze only new URLs that haven't been processed before."""
        existing_interactions = self.load_existing_data()
        urls_to_analyze = [url for url in self.urls if url not in existing_interactions]

        if not urls_to_analyze:
            print("[!] No new pages found to analyze. Skipping analysis.")
            return

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()

            for url in urls_to_analyze:
                try:
                    print(f"[+] Analyzing: {url}")
                    page.goto(url, wait_until="domcontentloaded")
                    time.sleep(2)

                    content = page.content()
                    self.extract_forms_and_buttons(content, url)

                except Exception as e:
                    print(f"[!] Error analyzing {url}: {e}")

            browser.close()

        self.save_data()

if __name__ == "__main__":
    analyzer = BusinessLogicAnalyzer(
        "https://slaying.ddns.net",
        "directories.json",
        "available.json"
    )
    analyzer.analyze()
