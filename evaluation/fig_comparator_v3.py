import json
import base64
import numpy as np
import logging
import re
from collections import Counter

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PlotlyComparator:
    # 固定的 Plotly 默认颜色序列，用于解析索引颜色
    PLOTLY_DEFAULT_SEQUENCE = [
        '#636efa', '#EF553B', '#00cc96', '#ab63fa', '#FFA15A',
        '#19d3f3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'
    ]

    NAMED_COLORS = {
        'blue': '#0000ff', 'red': '#ff0000', 'green': '#008000', 'black': '#000000',
        'white': '#ffffff', 'cyan': '#00ffff', 'magenta': '#ff00ff', 'yellow': '#ffff00',
        'orange': '#ffa500', 'purple': '#800080', 'gray': '#808080', 'grey': '#808080'
    }

    def __init__(self, weights=None):
        # 调整权重以包含 type (结构类型)，总和为 1.0
        if weights is None:
            self.weights = {
                'type_color': 0.2,  # 样式/颜色
                'text': 0.3,  # 文本内容
                'data': 0.3,  # 数据数值
                'type': 0.2  # 图表结构类型 (scatter/bar/etc)
            }
        else:
            self.weights = weights

    def _normalize_type(self, t_type):
        """归一化图表类型，解决 histogram vs bar 的兼容性问题"""
        if not t_type:
            return 'scatter'
        t_type = t_type.lower()
        if t_type == 'histogram':
            return 'bar'
        if t_type == 'scattergl':
            return 'scatter'
        return t_type

    def _hex_to_rgb(self, hex_str):
        """将 Hex 字符串转换为 RGB 元组"""
        hex_str = hex_str.lstrip('#')
        if len(hex_str) == 3:
            hex_str = ''.join([c * 2 for c in hex_str])
        try:
            return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return (0, 0, 0)

    def _parse_color(self, color_input, trace_index=0):
        """
        核心颜色解析器：处理 None(默认色), 命名颜色, RGB字符串, Hex
        """
        # 1. 处理默认值：根据 trace_index 返回 Plotly 默认轮播色
        if color_input is None:
            default_hex = self.PLOTLY_DEFAULT_SEQUENCE[trace_index % len(self.PLOTLY_DEFAULT_SEQUENCE)]
            return self._hex_to_rgb(default_hex)

        if isinstance(color_input, (list, np.ndarray)):
            return "data_array"  # 暂不处理渐变色数组

        c_str = str(color_input).strip().lower()

        # 2. 处理 rgb(r, g, b)
        if c_str.startswith('rgb'):
            try:
                nums = re.findall(r'\d+', c_str)
                if len(nums) >= 3:
                    return (int(nums[0]), int(nums[1]), int(nums[2]))
            except:
                pass

        # 3. 处理命名颜色
        if c_str in self.NAMED_COLORS:
            c_str = self.NAMED_COLORS[c_str]

        # 4. 处理 Hex
        if c_str.startswith('#') or re.match(r'^[0-9a-f]{3,6}$', c_str):
            if not c_str.startswith('#'): c_str = '#' + c_str
            return self._hex_to_rgb(c_str)

        return (0, 0, 0)

    def _calculate_color_similarity(self, rgb1, rgb2):
        """
        计算颜色相似度 (0.0 ~ 1.0) 基于 RGB 欧氏距离
        """
        if rgb1 == "data_array" or rgb2 == "data_array":
            return 1.0 if rgb1 == rgb2 else 0.0

        r1, g1, b1 = rgb1
        r2, g2, b2 = rgb2

        dist = np.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
        max_dist = 441.67  # sqrt(255^2 * 3)

        score = max(0, 1 - (dist / max_dist))

        # 提高容错率：如果相似度 > 0.8，视为非常接近
        if score > 0.8:
            score = 0.8 + (score - 0.8) * (0.2 / 0.2)

        return score

    def _normalize_color_simple(self, color):
        """简化版的颜色归一化，用于 Data 比较中的辅助判断"""
        if not color:
            return "default_alias"
        c = str(color).strip().lower()
        if re.match(r'^#[0-9a-f]{3}$', c):
            c = '#' + ''.join([x * 2 for x in c[1:]])
        c = c.replace(" ", "")
        # 检查是否在默认主题里
        if c.upper() in [x.upper() for x in self.PLOTLY_DEFAULT_SEQUENCE]:
            return "default_alias"
        return c

    @staticmethod
    def _calculate_f1(gt_items, gen_items):
        """计算两个列表的 F1 Score"""
        if not gt_items and not gen_items:
            return 1.0
        if not gt_items or not gen_items:
            return 0.0

        gt_counter = Counter(gt_items)
        gen_counter = Counter(gen_items)

        tp_counter = gt_counter & gen_counter
        tp = sum(tp_counter.values())

        fp = sum(gen_counter.values()) - tp
        fn = sum(gt_counter.values()) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        if precision + recall == 0:
            return 0.0

        return 2 * (precision * recall) / (precision + recall)

    def decode_plotly_data(self, prop_data):
        """
        数据解码：包含 Base64 解码及字节对齐修复
        """
        if prop_data is None: return np.array([])
        if isinstance(prop_data, list): return np.array(prop_data)

        if isinstance(prop_data, dict) and 'bdata' in prop_data:
            try:
                decoded_bytes = base64.b64decode(prop_data['bdata'])
                dtype_map = {'f8': np.float64, 'f4': np.float32, 'i4': np.int32, 'i8': np.int64, 'u1': np.uint8}
                dt = dtype_map.get(prop_data.get('dtype'), np.float64)

                # 字节对齐检查
                element_size = np.dtype(dt).itemsize
                if len(decoded_bytes) % element_size != 0:
                    valid_len = (len(decoded_bytes) // element_size) * element_size
                    if valid_len > 0:
                        decoded_bytes = decoded_bytes[:valid_len]
                    else:
                        return np.array([])

                return np.frombuffer(decoded_bytes, dtype=dt)
            except Exception:
                return np.array([])

        return np.array(prop_data)

    # --- 1. 图表类型结构评测 (Structure/Type) ---
    def compare_type(self, fig_a, fig_b):
        def extract_trace_type_info(fig):
            traces = fig.get('data', [])
            if traces is None:
                traces = []
            trace_types = []

            for t in traces:
                if getattr(t, 'visible', True):
                    t_type = t.get('type', 'scatter')

                    # 细分 scatter 类型
                    if t_type == 'scatter':
                        mode = t.get('mode', '')
                        if 'lines' in mode and 'markers' in mode:
                            trace_types.append('scatter_with_lines_and_markers')
                        elif 'lines' in mode:
                            trace_types.append('scatter_line')
                        elif 'markers' in mode:
                            trace_types.append('scatter_markers')
                        else:
                            trace_types.append('scatter')  # 默认

                    # 细分 violin 类型
                    elif t_type == 'violin':
                        box = t.get('box', None)
                        if box is not None:
                            box_visible = box.get('visible', True)
                            if box_visible:
                                trace_types.append('violin_with_box_visible')
                            else:
                                trace_types.append('violin_without_box')
                        else:
                            trace_types.append('violin_without_box')
                    else:
                        trace_types.append(t_type)

            return trace_types

        fig_a_trace_types = extract_trace_type_info(fig_a)
        fig_b_trace_types = extract_trace_type_info(fig_b)
        return self._calculate_f1(fig_a_trace_types, fig_b_trace_types)

    # --- 2. 样式评测 (Style/Color) ---
    def compare_trace_style(self, fig_a, fig_b):
        # 确保引入 scipy 的线性指派算法
        try:
            from scipy.optimize import linear_sum_assignment
        except ImportError:
            logger.error("Scipy is required for optimal matching. Please install scipy.")
            return 0.0

        def extract_trace_info(fig):
            traces = fig.get('data', [])
            if traces is None:
                traces = []
            info_list = []
            for idx, t in enumerate(traces):
                t_type = t.get('type', 'scatter')
                # 尝试获取颜色，优先级：marker > line > 直接属性
                c = None
                if 'marker' in t and isinstance(t['marker'], dict):
                    c = t['marker'].get('color')
                if not c and 'line' in t and isinstance(t['line'], dict):
                    c = t['line'].get('color')
                if not c:
                    c = t.get('color')

                rgb = self._parse_color(c, trace_index=idx)
                info_list.append({'type': t_type, 'rgb': rgb})
            return info_list

        info_a = extract_trace_info(fig_a)
        info_b = extract_trace_info(fig_b)

        n_a = len(info_a)
        n_b = len(info_b)

        # 边界情况处理
        if n_a == 0 and n_b == 0: return 1.0
        if n_a == 0 or n_b == 0: return 0.0

        # 1. 构建相似度矩阵 (Score Matrix)
        score_matrix = np.zeros((n_a, n_b))

        for i in range(n_a):
            for j in range(n_b):
                item_a = info_a[i]
                item_b = info_b[j]

                # 类型归一化检查
                type_a_norm = self._normalize_type(item_a['type'])
                type_b_norm = self._normalize_type(item_b['type'])

                # 如果图表类型根本不同（比如 bar vs scatter），直接不匹配
                if type_a_norm != type_b_norm:
                    score_matrix[i, j] = 0.0
                else:
                    # 计算颜色相似度
                    score_matrix[i, j] = self._calculate_color_similarity(item_a['rgb'], item_b['rgb'])

        # 2. 使用匈牙利算法寻找全局最优匹配
        # linear_sum_assignment 旨在最小化成本，所以我们将成本设为 (1 - 相似度)
        cost_matrix = 1.0 - score_matrix
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # 3. 计算匹配对的总得分
        total_matched_score = score_matrix[row_ind, col_ind].sum()

        # 4. 归一化
        # 分母使用 max(n_a, n_b) 以惩罚生成的 Trace 数量过多或过少的情况
        final_score = total_matched_score / max(n_a, n_b)

        return final_score
    # --- 3. 文本内容评测 (Text) ---
    def compare_text_content(self, fig_a, fig_b):
        def extract_text(fig):
            text_tokens = []
            layout = fig.get('layout', {})
            data = fig.get('data', [])

            if layout is None:
                layout = {}
            if data is None:
                data = []

            # 1. 标题 (Layout Title)
            if 'title' in layout:
                if isinstance(layout['title'], dict):
                    text_tokens.append(layout['title'].get('text', ''))
                elif isinstance(layout['title'], str):
                    text_tokens.append(layout['title'])

            # 2. 轴标签 (Axis Titles)
            for axis in ['xaxis', 'yaxis', 'zaxis']:
                if axis in layout:
                    # layout[axis] 可能为 None
                    axis_obj = layout[axis]
                    if isinstance(axis_obj, dict):
                        title = axis_obj.get('title', {})
                        if isinstance(title, dict):
                            text_tokens.append(title.get('text', ''))
                        elif isinstance(title, str):
                            text_tokens.append(title)

            # 3. Trace Names
            global_show_legend = layout.get('showlegend', True)

            for trace in data:
                trace_show_legend = trace.get('showlegend', True)

                # 只有全局开启图例且 Trace 自身也显示时，才比较 Name
                if 'name' in trace and global_show_legend and trace_show_legend:
                    text_tokens.append(str(trace['name']))

                # 显式文本 (text 属性) 通常是直接标在图上的
                if 'text' in trace and isinstance(trace['text'], str):
                    text_tokens.append(trace['text'])

            return [str(t).strip() for t in text_tokens if t and str(t).strip()]

        text_a = extract_text(fig_a)
        text_b = extract_text(fig_b)
        return self._calculate_f1(text_a, text_b)

    def _calculate_array_similarity(self, arr1, arr2, require_sort=False):
        """
        :param require_sort: 是否需要排序。
                             对于折线图(Trend)、柱状图(Order)应为 False；
                             对于直方图(Distribution)应为 True。
        """
        arr1 = np.array(arr1)
        arr2 = np.array(arr2)

        n1, n2 = len(arr1), len(arr2)
        if n1 == 0 and n2 == 0: return 1.0
        if n1 == 0 or n2 == 0: return 0.0

        # 非数值类型：保持原有逻辑
        if not np.issubdtype(arr1.dtype, np.number) or not np.issubdtype(arr2.dtype, np.number):
            matches = np.sum(np.isin(arr1, arr2))
            recall = matches / n1
            precision = np.sum(np.isin(arr2, arr1)) / n2
            if precision + recall == 0: return 0.0
            return 2 * (precision * recall) / (precision + recall)
        else:
            # 数值类型处理
            arr1 = arr1.astype(np.float64).flatten()
            arr2 = arr2.astype(np.float64).flatten()

            # 处理 NaN/Inf
            arr1 = np.nan_to_num(arr1, nan=0.0, posinf=0.0, neginf=0.0)
            arr2 = np.nan_to_num(arr2, nan=0.0, posinf=0.0, neginf=0.0)

            # [关键修改] 根据参数决定是否排序
            if require_sort:
                arr1 = np.sort(arr1)
                arr2 = np.sort(arr2)
            # 如果不排序，保留原始顺序，直接进行插值对齐和距离计算

            len_ratio = min(n1, n2) / max(n1, n2)
            length_score = np.sqrt(len_ratio)

            # 线性插值对齐长度（即使不排序，为了计算欧氏距离也必须长度一致）
            # 注意：如果不排序，interp 相当于对“波形”进行缩放，这是合理的
            if n1 == n2:
                arr2_aligned = arr2
            else:
                x_target = np.linspace(0, 1, n1)
                x_source = np.linspace(0, 1, n2)
                try:
                    arr2_aligned = np.interp(x_target, x_source, arr2)
                except Exception:
                    return 0.0

            dist = np.linalg.norm(arr1 - arr2_aligned)
            norm_sum = np.linalg.norm(arr1) + np.linalg.norm(arr2_aligned)

            if norm_sum == 0:
                return 1.0 if dist == 0 else 0.0

            shape_score = 1 - (dist / norm_sum)
            shape_score = max(0.0, shape_score)

            return shape_score * length_score
    # --- 4. 数据数值评测 (Data) ---
    def compare_data_values(self, fig_a, fig_b):
        # 必须确保引入了 linear_sum_assignment
        try:
            from scipy.optimize import linear_sum_assignment
        except ImportError:
            # 如果没有 scipy，回退到原有的贪婪算法或报错
            # 这里简单做一个简单的依赖提示，实际使用请确保环境有 scipy
            logger.error("Scipy is required for optimal matching. Please install scipy.")
            return 0.0

        traces_a = fig_a.get('data', [])
        traces_b = fig_b.get('data', [])
        if traces_a is None: traces_a = []
        if traces_b is None: traces_b = []

        # 排除完全不需要比较数据的图表类型 (如 heatmap, contour 可能太复杂，视需求而定)
        # 注意：histogram/box 现在可以保留，因为我们支持了 require_sort=True
        EXCLUDED_TRACE_TYPES = {
            "parcoords", "histogram2d", "histogram2dcontour"
        }

        def filter_traces(traces):
            if traces is None: return []
            kept = []
            for tr in traces:
                tr_type = tr.get("type", "scatter")
                if tr_type in EXCLUDED_TRACE_TYPES:
                    continue
                kept.append(tr)
            return kept

        traces_a = filter_traces(traces_a)
        traces_b = filter_traces(traces_b)

        n_a, n_b = len(traces_a), len(traces_b)
        if n_a == 0 and n_b == 0: return 1.0
        if n_a == 0 or n_b == 0: return 0.0

        # 定义必须进行排序比较的图表类型 (分布类)
        DISTRIBUTION_TYPES = {'histogram', 'box', 'violin'}

        def get_meta(t):
            return t.get('type', 'scatter')

        meta_a = [get_meta(t) for t in traces_a]
        meta_b = [get_meta(t) for t in traces_b]

        # 初始化相似度矩阵
        score_matrix = np.zeros((n_a, n_b))

        # 目标比较维度
        target_dims = ['x', 'y', 'z', 'values', 'labels', 'lon', 'lat', 'r', 'theta', 'parents', 'ids']

        for i in range(n_a):
            for j in range(n_b):
                t_type_a = self._normalize_type(meta_a[i])
                t_type_b = self._normalize_type(meta_b[j])

                # 1. 类型不一致，数据相似度直接为 0 (防止 bar 和 scatter 强行匹配)
                if t_type_a != t_type_b:
                    score_matrix[i, j] = 0.0
                    continue

                # 2. 判断是否需要排序
                # 如果是分布类图表(histogram)，数据本身无序，需要排序后比较分布
                # 如果是序列类图表(scatter/bar)，数据有序，不需要排序
                should_sort = t_type_a in DISTRIBUTION_TYPES

                ta, tb = traces_a[i], traces_b[j]
                dim_scores = []
                valid_dims = 0

                # 处理 dimensions (例如 splom, parcats 等)
                if 'dimensions' in ta and 'dimensions' in tb:
                    dims_a = ta.get('dimensions', [])
                    dims_b = tb.get('dimensions', [])
                    vals_a = []
                    vals_b = []
                    for d in dims_a: vals_a.extend(self.decode_plotly_data(d.get('values', [])))
                    for d in dims_b: vals_b.extend(self.decode_plotly_data(d.get('values', [])))

                    if vals_a and vals_b:
                        # 复杂维度通常视作无序集合或分布，这里暂定 True，也可视情况而定
                        dim_scores.append(self._calculate_array_similarity(vals_a, vals_b, require_sort=True))
                        valid_dims += 1

                # 处理常规维度
                for dim in target_dims:
                    if dim in ta and dim in tb:
                        va = self.decode_plotly_data(ta[dim])
                        vb = self.decode_plotly_data(tb[dim])

                        # 调用修改后的相似度计算
                        sim = self._calculate_array_similarity(va, vb, require_sort=should_sort)
                        dim_scores.append(sim)
                        valid_dims += 1

                # 聚合当前 Trace 对的得分
                if valid_dims > 0:
                    base_score = np.mean(dim_scores)
                else:
                    # 空 Trace 匹配检测
                    is_ta_empty = all(d not in ta for d in target_dims)
                    is_tb_empty = all(d not in tb for d in target_dims)
                    base_score = 1.0 if (is_ta_empty and is_tb_empty) else 0.0

                score_matrix[i, j] = base_score

        # ---------------------------------------------------------
        # 使用匈牙利算法 (KM算法) 进行全局最优匹配
        # ---------------------------------------------------------
        # linear_sum_assignment 寻找的是最小成本，所以我们要最大化相似度 -> 最小化 (1 - 相似度)
        cost_matrix = 1.0 - score_matrix

        # row_ind, col_ind 是匹配好的行索引和列索引
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # 提取匹配对的相似度总和
        total_matched_score = score_matrix[row_ind, col_ind].sum()

        # 归一化：除以 (GT Trace数量 和 Gen Trace数量 的最大值)
        # 这样如果生成的 Trace 多了或少了，都会导致分母变大，从而扣分
        final_score = total_matched_score / max(n_a, n_b)

        return final_score


    def evaluate(self, fig_a, fig_b):
        if not fig_a: fig_a = {}
        if not fig_b: fig_b = {}

        s_style = self.compare_trace_style(fig_a, fig_b)
        s_text = self.compare_text_content(fig_a, fig_b)
        s_data = self.compare_data_values(fig_a, fig_b)
        s_type = self.compare_type(fig_a, fig_b)

        final_score = (
                s_style * self.weights['type_color'] +
                s_text * self.weights['text'] +
                s_data * self.weights['data'] +
                s_type * self.weights['type']
        )

        return {
            "total_score": round(final_score, 4),
            "details": {
                "style_f1": round(s_style, 4),
                "text_f1": round(s_text, 4),
                "data_sim": round(s_data, 4),
                "type_f1": round(s_type, 4)
            }
        }


if __name__ == "__main__":
    # 示例用法
    # 请确保路径和文件存在，或修改为实际测试路径
    try:
        # 假设这里是你的测试文件路径
        # gen_path = "path/to/gen.json"
        # gt_path = "path/to/gt.json"

        # with open(gen_path, "r", encoding='utf-8') as f:
        #     gen_fig = json.load(f)[0]['figure']
        # with open(gt_path, "r", encoding='utf-8') as f:
        #     gt_fig = json.load(f)[0]['figure']

        # comparator = PlotlyComparator()
        # res = comparator.evaluate(gt_fig, gen_fig)
        # print("评测报告:", json.dumps(res, indent=2, ensure_ascii=False))
        pass
    except Exception as e:
        print(f"Error loading files: {e}")