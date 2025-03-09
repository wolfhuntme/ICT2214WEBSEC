import sys
import time
from list import crawl_list
from scrape import run_scrape
from zero import run_zero_shot_classification
from eventCluster import run_event_clustering
from predict import run_prediction
from execute import run_execute
import os

base_url = "https://slaying.ddns.net"

def run_full_pipeline(base_url):
    print("[Orchestrator] Starting full pipeline...")
    # Discover new URLs
    crawl_list(base_url)
    # Scrape the discovered URLs
    run_scrape(base_url)

    # Check if scrape.json exists and has data before proceeding
    if not os.path.exists("resource/scrape.json") or os.stat("resource/scrape.json").st_size == 0:
        print("No scraped data found. Skipping zero-shot classification, clustering, prediction, and execution.")
        return

    # Run zero-shot classification to update element labels
    run_zero_shot_classification()
    # Run clustering for event grouping
    run_event_clustering()
    # Run prediction (model fine-tuning and beam search decoding)
    run_prediction()
    # Execute workflow actions and update the RL model based on feedback
    run_execute()
    print("[Orchestrator] Full pipeline completed.")

def main():
    default_url = "https://slaying.ddns.net"
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = default_url
        print("No URL provided. Using default URL:", base_url)

    # Here you can add state detection logic. For now we assume a state change (e.g. logged in) is detected.
    state_change_detected = True  # Replace with actual detection logic as needed.
    if state_change_detected:
        run_full_pipeline(base_url)
    else:
        print("No state change detected. Exiting.")

if __name__ == "__main__":
    main()