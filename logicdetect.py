#!/usr/bin/env python3
"""
LogicDetect - A Proof-of-Concept tool for discovering business logic flaws
by simulating multi-step user workflows in a web application, with optional
AI/ML-based anomaly detection.

Author: Security Team
Date: 2025-01-21
"""

import json
import time
import argparse
import random
from typing import List, Dict, Any
import pandas as pd
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import the anomaly detection functions
from anomaly_detection import detect_anomalies

###############################################################################
# Section 1: Scenario Loading & Data Structures
###############################################################################

def load_scenario(file_path: str) -> Dict[str, Any]:
    """
    Loads a JSON scenario file describing the steps (login, add to cart, checkout, etc.).
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        scenario_data = json.load(f)
    return scenario_data


###############################################################################
# Section 2: Core Workflow Execution
###############################################################################

def find_element(driver, locator: Dict[str, str]):
    """
    Helper to locate elements. 
    locator = {"by": "id", "value": "username"}
    """
    by_map = {
        "id": By.ID,
        "name": By.NAME,
        "xpath": By.XPATH,
        "css": By.CSS_SELECTOR,
        "class": By.CLASS_NAME,
        "tag": By.TAG_NAME,
        "link": By.LINK_TEXT,
    }
    by = by_map.get(locator.get("by", "id"))
    value = locator.get("value", "")
    
    try:
        element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except:
        return None


def perform_step(driver, step: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    """
    Execute a single step. Return a dictionary with step results or anomalies.
    """
    step_type = step.get("type")
    start_time = time.time()  # start timing

    # Default placeholders for "status_code" or "content_length" if relevant
    status_code = None
    content_length = None

    if step_type == "navigate":
        url_path = step.get("url_path", "/")
        full_url = base_url + url_path
        driver.get(full_url)
        # For a navigate step, we can check e.g. page source length
        content_length = len(driver.page_source)
        step_detail = f"Navigated to {full_url}"
        step_status = "ok"

    elif step_type == "input":
        locator = step.get("locator", {})
        input_text = step.get("input_text", "")
        element = find_element(driver, locator)
        if element:
            element.clear()
            element.send_keys(input_text)
            step_detail = f"Entered {input_text}"
            step_status = "ok"
        else:
            step_detail = "Element not found"
            step_status = "error"

    elif step_type == "click":
        locator = step.get("locator", {})
        element = find_element(driver, locator)
        if element:
            element.click()
            step_detail = "Clicked element"
            step_status = "ok"
        else:
            step_detail = "Element not found"
            step_status = "error"

    elif step_type == "assert":
        check_type = step.get("check")
        value = step.get("value", "")
        if check_type == "text_present":
            if value in driver.page_source:
                step_detail = f"Text '{value}' found."
                step_status = "ok"
            else:
                step_detail = f"Text '{value}' NOT found. Potential logic flaw?"
                step_status = "warning"
        else:
            step_detail = f"Unknown assert check: {check_type}"
            step_status = "error"

    elif step_type == "api_manipulation":
        api_endpoint = step.get("endpoint", "")
        method = step.get("method", "GET").upper()
        payload = step.get("payload", {})
        full_url = base_url + api_endpoint
        
        try:
            if method == "GET":
                resp = requests.get(full_url, params=payload)
            else:
                resp = requests.post(full_url, json=payload)
            
            status_code = resp.status_code
            content_length = len(resp.text)

            if resp.status_code == 200 and step.get("expected_fail", False):
                step_detail = (f"API call succeeded unexpectedly on {api_endpoint}. "
                               f"Potential logic flaw?")
                step_status = "warning"
            else:
                step_detail = f"API {method} {api_endpoint} => {resp.status_code}"
                step_status = "ok"
        except requests.RequestException as e:
            step_detail = str(e)
            step_status = "error"

    else:
        step_detail = "Unknown step type"
        step_status = "error"

    elapsed = time.time() - start_time

    return {
        "step_type": step_type,
        "status": step_status,
        "detail": step_detail,
        "time_taken": round(elapsed, 3),
        # Additional metrics for ML
        "status_code": status_code if status_code is not None else 0,
        "content_length": content_length if content_length is not None else 0,
    }


def run_scenario(scenario_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Execute all steps in the scenario in a Selenium-driven browser,
    capturing potential logic flaws (anomalies) along the way.
    """
    base_url = scenario_data.get("base_url", "")
    steps = scenario_data.get("steps", [])

    # Optional: Headless mode
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    
    step_results = []
    try:
        for step in steps:
            result = perform_step(driver, step, base_url)
            step_results.append(result)
            # Optional small delay to mimic user interaction
            time.sleep(random.uniform(0.5, 1.5))
    finally:
        driver.quit()

    return step_results


###############################################################################
# Section 3: Simple Rule-Based and ML-Based Analysis
###############################################################################

def analyze_results(step_results: List[Dict[str, Any]], model_path=None) -> List[str]:
    """
    Combine:
    1) Basic rule-based anomalies (e.g., status == 'warning' or 'error')
    2) Optional ML-based anomaly detection using the Isolation Forest
    """
    anomalies = []

    # --- (A) Rule-based detection
    for i, result in enumerate(step_results):
        status = result["status"]
        detail = result["detail"]
        if status == "warning":
            anomalies.append(f"[STEP {i+1}] Potential logic issue: {detail}")
        elif status == "error":
            anomalies.append(f"[STEP {i+1}] Error: {detail}")

    # --- (B) ML-based detection
    if model_path:
        df = pd.DataFrame(step_results)
        # The anomaly_detection module will read the relevant columns from the trained model
        predictions = detect_anomalies(model_path, df)
        # predictions: array of -1 (anomaly) or 1 (normal)
        for i, pred in enumerate(predictions):
            if pred == -1:
                anomalies.append(f"[STEP {i+1}] ML-based anomaly detection flagged this step.")
    
    return anomalies


###############################################################################
# Section 4: Command-Line Interface
###############################################################################

def main():
    parser = argparse.ArgumentParser(description="LogicDetect - Business Logic Flaw Detection (PoC)")
    parser.add_argument("--scenario", required=True, help="Path to scenario JSON")
    parser.add_argument("--model", help="Path to trained ML model (optional)")
    args = parser.parse_args()

    # 1. Load scenario file
    scenario_data = load_scenario(args.scenario)

    # 2. Run scenario steps
    step_results = run_scenario(scenario_data)

    # 3. Analyze results with optional ML-based anomaly detection
    anomalies = analyze_results(step_results, model_path=args.model)

    # 4. Print a small report
    print("\n=== LogicDetect Execution Report ===")
    print(f"Scenario Name: {scenario_data.get('name', 'Unnamed Scenario')}")
    print("------------------------------------")

    for i, result in enumerate(step_results):
        print(f"Step {i+1}: {result['step_type']} => {result['status']} | {result['detail']} "
              f"(time={result['time_taken']}s, code={result['status_code']}, length={result['content_length']})")

    print("------------------------------------")
    if anomalies:
        print("Anomalies / Warnings:")
        for a in anomalies:
            print(a)
    else:
        print("No obvious anomalies detected. (This does not guarantee no logic flaws!)")


if __name__ == "__main__":
    main()
