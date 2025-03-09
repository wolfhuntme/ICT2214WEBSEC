import pickle

# Load the experience buffer
buffer_path = "resource/experience_buffer.pkl"  # Adjust the path if needed
with open(buffer_path, "rb") as f:
    experience_buffer = pickle.load(f)

# Print all stored experiences
print("Total experiences stored:", len(experience_buffer))
for i, exp in enumerate(experience_buffer):
    print(f"Experience {i+1}: {exp}")
