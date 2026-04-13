import copy

from openai import OpenAI
import re
import time
from typing import Optional, Tuple
import json

api_key = ""
api_base = ""
client = OpenAI(api_key=api_key, base_url=api_base)


def call_llm(messages, model="gpt-5", max_retries=10, initial_delay=1):
    delay = initial_delay

    for attempt in range(1, max_retries + 1):
        try:
            completion = client.chat.completions.create(
                # model=model,
                model='gemini-3-pro-preview',
                messages=messages,
                stream=False,
                reasoning_effort="low",
                max_completion_tokens=32768
            )
            if not completion.choices:
                raise ValueError("API返回了空的 choices 列表")

            message_obj = completion.choices[0].message
            content = message_obj.content

            if not content:
                raise ValueError("API返回的 content 为空 (None or Empty String)")

            if hasattr(completion, 'usage') and completion.usage:
                print(f"✔ 成功 | Input: {completion.usage.prompt_tokens} | Output: {completion.usage.completion_tokens}")

            return content

        except Exception as e:
            print(f"⚠ 失败 (第 {attempt}/{max_retries} 次): {e}")

            if attempt == max_retries:
                print("❌ 已达到最大重试次数，彻底放弃。")
                raise e

            time.sleep(delay)
            delay *= 1.5
            print(f"⏳ 等待 {delay:.1f} 秒后重试...")

    return None

if __name__ == "__main__":
    print("-" * 50)

    with open("temp.txt", "r", encoding="utf-8") as f:
        content = f.read()

    test_messages = [
        {
            "role": "user",
            "content": content
        }
    ]
    try:
        response = call_llm(test_messages, "gpt-5", max_retries=5, initial_delay=2)

        # 检查响应
        if response:
            print("✓ API调用成功！")
            print("\n响应内容:")
            print(response)
            print("-" * 50)
        else:
            print("✗ API调用失败：未获取到有效响应")

    except Exception as e:
        print(f"✗ API调用最终失败：{type(e).__name__}")
        print(f"错误详情：{str(e)}")
