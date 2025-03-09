import os
import pandas as pd
import re
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import LabelEncoder
from tensorflow.keras.preprocessing.sequence import pad_sequences
from sklearn.model_selection import train_test_split
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Embedding, Bidirectional, LSTM, Dense, Dropout
import matplotlib.pyplot as plt
import sys

def run_prediction():
    sys.stdout.reconfigure(encoding='utf-8')
    FILE_PATH = 'resource/clustered_output.csv'

    # Read the CSV directly
    try:
        df = pd.read_csv(FILE_PATH)
    except Exception as e:
        raise ValueError(f"Failed to read {FILE_PATH}: {e}")

    # Ensure the required columns exist and fill missing values
    for col in ['url', 'selector', 'page_title', 'classification']:
        if col not in df.columns:
            raise ValueError(f"Expected column '{col}' not found in CSV.")
        df[col] = df[col].fillna("")

    # Filter for login-related workflows
    df = df[df['url'].str.contains('/login', case=False, na=False)]

    # Data Enrichment: create a combined token
    df['token'] = (df['url'].str.strip() + " | " +
                   df['selector'].str.strip() + " | " +
                   df['page_title'].str.strip() + " | " +
                   df['classification'].str.strip())

    # Group rows by cluster into sequences
    sequences = []
    current_sequence = []
    for i in range(len(df)):
        if i == 0:
            current_sequence.append(df.iloc[i]['token'])
        else:
            if df.iloc[i]['cluster'] == df.iloc[i - 1]['cluster']:
                current_sequence.append(df.iloc[i]['token'])
            else:
                sequences.append(current_sequence)
                current_sequence = [df.iloc[i]['token']]
    sequences.append(current_sequence)

    EOS_TOKEN = "<EOS>"
    sequences = [seq + [EOS_TOKEN] for seq in sequences]

    encoder = LabelEncoder()
    all_tokens = [item for sublist in sequences for item in sublist]
    encoder.fit(all_tokens)
    encoded_sequences = [encoder.transform(seq) for seq in sequences]

    X, y = [], []
    for seq in encoded_sequences:
        for i in range(len(seq) - 1):
            X.append(seq[:i + 1])
            y.append(seq[i + 1])

    X_padded = pad_sequences(X, padding='post')
    X_train, X_test, y_train, y_test = train_test_split(X_padded, y, test_size=0.2, random_state=42)
    X_train, X_test = np.array(X_train), np.array(X_test)
    y_train, y_test = np.array(y_train), np.array(y_test)

    vocab_size = len(encoder.classes_)
    model_path = "resource/workflow_lstm_model.keras"
    if os.path.exists(model_path):
        print("Loading existing model...")
        model = load_model(model_path)
        # Fine-tuning (adaptive training)
        model.fit(X_train, y_train, epochs=5, batch_size=32, validation_data=(X_test, y_test))
    else:
        print("Building a new model...")
        model = Sequential([
            Embedding(input_dim=vocab_size, output_dim=64, input_length=X_train.shape[1]),
            Bidirectional(LSTM(128, return_sequences=True)),
            Dropout(0.1),
            Bidirectional(LSTM(64)),
            Dense(128, activation='relu'),
            Dense(vocab_size, activation='softmax')
        ])
        model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
        model.fit(X_train, y_train, epochs=50, batch_size=32, validation_data=(X_test, y_test))
    model.save(model_path)
    print(f"Model saved as {model_path}")

    # Beam Search Decoding (rest of your code remains unchanged)
    def beam_search_decode(model, start_sequence, encoder, beam_width=3, max_steps=10, pad_len=None):
        if pad_len is None:
            pad_len = len(start_sequence)
        eos_token_id = None
        if "<EOS>" in encoder.classes_:
            eos_token_id = np.where(encoder.classes_ == "<EOS>")[0][0]
        beam = [(start_sequence, 0.0)]
        for _ in range(max_steps):
            new_beam = []
            for seq, score in beam:
                seq_padded = pad_sequences([seq], maxlen=pad_len, padding='post')
                preds = model.predict(seq_padded, verbose=0)[0]
                top_indices = np.argsort(preds)[-beam_width:]
                for idx in top_indices:
                    token_prob = preds[idx]
                    new_score = score + np.log(token_prob + 1e-10)
                    new_seq = np.append(seq, idx)[-pad_len:]
                    new_beam.append((new_seq, new_score))
            new_beam.sort(key=lambda x: x[1], reverse=True)
            beam = new_beam[:beam_width]
            best_seq, best_score = beam[0]
            if eos_token_id is not None and best_seq[-1] == eos_token_id:
                return best_seq
        return beam[0][0]

    start_seq = X_test[0]
    best_sequence = beam_search_decode(model, start_seq, encoder, beam_width=3, max_steps=10, pad_len=X_test.shape[1])
    decoded_tokens = encoder.inverse_transform(best_sequence.astype(int))
    output_file = "resource/PredictSelection.txt"
    with open(output_file, "w") as f:
        for token in decoded_tokens:
            f.write(token + "\n")
    print(f"Beam Search Final Sequence of Tokens saved to {output_file}")


if __name__ == "__main__":
    run_prediction()
