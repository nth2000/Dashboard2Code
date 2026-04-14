import os
import json
import sys
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from agent_environment import DashboardEnvironment
from vlm_agent import VLMAgent
from dashboard_server import start_server_background, stop_server

sys.stdout.reconfigure(encoding='utf-8')

MAX_WORKERS = 16
print_lock = threading.Lock()


def safe_print(message):
    """线程安全的打印函数"""
    with print_lock:
        print(message)


def generate_code_for_dashboard_worker(dashboard_url, dashboard_id, output_dir, max_steps,
                                       enable_screenshot_matching, enable_context_compression,
                                       enable_a11y_tree, verbose=True):
    """
    Worker 函数：处理单个 Dashboard 的生成任务。
    逻辑基本复用原函数的逻辑，但将 print 替换为 safe_print，并将结果返回供主线程汇总。
    """
    t_name = threading.current_thread().name

    # 创建该dashboard的专属目录
    dashboard_output_dir = os.path.join(output_dir, 'trajectories', str(dashboard_id))
    screenshots_dir = os.path.join(dashboard_output_dir, 'screenshots')
    # 线程安全创建目录
    os.makedirs(screenshots_dir, exist_ok=True)

    # 初始化环境和Agent
    env = None
    result = {
        'dashboard_id': dashboard_id,
        'dashboard_url': dashboard_url,
        'generated_code': None,
        'success': False,
        'steps_taken': 0,
        'trajectory': [],
        'start_time': datetime.now().isoformat(),
        'end_time': None,
        'screenshot_stats': {
            'total_steps': 0,
            'screenshots_saved': 0,
            'screenshots_matched': 0,
            'match_details': []
        }
    }

    try:
        env = DashboardEnvironment(dashboard_url, headless=True)
        agent = VLMAgent(
            enable_screenshot_matching=enable_screenshot_matching,
            enable_context_compression=enable_context_compression,
            enable_a11y_tree=enable_a11y_tree
        )

        if verbose:
            safe_print(f"[{t_name}] 🟢 Start generating for Dashboard {dashboard_id}")

        for step in range(max_steps):
            step_num = step + 1
            result['screenshot_stats']['total_steps'] = step_num

            # 获取观察
            screenshot = env.get_screenshot()

            current_a11y_tree = None
            if enable_a11y_tree:
                try:
                    current_a11y_tree = env.get_a11y_tree()
                except Exception as e:
                    pass  # 忽略错误

            # Agent推理
            response = agent.step(screenshot, step_num, a11y_tree_text=current_a11y_tree)

            # 匹配逻辑
            match_info = response.get('match_info', {"matched": False})
            is_matched = match_info.get('matched', False)

            if is_matched:
                result['screenshot_stats']['screenshots_matched'] += 1
                result['screenshot_stats']['match_details'].append({
                    'current_step': step_num,
                    'matched_step': match_info.get('step_index'),
                    'hash_diff': match_info.get('hash_diff')
                })

            # 截图保存逻辑
            screenshot_filename = None
            if not is_matched or step_num == 1:
                screenshot_filename = f"step_{step_num:03d}_before.png"
                screenshot_path = os.path.join(screenshots_dir, screenshot_filename)
                screenshot.save(screenshot_path)
                result['screenshot_stats']['screenshots_saved'] += 1
            else:
                matched_step = match_info.get('step_index', 'unknown')
                screenshot_filename = f"[matched_with_step_{matched_step}]"

            # 记录步骤
            step_record = {
                'step': step_num,
                'timestamp': datetime.now().isoformat(),
                'screenshot_before': screenshot_filename,
                'screenshot_matched': is_matched,
                'match_info': match_info,
                'thinking': response.get('thought', ''),
                'action': response.get('action', {}),
                'code_snippet': response.get('code'),
                'action_result': None,
                'screenshot_after': None
            }

            # 打印精简日志
            if verbose:
                thought_snippet = response.get('thought', '')[:100] + "..." if len(
                    response.get('thought', '')) > 100 else response.get('thought', '')
                safe_print(
                    f"[{t_name}]   App {dashboard_id} | Step {step_num}: {response['action']['type']} | Think: {thought_snippet}")

            # 检查完成
            if response['action']['type'] == 'DONE':
                final_code = response.get('code')
                if not final_code:
                    final_code = response['action'].get('code')
                result['generated_code'] = final_code
                result['success'] = True
                result['steps_taken'] = step_num
                step_record['action_result'] = {'success': True, 'message': 'Task completed'}
                result['trajectory'].append(step_record)
                break

            elif response['action']['type'] == 'FAIL':
                result['steps_taken'] = step_num
                step_record['action_result'] = {'success': False, 'message': 'Task failed'}
                result['trajectory'].append(step_record)
                break

            # 执行动作
            action_result = env.execute_action(response['action'])
            step_record['action_result'] = action_result

            # 保存 After 截图
            time.sleep(0.5)
            screenshot_after = env.get_screenshot(apply_marks=False)
            screenshot_after_filename = f"step_{step_num:03d}_after.png"
            screenshot_after_path = os.path.join(screenshots_dir, screenshot_after_filename)
            screenshot_after.save(screenshot_after_path)
            step_record['screenshot_after'] = screenshot_after_filename
            result['screenshot_stats']['screenshots_saved'] += 1

            result['trajectory'].append(step_record)

        # 步数耗尽处理
        if result['steps_taken'] == 0:
            result['steps_taken'] = max_steps

    except Exception as e:
        safe_print(f"[{t_name}] ❌ Error in Dashboard {dashboard_id}: {e}")
        result['error'] = str(e)
    finally:
        result['end_time'] = datetime.now().isoformat()

        # 计算统计数据
        if result['screenshot_stats']['total_steps'] > 0:
            result['screenshot_stats']['save_ratio'] = result['screenshot_stats']['screenshots_saved'] / (
                        result['screenshot_stats']['total_steps'] * 2)
            result['screenshot_stats']['match_ratio'] = result['screenshot_stats']['screenshots_matched'] / \
                                                        result['screenshot_stats']['total_steps']

        # 保存 Trajectory (IO 操作放在 Worker 中分摊压力)
        trajectory_file = os.path.join(dashboard_output_dir, 'trajectory.json')
        with open(trajectory_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        if env:
            try:
                env.close()
            except:
                pass

        safe_print(f"[{t_name}] 🏁 Finished Dashboard {dashboard_id}. Success: {result['success']}")

    return result


def run_generation(dashboard_list_path, output_dir, output_file, server_host='localhost',
                   server_port=5000,
                   enable_screenshot_matching=True,
                   enable_context_compression=False,
                   enable_a11y_tree=False):
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(output_dir, f"run_{run_timestamp}")
    print("🚀 Starting dashboard server...")
    start_server_background(json_path=dashboard_list_path, host=server_host, port=server_port)
    server_ip = f"http://{server_host}:{server_port}"
    print(f"🔗 Server running at {server_ip}")

    # 等待服务器就绪
    time.sleep(3)

    # 2. 准备数据
    with open(dashboard_list_path, 'r', encoding='utf-8') as f:
        dashboard_list = json.load(f)

    # 创建目录
    os.makedirs(output_dir, exist_ok=True)
    code_output_dir = os.path.join(output_dir, 'generated_codes')
    os.makedirs(code_output_dir, exist_ok=True)

    # 汇总数据容器
    results_summary = []
    formatted_output = {}

    # 统计计数器
    stats = {
        'success_count': 0,
        'total_screenshots_saved': 0,
        'total_screenshots_matched': 0,
        'total_steps': 0
    }

    start_time = datetime.now().isoformat()
    total_dashboards = len(dashboard_list)

    print(f"📋 Loaded {total_dashboards} dashboards. Starting thread pool with {MAX_WORKERS} workers...")
    print("=" * 80)

    # 3. 线程池执行
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_id = {}

        # --- 修改点 1: 适配字典格式输入 ---
        # 遍历字典的 items()，直接使用 key 作为 dashboard_id (例如 "310")
        # 这样能保证 ID 与原始数据一一对应
        for dash_id, original_data in dashboard_list.items():
            # 确保 dash_id 是字符串或适合路径的格式
            dashboard_url = f"{server_ip}/dashboard/{dash_id}"

            future = executor.submit(
                generate_code_for_dashboard_worker,
                dashboard_url=dashboard_url,
                dashboard_id=dash_id,  # 传入真实的 ID (如 "310")
                output_dir=output_dir,
                max_steps=25,
                enable_screenshot_matching=enable_screenshot_matching,
                enable_context_compression=enable_context_compression,
                enable_a11y_tree=enable_a11y_tree,
                verbose=True
            )
            future_to_id[future] = dash_id

        # 处理结果 (As Completed)
        completed_count = 0
        for future in as_completed(future_to_id):
            completed_count += 1
            dash_id = future_to_id[future]

            try:
                result = future.result()

                # --- 修改点 2: 保留原始字段并更新 code ---

                # 1. 获取原始数据 (使用 copy 防止引用修改问题)
                original_entry = dashboard_list.get(str(dash_id), {}).copy()

                # 2. 更新/覆盖 code 字段
                generated_code = result.get('generated_code') if result.get('generated_code') else ""
                original_entry['code'] = generated_code

                # 3. 将包含所有原始域 + 新生成的 code 的字典写入输出
                formatted_output[str(dash_id)] = original_entry

                # 2. 保存代码文件 (逻辑不变，仅作备份用)
                if result['generated_code']:
                    code_file = os.path.join(code_output_dir, f"{dash_id}.py")
                    with open(code_file, 'w', encoding='utf-8') as f:
                        f.write(result['generated_code'])
                    stats['success_count'] += 1

                # 3. 累加统计
                stats['total_steps'] += result['screenshot_stats']['total_steps']
                stats['total_screenshots_saved'] += result['screenshot_stats']['screenshots_saved']
                stats['total_screenshots_matched'] += result['screenshot_stats']['screenshots_matched']

                # 4. 添加到摘要列表
                summary_entry = {
                    'dashboard_id': result['dashboard_id'],
                    'success': result['success'],
                    'steps_taken': result['steps_taken'],
                    'error': result.get('error'),
                    'screenshot_stats': result['screenshot_stats']
                }
                results_summary.append(summary_entry)

                safe_print(
                    f"📊 Progress: {completed_count}/{total_dashboards} completed. (Success so far: {stats['success_count']})")

            except Exception as exc:
                safe_print(f"❌ Exception generated for Dashboard {dash_id}: {exc}")
                # 即使发生异常，也尝试把原始数据写回去，防止该条目丢失
                if str(dash_id) not in formatted_output:
                    original_entry = dashboard_list.get(str(dash_id), {}).copy()
                    original_entry['code'] = ""  # 失败时为空或保留原值，看你需求，这里设为空字符串
                    formatted_output[str(dash_id)] = original_entry

    # 4. 最终统计与保存
    print("\n" + "=" * 80)
    print("🛑 Stopping server...")
    stop_server()

    end_time = datetime.now().isoformat()

    # 计算最终比率
    success_rate = stats['success_count'] / total_dashboards if total_dashboards > 0 else 0
    avg_steps = stats['total_steps'] / total_dashboards if total_dashboards > 0 else 0

    theoretical_total_screenshots = stats['total_steps'] * 2
    storage_saved_ratio = 1 - (stats[
                                   'total_screenshots_saved'] / theoretical_total_screenshots) if theoretical_total_screenshots > 0 else 0

    print(f"CODE GENERATION COMPLETED")
    print(f"Overall Success Rate: {success_rate:.2%} ({stats['success_count']}/{total_dashboards})")
    print(f"Storage Saved: {storage_saved_ratio:.1%}")
    print("=" * 80)

    # 构建 Metadata
    metadata = {
        'run_info': {
            'start_time': start_time,
            'end_time': end_time,
            'workers': MAX_WORKERS,
            'dataset': dashboard_list_path
        },
        'statistics': {
            'success_rate': success_rate,
            'success_count': stats['success_count'],
            'total_count': total_dashboards,
            'avg_steps': avg_steps,
            'screenshot_stats': {
                'total_steps': stats['total_steps'],
                'screenshots_saved': stats['total_screenshots_saved'],
                'screenshots_matched': stats['total_screenshots_matched'],
                'storage_saved_ratio': storage_saved_ratio
            }
        },
        'results': results_summary
    }

    # 保存文件
    metadata_path = os.path.join(output_dir, 'generation_metadata.json')
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    herokuapp_output_path = os.path.join(output_dir, output_file)
    with open(herokuapp_output_path, 'w', encoding='utf-8') as f:
        json.dump(formatted_output, f, indent=2, ensure_ascii=False)

    print(f"✅ Output saved to: {herokuapp_output_path}")
    print(f"✅ Metadata saved to: {metadata_path}")


if __name__ == '__main__':
    dashboard_list_path = 'data/datasets/dashboard2code_v1.json'
    output_dir = 'generated_outputs'
    output_file = 'gemini3pro_without_dom.json'

    enable_matching = True
    enable_compression = True
    enable_a11y = True

    run_generation(dashboard_list_path, output_dir, output_file,
                   enable_screenshot_matching=enable_matching,
                   enable_context_compression=enable_compression,
                   enable_a11y_tree=enable_a11y)