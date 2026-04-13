import subprocess
import os
import time

# 配置列表
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
    "claudesonnet45_claudesonnet45_2stage",
]


def run_batch():
    # 确保输出目录存在
    # os.makedirs("semantic_eval_results", exist_ok=True)

    start_all = time.time()

    for i, config in enumerate(configs):
        print(f"\n{'=' * 60}")
        print(f"进程 [{i + 1}/{len(configs)}]: 正在运行 {config}")
        print(f"{'=' * 60}")

        # 设置环境变量
        env = os.environ.copy()
        env["EVAL_CONFIG_NAME"] = config

        try:
            # 运行子进程
            # 使用 sys.executable 确保使用相同的 Python 解释器
            result = subprocess.run(
                # ["python", "batch_semantic_eval.py"],
                # ["python", "batch_task_executor.py"],
                ["python", "batch_image_eval.py"],
                # ["python", "run_error_analysis.py"],
                env=env,
                check=True  # 如果脚本报错会抛出异常
            )
            print(f"成功完成: {config}")

        except subprocess.CalledProcessError as e:
            print(f"❌ 运行失败: {config}. 错误码: {e.returncode}")
            # 如果某个配置失败了，你可以选择 continue 继续下一个，或者 sys.exit(1) 停止全部
            continue

    end_all = time.time()
    total_min = (end_all - start_all) / 60
    print(f"\n✨ 所有任务已完成！总耗时: {total_min:.2f} 分钟。")


if __name__ == "__main__":
    run_batch()