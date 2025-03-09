import json
import time
from bs4 import BeautifulSoup
import sys
from browser import launch_browser, new_page, navigate_to, close_browser


def crawl_list(base_url, output_file="resource/list.json"):
    # Ensure UTF-8 output
    sys.stdout.reconfigure(encoding='utf-8')

    visited_urls = set()
    urls_to_visit = [base_url]
    api_endpoints = set()
    crawled_data = []

    # Try to load existing data
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            crawled_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        crawled_data = []

    existing_urls = {entry["url"] for entry in crawled_data}
    new_urls = set()

    p, browser = launch_browser(headless=True)
    page = new_page(browser)

    while urls_to_visit:
        url = urls_to_visit.pop(0)
        if url in visited_urls:
            continue

        try:
            print(f"[+] Crawling: {url}")
            navigate_to(page, url)

            # Capture API calls by intercepting requests
            def intercept(route):
                request = route.request
                if request.url.startswith(base_url.split('#')[0]):
                    api_endpoints.add(request.url)
                route.continue_()

            page.route("**/*", intercept)

            content = page.content()
            soup = BeautifulSoup(content, "html.parser")
            links = {a['href'] for a in soup.find_all('a', href=True)}
            full_links = set()
            for link in links:
                if link.startswith("#/") or (link.startswith("/") and not link.startswith("//")):
                    full_links.add(f"{base_url.split('#')[0]}{link}")
                elif link.startswith(base_url.split('#')[0]):
                    full_links.add(link)
            urls_to_visit.extend(full_links - visited_urls)
            visited_urls.add(url)

            if url not in existing_urls:
                new_urls.add(url)
                crawled_data.append({
                    "url": url,
                    "api_endpoints": list(api_endpoints),
                    "crawled_at": time.time()
                })
        except Exception as e:
            print(f"[!] Error crawling {url}: {e}")

    close_browser(p, browser)

    if new_urls:
        print("\n[🚀] Newly Discovered URLs:")
        for new_url in new_urls:
            print(f" - {new_url}")
    else:
        print("\n[✅] No new URLs found!")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(crawled_data, f, indent=4)
    print(f"[+] Crawled Data Saved to {output_file}")
    return crawled_data


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        print("[❌] No URL provided! Exiting.")
        sys.exit(1)
    crawl_list(base_url)
