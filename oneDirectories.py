# import json
# import time
# from playwright.sync_api import sync_playwright
# from bs4 import BeautifulSoup
#
# class WebCrawler:
#     def __init__(self, base_url):
#         self.base_url = base_url.rstrip("/")
#         self.visited_urls = set()
#         self.urls_to_visit = [base_url]
#         self.api_endpoints = set()
#
#     def extract_links(self, page_content):
#         """Extracts internal links and correctly formats hash-based routes"""
#         soup = BeautifulSoup(page_content, "html.parser")
#         links = {a['href'] for a in soup.find_all('a', href=True)}
#
#         full_links = set()
#         for link in links:
#             if link.startswith("#/"):
#                 full_links.add(f"{self.base_url.split('#')[0]}{link}")
#             elif link.startswith("/") and not link.startswith("//"):
#                 full_links.add(f"{self.base_url.split('#')[0]}{link}")
#             elif link.startswith(self.base_url.split('#')[0]):
#                 full_links.add(link)
#
#         return full_links
#
#     def capture_api_calls(self, page):
#         """Intercept API calls dynamically"""
#         def intercept(route):
#             request = route.request
#             if request.url.startswith(self.base_url.split('#')[0]):
#                 self.api_endpoints.add(request.url)
#             route.continue_()
#
#         page.route("**/*", intercept)
#
#     def crawl(self):
#         with sync_playwright() as p:
#             browser = p.chromium.launch(headless=False)
#             page = browser.new_page()
#             page.set_default_navigation_timeout(10000)
#
#             while self.urls_to_visit:
#                 url = self.urls_to_visit.pop(0)
#                 if url in self.visited_urls:
#                     continue
#
#                 try:
#                     print(f"[+] Crawling: {url}")
#                     page.goto(url, wait_until="domcontentloaded")
#                     time.sleep(2)
#                     self.capture_api_calls(page)
#
#                     content = page.content()
#                     new_links = self.extract_links(content)
#                     self.urls_to_visit.extend(new_links - self.visited_urls)
#
#                     self.visited_urls.add(url)
#
#                 except Exception as e:
#                     print(f"[!] Error: {e}")
#
#             browser.close()
#
#         # Save discovered data
#         discovered_data = {
#             "urls": list(self.visited_urls),
#             "api_endpoints": list(self.api_endpoints)
#         }
#         with open("directories.json", "w") as f:
#             json.dump(discovered_data, f, indent=4)
#
#         print("\n[+] Discovered data saved in directories.json")
#         return discovered_data
#
# if __name__ == "__main__":
#     crawler = WebCrawler("https://slaying.ddns.net/#/")
#     crawler.crawl()

import json
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

class WebCrawler:
    def __init__(self, base_url, output_file="directories.json"):
        self.base_url = base_url.rstrip("/")
        self.output_file = output_file
        self.visited_urls = set()
        self.urls_to_visit = [base_url]
        self.api_endpoints = set()

    def load_existing_data(self):
        """Load existing URLs to prevent duplicates."""
        try:
            with open(self.output_file, "r") as f:
                data = json.load(f)
                return set(data.get("urls", [])), set(data.get("api_endpoints", []))
        except FileNotFoundError:
            return set(), set()

    def save_data(self):
        """Append new URLs instead of replacing existing ones."""
        existing_urls, existing_endpoints = self.load_existing_data()

        updated_data = {
            "urls": list(existing_urls | self.visited_urls),
            "api_endpoints": list(existing_endpoints | self.api_endpoints)
        }

        with open(self.output_file, "w") as f:
            json.dump(updated_data, f, indent=4)

        print(f"[+] Updated discovered URLs in {self.output_file}")

    def extract_links(self, page_content):
        """Extract internal links and correctly format hash-based routes."""
        soup = BeautifulSoup(page_content, "html.parser")
        links = {a['href'] for a in soup.find_all('a', href=True)}

        full_links = set()
        for link in links:
            if link.startswith("#/"):
                full_links.add(f"{self.base_url.split('#')[0]}{link}")
            elif link.startswith("/") and not link.startswith("//"):
                full_links.add(f"{self.base_url.split('#')[0]}{link}")
            elif link.startswith(self.base_url.split('#')[0]):
                full_links.add(link)

        return full_links

    def capture_api_calls(self, page):
        """Intercept API calls dynamically."""
        def intercept(route):
            request = route.request
            if request.url.startswith(self.base_url.split('#')[0]):
                self.api_endpoints.add(request.url)
            route.continue_()

        page.route("**/*", intercept)

    def crawl(self):
        """Crawl the site and find new links dynamically."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.set_default_navigation_timeout(10000)

            existing_urls, _ = self.load_existing_data()

            while self.urls_to_visit:
                url = self.urls_to_visit.pop(0)
                if url in self.visited_urls or url in existing_urls:
                    continue

                try:
                    print(f"[+] Crawling: {url}")
                    page.goto(url, wait_until="domcontentloaded")
                    time.sleep(2)
                    self.capture_api_calls(page)

                    content = page.content()
                    new_links = self.extract_links(content)
                    self.urls_to_visit.extend(new_links - self.visited_urls)

                    self.visited_urls.add(url)

                except Exception as e:
                    print(f"[!] Error crawling {url}: {e}")

            browser.close()

        self.save_data()

if __name__ == "__main__":
    crawler = WebCrawler("https://slaying.ddns.net/#/")
    crawler.crawl()
