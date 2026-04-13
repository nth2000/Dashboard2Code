import base64
import json
import re
import traceback
from io import BytesIO
from PIL import Image
from call_llm.call_gemini_flash import call_llm


class EvalAgent:
    VIEWPORT_W = 1920
    VIEWPORT_H = 1080

    def __init__(self, api_key=None):
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self):
        with open("../prompt/executor_prompt.txt", "r", encoding="utf-8") as f:
            prompt_text = f.read()
        return prompt_text

    def encode_image(self, image):
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def parse_response(self, response_text):
        try:
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {"type": "FAIL", "reason": "No JSON found"}
        except Exception as e:
            return {"type": "FAIL", "reason": f"JSON Parse Error: {str(e)}"}

    def _normalize_tree(self, tree):
        """
        将 DOM 树中的 [left, top, width, height] (Pixels)
        转换为 [ymin, xmin, ymax, xmax] (0-1000 Normalized)
        """
        normalized_tree = []
        for node in tree:
            # 原始数据: [x, y, w, h] (像素)
            x, y, w, h = node['box']

            # 计算归一化坐标 [ymin, xmin, ymax, xmax]
            # ymin
            y1 = int((y / self.VIEWPORT_H) * 1000)
            # xmin
            x1 = int((x / self.VIEWPORT_W) * 1000)
            # ymax
            y2 = int(((y + h) / self.VIEWPORT_H) * 1000)
            # xmax
            x2 = int(((x + w) / self.VIEWPORT_W) * 1000)

            # 边界修正，防止超出 0-1000
            y1 = max(0, min(1000, y1))
            x1 = max(0, min(1000, x1))
            y2 = max(0, min(1000, y2))
            x2 = max(0, min(1000, x2))

            new_node = node.copy()
            new_node['box'] = [y1, x1, y2, x2]  # Gemini 格式
            normalized_tree.append(new_node)

        return normalized_tree

    def _denormalize_action(self, action):
        """
        将 Action 中的 0-1000 坐标转换为实际像素坐标 (1920x1080)
        """
        if not action:
            return action

        new_action = action.copy()

        # 转换辅助函数
        def to_px_x(val_1000):
            return int((val_1000 / 1000) * self.VIEWPORT_W)

        def to_px_y(val_1000):
            return int((val_1000 / 1000) * self.VIEWPORT_H)

        # 映射所有可能的坐标字段
        if 'x' in new_action: new_action['x'] = to_px_x(new_action['x'])
        if 'y' in new_action: new_action['y'] = to_px_y(new_action['y'])

        if 'from_x' in new_action: new_action['from_x'] = to_px_x(new_action['from_x'])
        if 'from_y' in new_action: new_action['from_y'] = to_px_y(new_action['from_y'])
        if 'to_x' in new_action: new_action['to_x'] = to_px_x(new_action['to_x'])
        if 'to_y' in new_action: new_action['to_y'] = to_px_y(new_action['to_y'])

        return new_action

    def run_task(self, environment, task_description, max_steps=10):
        trajectory = []
        max_resets = 3
        reset_count = 0

        try:
            print(f"--- Starting Task: {task_description} ---")

            while reset_count <= max_resets:
                if reset_count > 0:
                    print(f"*** Triggering RESET ({reset_count}/{max_resets}) ***")
                    environment.reset()

                prev_screenshot = None
                current_loop_trajectory = []
                task_status = "RUNNING"

                for step in range(max_steps):
                    # 1. 获取环境状态
                    current_screenshot = environment.get_screenshot(apply_marks=False)

                    # 获取原始像素 DOM 树 (Array of objects)
                    raw_tree = environment.get_a11y_tree()

                    # 在 Python 端进行归一化处理 (Pixels -> 0-1000)
                    normalized_tree = self._normalize_tree(raw_tree)

                    # --- 构建 Action History ---
                    if not current_loop_trajectory:
                        history_str = "None (Start of task)"
                    else:
                        history_lines = []
                        for item in current_loop_trajectory:
                            # 记录给 LLM 看的 Action (normalized)
                            action_str = json.dumps(item['action'])
                            history_lines.append(f"Step {item['step'] + 1}: {action_str}")
                        history_str = "\n".join(history_lines)

                    # 2. 构造 Prompt
                    content_list = [
                        {"type": "text", "text": f"**User Task**: {task_description}"},
                        {"type": "text", "text": f"**Action History**:\n{history_str}"},
                        {"type": "text",
                         "text": f"**Accessibility Tree (Box: [ymin, xmin, ymax, xmax], 0-1000)**:\n{json.dumps(normalized_tree)}"}
                    ]

                    if prev_screenshot:
                        content_list.append({"type": "text", "text": "**Previous Screen**:"})
                        content_list.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{self.encode_image(prev_screenshot)}"}
                        })

                    content_list.append({"type": "text", "text": "**Current Screen**:"})
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{self.encode_image(current_screenshot)}"}
                    })

                    messages = [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": content_list}
                    ]

                    # 3. 调用模型
                    response_text = call_llm(messages)
                    action_normalized = self.parse_response(response_text)
                    print(f"Step {step + 1} (Reset {reset_count}): {action_normalized.get('type')}")

                    prev_screenshot = current_screenshot
                    action_type = action_normalized.get('type')

                    # 4. 处理终止状态
                    if action_type == 'DONE':
                        current_loop_trajectory.append(
                            {"step": step, "action": action_normalized, "response": "Finished"})
                        trajectory.extend(current_loop_trajectory)
                        return {
                            "success": True, "status": "DONE", "trajectory": trajectory,
                            "final_screenshot": current_screenshot,
                            "final_chart_data": environment.scan_current_graphs()
                        }

                    if action_type == 'FAIL':
                        current_loop_trajectory.append(
                            {"step": step, "action": action_normalized, "response": "Agent Give Up"})
                        trajectory.extend(current_loop_trajectory)
                        return {
                            "success": False, "status": "FAIL",
                            "reason": action_normalized.get('reason', 'Unknown failure'),
                            "trajectory": trajectory, "final_screenshot": current_screenshot,
                            "final_chart_data": []
                        }

                    if action_type == 'RESET':
                        current_loop_trajectory.append(
                            {"step": step, "action": action_normalized, "response": "Request Reset"})
                        task_status = "RESET"
                        break

                    # 5. 反归一化 (0-1000 -> Pixels) 以便执行
                    action_pixels = self._denormalize_action(action_normalized)

                    # 6. 执行交互 (传入像素坐标)
                    exec_result = environment.execute_action(action_pixels)

                    current_loop_trajectory.append({
                        "step": step,
                        "reset_attempt": reset_count,
                        "action": action_normalized,  # 记录 LLM 的意图 (0-1000)
                        "action_pixels": action_pixels,  # 记录实际执行的像素坐标
                        "result": exec_result
                    })

                trajectory.extend(current_loop_trajectory)
                if task_status == "RESET":
                    reset_count += 1
                    continue
                else:
                    break

            final_screenshot = environment.get_screenshot(apply_marks=False)
            return {
                "success": False,
                "status": "MAX_RESETS_EXCEEDED" if reset_count > max_resets else "MAX_STEPS_REACHED",
                "trajectory": trajectory,
                "final_screenshot": final_screenshot,
                "reason": "Exceeded maximum attempts or steps",
                "final_chart_data": []
            }

        except Exception as e:
            error_msg = traceback.format_exc()
            print(f"CRITICAL ERROR: {error_msg}")
            return {
                "success": False, "status": "CRITICAL_ERROR",
                "reason": str(e), "trajectory": trajectory
            }