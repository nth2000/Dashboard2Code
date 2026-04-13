import base64
import json
import os
from typing import List, Dict, Any
import sys

sys.path.append('..')
from call_llm.call_gemini_flash import call_llm
# from call_llm.call_gpt import call_llm


class DashboardEvaluator:
    def __init__(self):
        pass

    def _encode_image(self, image_path: str) -> str:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]

        try:
            return json.loads(cleaned_text.strip())
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {e}")
            print(f"Raw Response: {response_text}")
            return {"error": "JSON parse failed", "raw": response_text}

    def _construct_messages(self, prompt: str, image_paths: List[str]) -> List[Dict]:
        content_list = [{"type": "text", "text": prompt}]

        for path in image_paths:
            base64_img = self._encode_image(path)
            mime_type = "image/jpeg" if path.lower().endswith(('.jpg', '.jpeg')) else "image/png"
            content_list.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_img}"
                }
            })

        return [{
            "role": "user",
            "content": content_list
        }]


    def evaluate_visual_fidelity(self, gt_img_path: str, gen_img_path: str) -> Dict[str, Any]:
        prompt = """
You are an expert UI judge evaluating the fidelity of a Generated Dashboard Screenshot (GEN) against a Ground Truth Dashboard screenshot (GT).
Your goal is to assess how well the generated screenshot specifically recreated the visual appearance of the ground truth screenshot.

Image 1: Ground Truth (GT)
Image 2: Generated (GEN)

Please evaluate the GEN image based on the following specific criteria. 
**Ignore minor differences in window size or exact axis tick values (numbers on the axis), as rendering engines may vary.**

### Scoring Criteria:
1. **Layout & Components (0-20)**: 
   - Are all figures and interactive components present (e.g. Dropdowns, Sliders, Buttons, Tabs)?
   - Does the arrangement of figures and interactive components in the GEN image match the GT image?
2. **Chart Types (0-20)**:
   - Are all chart types correct (e.g., Bar vs Line vs Scatter)?
3. **Text Content (0-10)**: 
   - Do the Main Titles, Axis Titles, Legend Texts and Annotations match? 
   - (Note: Ignore precise axis tick numbers like '0.0' vs '0', focus on the semantic labels).
4. **Data & Grouping (0-20)**: 
   - Do the data trends look identical? 
   - Is the number of bars/lines/groups the same?
5. **Style & Aesthetics (0-20)**: 
   - Style matching: Does the GEN image match the GT in terms of colors (line colors, fill colors, etc.), marker types (point shapes, line styles, etc.), legends, grids, and other stylistic details?
   - Backgrounds and borders: Do they match the GT?
6. **Clarity (0-10)**: 
   - Is the layout clean?
   - **Crucial**: Are there any overlapping elements, cut-off text, or broken CSS rendering?

### Output Format:
Return a JSON object with specific scores and specific comments for each dimension.
{
    "layout_score": int,
    "layout_comment": "string",
    "chart_type_score": int,
    "chart_type_comment": "string",
    "text_content_score": int,
    "text_content_comment": "string",
    "data_fidelity_score": int,
    "data_fidelity_comment": "string",
    "style_score": int,
    "style_comment": "string",
    "clarity_score": int,
    "clarity_comment": "string"
}
    """
        messages = self._construct_messages(prompt, [gt_img_path, gen_img_path])
        response_text = call_llm(messages)
        result = self._parse_json_response(response_text)

        # Calculate total score out of 100
        if "error" not in result:
            total_score = (
                    result.get("layout_score", 0) +
                    result.get("chart_type_score", 0) +
                    result.get("text_content_score", 0) +
                    result.get("data_fidelity_score", 0) +
                    result.get("style_score", 0) +
                    result.get("clarity_score", 0)
            )
            result["total_score"] = total_score

        return result


    def evaluate_dynamic_behavior(self,
                                  gt_start: str, gt_end: str,
                                  gen_start: str, gen_end: str,
                                  task_description: str) -> Dict[str, Any]:
        prompt = f"""
Evaluate if the Generated Dashboard (GEN) behaves exactly like the Ground Truth (GT) for the user task: "{task_description}".

Images provided in order:
1. GT Start (Before Task)
2. GT End (After Task)
3. GEN Start (Before Task)
4. GEN End (After Task)

**Your task**: Compare the CHANGES from Image 1->2 (GT Delta) with the CHANGES from Image 3->4 (GEN Delta).

Focus ONLY on behavior consistency:
- Did the same data values change in both?
- Did the same visual elements get highlighted/updated?
- Did the same controls respond to the interaction?
- Did the dashboard update in the expected way?

**Do NOT evaluate**:
- Overall visual quality (handled separately)
- Layout integrity (handled separately)
- Style matching (handled separately)

Rate ONLY the dynamic behavior consistency on 0-10:
- 10: Perfect behavior match, GEN responds exactly like GT
- 7-9: Very similar behavior with minor differences
- 4-6: Correct general direction but noticeable differences
- 1-3: Behavior differs significantly
- 0: No behavior change or completely wrong response

Output JSON format only:
{{
    "dynamic_behavior_consistency_score": int (0-10),
    "reasoning": "brief explanation focusing on behavior changes"
}}
"""
        image_paths = [gt_start, gt_end, gen_start, gen_end]
        messages = self._construct_messages(prompt, image_paths)

        response_text = call_llm(messages)
        return self._parse_json_response(response_text)

if __name__ == "__main__":
    evaluator = DashboardEvaluator()

    task_desc = "Select 'Customer Type' in the 'Categorical Dimension' checklist"

    gt_t0 = r"C:\ws\pycharm_ws\dashboard2code\evaluation\task_execution_results\run_20251216_151942\App_10\step_0_initial\screenshot.png"
    gt_t1 = r"C:\ws\pycharm_ws\dashboard2code\evaluation\task_execution_results\run_20251216_151942\App_10\step_2\screenshot.png"
    gen_t0 = r"C:\ws\pycharm_ws\dashboard2code\evaluation\task_execution_results\run_20251218_105639\App_10\step_0_initial\screenshot.png"
    gen_t1 = r"C:\ws\pycharm_ws\dashboard2code\evaluation\task_execution_results\run_20251218_105639\App_10\step_2\screenshot.png"

    if all(os.path.exists(p) for p in [gt_t0, gt_t1, gen_t0, gen_t1]):

        print(">>> Running Visual Fidelity Evaluation at T0...")
        visual_t0 = evaluator.evaluate_visual_fidelity(gt_t0, gen_t0)
        print(json.dumps(visual_t0, indent=2, ensure_ascii=False))

        print("\n>>> Running Dynamic Behavior Evaluation (T0 -> T1)...")
        dynamic_res = evaluator.evaluate_dynamic_behavior(gt_t0, gt_t1, gen_t0, gen_t1, task_desc)
        print(json.dumps(dynamic_res, indent=2, ensure_ascii=False))

        print("\n>>> Running Visual Fidelity Evaluation at T1...")
        visual_t1 = evaluator.evaluate_visual_fidelity(gt_t1, gen_t1)
        print(json.dumps(visual_t1, indent=2, ensure_ascii=False))

    else:
        print("错误：未找到测试图片，请在代码中配置正确的图片路径。")