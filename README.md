# **ICT2214 WEBSEC Project: LogicDetect**  

LogicDetect is an automated business logic flaw detector that uses **Machine Learning (ML)** to exploit vulnerabilities.

---

## **Project Structure**
The repository consists of the following key directories:

- **`ML_POC/`** - Final proof of concept (PoC) implementation of the tool
- **`ML_attempt/`** - Early ML model attempts and experiments.
- **`MilestoneGUI/`** - Milestone demonstration with a GUI for testing logic flaws.

---

## **Dependencies**  

Ensure the following dependencies are installed before running the project.

### **1. Install Required Python Libraries**  
Run the following commands in your terminal:
```sh
pip install flask flask-cors
pip install -r requirements.txt
```
(Note: Ensure `requirements.txt` is in the project root directory.)

### **2. Install Live Server Extension**  
- Install the [Live Server (Five Server)](https://marketplace.visualstudio.com/items?itemName=yandeu.five-server) extension for **Visual Studio Code**.

### **3. Install Graphviz**  
- Download and install [Graphviz](https://graphviz.org/download/) for your operating system.  

---

## **Repository Setup**  
Follow these steps to clone and set up the repository:

1. Open a command prompt or terminal.  
2. Clone the repository:
   ```sh
   git clone https://github.com/wolfhuntme/ICT2214WEBSEC.git
   ```
3. Initialize Git Large File Storage (LFS):
   ```sh
   git lfs install
   ```
4. Pull large files using Git LFS:
   ```sh
   git lfs pull
   ```
5. Verify that `venv.zip` (a Virtual Environment file) is present in the repository.

---

## **Running the Milestone Demonstration (GUI for Coupon & Bid ID Exploits)**  

To run the milestone app demonstration (found in `MilestoneGUI/`), follow these steps:

1. Open a command prompt **in Administrator mode**.  
2. Navigate to the milestone directory:
   ```sh
   cd MilestoneGUI
   ```
3. Unzip the virtual environment (`venv.zip`).  
4. Activate the virtual environment:  
   - **Windows:**  
     ```sh
     venv\Scripts\activate
     ```
   - **Mac/Linux:**  
     ```sh
     source venv/bin/activate
     ```
5. Start the Flask backend:
   ```sh
   python app.py
   ```
6. Open `gui.html` using **Live Server** via localhost.  
7. Input the target URL to **attack/train**.

---

## **Running the Final Proof of Concept (PoC) Product**  

To execute the final version of the ML-based business logic flaw detector (`ML_POC/`), run:

```sh
cd ML_POC
python lstm_execute_RL.py
```

---

## **Additional Notes**  
- Ensure you have the correct Python version (recommended: **Python 3.8+**).  
- Use **Administrator Mode** when necessary to avoid permission issues.  
- The tool integrates **LSTM-based prediction** and **Reinforcement Learning** to automate web attacks.  

---

