import json
import os
import ast
from tqdm import tqdm
from semantic_eval import evaluate_code
from concurrent.futures import ThreadPoolExecutor, as_completed  # 引入并发库

# ================= 配置 =================
# CONFIG_NAME = "gemini3pro_with_dom_gpt_as_judge"
CONFIG_NAME = os.getenv("EVAL_CONFIG_NAME", "gemini3pro_with_dom")

GT_JSON_PATH = "../data/datasets/dashboard2code_v1.json"
GEN_JSON_PATH = f"../generated_outputs/{CONFIG_NAME}/{CONFIG_NAME}.json"
OUTPUT_JSON_PATH = f"semantic_eval_results/{CONFIG_NAME}.json"
MAX_WORKERS = 64

# =======================================

def is_syntax_valid(code):
    """检查代码是否有语法错误"""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False
    except Exception:
        return False


def process_single_app(app_id, gt_code, gen_code):
    """
    处理单个 App 的评估逻辑，供线程池调用。
    返回: (app_id, result_dict)
    """
    if not gen_code or gen_code.strip() == "":
        return app_id, {
            "score": 0.0,
            "category": "EMPTY CODE",
            "reasoning": "Generated code is empty. No content to evaluate."
        }
    # ------------------------------
    # 1. 处理 Syntax Error (直接判0分)
    if not is_syntax_valid(gen_code):
        return app_id, {
            "score": 0.0,
            "category": "SYNTAX ERROR",
            "reasoning": "Code failed to parse (SyntaxError). Execution impossible."
        }

    # 2. 调用 LLM 评估
    try:
        eval_result = evaluate_code(gt_code, gen_code)
        return app_id, eval_result
    except Exception as e:
        # 捕获异常，防止单个线程崩溃影响整体
        return app_id, {
            "score": 0.0,
            "category": "EVAL ERROR",
            "reasoning": f"Evaluation script failed: {str(e)}"
        }


def run_batch_eval():
    print(f"🚀 Starting Batch Semantic Evaluation with {MAX_WORKERS} threads...")

    # 1. 加载数据
    with open(GT_JSON_PATH, 'r', encoding='utf-8') as f:
        gt_data = json.load(f)
    with open(GEN_JSON_PATH, 'r', encoding='utf-8') as f:
        gen_data = json.load(f)

    results = {}

    # 获取共同的 App ID
    gt_ids = set(gt_data.keys())
    gen_ids = set(gen_data.keys())
    common_ids = sorted(list(gt_ids.intersection(gen_ids)))

    print(f"found {len(common_ids)} apps to evaluate.")

    # 2. 并行处理
    # 使用 ThreadPoolExecutor 创建线程池
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        # map 或者 submit 都可以，这里使用 submit 以便配合 tqdm 显示进度
        future_to_appid = {}
        for app_id in common_ids:
            gt_code = gt_data[app_id].get('code', '')
            gen_code = gen_data[app_id].get('code', '')

            # 提交任务到线程池
            future = executor.submit(process_single_app, app_id, gt_code, gen_code)
            future_to_appid[future] = app_id

        # 使用 as_completed 在任务完成时即时处理，并更新进度条
        for future in tqdm(as_completed(future_to_appid), total=len(common_ids), desc="Evaluating"):
            app_id = future_to_appid[future]
            try:
                # 获取线程返回值
                _, result = future.result()
                results[app_id] = result
            except Exception as e:
                print(f"\n[Critical Error] Thread execution failed for App {app_id}: {e}")
                results[app_id] = {
                    "score": 0.0,
                    "category": "THREAD ERROR",
                    "reasoning": str(e)
                }

    # 3. 保存结果
    print(f"Saving results for {len(results)} items...")
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Done! Results saved to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    run_batch_eval()