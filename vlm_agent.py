# vlm_agent.py
import base64
import json
import hashlib
import re
from io import BytesIO
from PIL import Image
from call_llm.call_gemini import call_llm
# from call_llm.call_gpt import call_llm
# from call_llm.call_claude import call_llm
# from call_llm.call_qwen import call_llm
import json
import copy


class VLMAgent:
    def __init__(self, model="gpt-5", api_key=None,
                 enable_screenshot_matching=True,
                 enable_context_compression=False,
                 enable_a11y_tree=False):
        self.model = model
        self.conversation_history = []  # 存储对话历史
        self.task_description = None
        self.is_initialized = False

        # 功能开关
        self.enable_screenshot_matching = enable_screenshot_matching
        self.enable_context_compression = enable_context_compression
        self.enable_a11y_tree = enable_a11y_tree

        self.screenshot_cache = []  # 截图缓存列表

    def load_task_description(self, prompt_file="prompt/generator_prompt.txt"):
        with open(prompt_file, "r", encoding="utf-8") as f:
            self.task_description = f.read()

    # --- 图片处理辅助函数 ---

    def encode_image(self, image, target_size=None):
        """将 PIL Image 编码为 Base64 字符串，可选择调整大小。"""
        img_to_encode = image
        if target_size:
            img_to_encode = image.resize(target_size, Image.Resampling.LANCZOS)

        buffered = BytesIO()
        img_to_encode.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def compute_hash(self, image):
        """计算图片的 MD5 哈希值，用于精确匹配。"""
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return hashlib.md5(buffered.getvalue()).hexdigest()

    def _resize_base64_image(self, base64_str, target_size=(480, 270)):
        """解码 Base64，调整图片大小，然后重新编码为 Base64。"""
        try:
            img_data = base64.b64decode(base64_str)
            img = Image.open(BytesIO(img_data))
            # 如果图片已经很小，则不再处理
            if img.width <= target_size[0]:
                return base64_str
            return self.encode_image(img, target_size=target_size)
        except Exception as e:
            print(f"图片压缩失败: {e}")
            return base64_str

    # --- 核心逻辑辅助函数 ---

    def _compress_history_images(self):
        """
        压缩历史记录中'上一轮' User 消息里的图片。
        应在存入新一轮高清图之前调用。
        """
        if not self.enable_context_compression or not self.conversation_history:
            return

        # 倒序查找最近的一条 User 消息
        for i in range(len(self.conversation_history) - 1, -1, -1):
            msg = self.conversation_history[i]
            if msg['role'] == 'user' and isinstance(msg['content'], list):
                for item in msg['content']:
                    if item['type'] == 'image_url':
                        url = item['image_url']['url']
                        if url.startswith("data:image/png;base64,"):
                            raw_b64 = url.split(",")[1]
                            # 执行压缩
                            new_b64 = self._resize_base64_image(raw_b64)
                            item['image_url']['url'] = f"data:image/png;base64,{new_b64}"
                # 我们只压缩最近的一条，假设更早的已经被压缩过了
                break

    def find_matching_screenshot(self, current_image):
        """在缓存中查找是否有与当前截图 MD5 完全匹配的记录。"""
        if not self.enable_screenshot_matching or not self.screenshot_cache:
            return {"matched": False}

        current_hash = self.compute_hash(current_image)
        for cached in self.screenshot_cache:
            if cached['hash'] == current_hash:
                return {
                    "matched": True,
                    "step_index": cached['step'],
                    "confidence": 1.0
                }
        return {"matched": False}

    def parse_response(self, response_text):
        if len(response_text) >= 200000:
            return {"thought": "response_broken", "action": {"type": "FAIL"}, "code": None}
        # --- 辅助函数：基于栈的 JSON 提取器 (极快且鲁棒) ---
        python_match = re.search(r'```python\s*(.*?)(?:```|$)', response_text, re.DOTALL)
        if python_match:
            code_content = python_match.group(1).strip()
            if code_content:
                return {
                    "thought": "Parsed from Python block (fallback).",
                    "action": {"type": "DONE"},
                    "code": code_content
                }

        def extract_json_with_stack(text):
            stack = []
            first_brace_index = -1

            # 优化：先快速定位第一个 {，避免遍历前面的长篇大论
            start_search = text.find('{')
            if start_search == -1:
                return None

            for i, char in enumerate(text[start_search:], start=start_search):
                if char == '{':
                    if not stack:
                        first_brace_index = i
                    stack.append('{')
                elif char == '}':
                    if stack:
                        stack.pop()
                        # 如果栈空了，说明找到了一个完整的顶层 JSON 对象
                        if not stack:
                            try:
                                candidate = text[first_brace_index: i + 1]
                                return json.loads(candidate, strict=False)
                            except json.JSONDecodeError:
                                # 解析失败，可能是伪 JSON，继续寻找下一个
                                continue

            # 处理截断情况：如果循环结束栈不为空，尝试修复
            if stack and first_brace_index != -1:
                # 尝试闭合所有未闭合的括号
                closing_padding = '}' * len(stack)
                try:
                    candidate = text[first_brace_index:] + closing_padding
                    return json.loads(candidate, strict=False)
                except json.JSONDecodeError:
                    pass
            return None

        # --- 1. 尝试使用 Markdown 代码块提取 (最标准情况) ---
        markdown_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if markdown_match:
            try:
                return json.loads(markdown_match.group(1), strict=False)
            except json.JSONDecodeError:
                pass

        # --- 2. 使用栈提取器 (处理嵌套和部分截断) ---
        # 这比原来的 re.search(r'\{.*\}') 快得多且不会卡死
        parsed = extract_json_with_stack(response_text)
        if parsed:
            return parsed

        # --- 3. 尝试 Python 代码块提取 ---

        # --- 4. 最后的 Fallback：物理截断修复 (修复了原来的 Off-by-one 错误) ---
        last_brace_index = response_text.rfind('}')
        if last_brace_index != -1:
            # 关键修复：使用 index + 1 来包含最后一个括号
            truncated_text = response_text[:last_brace_index + 1]
            parsed = extract_json_with_stack(truncated_text)
            if parsed:
                return parsed

        # --- 失败返回 ---
        # 如果 text 确实太长，截断放入 thought 以免日志爆炸
        thought_text = response_text if len(response_text) < 5000 else response_text[:5000] + "...(truncated)"
        return {"thought": thought_text, "action": {"type": "FAIL"}, "code": None}

    def step(self, screenshot=None, step_num=0, a11y_tree_text=None):
        if not self.task_description:
            self.load_task_description()
        user_content_clean = []

        if not self.is_initialized:
            self.conversation_history.append({
                "role": "system",
                "content": "You are an expert at analyzing dashboards and generating Python code."
            })
            user_content_clean.append({"type": "text", "text": self.task_description})
            user_content_clean.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{self.encode_image(screenshot)}"}
            })
            self.screenshot_cache.append({'step': step_num, 'hash': self.compute_hash(screenshot)})
            self.is_initialized = True

        else:
            # --- Round 2+: 后续交互逻辑 ---

            # A. 压缩历史上下文 (Context Compression)
            # 在引入新图片前，先把历史里的上一张图片变小
            if self.enable_context_compression:
                self._compress_history_images()

            # B. 截图匹配检查
            match_result = self.find_matching_screenshot(screenshot)

            if match_result["matched"]:
                # print(f"✓ 截图命中缓存：Step {match_result['step_index']}")
                user_content_clean.append({
                    "type": "text",
                    "text": f"The current screenshot matches step {match_result['step_index']}. No new screenshot provided."
                })
            else:
                # print(f"✗ 未命中缓存，发送新截图。")
                user_content_clean.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{self.encode_image(screenshot)}"}
                })
                # 加入缓存
                self.screenshot_cache.append({'step': step_num, 'hash': self.compute_hash(screenshot)})

        # 2. 构造发送给 LLM 的临时消息列表 (Inject Input Enhancement)
        # 我们复制当前历史，加上当前的 User 消息，并在此处临时注入 A11y Tree

        messages_to_send = [msg.copy() for msg in self.conversation_history]

        # 创建一个临时的 User Message 用于发送
        temp_user_message = {"role": "user", "content": user_content_clean.copy()}

        # 输入增强：注入 A11y Tree / DOM
        # 注意：这只存在于 temp_user_message 中，不会被 append 到 self.conversation_history
        if self.enable_a11y_tree and a11y_tree_text:
            temp_user_message["content"].append({
                "type": "text",
                "text": f"You have access to the DOM tree, the box within is formalized by coordination [x, y, width, height],"
                        f" make use of it to get the accurate position of elements."
                        f"\n[Accessibility Tree / DOM Structure]\n{a11y_tree_text}\n"
            })
        temp_user_message["content"].append({
            "type": "text",
            "text": f"\n[System Info]\nCurrent Step: {step_num}\n"
        })

        messages_to_send.append(temp_user_message)

        debug_print_payload(messages_to_send)
        # 3. 调用 LLM
        response_text = call_llm(messages_to_send, self.model)

        parsed_response = self.parse_response(response_text)

        # if not parsed_response.get('thought', ''):
        #     print("=" * 75)
        #     print(f"step {step_num} Response: {parsed_response}")
        #     print("=" * 75)

        # 4. 更新历史记录 (Storage)

        # A. 存入 User 消息 ("干净"版本，无 A11y Tree，当前轮次高清)
        self.conversation_history.append({"role": "user", "content": user_content_clean})

        # B. 存入 Assistant 回复 (可选压缩：移除 Thought)
        if self.enable_context_compression:
            compressed_response = {}
            # 只保留 action 和 code
            compressed_response['thought'] = "(Thinking process compressed for history)"
            if 'action' in parsed_response:
                compressed_response['action'] = parsed_response['action']
            if 'code' in parsed_response and parsed_response['code']:
                compressed_response['code'] = parsed_response['code']

            # 防止空 JSON
            if not compressed_response:
                compressed_response = {"action": parsed_response.get("action", {"type": "FAIL"})}

            self.conversation_history.append({
                "role": "assistant",
                "content": json.dumps(compressed_response, ensure_ascii=False)
            })
        else:
            # 不压缩，保留原始回复
            self.conversation_history.append({
                "role": "assistant",
                "content": response_text
            })

        return parsed_response

    def reset(self):
        self.conversation_history = []
        self.is_initialized = False
        self.screenshot_cache = []
        print("Reset complete.")


def debug_print_payload(messages):
    print("\n" + "=" * 30 + " LLM PAYLOAD DEBUG " + "=" * 30)
    debug_msgs = copy.deepcopy(messages)

    for i, msg in enumerate(debug_msgs):
        role = msg['role'].upper()
        content = msg['content']
        if isinstance(content, list):
            # 处理多模态列表 (User 消息)
            processed_content = []
            for item in content:
                if item['type'] == 'image_url':
                    # 替换图片 Base64
                    url = item['image_url']['url']
                    img_len = len(url)
                    processed_content.append(f"[IMAGE: Base64 data (len={img_len})]")

                elif item['type'] == 'text':
                    text = item['text']
                    # 检查是否是长文本并替换
                    if "Accessibility Tree" in text or "[DOM Structure]" in text:
                        processed_content.append(f"[TEXT: DOM/A11y Tree Placeholder (len={len(text)})]")
                    elif len(text) > 500:
                        # 假设超长文本通常是 Task Description
                        snippet = text[:50] + "..."
                        processed_content.append(
                            f"[TEXT: Long Text/Task Desc (len={len(text)}) - Starts with: {snippet}]")
                    else:
                        # 短文本直接保留 (如 "Current Step: 5")
                        processed_content.append(f"[TEXT: {text.strip()}]")

            msg['content'] = processed_content

        elif isinstance(content, str):
            # 处理字符串 (通常是 System 或 Assistant)
            try:
                # 尝试解析 JSON (针对 Assistant 的压缩回复)
                data = json.loads(content)
                if isinstance(data, dict):
                    # 如果包含代码，缩略代码
                    if 'code' in data and data['code'] and len(data['code']) > 50:
                        data['code'] = "[PYTHON CODE HIDDEN]"

                    # 重点：高亮显示是否存在 thought
                    if 'thought' not in data:
                        data['WARNING'] = "⚠️ MISSING 'thought' KEY!"

                    msg['content'] = data  # 替换为解析后的字典方便阅读
            except json.JSONDecodeError:
                pass  # 普通文本保持不变

    # 打印格式化后的 JSON
    print(json.dumps(debug_msgs, indent=2, ensure_ascii=False))
    print("=" * 80 + "\n")