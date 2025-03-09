import os
from execute import run_execute
from predict import run_prediction

def run_demo(num_runs=1):
    # Demo prepared prediction values (each line corresponds to a demo action)
    demo_data = """<EOS>
https://slaying.ddns.net#/login | input#email OWASP Juice Shop | Important | 0.8152
https://slaying.ddns.net#/login | input#password OWASP Juice Shop | Important | 0.8631
https://slaying.ddns.net#/login | button#loginButton OWASP Juice Shop | Important | 0.8898
"""
    demo_file = "resource/PredictSelection.txt"

    for i in range(num_runs):
        print(f"\n[Demo] Run iteration {i+1}/{num_runs}")
        # Write the demo data to the prediction file
        with open(demo_file, "w", encoding="utf-8") as f:
            f.write(demo_data)
        print(f"[Demo] Demo prediction file written to {demo_file}")

        # Run the execute module with the demo predictions
        print("[Demo] Running execution with demo data...")
        run_execute()

        # Optionally, run prediction to further fine-tune/update the model based on demo experience
        print("[Demo] Running prediction (model training/fine-tuning) using demo data...")
        run_prediction()

if __name__ == "__main__":
    # Change this variable to run the demo the desired number of times.
    demo_runs = 80
    run_demo(demo_runs)
