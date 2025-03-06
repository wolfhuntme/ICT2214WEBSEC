import pandas as pd
import json
from collections import defaultdict, Counter
from prefixspan import PrefixSpan

# ML imports
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

import pydot
import os

###############################################################################
# 1. Flatten Nested JSON Columns
###############################################################################
def parse_nested_columns(row_dict, nested_cols=None):
    """
    For each column in nested_cols, parse JSON and flatten sub-keys into names like
    session_data.bid or cookies[0].domain. We do NOT store a top-level dict or list,
    only sub-keys.
    """
    if nested_cols is None:
        nested_cols = ["session_data", "local_storage", "cookies"]

    flattened = {}
    for col in nested_cols:
        raw_value = row_dict.get(col, "")
        # If empty or NaN, mark it as NoValue
        if pd.isna(raw_value) or raw_value == "":
            flattened[col] = "NoValue"
            continue

        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            flattened[col] = "NoValue"
            continue

        if isinstance(parsed, dict):
            for k, v in parsed.items():
                flattened[f"{col}.{k}"] = v if v != "" else "NoValue"
        elif isinstance(parsed, list):
            if len(parsed) == 0:
                flattened[col] = "NoValue"
            else:
                for idx, item in enumerate(parsed):
                    if isinstance(item, dict):
                        for sub_k, sub_v in item.items():
                            flattened[f"{col}[{idx}].{sub_k}"] = sub_v if sub_v != "" else "NoValue"
                    else:
                        flattened[f"{col}[{idx}]"] = item if item != "" else "NoValue"
        else:
            flattened[col] = parsed if parsed != "" else "NoValue"

    return flattened

def flatten_csv_data(csv_path, nested_cols=None, output_path="flattened_output.csv"):
    """
    Reads the CSV, parses nested JSON columns, and exports a flattened CSV.
    Removes the original nested columns to avoid duplication.
    """
    if nested_cols is None:
        nested_cols = ["session_data", "local_storage", "cookies"]

    df = pd.read_csv(csv_path)
    flattened_rows = []
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        nested_dict = parse_nested_columns(row_dict, nested_cols)
        # Remove original columns
        for col in nested_cols:
            if col in row_dict:
                del row_dict[col]
        merged = {**row_dict, **nested_dict}
        flattened_rows.append(merged)

    df_flat = pd.DataFrame(flattened_rows)
    df_flat = df_flat.fillna("NoValue")
    df_flat.to_csv(output_path, index=False)
    print(f"Flattened CSV exported to: {output_path}")
    return df_flat

###############################################################################
# 2. Group Rows into Flows Based on First Character of 'id'
###############################################################################
def create_workflows(df_flat):
    workflow_sequences = defaultdict(list)
    workflow_rows = defaultdict(list)

    for _, row in df_flat.iterrows():
        row_id = str(row.get("id", ""))
        if row_id == "":
            wid = "Unknown"
        else:
            wid = row_id[0]
        action_step = f"{row.get('action', 'NoAction')} {row.get('element_label', 'NoLabel')}"
        workflow_sequences[wid].append(action_step)
        workflow_rows[wid].append(row.to_dict())

    return workflow_sequences, workflow_rows

###############################################################################
# 3. Analyze Overall Parameter Consistency for Each Flow
###############################################################################
def analyze_flow_consistency(workflow_rows, monitored_prefixes=None):
    if monitored_prefixes is None:
        monitored_prefixes = ["session_data", "local_storage", "cookies"]

    flow_consistency_summary = {}

    for flow_id, rows in workflow_rows.items():
        param_summary = {}
        all_monitored_keys = set()

        # Gather all keys that start with monitored prefixes
        for r in rows:
            for key in r.keys():
                if any(key.startswith(prefix) for prefix in monitored_prefixes):
                    all_monitored_keys.add(key)

        for key in all_monitored_keys:
            values = []
            steps_present = []
            for idx, r in enumerate(rows, start=1):
                val = r.get(key, "NoValue")
                values.append(val)
                if val != "NoValue":
                    steps_present.append(idx)
            present_in_all = (len(steps_present) == len(rows))
            # Determine consistency and count changes
            if values and all(v == values[0] for v in values):
                consistent = True
                change_details = "Never changed"
                change_count = 0
            else:
                consistent = False
                change_indices = []
                for i in range(1, len(values)):
                    if values[i] != values[i-1]:
                        change_indices.append(i + 1)
                change_details = f"Changed at steps: {change_indices}" if change_indices else "Inconsistent"
                change_count = len(change_indices)

            param_summary[key] = {
                "present_in_all": present_in_all,
                "consistent": consistent,
                "start_value": values[0] if values else "NoValue",
                "end_value": values[-1] if values else "NoValue",
                "change_details": change_details,
                "change_count": change_count,
                "all_values": values
            }

        flow_consistency_summary[flow_id] = param_summary

    return flow_consistency_summary

###############################################################################
# 4. Frequent Pattern Mining (PrefixSpan)
###############################################################################
def find_frequent_patterns(workflow_sequences, min_support=2, max_pattern_len=None):
    sequences = list(workflow_sequences.values())
    ps = PrefixSpan(sequences)
    ps.lazy = True

    results = []
    for (pattern, support) in ps.frequent(min_support):
        if max_pattern_len is not None and isinstance(pattern, list) and len(pattern) > max_pattern_len:
            continue
        results.append((pattern, support))
    return results

###############################################################################
# 5. Build ML Dataset for Business Logic Flaw Detection
###############################################################################
def build_ml_dataset(workflow_sequences, flow_consistency_summary):
    data = []
    for flow_id, seq in workflow_sequences.items():
        features = {}
        features["flow_id"] = flow_id
        features["num_steps"] = len(seq)
        inconsistency_count = 0
        details = []
        param_summary = flow_consistency_summary.get(flow_id, {})

        for key, info in param_summary.items():
            if not info["consistent"]:
                inconsistency_count += 1
                details.append(f"{key}: {info['change_details']}")

        features["inconsistent_param_count"] = inconsistency_count
        features["inconsistency_details"] = "; ".join(details) if details else "None"
        features["flaw_label"] = 1 if inconsistency_count > 0 else 0
        data.append(features)

    df_ml = pd.DataFrame(data)
    return df_ml

###############################################################################
# 6. Train ML Model to Predict Business Logic Flaws
###############################################################################
def train_and_predict_flaws(df_ml):
    if len(df_ml) < 2 or df_ml["flaw_label"].nunique() < 2:
        print("Not enough data to train ML model (need at least 2 flows and both classes).")
        df_ml["predicted_flaw"] = "NoModel"
        return df_ml

    X = df_ml[["num_steps", "inconsistent_param_count"]]
    y = df_ml["flaw_label"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)
    predictions = clf.predict(X_test)
    acc = accuracy_score(y_test, predictions)
    print(f"ML Model Accuracy (flaw detection): {acc:.2f}")
    df_ml["predicted_flaw"] = clf.predict(X)
    return df_ml

###############################################################################
# 7. Generate Detailed Insights on Consistency Segments (Numeric labeling)
###############################################################################
def generate_detailed_insights(workflow_rows, monitored_prefixes=None, output_csv="detailed_insights.csv"):
    if monitored_prefixes is None:
        monitored_prefixes = ["session_data", "local_storage", "cookies"]

    insights = []
    for flow_id, rows in workflow_rows.items():
        all_keys = set()
        for r in rows:
            for key in r.keys():
                if any(key.startswith(pref) for pref in monitored_prefixes):
                    all_keys.add(key)
        # Filter out top-level keys; keep sub-keys only
        filtered_keys = [k for k in all_keys if "." in k or "[" in k]
        for key in filtered_keys:
            values = [r.get(key, "NoValue") for r in rows]
            start_idx = 0
            while start_idx < len(values):
                current_value = values[start_idx]
                end_idx = start_idx
                while end_idx + 1 < len(values) and values[end_idx+1] == current_value:
                    end_idx += 1
                if current_value != "NoValue":
                    insights.append({
                        "flow_id": flow_id,
                        "parameter": key,
                        "consistent_value": current_value,
                        "segment": f"{start_idx+1} to {end_idx+1}",
                        "segment_length": end_idx - start_idx + 1
                    })
                start_idx = end_idx + 1

    df_insights = pd.DataFrame(insights)
    df_insights.to_csv(output_csv, index=False)
    print(f"Detailed insights exported to: {output_csv}")
    return df_insights

###############################################################################
# 8. Export Workflow Summary CSV with Consistency, ML Predictions, and Most Suspect Parameter
###############################################################################
def export_workflow_summary(workflow_sequences, flow_consistency_summary, df_ml, frequent_patterns,
                            output_csv="workflow_summary.csv"):
    summary_rows = []
    for flow_id, seq in workflow_sequences.items():
        row = {
            "flow_id": flow_id,
            "sequence": " -> ".join(seq),
            "num_steps": len(seq)
        }
        param_info = flow_consistency_summary.get(flow_id, {})
        details = []
        # Determine the parameter most likely to be a flaw based on the highest change_count
        suspect_param = None
        max_changes = 0
        for key, info in param_info.items():
            present = "Yes" if info["present_in_all"] else "Partial"
            consistency = "Consistent" if info["consistent"] else "Inconsistent"
            details.append(f"{key} ({present}, {consistency}, start: {info['start_value']}, end: {info['end_value']})")
            if not info["consistent"] and info["change_count"] > max_changes:
                max_changes = info["change_count"]
                suspect_param = key

        row["parameter_summary"] = " | ".join(details) if details else "No monitored parameters"
        row["most_suspect_parameter"] = f"{suspect_param} (changed {max_changes} times)" if suspect_param else "None"
        summary_rows.append(row)

    df_summary = pd.DataFrame(summary_rows)
    df_final = df_summary.merge(df_ml, on="flow_id", how="left")

    desired_cols = ["flow_id", "sequence", "num_steps", "parameter_summary",
                    "most_suspect_parameter", "inconsistent_param_count", "inconsistency_details",
                    "flaw_label", "predicted_flaw"]
    existing_cols = [col for col in desired_cols if col in df_final.columns]
    other_cols = [c for c in df_final.columns if c not in existing_cols]
    df_final = df_final[existing_cols + other_cols]

    df_final.to_csv(output_csv, index=False)
    print(f"Workflow summary with ML predictions exported to: {output_csv}\n")

    print("=== Global Frequent Patterns (min support=2) ===")
    for item in frequent_patterns:
        pattern, support = item
        if isinstance(pattern, list):
            pattern_str = " -> ".join(pattern)
        else:
            pattern_str = str(pattern)
        print(f"Pattern: {pattern_str}, Support: {support}")

###############################################################################
# 9. Graph Visualization of Each Flow (Numeric labels)
###############################################################################
def generate_flow_graphs(workflow_sequences, workflow_rows, flow_consistency_summary,
                         output_dir="flow_graphs", show_param_changes=True):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for flow_id, seq in workflow_sequences.items():
        if len(seq) == 0:
            continue

        graph = pydot.Dot(f"Flow_{flow_id}", graph_type='digraph', rankdir='LR')
        node_names = []
        for i, action in enumerate(seq, start=1):
            node_label = f"Step {i}: {action}"
            node = pydot.Node(f"{flow_id}_{i}", label=node_label, shape="box")
            graph.add_node(node)
            node_names.append(f"{flow_id}_{i}")

        param_summary = flow_consistency_summary.get(flow_id, {})

        def get_param_changes_at_transition(param_summary, step_idx, next_idx):
            changes = []
            for key, info in param_summary.items():
                vals = info.get("all_values", [])
                if 0 <= (step_idx - 1) < len(vals) and 0 <= (next_idx - 1) < len(vals):
                    if vals[step_idx - 1] != vals[next_idx - 1]:
                        changes.append(key)
            return changes

        for i in range(1, len(seq)):
            src = node_names[i-1]
            dst = node_names[i]
            if show_param_changes:
                changed_params = get_param_changes_at_transition(param_summary, i, i+1)
                if changed_params:
                    edge_label = "\\n".join(changed_params)
                    edge = pydot.Edge(src, dst, label=edge_label)
                else:
                    edge = pydot.Edge(src, dst)
            else:
                edge = pydot.Edge(src, dst)
            graph.add_edge(edge)

        graph_path = os.path.join(output_dir, f"flow_{flow_id}.png")
        graph.write_png(graph_path)
        print(f"Exported flow graph for flow {flow_id} -> {graph_path}")

###############################################################################
# 10. Merge Insights with Steps (HTML Visual Display, Numeric parsing)
###############################################################################
def merge_flow_insights_with_steps(detailed_insights_df, workflow_sequences, output_html="visual_display.html"):
    df_merged = detailed_insights_df.copy()
    actions_in_segment_list = []

    for idx, row in df_merged.iterrows():
        flow_id = row["flow_id"]
        segment_str = row["segment"]
        if flow_id not in workflow_sequences or " to " not in segment_str:
            actions_in_segment_list.append("")
            continue
        start_str, end_str = segment_str.split(" to ")
        try:
            start_step = int(start_str)
            end_step = int(end_str)
        except ValueError:
            actions_in_segment_list.append("")
            continue

        all_actions = workflow_sequences[flow_id]
        end_step = min(end_step, len(all_actions))
        if start_step > len(all_actions):
            actions_in_segment_list.append("No actions (segment out of range)")
            continue

        sub_actions = all_actions[start_step - 1 : end_step]
        actions_str = " | ".join(sub_actions)
        actions_in_segment_list.append(actions_str)

    df_merged["actions_in_segment"] = actions_in_segment_list

    flow_sequence_list = []
    for idx, row in df_merged.iterrows():
        flow_id = row["flow_id"]
        if flow_id in workflow_sequences:
            labeled_steps = []
            for i, action in enumerate(workflow_sequences[flow_id], start=1):
                labeled_steps.append(f"Step {i}: {action}")
            flow_sequence_list.append(" || ".join(labeled_steps))
        else:
            flow_sequence_list.append("No sequence found")
    df_merged["full_flow_sequence"] = flow_sequence_list

    df_merged.sort_values(by=["flow_id", "parameter", "segment"], inplace=True)
    html_str = df_merged.to_html(index=False, escape=False)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='UTF-8'></head><body>")
        f.write("<h1>Detailed Flow Segments with Actions</h1>")
        f.write(html_str)
        f.write("</body></html>")
    print(f"Visual display exported to: {output_html}")
    return df_merged

###############################################################################
# Main Execution
###############################################################################
if __name__ == "__main__":
    # Step A: Flatten the CSV
    input_csv = "resource/automation_log10.csv"  # Update path if needed
    df_flattened = flatten_csv_data(
        input_csv,
        ["session_data", "local_storage", "cookies"],
        "flattened_output.csv"
    )

    # Step B: Create flows
    workflow_sequences, workflow_rows = create_workflows(df_flattened)

    # Step C: Analyze consistency
    flow_consistency_summary = analyze_flow_consistency(workflow_rows)

    # Step D: Frequent patterns (manual max pattern length)
    frequent_patterns = find_frequent_patterns(
        workflow_sequences,
        min_support=5,        # Adjust support as needed
        max_pattern_len=5     # Skip patterns longer than 5
    )

    # Step E: Build ML dataset
    df_ml = build_ml_dataset(workflow_sequences, flow_consistency_summary)

    # Step F: Train ML
    df_ml = train_and_predict_flaws(df_ml)

    # Step G: Generate detailed insights
    detailed_insights_df = generate_detailed_insights(
        workflow_rows,
        output_csv="detailed_insights.csv"
    )

    # Step H: Export workflow summary (with suspect parameter)
    export_workflow_summary(
        workflow_sequences,
        flow_consistency_summary,
        df_ml,
        frequent_patterns,
        "workflow_summary.csv"
    )

    # Step I: Merge insights for HTML display
    df_visual = merge_flow_insights_with_steps(
        detailed_insights_df,
        workflow_sequences,
        "visual_display.html"
    )

    # Step J: Generate graph visualizations
    generate_flow_graphs(
        workflow_sequences,
        workflow_rows,
        flow_consistency_summary,
        output_dir="flow_graphs",
        show_param_changes=True
    )

    print("Process completed successfully.")
