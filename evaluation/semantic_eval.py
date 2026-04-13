import json
import re
import sys
import os

sys.path.append("..")
from call_llm.call_gemini_flash import call_llm
# from call_llm.call_gpt import call_llm


SCORING_MAP = {
    "FUNCTIONAL EQUIVALENT": 100.0,
    "MINOR DISCREPANCY": 80.0,
    "MODERATE DISCREPANCY": 60.0,
    "SIGNIFICANT DEFECT": 40.0,
    "CRITICAL DEFECT": 20.0,
    "MISMATCH": 0.0
}


def construct_prompt(code_gt: str, code_gen: str) -> str:
    """Construct prompt content"""
    return f"""
You are a Senior Python Code Reviewer specializing in Plotly Dash applications.
Your task is to compare "Generated Code" against "Ground Truth Code" to evaluate their **Functional Equivalence**.

### Goal
Determine if the Generated Code implements the same interactive logic and data visualization behavior as the Ground Truth.
**Do not obsess over variable names, comment styles, or helper function structures.** Focus on the semantic logic of `app.layout` and `@app.callback`.

### Ground Truth Code:
{code_gt}

### Generated Code:
{code_gen}

### Evaluation Criteria
Analyze the code based on two dimensions:
1. **Layout Structure**: Are the component hierarchies (Divs, Graphs, Buttons) semantically identical?
2. **Callback Logic**: Do the callbacks listen to the same Inputs, update the same Outputs, and perform equivalent data transformations?

### Scoring Rubric (Select one Category)

1. **"Functional Equivalent"** (Score: 100)
   - The code is logically identical to the Ground Truth.
   - It produces the exact same UI structure and handles interactions (clicks, filters) correctly.
   - *Note: Different variable names or import aliases are ACCEPTABLE.*

2. **"Minor Discrepancy"** (Score: 80)
   - The code is mostly correct, but has very minor issues.
   - Example: UI layout is correct, but a default value is slightly off, or a color/style parameter is different.
   - Core interactivity works perfectly.

3. **"Moderate Discrepancy"** (Score: 60)
   - The UI and core logic are present, but there are noticeable functional gaps.
   - Example: The main chart updates, but a secondary filter is ignored; or the layout structure has changed enough to affect usability but not break the app.
   - The app is usable but not "polished".

4. **"Significant Defect"** (Score: 40)
   - The UI components exist, but the interactive logic (Callbacks) has major flaws.
   - Example: Callbacks trigger errors, or the data transformation logic is incorrect (e.g., wrong aggregation).
   - The app runs, but the main feature is buggy.

5. **"Critical Defect"** (Score: 20)
   - The code attempts to implement the task but fails significantly.
   - Example: UI is missing key components, or callbacks are hallucinated/non-functional.
   - The code might run, but it fails to perform the primary task entirely.

6. **"Mismatch"** (Score: 0)
   - The code is syntactically broken, irrelevant, uses the wrong libraries, or is empty.

### Output Format
You must respond with a SINGLE JSON object. 
{{
    "reasoning": "Step-by-step analysis of Layout and Callbacks differences...",
    "category": "Functional Equivalent", // Must be one of: "Functional Equivalent", "Minor Discrepancy", "Moderate Discrepancy", "Significant Defect", "Critical Defect", "Mismatch"
    "score": 100 // Corresponding integer score from the rubric
}}
"""


def extract_and_parse_json(text: str) -> dict:
    """Robust JSON parser"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    try:
        # Try to extract JSON block using regex
        pattern = r"\{(?:[^{}]|(?R))*\}"
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        else:
            raise ValueError("No JSON object found in text")
    except Exception as e:
        return {
            "category": "JSON_ERROR",
            "reasoning": f"Failed to parse JSON: {str(e)}",
            "raw_output": text
        }


def calculate_score(parsed_data: dict) -> dict:
    """Calculate score based on parsed JSON"""
    category_raw = parsed_data.get("category", "MISMATCH").upper()
    reasoning = parsed_data.get("reasoning", "No reasoning provided.")

    model_score = parsed_data.get("score")

    final_score = 0.0
    final_category = "MISMATCH"

    # Fuzzy match category
    matched = False
    for key, score in SCORING_MAP.items():
        # Handle potential spaces, case differences, and replace underscores with spaces
        normalized_key = key.replace("_", " ")
        normalized_raw = category_raw.replace("_", " ")

        if normalized_key in normalized_raw:
            final_score = score
            final_category = key
            matched = True
            break

    # If category not matched but model provided a score, use it as fallback
    if not matched and isinstance(model_score, (int, float)):
        final_score = float(model_score)
        final_category = "UNKNOWN_CATEGORY"

    return {
        "score": final_score,
        "category": final_category,
        "reasoning": reasoning,
        "raw_output": parsed_data.get("raw_output", "")
    }


def evaluate_code(code_gt: str, code_gen: str) -> dict:
    prompt = construct_prompt(code_gt, code_gen)
    # Recommended to use temperature=0.0 for stable evaluation results
    messages = [{"role": "user", "content": prompt}]

    # Call LLM
    llm_output = call_llm(messages)
    parsed_json = extract_and_parse_json(llm_output)

    if parsed_json.get("category") == "JSON_ERROR":
        return {"score": 0.0, **parsed_json}

    result = calculate_score(parsed_json)
    return result


if __name__ == "__main__":
    # Test code
    # For demonstration, no need to read actual files, just print structure
    print("Semantic Evaluation Script Updated.")
    print(f"Scoring Map: {json.dumps(SCORING_MAP, indent=2)}")
    print("Semantic Evaluation Script Updated.")
    print(f"Scoring Map: {json.dumps(SCORING_MAP, indent=2)}")