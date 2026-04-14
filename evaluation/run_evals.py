import subprocess
import os
import time

configs = [
    # "gemini3pro_without_dom",
    # "gemini3pro_with_dom",
    # "gpt51_with_dom", "gpt51_without_dom",
    # "claudesonnet45_with_dom", "claudesonnet45_without_dom",
    # "qwen3vl8b_with_dom", "qwen3vl8b_without_dom",
    # "qwen3vl30b_with_dom", "qwen3vl30b_without_dom",
    # "internvl30b_with_dom", "internvl30b_without_dom",
    # "internvl8b_with_dom", "internvl8b_without_dom",
    # "gemini3pro_generate_directly", "gpt51_generate_directly",
    # "gemini3pro_without_thought", "gemini3pro_without_compression",
    # "gpt51_without_thought", "gpt51_without_compression",
    # "gemini3pro_with_dom_gpt_as_judge",
    # "gpt51_with_dom_gpt_as_judge",
    # "gemini3pro_gemini3pro_2stage",
    # "gemini3pro_claudesonnet45_2stage",
    # "claudesonnet45_claudesonnet45_2stage",
]


def run_batch():
    start_all = time.time()
    for i, config in enumerate(configs):
        print(f"\n{'=' * 60}")
        print(f"Process [{i + 1}/{len(configs)}]: Running {config}")
        print(f"{'=' * 60}")

        # Set environment variable for the subprocess
        env = os.environ.copy()
        env["EVAL_CONFIG_NAME"] = config

        try:
            # Run the evaluation script
            result = subprocess.run(
                # ["python", "batch_semantic_eval.py"],
                # ["python", "batch_task_executor.py"],
                ["python", "batch_image_eval.py"],
                # ["python", "run_error_analysis.py"],
                env=env,
                check=True
            )
            print(f"Successfully completed: {config}")

        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to run: {config}. Error code: {e.returncode}")
            continue

    end_all = time.time()
    total_min = (end_all - start_all) / 60
    print(f"\n✨ All tasks completed! Total time: {total_min:.2f} minutes.")


if __name__ == "__main__":
    run_batch()