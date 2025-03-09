import os
import time
import pickle
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences
import asyncio
from playwright.async_api import async_playwright

# ----- Greedy Decoding Function -----
def greedy_decode(model, start_seq, encoder, pad_len, max_steps=20):
    seq = list(start_seq)
    eos_token_id = np.where(encoder.classes_ == "<EOS>")[0][0] if "<EOS>" in encoder.classes_ else None
    for _ in range(max_steps):
        seq_padded = pad_sequences([seq], maxlen=pad_len, padding="post")
        preds = model.predict(seq_padded, verbose=0)[0]
        next_token = int(np.argmax(preds))
        seq.append(next_token)
        if eos_token_id is not None and next_token == eos_token_id:
            break
    return seq

# ----- Token Parsing Function -----
def parse_token(token):
    """
    Expects token in the format: "url | selector | action"
    Returns a tuple: (url, selector, action)
    """
    parts = token.split(" | ")
    if len(parts) >= 3:
        url = parts[0].strip()
        selector = parts[1].strip()
        action = parts[2].strip().lower()
        return url, selector, action
    return None, None, None

# ----- Dummy Reward Function with Sequence Checking -----
def calculate_reward_with_sequence(action, selector, page, predicted_token, expected_token):
    """
    Returns a reward based on both the action type and whether the predicted token
    matches the expected token in the sequence.
    """
    if action == "input":
        base_reward = 10
    elif action == "click":
        base_reward = 5
    elif action == "manipulation":
        base_reward = 8
    else:
        base_reward = 2
    if predicted_token == expected_token:
        seq_reward = 10
    else:
        seq_reward = -5
    return base_reward + seq_reward

# ----- Continuous Playwright Execution with Experience Storage and Sequence Checking -----
async def continuous_execute_actions(final_sequence):
    expected_sequence = [
        "https://slaying.ddns.net/#/login | input#email | input",
        "https://slaying.ddns.net/#/login | input#password | input",
        "https://slaying.ddns.net/#/login | button#loginButton | click",
        "https://slaying.ddns.net/#/search | button.mat-focus-indicator.btn-basket.mat-button.mat-raised-button.mat-button-base.mat-primary.ng-star-inserted | click",
        "https://slaying.ddns.net/#/search | button.mat-focus-indicator.buttons.mat-button.mat-button-base.ng-star-inserted | click",
        # Add more steps if needed
        "https://slaying.ddns.net/#/basket | body | manipulation"
    ]
    expected_index = 0

    experiences = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        total_reward = 0
        previous_token = None

        for token in final_sequence:
            if token == "<EOS>":
                print("EOS token reached. Ending interaction.")
                break
            if token == previous_token:
                continue
            previous_token = token

            url, selector, action = parse_token(token)
            if not selector:
                selector = "#default-selector"

            expected_token = expected_sequence[expected_index] if expected_index < len(expected_sequence) else None

            # Navigate if needed
            if page.url != url:
                await page.goto(url)
                time.sleep(1)

            print(f"Executing: action='{action}', selector='{selector}', URL='{url}'")
            try:
                if action == "click":
                    await page.click(selector)
                elif action == "input":
                    if "email" in selector.lower():
                        await page.fill(selector, "user@example.com")
                    elif "password" in selector.lower():
                        await page.fill(selector, "password123")
                    else:
                        await page.fill(selector, "test input")
                elif action == "manipulation":
                    # Scrape sessionStorage keys dynamically
                    session_keys = await page.evaluate("() => Object.keys(sessionStorage)")
                    print(f"Session storage keys: {session_keys}")
                    if session_keys:
                        # For example, choose the first key dynamically
                        target_key = session_keys[0]
                        new_value = "8"
                        print(f"Updating sessionStorage key '{target_key}' to '{new_value}'")
                        await page.evaluate(f"() => {{ sessionStorage['{target_key}'] = '{new_value}'; }}")
                        await page.reload()
                        time.sleep(5)
                    else:
                        print("[!] No sessionStorage keys found; skipping manipulation.")

                else:
                    # fallback if the action doesn't match known types
                    await page.click(selector)
            except Exception as e:
                print(f"[!] Error executing {action} on {selector}: {e}")

            await asyncio.sleep(1)

            # Reward logic
            step_reward = 5  # fallback reward
            if expected_token and token == expected_token:
                step_reward = 20  # big reward for correct step
                expected_index += 1
            else:
                step_reward = -5  # penalty if out of order or unexpected
            total_reward += step_reward
            print(f"Reward for this step: {step_reward}")

            experiences.append({
                "token": token,
                "action": action,
                "selector": selector,
                "url": url,
                "reward": step_reward,
                "expected_token": expected_token
            })

        print("Total reward accumulated:", total_reward)
        await browser.close()
    return experiences

# ----- End-to-End Demo Function -----
def run_end_to_end_demo():
    seq_file = "resource/lstm_sequences.npy"
    enc_file = "resource/encoder.pkl"
    model_file = "resource/lstm_model.keras"
    if not os.path.exists(seq_file) or not os.path.exists(enc_file) or not os.path.exists(model_file):
        print("Required training files missing. Please run your training pipeline first.")
        return
    
    model = load_model(model_file)
    with open(enc_file, "rb") as f:
        encoder = pickle.load(f)
    
    X_data = np.load(seq_file)  # Shape: (num_sequences, sequence_length)
    start_seq = X_data[0]  # Use the first sequence for demo
    pad_len = X_data.shape[1]
    
    predicted_indices = greedy_decode(model, start_seq, encoder, pad_len, max_steps=20)
    decoded_tokens = encoder.inverse_transform(np.array(predicted_indices))
    final_sequence = [token for token in decoded_tokens if token != "<PAD>"]
    print("Final predicted sequence:", final_sequence)
    
    experiences = asyncio.run(continuous_execute_actions(final_sequence))
    print("Collected experiences:")
    for exp in experiences:
        print(exp)
    
    with open("resource/experience_buffer.pkl", "wb") as f:
        pickle.dump(experiences, f)
    print("Experience buffer saved as resource/experience_buffer.pkl")

if __name__ == "__main__":
    # Optionally accept a URL argument from sys.argv (not strictly used in this script).
    run_end_to_end_demo()
