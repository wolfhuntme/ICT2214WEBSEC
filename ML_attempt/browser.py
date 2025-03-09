import time
from playwright.sync_api import sync_playwright

def launch_browser(headless=True):
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=headless)
    return p, browser

# Increase the default navigation timeout to 30000 ms.
def new_page(browser, navigation_timeout=30000):
    page = browser.new_page()
    page.set_default_navigation_timeout(navigation_timeout)
    return page

def navigate_to(page, url, wait_time=2, wait_until="domcontentloaded"):
    page.goto(url, wait_until=wait_until)
    time.sleep(wait_time)
    return page

def close_browser(p, browser):
    browser.close()
    p.stop()
