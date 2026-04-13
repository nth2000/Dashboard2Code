import os
import json
import time
import shutil
from datetime import datetime
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append("..")
from dashboard_server import start_server_background, stop_server
from agent_environment import DashboardEnvironment
from eval_agent import EvalAgent

# --- 配置区域 ---
OUTPUT_DIR = "task_execution_results"
SERVER_HOST = "localhost"
SERVER_PORT = 8080

# 并发配置
# ⚠️ 注意：每个 Worker 都会启动一个浏览器实例 (Chrome/Firefox)。
# 请根据你的内存大小调整此数字。建议 4-8 之间。
MAX_WORKERS = 16

# 全局锁，用于防止 print 输出在控制台混乱
print_lock = threading.Lock()


def safe_print(message):
    """线程安全的打印函数"""
    with print_lock:
        print(message)


def ensure_dir(path):
    if not os.path.exists(path):
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            pass  # 防止多线程创建目录时的竞争条件报错


def save_artifacts(output_path, screenshot, chart_data, metadata=None):
    ensure_dir(output_path)
    if screenshot:
        screenshot.save(os.path.join(output_path, "screenshot.png"))
    with open(os.path.join(output_path, "chart_data.json"), "w", encoding='utf-8') as f:
        json.dump(chart_data, f, indent=2, ensure_ascii=False)
    if metadata:
        with open(os.path.join(output_path, "metadata.json"), "w", encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)


def process_single_app(index, app_id, app_info, current_run_dir):
    """
    处理单个 App 的所有任务，这个函数将在线程池中运行。
    """
    # --- 修改点开始 ---
    # 旧逻辑: dashboard_url = f"http://{SERVER_HOST}:{SERVER_PORT}/dashboard/{index + 1}/"
    # 新逻辑: 使用真实的 app_id (JSON Key) 进行路由
    dashboard_url = f"http://{SERVER_HOST}:{SERVER_PORT}/dashboard/{app_id}/"
    # --- 修改点结束 ---

    app_output_dir = os.path.join(current_run_dir, f"App_{app_id}")

    # 简单的线程标识，用于日志
    t_name = threading.current_thread().name

    safe_print(f"\n[{t_name}] 🟢 Processing App: {app_id} (Batch Index: {index + 1})")
    safe_print(f"[{t_name}] 🔗 URL: {dashboard_url}")

    env = None
    try:
        # 初始化环境 (必须 headless=True，否则多线程弹窗会无法操作)
        env = DashboardEnvironment(dashboard_url=dashboard_url, headless=True)

        # --- Step 0: 初始状态 ---
        time.sleep(3)

        init_screenshot = env.get_screenshot(apply_marks=False)
        init_chart_data = env.scan_current_graphs()

        save_artifacts(
            os.path.join(app_output_dir, "step_0_initial"),
            init_screenshot,
            init_chart_data,
            metadata={"type": "initial_state", "url": dashboard_url, "success": True, "status": "SUCCESS"}
        )

        # --- Step 1..N: 执行任务 ---
        tasks = app_info.get("tasks", [])
        if not tasks:
            safe_print(f"[{t_name}] ⚠️ No tasks found for App {app_id}")

        # 为该线程实例化 Agent
        agent = EvalAgent()

        for i, task_desc in enumerate(tasks):
            step_id = i + 1
            # 这里的 reset 非常重要，确保任务之间状态隔离
            env.reset()
            safe_print(f"[{t_name}] 🤖 App {app_id} | Task {step_id}: \"{task_desc}\"")

            try:
                # 执行任务
                result = agent.run_task(
                    environment=env,
                    task_description=task_desc,
                    max_steps=10
                )

                # 收集结果
                step_dir = os.path.join(app_output_dir, f"step_{step_id}")

                metadata = {
                    "task_description": task_desc,
                    "success": result["success"],
                    "status": result["status"],
                    "execution_time": datetime.now().isoformat(),
                    "trajectory": result.get("trajectory", [])
                }

                save_artifacts(
                    step_dir,
                    result.get("final_screenshot"),
                    result.get("final_chart_data", {}),
                    metadata
                )

                if not result["success"]:
                    safe_print(f"[{t_name}]    ❌ App {app_id} | Task {step_id} failed: {result['status']}")
                else:
                    safe_print(f"[{t_name}]    ✅ App {app_id} | Task {step_id} completed.")

            except Exception as task_e:
                safe_print(f"[{t_name}]    ❌ Error in Task {step_id} for App {app_id}: {task_e}")

    except Exception as e:
        safe_print(f"[{t_name}] ❌ Critical Error processing App {app_id}: {e}")
        # 在多线程中打印堆栈可能会乱，但在调试时很有用
        # import traceback; traceback.print_exc()

    finally:
        if env:
            try:
                env.close()
            except:
                pass
        safe_print(f"[{t_name}] 🏁 Finished App: {app_id}")


def record_failure_for_skipped_app(app_id, app_info, current_run_dir, reason="SERVER_LOAD_FAILED"):
    """
    手动记录失败 App 的结果，不启动浏览器，直接写入 FAIL 记录。
    """
    app_output_dir = os.path.join(current_run_dir, f"App_{app_id}")
    ensure_dir(app_output_dir)

    tasks = app_info.get("tasks", [])
    safe_print(f"🚫 App {app_id} failed to load on server. Recording FAIL for {len(tasks)} tasks.")

    # 记录 Step 0 (即使失败也占位)
    save_artifacts(
        os.path.join(app_output_dir, "step_0_initial"),
        None, {},
        metadata={"type": "initial_state", "status": "FAILED", "error": reason}
    )

    for i, task_desc in enumerate(tasks):
        step_id = i + 1
        step_dir = os.path.join(app_output_dir, f"step_{step_id}")

        metadata = {
            "task_description": task_desc,
            "success": False,
            "status": reason,
            "execution_time": datetime.now().isoformat(),
            "trajectory": []
        }

        save_artifacts(step_dir, None, {}, metadata)


def run_batch_evaluation(dataset_path, output_dir_suffix=None):
    # 1. 准备输出目录
    if output_dir_suffix is None:
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_run_dir = os.path.join(OUTPUT_DIR, f"run_{run_timestamp}")
    else:
        current_run_dir = os.path.join(OUTPUT_DIR, output_dir_suffix)
    ensure_dir(current_run_dir)
    print(f"📂 Results will be saved to: {current_run_dir}")

    # 2. 检查数据集
    if not os.path.exists(dataset_path):
        print(f"❌ Dataset not found: {dataset_path}")
        return

    # 3. 启动 Dashboard Server (全局单例)
    print("🚀 Starting Dashboard Server...")
    # 修改点：接收 server, thread, 和 failed_list
    server, thread, failed_list = start_server_background(json_path=dataset_path, host=SERVER_HOST, port=SERVER_PORT)

    # 确保 failed_list 是一个集合或列表，防止为 None
    failed_ids = set(failed_list) if failed_list else set()
    if failed_ids:
        print(f"⚠️ Server reported {len(failed_ids)} failed apps: {failed_ids}")

    # 等待服务器完全启动
    time.sleep(5)

    try:
        # 4. 加载数据集
        with open(dataset_path, 'r', encoding='utf-8') as f:
            apps_data = json.load(f)  # 这是一个 dict

        total_apps = len(apps_data)
        apps_items = list(apps_data.items())

        # 5. 处理 Server 启动失败的 Apps (直接记录为失败，不进入线程池)
        valid_tasks_to_run = {}  # 存储需要跑的: {future: app_id}

        # 先处理所有失败的
        for index, (app_id, app_info) in enumerate(apps_items):
            if app_id in failed_ids:
                record_failure_for_skipped_app(app_id, app_info, current_run_dir)

        print(
            f"📋 Loaded {total_apps} apps. {len(failed_ids)} failed initially. Starting thread pool for remaining {total_apps - len(failed_ids)} apps...")

        # 6. 多线程执行 (只执行没失败的)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_app = {}

            for index, (app_id, app_info) in enumerate(apps_items):
                if app_id in failed_ids:
                    continue  # 跳过已记录失败的 App

                # 注意：index 依然传递用于日志，但不用于 URL
                future = executor.submit(
                    process_single_app,
                    index,
                    app_id,
                    app_info,
                    current_run_dir
                )
                future_to_app[future] = app_id

            # 等待完成并监控进度
            completed_count = len(failed_ids)  # 初始进度包括了那些直接失败的
            for future in as_completed(future_to_app):
                app_id = future_to_app[future]
                completed_count += 1
                try:
                    future.result()  # 获取结果，如果有异常这里会抛出
                except Exception as exc:
                    safe_print(f"❌ Exception generated for App {app_id}: {exc}")

                # 打印总体进度
                safe_print(f"📊 Progress: {completed_count}/{total_apps} apps processed.")

    finally:
        print("\n🛑 Stopping server...")
        stop_server()
        # 确保所有线程结束后退出
        print("✅ Done.")
        os._exit(0)


if __name__ == "__main__":
    # --- 修改点：数据集路径配置 ---
    # MY_DATASET_PATH = r"../data/datasets/dashboard2code_v1.json"
    # MY_DATASET_PATH = "../data/datasets/debug.json"
    EVAL_CONFIG_NAME = os.getenv("EVAL_CONFIG_NAME", "gemini3pro_with_dom")
    MY_DATASET_PATH = f"../generated_outputs/{EVAL_CONFIG_NAME}/{EVAL_CONFIG_NAME}.json"
    OUTPUT_DIR_SUFFIX = f"{EVAL_CONFIG_NAME}"
    # OUTPUT_DIR_SUFFIX = None

    # if os.path.exists(MY_DATASET_PATH):
    #     print("yes")
    #
    # print(MY_DATASET_PATH)
    # print(OUTPUT_DIR_SUFFIX)
    # exit(0)

    run_batch_evaluation(MY_DATASET_PATH, OUTPUT_DIR_SUFFIX)