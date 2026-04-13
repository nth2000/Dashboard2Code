import os
import json
import numpy as np
import pandas as pd
from tqdm import tqdm
import warnings

# 忽略警告
warnings.filterwarnings('ignore')

# ================= 依赖检查与导入 =================

try:
    from fig_comparator_v3 import PlotlyComparator
    from static_analysis import build_layout_tree, tree_edit_distance, count_nodes, calculate_component_f1
except ImportError as e:
    print(f"⚠️ 缺少依赖库或导入错误: {e}")
    print("请确保 fig_comparator_v2.py 和 static_analysis.py 在同一目录下。")


    # 为了防止代码直接崩溃，这里定义空类/函数供调试
    class PlotlyComparator:
        def evaluate(self, a, b):
            return {
                'total_score': 0,
                'details': {'style_f1': 0, 'text_f1': 0, 'data_sim': 0, 'type_f1': 0}
            }


    def build_layout_tree(c):
        return None


    def tree_edit_distance(a, b):
        return 0


    def count_nodes(n):
        return 0


    def calculate_component_f1(a, b):
        return 0, 0, 0, 0, 0

# ================= 配置区域 =================

BASE_RUN_DIR = "task_execution_results"
GT_RUN_DIR_NAME = "ground_truth"
LLM_IMAGE_EVAL_DIR = "image_eval_results"
GT_CODE_JSON_PATH = "../data/datasets/dashboard2code_v1.json"
GEN_CODE_BASE_DIR = "../generated_outputs"
SEMANTIC_EVAL_DIR = "semantic_eval_results"

# 【新增】缓存配置
CACHE_DIR = "processing_cache"
FORCE_RECALCULATE = False  # 如果设为 True，则忽略缓存强制重新计算

CONFIG_LIST = [
    "gemini3pro_with_dom", "gemini3pro_without_dom",
    "gpt51_with_dom", "gpt51_without_dom",
    "claudesonnet45_with_dom", "claudesonnet45_without_dom",
    "qwen3vl8b_with_dom", "qwen3vl8b_without_dom",
    "qwen3vl30b_with_dom", "qwen3vl30b_without_dom",
    "internvl30b_with_dom", "internvl30b_without_dom",
    "internvl8b_with_dom", "internvl8b_without_dom",
    "gemini3pro_generate_directly", "gpt51_generate_directly",
    "gemini3pro_without_thought", "gemini3pro_without_compression",
    "gpt51_without_thought", "gpt51_without_compression",
    "gemini3pro_with_dom_gpt_as_judge",
    "gpt51_with_dom_gpt_as_judge",
    "gemini3pro_gemini3pro_2stage",
    "gemini3pro_claudesonnet45_2stage",
    "claudesonnet45_claudesonnet45_2stage"
]

comparator = PlotlyComparator()


# ================= 辅助函数 =================

def get_difficulty(app_id):
    try:
        return int(str(app_id)[0])
    except:
        return 0


def load_json_safe(path):
    """安全的 JSON 加载函数，确保文件句柄关闭"""
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading {path}: {e}")
    return {}


def load_gt_code_map():
    data = load_json_safe(GT_CODE_JSON_PATH)
    if not data:
        print(f"⚠️ Warning: GT Code JSON not found or empty at {GT_CODE_JSON_PATH}")
    return data


# ================= 静态分析逻辑 =================

def analyze_static_single_app(app_id, gt_code, gen_code, sem_data):
    result = {
        "TED": 0.0,
        "Component coverage": 0.0,
        "Semantic": sem_data.get("score", 0),
        "Static_Valid": False
    }
    try:
        gt_root = build_layout_tree(gt_code)
        gen_root = build_layout_tree(gen_code)

        if gt_root and gen_root:
            ted = tree_edit_distance(gt_root, gen_root)
            max_nodes = count_nodes(gt_root) + count_nodes(gen_root)
            struct_score = 1.0 - (ted / max_nodes) if max_nodes > 0 else 0
            f1, _, _, _, _ = calculate_component_f1(gt_root, gen_root)

            result["TED"] = round(struct_score * 100, 2)
            result["Component coverage"] = round(f1 * 100, 2)
            result["Static_Valid"] = True
    except Exception:
        pass  # 保持默认值
    return result


def get_static_metrics_map(model_name, gt_code_map):
    metrics_map = {}
    gen_json_path = os.path.join(GEN_CODE_BASE_DIR, model_name, f"{model_name}.json")
    sem_json_path = os.path.join(SEMANTIC_EVAL_DIR, f"{model_name}.json")

    gen_data = load_json_safe(gen_json_path)
    sem_data_map = load_json_safe(sem_json_path)

    for app_id in gt_code_map.keys():
        gt_entry = gt_code_map.get(app_id, {})
        gen_entry = gen_data.get(app_id, {})
        sem_entry = sem_data_map.get(app_id, {})

        metrics_map[app_id] = analyze_static_single_app(
            app_id,
            gt_entry.get('code', ''),
            gen_entry.get('code', ''),
            sem_entry
        )
    return metrics_map


# ================= 动态分析逻辑 =================

def parse_run_dir(run_dir):
    results = {}
    if not os.path.exists(run_dir):
        return results

    for app_dir_name in os.listdir(run_dir):
        if not app_dir_name.startswith("App_"): continue
        app_id = app_dir_name.replace("App_", "")
        app_path = os.path.join(run_dir, app_dir_name)

        # Step 0: Initial Render Check
        is_render_ok = False
        step0_path = os.path.join(app_path, "step_0_initial", "metadata.json")
        meta0 = load_json_safe(step0_path)
        if meta0:
            status = meta0.get("status")
            if status not in ["SERVER_LOAD_FAILED", "FAILED", "ERROR"]:
                is_render_ok = True

        tasks_list = []
        task_success_count = 0

        # Step 0 check
        tasks_list.append({
            "step_id": "step_0_initial",
            "success": is_render_ok,
            "charts": []  # Step 0 通常没有 chart_data
        })
        if is_render_ok:
            pass

        try:
            steps = sorted([d for d in os.listdir(app_path) if d.startswith("step_") and not d.startswith("step_0")],
                           key=lambda x: int(x.split('_')[1]))
        except:
            steps = []

        for step_dir in steps:
            meta = load_json_safe(os.path.join(app_path, step_dir, "metadata.json"))
            charts = []
            if meta:
                chart_path = os.path.join(app_path, step_dir, "chart_data.json")
                if os.path.exists(chart_path):
                    charts = load_json_safe(chart_path)

                is_success = meta.get("success", False)
                tasks_list.append({"step_id": step_dir, "success": is_success, "charts": charts})
                if is_success:
                    task_success_count += 1

        real_tasks = [t for t in tasks_list if t['step_id'] != 'step_0_initial']

        if len(real_tasks) > 0:
            sr = (task_success_count / len(real_tasks) * 100)
        else:
            sr = 0.0

        results[app_id] = {"initial_render_success": is_render_ok, "tasks": tasks_list, "sr": sr}
    return results


def compare_charts(gt_charts, gen_charts):
    metrics = {
        "total": [], "style": [], "text": [], "data": [], "type": []
    }

    min_len = min(len(gt_charts), len(gen_charts))

    for i in range(min_len):
        eval_res = comparator.evaluate(gt_charts[i].get('figure', {}), gen_charts[i].get('figure', {}))
        metrics["total"].append(eval_res['total_score'])
        metrics["style"].append(eval_res['details']['style_f1'])
        metrics["text"].append(eval_res['details']['text_f1'])
        metrics["data"].append(eval_res['details']['data_sim'])
        metrics["type"].append(eval_res['details']['type_f1'])

    max_len = max(len(gt_charts), len(gen_charts))

    if max_len == 0:
        return {k: 1.0 for k in metrics.keys()}

    result = {}
    for key, values in metrics.items():
        result[key] = sum(values) / max_len if max_len > 0 else 0.0

    return result


# ================= 主流程 =================

def process_model(model_name, gt_run_data, gt_code_map):
    # 【更新 1】缓存检查逻辑
    cache_path = os.path.join(CACHE_DIR, f"{model_name}.json")
    if not FORCE_RECALCULATE and os.path.exists(cache_path):
        # print(f"🔄 Loading cached results for {model_name}...")
        return load_json_safe(cache_path)

    gen_run_dir = os.path.join(BASE_RUN_DIR, model_name)
    gen_run_data = parse_run_dir(gen_run_dir)
    llm_scores = load_json_safe(os.path.join(LLM_IMAGE_EVAL_DIR, f"{model_name}.json"))
    static_metrics_map = get_static_metrics_map(model_name, gt_code_map)

    app_metrics = []
    all_ids = sorted(list(set(gt_run_data.keys()) | set(gen_run_data.keys()) | set(gt_code_map.keys())))

    for app_id in all_ids:
        app_gt = gt_run_data.get(app_id, {"tasks": []})
        app_gen = gen_run_data.get(app_id, {"tasks": [], "sr": 0, "initial_render_success": False})
        app_llm = llm_scores.get(app_id, {})
        app_static = static_metrics_map.get(app_id, {"TED": 0, "Component coverage": 0, "Semantic": 0})

        is_render_success = app_gen.get("initial_render_success", False)

        row = {
            "Model": model_name,
            "AppID": app_id,
            "Difficulty": get_difficulty(app_id),
            "Code execution rate": 100.0 if is_render_success else 0.0,
            "Task execution rate": app_gen.get("sr", 0) if is_render_success else 0.0,

            # Static
            "Component coverage": app_static["Component coverage"] if is_render_success else 0.0,
            "TED": app_static["TED"] if is_render_success else 0.0,
            "Semantic": app_static["Semantic"] if is_render_success else 0.0,

            # Figure Metrics
            "Figure": 0.0,
            "Fig-Style": 0.0,
            "Fig-Text": 0.0,
            "Fig-Data": 0.0,
            "Fig-Type": 0.0,

            # LLM Metrics
            "LLM-Visual": 0.0,
            "LLM-Behavior": 0.0
        }

        if is_render_success:
            gen_step_success_map = {t['step_id']: t['success'] for t in app_gen['tasks']}

            # Figure Comparison
            fig_metrics_lists = {"total": [], "style": [], "text": [], "data": [], "type": []}
            total_steps = max(len(app_gt['tasks']), len(app_gen['tasks']))

            for i in range(total_steps):
                gt_task = app_gt['tasks'][i] if i < len(app_gt['tasks']) else None
                gen_task = app_gen['tasks'][i] if i < len(app_gen['tasks']) else None

                if gen_task and gen_task.get('success', False):
                    res = compare_charts(gt_task.get('charts', []), gen_task.get('charts', []))
                    fig_metrics_lists["total"].append(res['total'])
                    fig_metrics_lists["style"].append(res['style'])
                    fig_metrics_lists["text"].append(res['text'])
                    fig_metrics_lists["data"].append(res['data'])
                    fig_metrics_lists["type"].append(res['type'])
                else:
                    for k in fig_metrics_lists:
                        fig_metrics_lists[k].append(0.0)

            def avg(lst):
                return np.mean(lst) if lst else 0.0

            row["Figure"] = avg(fig_metrics_lists["total"]) * 100
            row["Fig-Style"] = avg(fig_metrics_lists["style"]) * 100
            row["Fig-Text"] = avg(fig_metrics_lists["text"]) * 100
            row["Fig-Data"] = avg(fig_metrics_lists["data"]) * 100
            row["Fig-Type"] = avg(fig_metrics_lists["type"]) * 100

            # LLM Metrics
            vis_vals = []
            dyn_vals = []

            for step_id, val in app_llm.get("visual_fidelity", {}).items():
                if gen_step_success_map.get(step_id, False):
                    vis_vals.append(val.get("total_score", 0))
                else:
                    vis_vals.append(0)

            for trans_key, val in app_llm.get("dynamic_behavior", {}).items():
                target = trans_key.split("_to_")[-1]
                if gen_step_success_map.get(target, False):
                    # 【更新 2】LLM Behavior 转换：0-10 -> 0-100
                    score_10 = val.get("dynamic_behavior_consistency_score", 0)
                    dyn_vals.append(score_10 * 10)
                else:
                    dyn_vals.append(0)

            row["LLM-Visual"] = avg(vis_vals)
            row["LLM-Behavior"] = avg(dyn_vals)

        app_metrics.append(row)

    # 【更新 1】写入缓存
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(app_metrics, f, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Failed to write cache for {model_name}: {e}")

    return app_metrics


def main():
    print("🚀 Starting Full Batch Analysis (Cached & Enhanced)...")

    # 确保输出目录存在
    os.makedirs("reports", exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    gt_code_map = load_gt_code_map()
    gt_run_path = os.path.join(BASE_RUN_DIR, GT_RUN_DIR_NAME)
    gt_run_data = parse_run_dir(gt_run_path)

    all_results = []

    for model in tqdm(CONFIG_LIST, desc="Processing Models"):
        try:
            model_data = process_model(model, gt_run_data, gt_code_map)
            all_results.extend(model_data)
        except Exception as e:
            print(f"❌ Error processing {model}: {e}")
            import traceback
            traceback.print_exc()

    if not all_results:
        print("No results generated.")
        return

    df = pd.DataFrame(all_results)

    # 【更新 3】计算 Total 分数
    # Formula: 0.1*Comp + 0.3*Sem + 0.2*Fig + 0.2*Vis + 0.2*Beh
    df["Total"] = (
            0.1 * df["Component coverage"] +
            0.3 * df["Semantic"] +
            0.2 * df["Figure"] +
            0.2 * df["LLM-Visual"] +
            0.2 * df["LLM-Behavior"]
    )

    # 定义列顺序，加入 Total
    cols = [
        "Model", "AppID", "Difficulty",
        "Total",  # 新增
        "Code execution rate", "Task execution rate",
        "Component coverage", "TED", "Semantic",
        "Figure", "Fig-Style", "Fig-Text", "Fig-Data", "Fig-Type",
        "LLM-Visual", "LLM-Behavior"
    ]

    # 确保列存在且顺序正确
    df = df[[c for c in cols if c in df.columns]]

    # 保存原始数据 (Raw)
    df.round(1).to_csv("reports/full_analysis_raw.csv", index=False)

    # ================= 报告生成 =================

    metrics_to_agg = [c for c in cols if c not in ["Model", "AppID", "Difficulty"]]

    def format_df(dframe):
        # 【更新 2】精度调整为小数点后 1 位
        return dframe.round(1)

    print("\n📊 Generating Overall Report...")
    df_overall = df.groupby(["Model"])[metrics_to_agg].mean().reset_index()
    df_overall = format_df(df_overall)

    # 按 Total 降序排列方便查看
    if "Total" in df_overall.columns:
        df_overall = df_overall.sort_values(by="Total", ascending=False)

    df_overall.to_csv("reports/report_overall.csv", index=False)
    print(df_overall.to_string(index=False))

    for diff in [1, 2, 3]:
        df_diff = df[df["Difficulty"] == diff]
        if not df_diff.empty:
            print(f"\n📊 Generating Difficulty Level {diff} Report...")
            report_diff = df_diff.groupby(["Model"])[metrics_to_agg].mean().reset_index()
            report_diff = format_df(report_diff)
            if "Total" in report_diff.columns:
                report_diff = report_diff.sort_values(by="Total", ascending=False)
            report_diff.to_csv(f"reports/report_difficulty_{diff}.csv", index=False)
        else:
            print(f"No data for Difficulty {diff}")

    print("\n✅ All reports saved in 'reports/' folder.")


if __name__ == "__main__":
    main()