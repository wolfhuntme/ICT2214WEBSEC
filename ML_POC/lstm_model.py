import re
import pandas as pd
import numpy as np
from tensorflow.keras.preprocessing.sequence import pad_sequences
from sklearn.preprocessing import LabelEncoder
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Embedding, LSTM, Dense, Dropout
from sklearn.model_selection import train_test_split
import pickle

# ----- Helper: Generalize the URL -----
from urllib.parse import urlparse

def generalize_url(url):
    parsed = urlparse(url)
    if parsed.fragment:
        # Ensure the fragment starts with a slash
        return parsed.fragment if parsed.fragment.startswith("/") else "/" + parsed.fragment
    return parsed.path if parsed.path else url


# ----- Step 1: Load and Preprocess the Automation Log -----
def load_and_extract_tokens(csv_path="resource/training_data.csv"):
    df = pd.read_csv(csv_path)
    
    # Check required columns
    for col in ["id", "url", "selector", "action"]:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' is missing from the automation log.")
    
    # Extract workflow and step number from 'id'
    df["workflow"] = df["id"].str.extract(r"([A-Za-z]+)")
    df["step"] = df["id"].str.extract(r"(\d+)").astype(int)
    df.sort_values(by=["workflow", "step"], inplace=True)
    
    # Normalize action (lowercase)
    df["action"] = df["action"].astype(str).str.strip().str.lower()
    
    # Create a new column for the generalized URL
    df["generalized_url"] = df["url"].apply(generalize_url)
    
    # Create a token: "generalized_url | selector | action"
    df["token"] = df["generalized_url"].str.strip() + " | " + df["selector"] + " | " + df["action"]
    
    # Group rows by workflow to build sequences
    sequences = []
    for workflow, group in df.groupby("workflow"):
        group = group.sort_values(by="step")
        seq = group["token"].tolist()
        # Append EOS token only once at the end
        seq.append("<EOS>")
        sequences.append(seq)
    return sequences

# ----- Step 2: Encode the Token Sequences -----
def encode_sequences(sequences):
    # Add a dedicated PAD token to the vocabulary
    all_tokens = [token for seq in sequences for token in seq]
    if "<PAD>" not in all_tokens:
        all_tokens.append("<PAD>")
    encoder = LabelEncoder()
    encoder.fit(all_tokens)
    encoded_sequences = [encoder.transform(seq) for seq in sequences]
    return encoded_sequences, encoder

# ----- Step 3: Create Training Data -----
def create_training_data(encoded_sequences, pad_value):
    X, y = [], []
    # For each sequence, use every prefix as input and the next token as the target.
    for seq in encoded_sequences:
        for i in range(len(seq) - 1):
            X.append(seq[:i+1])
            y.append(seq[i+1])
    X_padded = pad_sequences(X, padding="post", value=pad_value)
    return X_padded, np.array(y)

# ----- Step 4: Build and Train the LSTM Model -----
def train_lstm_model(X_train, y_train, vocab_size, input_length, model_path="resource/lstm_model.h5"):
    model = Sequential([
        Embedding(input_dim=vocab_size, output_dim=64, input_length=input_length),
        LSTM(128, return_sequences=False),
        Dropout(0.2),
        Dense(vocab_size, activation='softmax')
    ])
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    model.fit(X_train, y_train, epochs=40, batch_size=32, validation_split=0.1)
    model.save(model_path)
    return model

# ----- Main Training Pipeline -----
def main():
    # Load and extract sequences from automation log
    sequences = load_and_extract_tokens("resource/automation_log10.csv")
    print("Extracted token sequences:")
    for seq in sequences:
        print(seq)
    
    # Encode sequences
    encoded_sequences, encoder = encode_sequences(sequences)
    # Get the PAD token index
    pad_token_index = encoder.transform(["<PAD>"])[0]
    
    # Create training data
    X_padded, y = create_training_data(encoded_sequences, pad_value=pad_token_index)
    print("\nX_padded shape:", X_padded.shape)
    print("Example X sequence (indices):", X_padded[0])
    print("Decoded tokens for first sequence:", encoder.inverse_transform(X_padded[0]))
    
    # Optionally, split training and test data for evaluation
    X_train, X_test, y_train, y_test = train_test_split(X_padded, y, test_size=0.2, random_state=42)
    
    vocab_size = len(encoder.classes_)
    input_length = X_train.shape[1]
    
    # Train the model
    model = train_lstm_model(X_train, y_train, vocab_size, input_length, model_path="resource/lstm_model.h5")
    print("Model trained and saved as resource/lstm_demo.keras")
    
    # Save the encoder for later use
    with open("resource/encoder.pkl", "wb") as f:
        pickle.dump(encoder, f)
    print("Encoder saved as resource/encoder.pkl")
    
    # Save the padded training sequences for prediction
    np.save("resource/lstm_sequences.npy", X_padded)
    print("Training sequences saved as resource/lstm_sequences.npy")

if __name__ == "__main__":
    main()
