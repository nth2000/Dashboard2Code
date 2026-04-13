# agent_environment.py
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.action_chains import ActionChains
import time
import json
from PIL import Image
import io
from scripts.image_marker import mark_point_on_image
from selenium.webdriver.common.keys import Keys

class DashboardEnvironment:
    def __init__(self, dashboard_url, headless=False, target_width=1920, target_height=1080):
        """
        初始化交互环境
        """
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--start-maximized')

        self.driver = webdriver.Chrome(options=chrome_options)

        # 1. 打开页面
        self.driver.get(dashboard_url)

        # 2. 设置视口大小
        self.driver.set_window_size(target_width, target_height)
        time.sleep(0.5)
        actual_width = self.driver.execute_script("return window.innerWidth")
        actual_height = self.driver.execute_script("return window.innerHeight")
        width_offset = target_width - actual_width
        height_offset = target_height - actual_height
        self.driver.set_window_size(target_width + width_offset, target_height + height_offset)
        time.sleep(2)

        print(f"目标视口: {target_width}x{target_height}")

        self.step_count = 0
        self.max_steps = 25
        self.history = []
        self.current_offset = {'x': 0, 'y': 0}
        self.pending_marks = []

        # agent_environment.py 中的 DashboardEnvironment 类内

    def scan_current_graphs(self):
        """
        扫描当前页面上所有可见的 Dash 图表，提取其数据、布局及位置信息，
        并按照视觉位置（从上到下，从左到右）进行排序。
        """
        js_script = """
        const graphNodes = Array.from(document.querySelectorAll('.js-plotly-plot'));

        const results = graphNodes.map(node => {
            const rect = node.getBoundingClientRect();
            // 简单判断可见性
            const isVisible = rect.width > 0 && rect.height > 0;

            return {
                visible: isVisible,
                x: rect.x + window.scrollX,
                y: rect.y + window.scrollY,
                width: rect.width,
                height: rect.height,
                figure: {
                    data: node.data, 
                    layout: node.layout
                }
            };
        });

        return results.filter(r => r.visible);
        """
        try:
            raw_graphs = self.driver.execute_script(js_script)
        except Exception as e:
            print(f"Error scanning graphs: {e}")
            return []

        # Python 端进行空间排序 (Reading Order)
        # 容差 50px，视为同一行
        row_tolerance = 50
        sorted_graphs = sorted(raw_graphs, key=lambda g: (int(g['y'] // row_tolerance), g['x']))
        return sorted_graphs


    def get_screenshot(self, apply_marks=True):
        screenshot = self.driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(screenshot))

        if apply_marks and self.pending_marks:
            for x, y in self.pending_marks:
                img = mark_point_on_image(img, x, y)
            self.pending_marks = []
        return img

    def get_a11y_tree(self):
        with open(os.path.join(os.path.dirname(__file__), "scripts/get_a11y_tree.js"), "r", encoding='utf-8') as f:
            js_script = f.read()
        return self.driver.execute_script(js_script)

    def _reset_pointer(self):
        if self.current_offset['x'] != 0 or self.current_offset['y'] != 0:
            action_chains = ActionChains(self.driver)
            action_chains.move_by_offset(
                -self.current_offset['x'],
                -self.current_offset['y']
            ).perform()
            self.current_offset = {'x': 0, 'y': 0}

    def execute_action(self, action):
        self.step_count += 1

        try:
            if action['type'] == 'mark':
                x, y = action['x'], action['y']
                self.pending_marks.append((x, y))
                return {'success': True, 'message': f'Mark added at ({x}, {y})'}

            # 2. 执行动作
            self._reset_pointer()
            action_chains = ActionChains(self.driver)

            if action['type'] == 'click':
                action_chains.move_by_offset(action['x'], action['y']).click().perform()
                self.current_offset = {'x': action['x'], 'y': action['y']}
            elif action['type'] == 'double_click':
                action_chains.move_by_offset(action['x'], action['y']).double_click().perform()
                self.current_offset = {'x': action['x'], 'y': action['y']}
            elif action['type'] == 'move_mouse_to':
                action_chains.move_by_offset(action['x'], action['y']).perform()
                self.current_offset = {'x': action['x'], 'y': action['y']}
            elif action['type'] == 'drag':
                action_chains.move_by_offset(action['from_x'], action['from_y'])
                action_chains.click_and_hold()
                action_chains.move_by_offset(action['to_x'] - action['from_x'], action['to_y'] - action['from_y'])
                action_chains.release().perform()
                self.current_offset = {'x': action['to_x'], 'y': action['to_y']}
            elif action['type'] == 'scroll':
                if 'x' in action and 'y' in action:
                    scroll_origin = ScrollOrigin.from_viewport(action['x'], action['y'])
                    ActionChains(self.driver) \
                        .scroll_from_origin(scroll_origin, 0, action['amount']) \
                        .perform()
                    # self.current_offset = {'x': action['x'], 'y': action['y']}
                else:
                    # 全局滚动保持不变
                    ActionChains(self.driver).scroll_by_amount(0, action['amount']).perform()
            elif action['type'] == 'replace_text':
                action_chains.move_by_offset(action['x'], action['y'])
                action_chains.click()
                cmd_ctrl = Keys.CONTROL
                action_chains.key_down(cmd_ctrl).send_keys('a').key_up(cmd_ctrl)
                if 'text' in action:
                    action_chains.send_keys(action['text'])
                action_chains.perform()
                self.current_offset = {'x': action['x'], 'y': action['y']}
            else:
                raise ValueError(f"Unknown action type: {action['type']}")

            result = {
                'success': True,
                'message': 'Action executed'
            }

            self.history.append({'step': self.step_count, 'action': action, 'result': result})
            time.sleep(2)
            return result

        except Exception as e:
            error_res = {'success': False, 'error': str(e)}
            self.history.append({'step': self.step_count, 'action': action, 'result': error_res})
            return error_res

    def reset(self):
        self._reset_pointer()
        self.driver.refresh()
        self.step_count = 0
        self.history = []
        self.current_offset = {'x': 0, 'y': 0}
        self.pending_marks = []
        time.sleep(2)

    def close(self):
        self._reset_pointer()
        self.driver.quit()