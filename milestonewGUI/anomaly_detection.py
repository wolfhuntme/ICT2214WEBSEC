#!/usr/bin/env python3
"""
anomaly_detection.py

Provides functionality to:
- Train an Isolation Forest model on 'normal' scenario metrics
- Use the trained model to detect anomalies in new scenario runs

Author: Security Team
Date: 2025-01-21
"""

import argparse
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import pickle

def train_model(csv_path: str, save_path: str):
    """
    Train an Isolation Forest model using metrics from a CSV file.
    
    CSV file is expected to have columns like:
      step_time, step_status_code, content_length, ...
    Possibly a "label" column if you want supervised-like checking, but for this
    example, we'll assume unsupervised anomaly detection on 'normal' data only.
    """
    df = pd.read_csv(csv_path)
    
    # Drop any columns that are non-numerical or irrelevant.
    # For example, if you have a 'step_name' or 'detail' column, remove them for modeling.
    feature_cols = [col for col in df.columns if col not in ('step_name','label','detail')]
    
    # Prepare feature matrix
    X = df[feature_cols].values
    
    # Train Isolation Forest
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X)
    
    # Save model
    with open(save_path, 'wb') as f:
        pickle.dump((model, feature_cols), f)
    
    print(f"Model trained and saved to {save_path}")

def detect_anomalies(model_path: str, metrics_df: pd.DataFrame):
    """
    Load the Isolation Forest model from disk, predict anomalies on the given metrics.
    
    Returns an array of predictions where -1 indicates anomaly and 1 indicates normal.
    """
    with open(model_path, 'rb') as f:
        model, feature_cols = pickle.load(f)
    
    # Ensure we only use the same feature columns the model was trained on
    X = metrics_df[feature_cols].values
    
    predictions = model.predict(X)   # array of 1 or -1
    return predictions

def main():
    parser = argparse.ArgumentParser(description="Anomaly Detection Training Utility")
    parser.add_argument("--train", help="Path to CSV for training data")
    parser.add_argument("--save", help="Path to save the trained model (pickle file)")
    args = parser.parse_args()
    
    if args.train and args.save:
        train_model(args.train, args.save)
    else:
        print("Usage: anomaly_detection.py --train data.csv --save model.pkl")

if __name__ == "__main__":
    main()
