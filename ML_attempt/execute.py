import csv
import time
import re
import pickle
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import tensorflow as tf
import numpy as np
import os
import sys
from tensorflow.keras.models import load_model

def load_replay_buffer(filename="resource/replay_buffer.pkl"):
    try:
        with open(filename, "rb") as f:
            buffer = pickle.load(f)
        print("Loaded replay buffer with", len(buffer), "experiences.")
        return buffer
    except Exception:
        print("No existing replay buffer found. Starting fresh.")
        return []

def save_replay_buffer(buffer, filename="resource/replay_buffer.pkl"):
    with open(filename, "wb") as f:
        pickle.dump(buffer, f)
    print("Replay buffer saved with", len(buffer), "experiences.")

def load_selector_performance(filename="resource/selector_performance.pkl"):
    try:
        with open(filename, "rb") as f:
            data = pickle.load(f)
        print("Loaded selector performance data with", len(data), "entries.")
        return data
    except Exception:
        print("No existing selector performance data found. Starting fresh.")
        return {}

def save_selector_performance(data, filename="resource/selector_performance.pkl"):
    with open(filename, "wb") as f:
        pickle.dump(data, f)
    print("Selector performance data saved with", len(data), "entries.")

def update_selector_performance(performance, selector, success):
    if selector not in performance:
        performance[selector] = {"attempts": 0, "success": 0}
    performance[selector]["attempts"] += 1
    if success:
        performance[selector]["success"] += 1

def get_selector_success_rate(performance, selector):
    if selector not in performance or performance[selector]["attempts"] == 0:
        return None
    return performance[selector]["success"] / performance[selector]["attempts"]

def dynamic_fallback_selector(page, original_selector):
    print(f"[DEBUG] Performing dynamic fallback check for {original_selector}")
    tag = re.split(r'[#.]', original_selector)[0]
    candidates = page.locator(tag)
    count = candidates.count()
    print(f"[DEBUG] Found {count} potential fallback elements for {original_selector}")
    if count == 0:
        return original_selector
    original_text = ""
    try:
        original_text = page.locator(original_selector).first.inner_text().strip().lower()
    except Exception as e:
        print(f"[⚠️] Failed to extract text from {original_selector}: {e}")
    print(f"[DEBUG] Original button text: '{original_text}'")
    best_match = None
    for i in range(count):
        candidate = candidates.nth(i)
        try:
            candidate_text = candidate.inner_text().strip().lower()
        except Exception:
            candidate_text = ""
        if original_text and original_text in candidate_text:
            print(f"[✅] Found similar button: '{candidate_text}' -> using '{tag}:nth-of-type({i+1})'")
            return f"{tag}:nth-of-type({i+1})"
        if best_match is None:
            best_match = f"{tag}:nth-of-type({i+1})"
    print(f"[⚠️] No exact match found. Using first available fallback: {best_match}")
    return best_match

def detect_expected_state(page, expected_selector, timeout=5000):
    try:
        page.wait_for_selector(expected_selector, timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False

def calculate_reward(success, action, state_changed, expected_state=False, selector=""):
    if success:
        if expected_state:
            return 50
        elif action == "input":
            return 10
        elif action == "click" and state_changed:
            # Lower reward for clicks on nav bar/dropdown elements
            if any(keyword in selector.lower() for keyword in ["navbar", "nav", "dropdown"]):
                return 5  # Lower reward for nav bar dropdown clicks
            return 15
        else:
            return 10
    else:
        return -10 if state_changed else -20

def detect_state_change(page, prev_url, prev_local_storage, prev_elements):
    time.sleep(2)
    new_url = page.url
    url_changed = new_url != prev_url
    try:
        new_local_storage = page.evaluate("() => JSON.stringify(localStorage)")
    except Exception:
        new_local_storage = ""
    storage_changed = new_local_storage != prev_local_storage
    try:
        new_elements_count = page.locator("body *").count()
    except Exception:
        new_elements_count = 0
    elements_changed = new_elements_count != prev_elements
    return (url_changed or storage_changed or elements_changed), url_changed, storage_changed, elements_changed

def update_model_from_experience(model, experiences, optimizer, gamma=0.99):
    rewards = [exp["reward"] for exp in experiences]
    discounted_rewards = []
    cumulative = 0
    for r in rewards[::-1]:
        cumulative = r + gamma * cumulative
        discounted_rewards.insert(0, cumulative)
    discounted_rewards = np.array(discounted_rewards, dtype=np.float32)
    discounted_rewards = (discounted_rewards - np.mean(discounted_rewards)) / (np.std(discounted_rewards) + 1e-8)
    states = np.array([exp["step"] for exp in experiences], dtype=np.float32)
    states = np.expand_dims(states, axis=-1)
    actions = np.array([1 if exp["action"] == "click" else 0 for exp in experiences], dtype=np.int32)
    with tf.GradientTape() as tape:
        predictions = model(states, training=True)
        chosen_action_probs = tf.gather(predictions, actions, axis=1, batch_dims=1)
        log_probs = tf.math.log(chosen_action_probs + 1e-10)
        loss = -tf.reduce_mean(log_probs * discounted_rewards)
    grads = tape.gradient(loss, model.trainable_variables)
    optimizer.apply_gradients(zip(grads, model.trainable_variables))
    print(f"Updated model with loss: {loss.numpy()}")

def run_execute():
    sys.stdout.reconfigure(encoding='utf-8')
    PREDICTION_FILE = "resource/PredictSelection.txt"
    LOG_FILE = "resource/execution_log.csv"
    experience_buffer = []
    selector_performance = load_selector_performance()
    expected_state_map = {
        "click": {
            "button#navbarAccount": "div.mat-menu-panel"
        }
    }
    from browser import navigate_to  # reuse our navigation helper
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        print("[DEBUG] Launching browser...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        with open(LOG_FILE, "w", newline="") as log_file:
            writer = csv.writer(log_file)
            writer.writerow(["STEP", "URL", "SELECTOR", "ACTION", "SUCCESS",
                             "STATE CHANGE", "EXPECTED", "ERROR", "RL DECISION", "REWARD", "USED SELECTOR"])
            prev_url = ""
            prev_local_storage = ""
            prev_elements = 0
            # Read predictions
            predictions = []
            with open(PREDICTION_FILE, "r") as file:
                for line in file:
                    if line.strip() == "<EOS>":
                        continue
                    parts = line.strip().split(" | ")
                    if len(parts) >= 4:
                        url, selector_raw, page_title, importance = parts[:4]
                        selector_match = re.search(
                            r"(button|input|a|textarea|select)[^\s]*", selector_raw)
                        selector = selector_match.group(0) if selector_match else selector_raw
                        action = "input" if "input" in selector else "click" if "button" in selector else "navigate"
                        predictions.append({"url": url, "selector": selector, "action": action})
            for step, prediction in enumerate(predictions, start=1):
                url = prediction["url"]
                orig_selector = prediction["selector"]
                action = prediction["action"]
                used_selector = orig_selector
                success = False
                state_changed = False
                error_msg = ""
                expected_state = False

                rate = get_selector_success_rate(selector_performance, orig_selector)
                if rate is not None and rate < 0.3:
                    fallback = dynamic_fallback_selector(page, orig_selector)
                    print(f"[ℹ️] Selector '{orig_selector}' has low success rate ({rate:.2f}). Trying dynamic fallback '{fallback}'.")
                    if page.locator(fallback).count() > 0:
                        used_selector = fallback
                        print(f"[✅] Using fallback selector: {used_selector}")
                    else:
                        print(f"[⚠️] Fallback selector '{fallback}' not found. Keeping original selector.")
                try:
                    if page.url != url:
                        print(f"Navigating to {url}...")
                        navigate_to(page, url, wait_time=2)
                        time.sleep(2)
                    prev_url = page.url
                    try:
                        prev_local_storage = page.evaluate("() => JSON.stringify(localStorage)")
                    except Exception as e:
                        prev_local_storage = ""
                    prev_elements = page.locator("body *").count()
                    element = page.locator(used_selector)
                    if action == "click":
                        if element.count() > 0:
                            element.first.click()
                            success = True
                            print(f"[✅] Clicked {used_selector} (Fallback Used: {'Yes' if used_selector != orig_selector else 'No'})")
                        else:
                            error_msg = "Element not found"
                    elif action == "input":
                        if element.count() > 0:
                            if "password" in used_selector.lower():
                                element.first.fill("12345")
                            elif "email" in used_selector.lower():
                                element.first.fill("a@gmail.com")
                            else:
                                element.first.fill("TestInput")
                            success = True
                        else:
                            error_msg = "Input field not found"
                    elif action == "navigate":
                        navigate_to(page, url, wait_time=2)
                        success = True
                        print(f"Navigated to {url}")
                    state_changed, url_changed, storage_changed, elements_changed = detect_state_change(
                        page, prev_url, prev_local_storage, prev_elements
                    )
                    print(f"State Change - URL: {url_changed}, Storage: {storage_changed}, New Elements: {elements_changed}")
                    if action == "click" and used_selector in expected_state_map.get("click", {}):
                        exp_sel = expected_state_map["click"][used_selector]
                        expected_state = detect_expected_state(page, exp_sel, timeout=5000)
                        if expected_state:
                            print(f"Expected state '{exp_sel}' detected after clicking {used_selector}")
                        else:
                            print(f"Expected state '{exp_sel}' NOT detected after clicking {used_selector}")
                except Exception as e:
                    error_msg = str(e)
                    print(f"Error executing {action} on {used_selector}: {error_msg}")
                reward = calculate_reward(success, action, state_changed, expected_state)
                print(f"[🏆] Reward Assigned: {reward} for action '{action}' on selector '{used_selector}'")
                writer.writerow([step, url, orig_selector, action,
                                 "Y" if success else "N",
                                 "Y" if state_changed else "N",
                                 "Y" if expected_state else "N",
                                 error_msg, "[RL Decision Placeholder]", reward, used_selector])
                update_selector_performance(selector_performance, orig_selector, success)
                if used_selector != orig_selector:
                    update_selector_performance(selector_performance, used_selector, success)
                experience_buffer.append({
                    "step": step,
                    "url": url,
                    "selector": used_selector,
                    "action": action,
                    "reward": reward,
                    "prev_state": {
                        "url": prev_url,
                        "local_storage": prev_local_storage,
                        "elements": prev_elements
                    },
                    "current_state": {
                        "url": page.url,
                        "local_storage": page.evaluate("() => JSON.stringify(localStorage)"),
                        "elements": page.locator("body *").count()
                    }
                })
        browser.close()
    save_selector_performance(selector_performance)
    replay_buffer = load_replay_buffer()
    all_experiences = replay_buffer + experience_buffer
    MAX_BUFFER_SIZE = 1000
    if len(all_experiences) > MAX_BUFFER_SIZE:
        all_experiences = all_experiences[-MAX_BUFFER_SIZE:]
    save_replay_buffer(all_experiences)
    try:
        model = load_model("resource/workflow_lstm_model.keras")
    except Exception as e:
        print("Error loading model:", e)
        return
    optimizer = tf.keras.optimizers.Adam(learning_rate=0.001)
    BATCH_SIZE = 32
    mini_batch = random.sample(all_experiences, BATCH_SIZE) if len(all_experiences) >= BATCH_SIZE else all_experiences
    update_model_from_experience(model, mini_batch, optimizer)
    model.save("resource/workflow_lstm_model.keras")
    print("Model updated and saved as workflow_lstm_model.keras")

if __name__ == "__main__":
    run_execute()