import json
import time
from bs4 import BeautifulSoup
import sys
from browser import launch_browser, new_page, navigate_to, close_browser


class Scraper:
    def __init__(self, base_url, directories_file="resource/list.json", output_file="resource/scrape.json"):
        self.base_url = base_url.rstrip("/")
        self.directories_file = directories_file
        self.output_file = output_file
        self.page_data = []

    def load_urls(self):
        try:
            with open(self.directories_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "urls" in data:
                return data["urls"]
            elif isinstance(data, list):
                if all(isinstance(entry, dict) and "url" in entry for entry in data):
                    return [entry["url"] for entry in data]
                elif all(isinstance(entry, str) for entry in data):
                    return data
            print("[❌] Unexpected JSON format!")
            return []
        except (FileNotFoundError, json.JSONDecodeError):
            print("[❌] Directories file not found or invalid! Crawling required.")
            return []

    def extract_page_metadata(self, page):
        return page.title()

    def extract_javascript_data(self, page):
        js_data = {
            "local_storage": page.evaluate("() => JSON.stringify(localStorage)"),
            "session_storage": page.evaluate("() => JSON.stringify(sessionStorage)"),
            "javascript_variables": page.evaluate(
                "() => Object.keys(window).filter(key => key.includes('id') || key.includes('token'))")
        }
        return js_data

    def get_element_selector(self, element):
        tag = element.name
        id_attr = element.get("id")
        class_list = ".".join(element.get("class", []))
        if id_attr:
            return f"{tag}#{id_attr}"
        elif class_list:
            return f"{tag}.{class_list}"
        else:
            return tag

    def extract_page_elements(self, page, url):
        print(f"[🔎] Scanning: {url}")
        navigate_to(page, url, wait_time=5)
        page_title = self.extract_page_metadata(page)
        soup = BeautifulSoup(page.content(), "html.parser")
        elements = []
        # Extract buttons
        for btn in soup.find_all("button"):
            selector = self.get_element_selector(btn)
            text = btn.get_text(strip=True) or btn.get("aria-label", "") or btn.get("title", "")
            if text.strip():
                role = "submit" if "submit" in selector.lower() else "navigation"
                name_role = f"{text} ({role})"
                elements.append({
                    "type": "button",
                    "selector": selector,
                    "name_role": name_role,
                    "url": url,
                    "page_title": page_title
                })
        # Extract input fields
        for inp in soup.find_all("input"):
            selector = self.get_element_selector(inp)
            name_attr = inp.get("name") or inp.get("placeholder") or inp.get("aria-label") or "Unnamed"
            role = "password" if "password" in selector.lower() else "text"
            name_role = f"{name_attr} ({role})"
            elements.append({
                "type": "input",
                "selector": selector,
                "name_role": name_role,
                "url": url,
                "page_title": page_title
            })
        # Extract JavaScript data
        js_data = self.extract_javascript_data(page)
        elements.append({
            "type": "javascript_data",
            "url": url,
            "page_title": page_title,
            "local_storage": js_data["local_storage"],
            "session_storage": js_data["session_storage"],
            "javascript_variables": js_data["javascript_variables"]
        })
        self.page_data.extend(elements)
        print(f"[+] Extracted {len(elements)} elements from {url}")

    def save_data(self):
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.page_data, f, indent=4)
        print(f"[📂] Saved extracted elements to {self.output_file}")


def run_scrape(base_url):
    sys.stdout.reconfigure(encoding='utf-8')
    scraper = Scraper(base_url)
    urls_to_analyze = scraper.load_urls()
    if not urls_to_analyze:
        print("[❌] No URLs found. Exiting.")
        return
    p, browser = launch_browser(headless=False)
    page = new_page(browser)
    for url in urls_to_analyze:
        scraper.extract_page_elements(page, url)
    scraper.save_data()
    close_browser(p, browser)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        print("[❌] No URL provided! Exiting.")
        sys.exit(1)
    run_scrape(base_url)