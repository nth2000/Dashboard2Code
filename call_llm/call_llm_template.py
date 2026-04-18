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
    """
    Processes the input messages and returns the model's string response.
    """
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
                raise ValueError("API returned an empty choices list")

            message_obj = completion.choices[0].message
            content = message_obj.content

            if not content:
                raise ValueError("API returned empty content (None or Empty String)")

            if hasattr(completion, 'usage') and completion.usage:
                print(f"✔ Success | Input: {completion.usage.prompt_tokens} | Output: {completion.usage.completion_tokens}")

            return content

        except Exception as e:
            print(f"⚠ Failed (Attempt {attempt}/{max_retries}): {e}")

            if attempt == max_retries:
                print("❌ Maximum retries reached. Giving up.")
                raise e

            time.sleep(delay)
            delay *= 1.5
            print(f"⏳ Waiting {delay:.1f} seconds before retrying...")

    return None

if __name__ == "__main__":
    print("-" * 50)

    # with open("temp.txt", "r", encoding="utf-8") as f:
    #     content = f.read()

    content = "hello, introduce yourself"

    test_messages = [
        {
            "role": "user",
            "content": content
        }
    ]
    try:
        response = call_llm(test_messages, "gpt-5", max_retries=5, initial_delay=2)

        # Check response
        if response:
            print("✓ API call successful!")
            print("\nResponse content:")
            print(response)
            print("-" * 50)
        else:
            print("✗ API call failed: No valid response received")

    except Exception as e:
        print(f"✗ API call ultimately failed: {type(e).__name__}")
        print(f"Error details: {str(e)}")