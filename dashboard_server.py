import json
import logging
import sys
import threading
import ast
import astor
import traceback
from flask import Flask
from dash import Dash, html, dcc
from werkzeug.middleware.dispatcher import DispatcherMiddleware

sys.stdout.reconfigure(encoding='utf-8')

_server_instance = None
_server_thread = None


def load_dash_apps(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


class DashCallTransformer(ast.NodeTransformer):
    def __init__(self, url_base_pathname):
        self.url_base_pathname = url_base_pathname
        self.found_dash_call = False

    def visit_Call(self, node):
        is_dash_call = False

        if isinstance(node.func, ast.Name) and node.func.id == 'Dash':
            is_dash_call = True
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr == 'Dash':
                is_dash_call = True

        if is_dash_call:
            self.found_dash_call = True
            node.keywords = [
                kw for kw in node.keywords
                if kw.arg not in ['server', 'url_base_pathname', 'requests_pathname_prefix', 'routes_pathname_prefix']
            ]
            node.keywords.extend([
                ast.keyword(
                    arg='requests_pathname_prefix',
                    value=ast.Constant(value=self.url_base_pathname)
                ),
                ast.keyword(
                    arg='routes_pathname_prefix',
                    value=ast.Constant(value='/')
                )
            ])
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name) and decorator.func.id == 'callback':
                    print(f"  -> 自动修复: 将函数 {node.name} 的 @callback 替换为 @app.callback")
                    decorator.func = ast.Attribute(
                        value=ast.Name(id='app', ctx=ast.Load()),
                        attr='callback',
                        ctx=ast.Load()
                    )
        return self.generic_visit(node)


def inject_debug_layout(app, code_string):
    original_layout = app.layout

    def debug_layout_wrapper():
        if callable(original_layout):
            content = original_layout()
        else:
            content = original_layout

        return html.Div([
            html.Div(
                content,
                style={'flex': '1', 'overflow': 'auto', 'height': '100vh'}
            ),
            html.Div([
                html.Div([
                    html.H3("Source Code", style={'margin': '0 0 10px 0', 'fontSize': '16px'}),
                    dcc.Clipboard(
                        content=code_string,
                        title="Copy Code",
                        style={'display': 'inline-block', 'fontSize': '20px', 'verticalAlign': 'top',
                               'cursor': 'pointer'}
                    ),
                ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center',
                          'marginBottom': '10px'}),

                dcc.Textarea(
                    value=code_string,
                    readOnly=True,
                    style={'width': '100%', 'height': 'calc(100vh - 60px)', 'fontFamily': 'monospace',
                           'fontSize': '12px', 'border': '1px solid #ddd', 'backgroundColor': '#f5f5f5',
                           'resize': 'none'}
                )
            ], style={'width': '400px', 'borderLeft': '1px solid #ccc', 'padding': '15px', 'backgroundColor': '#fff',
                      'boxShadow': '-2px 0 5px rgba(0,0,0,0.05)', 'height': '100vh', 'boxSizing': 'border-box'})
        ], style={'display': 'flex', 'height': '100vh', 'overflow': 'hidden', 'margin': '0'})

    app.layout = debug_layout_wrapper


def create_dash_app_from_code(code_string, url_base_pathname, app_id, debug=False):
    try:
        tree = ast.parse(code_string)

        # 转换 AST，注入路径配置，但移除 server 注入
        transformer = DashCallTransformer(url_base_pathname)
        modified_tree = transformer.visit(tree)

        if not transformer.found_dash_call:
            print(f"[{app_id}] 警告: 未在代码中找到 Dash() 调用")

        ast.fix_missing_locations(modified_tree)
        modified_code = astor.to_source(modified_tree)

        lines = modified_code.split('\n')
        final_lines = []
        in_main_block = False

        for line in lines:
            if 'if __name__' in line and '__main__' in line:
                in_main_block = True
                final_lines.append('# ' + line)
                continue
            if in_main_block:
                if line.strip() and not line.startswith((' ', '\t', '#')):
                    in_main_block = False
                    final_lines.append(line)
                else:
                    final_lines.append('# ' + line)
            else:
                final_lines.append(line)

        final_code = '\n'.join(final_lines)

        # [修改] 命名空间中不再包含 _injected_server
        namespace = {
            '__name__': '__main__',
            '__builtins__': __builtins__,
        }

        # 执行代码。Dash() 会在内部创建自己的 Flask server (因为没有注入 server 参数)
        exec(final_code, namespace)

        app = None
        for name, obj in namespace.items():
            if isinstance(obj, Dash) and not name.startswith('_'):
                app = obj
                break

        if app is None:
            raise ValueError(f"应用 {app_id} 未能成功创建 Dash 实例")

        # [关键] 在这里检查 Layout。如果此时 layout 为 None，抛出异常。
        # 因为 app 是独立的，这里的异常不会影响主 server。
        if app.layout is None:
            raise ValueError(f"应用 {app_id} 的 layout 未被设置 (layout is None)")

        if debug:
            inject_debug_layout(app, code_string)

        return app

    except SyntaxError as e:
        print(f"[{app_id}] 代码语法错误: {e}")
        raise
    except Exception as e:
        print(f"[{app_id}] 执行代码时出错: {e}")
        # traceback.print_exc() # 可选：打印详细堆栈
        raise


def create_server(json_path, debug=False):
    """
    [修改] 使用 DispatcherMiddleware 合并应用
    [更新] URL路径改为使用真实的 app_id (例如 /dashboard/310/)
    """
    # 创建主 Flask 服务器 (作为入口)
    server = Flask(__name__)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    try:
        apps_data = load_dash_apps(json_path)
    except Exception as e:
        print(f"无法读取配置文件 {json_path}: {e}")
        return server, []

    mounts = {}
    failed_apps = []

    # 遍历所有应用
    # 虽然这里保留了 i (索引)，但在生成 URL 时我们只使用 app_id
    for i, (app_id, app_info) in enumerate(apps_data.items()):
        code = app_info.get('code', '')  # 兼容某些可能缺少code字段的情况

        # --- [修改点 1] ---
        # 使用 app_id 作为 URL 路径的一部分，而不是索引 i+1
        # 确保 app_id 是字符串
        safe_app_id = str(app_id)
        url_base = f'/dashboard/{safe_app_id}'

        # 传递给 Dash 的 url_base 需要带结尾斜杠以确保静态资源路径正确
        dash_url_base = url_base + '/'

        try:
            # 创建独立的 App
            dash_app = create_dash_app_from_code(code, dash_url_base, safe_app_id, debug=debug)

            # 只有成功创建且 Layout 正常的 App 才会运行到这里
            # dash_app.server 是 Dash 内部自动创建的 Flask 实例
            mounts[url_base] = dash_app.server

            print(f"✓ 已加载应用 {safe_app_id} -> {dash_url_base}")
        except Exception as e:
            print(f"✗ 加载应用 {safe_app_id} 失败: {e}")
            failed_apps.append(safe_app_id)

    # 使用 Middleware 将所有成功的 Dash Server 挂载到主 Server
    if mounts:
        server.wsgi_app = DispatcherMiddleware(server.wsgi_app, mounts)

    # 首页路由
    @server.route('/')
    def index():
        success_count = len(mounts)
        failed_count = len(failed_apps)

        links = []
        # --- [修改点 2] ---
        # 首页链接生成逻辑也改为使用 app_id
        for app_id, app_info in apps_data.items():
            safe_app_id = str(app_id)
            if safe_app_id not in failed_apps:
                links.append(
                    f'<li><a href="/dashboard/{safe_app_id}/">Dashboard {safe_app_id}</a></li>'
                )

        links_html = ''.join(links)

        error_section = ""
        if failed_apps:
            error_items = ''.join(
                [f'<li style="color: red; background-color: #fff0f0;">❌ {aid} 加载失败</li>' for aid in failed_apps])
            error_section = f'''
            <div style="margin-top: 30px; border-top: 2px solid #ffcccc; padding-top: 20px;">
                <h3 style="color: #cc0000;">加载失败的应用 ({failed_count}):</h3>
                <ul>{error_items}</ul>
            </div>
            '''

        return f'''
        <html>
            <head>
                <title>Dashboard Server</title>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; padding: 40px; background-color: #f5f5f5; }}
                    .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    h1 {{ color: #333; border-bottom: 3px solid #0066cc; padding-bottom: 10px; }}
                    ul {{ list-style-type: none; padding: 0; }}
                    li {{ margin: 15px 0; padding: 15px; background-color: #f9f9f9; border-radius: 4px; }}
                    a {{ color: #0066cc; text-decoration: none; font-size: 18px; font-weight: 500; }}
                    a:hover {{ text-decoration: underline; }}
                    .status-bar {{ margin-bottom: 20px; padding: 10px; background-color: #e8f5e9; color: #2e7d32; border-radius: 4px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>📊 Dashboard Server</h1>
                    <div class="status-bar">
                        成功加载: {success_count} | 失败: {failed_count} | Debug模式: {'开启' if debug else '关闭'}
                    </div>
                    <p>可用的 Dashboards:</p>
                    <ul>{links_html}</ul>
                    {error_section}
                </div>
            </body>
        </html>
        '''

    return server, failed_apps

def start_server_background(json_path='data/datasets/debug.json', host='localhost', port=5000, debug=False):
    global _server_instance, _server_thread

    print(f"从 {json_path} 加载 Dashboard 应用 (Debug={debug})...")
    print("-" * 40)

    server, failed_apps = create_server(json_path, debug=debug)
    _server_instance = server

    print("-" * 40)
    print(f"在后台启动服务器...")
    if failed_apps:
        print(f"⚠️  警告: 以下应用加载失败: {failed_apps}")
    else:
        print("所有应用加载成功。")
    print(f"访问 http://{host}:{port} 查看所有 dashboards")
    print("-" * 40)

    def run_server():
        # 注意：使用 DispatcherMiddleware 后，use_reloader=False 更加重要，否则可能出现线程问题
        server.run(host=host, port=port, debug=True, use_reloader=False)

    _server_thread = threading.Thread(target=run_server, daemon=True)
    _server_thread.start()

    return server, _server_thread, failed_apps


def stop_server():
    global _server_instance, _server_thread
    print("注意: Flask 开发服务器需要终止进程才能完全停止")
    _server_instance = None
    _server_thread = None


if __name__ == '__main__':
    # 示例用法
    # 请将此处路径替换为你实际的 JSON 文件路径
    # json_file_path = r"data/datasets/generated_candidate_random_with_tasks.json"
    # json_file_path = r"data/datasets/herokuapp_final.json"
    # json_file_path = r"data/datasets/generated_accepted.json"
    # json_file_path = r"data/datasets/debug.json"
    # json_file_path = r"generated_outputs/gemini3pro_with_dom/dashboard2code_v1_gemini3pro_with_dom.json"
    # json_file_path = r"generated_outputs/internvl30b_with_dom/internvl30b_with_dom.json"
    json_file_path = r"data/datasets/dashboard2code_v1.json"
    # json_file_path = r"generated_outputs/gemini3pro_without_dom/gemini3pro_without_dom.json"
    server, thread, failed_list = start_server_background(
        json_path=json_file_path,
        host='localhost',
        port=8080,
        # debug=False
        debug=True
    )

    if failed_list:
        print(f"Main 线程检测到失败的任务: {len(failed_list)} 个")

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务器...")
        stop_server()
