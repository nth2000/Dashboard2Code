import os
import json
import concurrent.futures
from tqdm import tqdm
import sys

# 引入你的评估类
from image_eval import DashboardEvaluator

# ================= 配置区域 =================
CONFIG_NAME = os.getenv("EVAL_CONFIG_NAME", "gemini3pro_with_dom")
# CONFIG_NAME = "gemini3pro_with_dom_gpt_as_judge"

GT_RUN_DIR = "task_execution_results/ground_truth"
GEN_RUN_DIR = f"task_execution_results/{CONFIG_NAME}"
OUTPUT_FILE = f"image_eval_results/{CONFIG_NAME}.json"
MAX_WORKERS = 64
# ===========================================

evaluator = DashboardEvaluator()


def get_screenshot_path(run_dir, app_id, step_id):
    """获取截图路径，如果不存在返回 None"""
    path = os.path.join(run_dir, f"App_{app_id}", step_id, "screenshot.png")
    return path if os.path.exists(path) else None


def get_step_metadata(run_dir, app_id, step_id):
    """读取 metadata.json 获取完整元数据"""
    meta_path = os.path.join(run_dir, f"App_{app_id}", step_id, "metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def process_single_app(app_id):
    app_result = {
        "visual_fidelity": {},
        "dynamic_behavior": {}
    }

    app_base_gen = os.path.join(GEN_RUN_DIR, f"App_{app_id}")
    if not os.path.exists(app_base_gen):
        return app_id, {"error": "App not found in GEN directory"}

    # 收集所有步骤
    all_steps = ["step_0_initial"]
    additional_steps = sorted(
        [d for d in os.listdir(app_base_gen) if d.startswith("step_") and not d.startswith("step_0")],
        key=lambda x: int(x.split('_')[1])
    )
    all_steps.extend(additional_steps)

    # 提前读取所有步骤的状态
    step_success_map = {}
    for step_id in all_steps:
        meta = get_step_metadata(GEN_RUN_DIR, app_id, step_id)
        if step_id == "step_0_initial":
            status = meta.get("status")
            fail_keywords = ["SERVER_LOAD_FAILED", "FAILED", "ERROR"]
            step_success_map[step_id] = (status not in fail_keywords) if status else True
        else:
            step_success_map[step_id] = meta.get("success", False)

    # --- 1. 对每个步骤进行视觉还原度评估 (保持不变) ---
    for step_id in all_steps:
        if not step_success_map.get(step_id, False):
            app_result["visual_fidelity"][step_id] = {"total_score": 0, "reason": "Task execution failed"}
            continue

        gt_img = get_screenshot_path(GT_RUN_DIR, app_id, step_id)
        gen_img = get_screenshot_path(GEN_RUN_DIR, app_id, step_id)

        if gt_img and gen_img:
            try:
                visual_score = evaluator.evaluate_visual_fidelity(gt_img, gen_img)
                app_result["visual_fidelity"][step_id] = visual_score
            except Exception as e:
                app_result["visual_fidelity"][step_id] = {"error": str(e)}
        else:
            app_result["visual_fidelity"][step_id] = {"error": "Missing screenshots"}

    # --- 2. 对每个转换进行动态行为一致性评估 (已修改) ---

    # 核心修改：固定初始状态为 step_0
    initial_step = all_steps[0]  # 通常是 "step_0_initial"

    # 遍历除去 step_0 以外的所有步骤作为 end_step
    for end_step in all_steps[1:]:

        # start_step 永远固定为 initial_step
        start_step = initial_step

        transition_key = f"{start_step}_to_{end_step}"

        # 逻辑：如果目标步骤（end_step）执行失败，行为一致性直接判定为 0
        if not step_success_map.get(end_step, False):
            app_result["dynamic_behavior"][transition_key] = {
                "dynamic_behavior_consistency_score": 0,
                "reason": f"Target step {end_step} failed"
            }
            continue

        # 图片路径获取：
        # Start 图片永远取自 step_0
        gt_start = get_screenshot_path(GT_RUN_DIR, app_id, start_step)
        gen_start = get_screenshot_path(GEN_RUN_DIR, app_id, start_step)

        # End 图片取自当前任务步骤
        gt_end = get_screenshot_path(GT_RUN_DIR, app_id, end_step)
        gen_end = get_screenshot_path(GEN_RUN_DIR, app_id, end_step)

        # 任务描述从 End Step 的元数据中获取（因为是该步骤对应的任务）
        meta_end = get_step_metadata(GT_RUN_DIR, app_id, end_step)
        task_desc = meta_end.get("task_description", "Unknown Task")

        if all([gt_start, gt_end, gen_start, gen_end]):
            try:
                dynamic_score = evaluator.evaluate_dynamic_behavior(
                    gt_start, gt_end, gen_start, gen_end, task_desc
                )
                app_result["dynamic_behavior"][transition_key] = dynamic_score
            except Exception as e:
                app_result["dynamic_behavior"][transition_key] = {"error": str(e)}
        else:
            app_result["dynamic_behavior"][transition_key] = {"error": "Missing screenshots"}

    return app_id, app_result

def run_batch_scoring():
    # 获取所有 App ID
    if not os.path.exists(GEN_RUN_DIR):
        print(f"Directory not found: {GEN_RUN_DIR}")
        return

    app_ids = [d.replace("App_", "") for d in os.listdir(GEN_RUN_DIR) if d.startswith("App_")]
    results_cache = {}

    # 如果文件已存在，可以选择加载已有结果，避免重复跑（可选逻辑）
    if os.path.exists(OUTPUT_FILE):
        print(f"Loading existing results from {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            results_cache = json.load(f)

    # 过滤掉已经跑过的 App (如果你想增量跑的话)
    apps_to_run = [aid for aid in app_ids if aid not in results_cache]

    print(f"🚀 Starting LLM Scoring for {len(apps_to_run)} apps (Threads: {MAX_WORKERS})...")
    print(f"   Evaluation scheme: 2n+1 (visual fidelity at each step + dynamic behavior between steps)")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_app = {executor.submit(process_single_app, aid): aid for aid in apps_to_run}

        # 使用 tqdm 显示进度条
        for future in tqdm(concurrent.futures.as_completed(future_to_app), total=len(apps_to_run)):
            app_id, data = future.result()
            results_cache[app_id] = data

            # (可选) 每跑完一个就实时保存一次，防止程序中断数据丢失
            if len(results_cache) % 5 == 0:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(results_cache, f, indent=4, ensure_ascii=False)

    # 最终保存
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results_cache, f, indent=4, ensure_ascii=False)

    print(f"✅ All Done! Results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    run_batch_scoring()