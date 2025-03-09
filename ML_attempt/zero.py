import json
import pandas as pd
from transformers import pipeline
import sys


def run_zero_shot_classification():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        with open("resource/zero_config.json", "r", encoding="utf-8") as cfg:
            config = json.load(cfg)
        confidence_threshold = config.get("confidence_threshold", 0.5)
    except Exception:
        confidence_threshold = 0.5

    with open("resource/scrape.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    labels = ["Important", "Non-Important"]

    def create_text(item):
        name_role = item.get("name_role", "Unnamed element")
        page_title = item.get("page_title", "Unknown page")
        element_type = item.get("type", "unknown element")
        text_parts = [f"This is a {element_type} labeled '{name_role}' on the {page_title} page."]
        if "api_calls" in item and isinstance(item["api_calls"], list) and item["api_calls"]:
            text_parts.append(f"It is associated with API calls: {', '.join(item['api_calls'])}.")
        if "javascript_variables" in item and isinstance(item["javascript_variables"], list) and item[
            "javascript_variables"]:
            text_parts.append(f"It has JavaScript variables: {', '.join(item['javascript_variables'])}.")
        return " ".join(text_parts)

    for item in data:
        text = create_text(item)
        result = classifier(text, candidate_labels=labels)
        top_label = result["labels"][0]
        top_score = result["scores"][0]
        if top_score < confidence_threshold:
            item["classification"] = "Important"
            item["confidence"] = round(top_score, 4)
        else:
            item["classification"] = top_label
            item["confidence"] = round(top_score, 4)

    df = pd.DataFrame(data)
    df.to_csv("resource/zero_shot_results.csv", index=False, encoding="utf-8")
    print("[✅] Zero-shot classification complete. Saved to 'resource/zero_shot_results.csv'")


if __name__ == "__main__":
    run_zero_shot_classification()
