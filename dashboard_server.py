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
    """Transforms AST to inject path prefixes and fix callback decorators."""
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
                    print(f"  -> Auto-fix: Replacing @callback with @app.callback in {node.name}")
                    decorator.func = ast.Attribute(
                        value=ast.Name(id='app', ctx=ast.Load()),
                        attr='callback',
                        ctx=ast.Load()
                    )
        return self.generic_visit(node)


def inject_debug_layout(app, code_string):
    original_layout = app.layout

    def debug_layout_wrapper():
        content = original_layout() if callable(original_layout) else original_layout

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
        transformer = DashCallTransformer(url_base_pathname)
        modified_tree = transformer.visit(tree)

        if not transformer.found_dash_call:
            print(f"[{app_id}] Warning: No Dash() call found in code.")

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
        namespace = {'__name__': '__main__', '__builtins__': __builtins__}
        exec(final_code, namespace)

        app = next((obj for name, obj in namespace.items() 
                    if isinstance(obj, Dash) and not name.startswith('_')), None)

        if app is None:
            raise ValueError(f"App {app_id} failed to create a Dash instance.")

        if app.layout is None:
            raise ValueError(f"App {app_id} layout is None.")

        if debug:
            inject_debug_layout(app, code_string)

        return app

    except Exception as e:
        print(f"[{app_id}] Error executing code: {e}")
        raise


def create_server(json_path, debug=False):
    server = Flask(__name__)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    try:
        apps_data = load_dash_apps(json_path)
    except Exception as e:
        print(f"Failed to read config {json_path}: {e}")
        return server, []

    mounts = {}
    failed_apps = []

    for app_id, app_info in apps_data.items():
        code = app_info.get('code', '')
        safe_app_id = str(app_id)
        url_base = f'/dashboard/{safe_app_id}'
        dash_url_base = url_base + '/'

        try:
            dash_app = create_dash_app_from_code(code, dash_url_base, safe_app_id, debug=debug)
            mounts[url_base] = dash_app.server
            print(f"✓ Loaded app {safe_app_id} -> {dash_url_base}")
        except Exception as e:
            print(f"✗ Failed to load app {safe_app_id}: {e}")
            failed_apps.append(safe_app_id)

    if mounts:
        server.wsgi_app = DispatcherMiddleware(server.wsgi_app, mounts)

    @server.route('/')
    def index():
        links = [
            f'<li><a href="/dashboard/{str(aid)}/">Dashboard {str(aid)}</a></li>'
            for aid in apps_data.keys() if str(aid) not in failed_apps
        ]
        
        error_section = ""
        if failed_apps:
            error_items = ''.join([f'<li style="color: red; background-color: #fff0f0;">❌ {aid} failed to load</li>' for aid in failed_apps])
            error_section = f'''
            <div style="margin-top: 30px; border-top: 2px solid #ffcccc; padding-top: 20px;">
                <h3 style="color: #cc0000;">Failed Apps ({len(failed_apps)}):</h3>
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
                    .status-bar {{ margin-bottom: 20px; padding: 10px; background-color: #e8f5e9; color: #2e7d32; border-radius: 4px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>📊 Dashboard Server</h1>
                    <div class="status-bar">
                        Loaded: {len(mounts)} | Failed: {len(failed_apps)} | Debug: {'ON' if debug else 'OFF'}
                    </div>
                    <p>Available Dashboards:</p>
                    <ul>{''.join(links)}</ul>
                    {error_section}
                </div>
            </body>
        </html>
        '''

    return server, failed_apps

def start_server_background(json_path='data/datasets/debug.json', host='localhost', port=5000, debug=False):
    global _server_instance, _server_thread

    print(f"Loading Dash apps from {json_path} (Debug={debug})...")
    print("-" * 40)

    server, failed_apps = create_server(json_path, debug=debug)
    _server_instance = server

    print("-" * 40)
    print(f"Starting background server...")
    if failed_apps:
        print(f"⚠️ Warning: These apps failed to load: {failed_apps}")
    
    print(f"Access the index at http://{host}:{port}")
    print("-" * 40)

    def run_server():
        server.run(host=host, port=port, debug=True, use_reloader=False)

    _server_thread = threading.Thread(target=run_server, daemon=True)
    _server_thread.start()

    return server, _server_thread, failed_apps


def stop_server():
    global _server_instance, _server_thread
    print("Note: Terminate the process to fully stop the Flask development server.")
    _server_instance = None
    _server_thread = None


if __name__ == '__main__':
    json_file_path = "data/datasets/dashboard2code_v1.json"
    server, thread, failed_list = start_server_background(
        json_path=json_file_path,
        host='localhost',
        port=8080,
        debug=True
    )

    if failed_list:
        print(f"Main thread detected {len(failed_list)} failed tasks.")

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
        stop_server()