import types
import sys
from collections import Counter  # [新增] 用于统计组件数量
from visualize_tree import visualize_tree  # 如果你有这个文件，请取消注释

# 尝试导入 dash 以获取准确类型，如果环境没有也做了兼容
try:
    import dash
    from dash import html, dcc
    import dash_bootstrap_components as dbc
except ImportError:
    pass

# ==========================================
# 1. 语义映射 & 剪枝策略
# ==========================================
TYPES_TO_IGNORE = {
    'Store',  # 纯数据逻辑，不可见
    'Br',  # 换行符，属于 styling 细节
    'Hr',  # 水平分割线，通常也是装饰性
    'Tooltip',  # 悬浮提示，属于增强交互，不影响主骨架
    'Interval',  # 定时器，纯逻辑
    'Location',  # URL 路由控制，纯逻辑
    'Download'  # 下载控件，通常不可见
}
# 剪枝列表：这些组件如果没写 id，会被视作“透明容器”，直接溶解掉
CONTAINER_TYPES_TO_PRUNE = {
    'Div', 'Row', 'Col', 'Container', 'Card', 'CardBody',
    'Form', 'FormGroup', 'InputGroup', 'Center',
    'Stack',
    # 新增以下文本容器，视作透明包装
    'P', 'Label', 'Span', 'Markdown', 'Small', 'I', 'B'

}


def normalize_type(raw_type):
    """
    将 Dash 组件类型归一化为通用业务组件名称。
    """
    simple_name = raw_type.split('.')[-1]

    # 1. 文本类归一
    if simple_name in ['H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'Header']:
        return 'Header'
    if simple_name in ['P', 'Label', 'Span', 'Markdown', 'Small', 'I', 'B']:
        return 'Text'

    # 2. 图表类归一 (直接统一，不读内部 figure)
    if 'Graph' in simple_name:
        return 'Graph'

    # 3. 核心交互组件映射
    if 'Button' in simple_name: return 'Button'
    if 'Input' in simple_name: return 'Input'
    if 'Dropdown' in simple_name: return 'Dropdown'
    if 'Checklist' in simple_name: return 'Checklist'
    if 'RadioItems' in simple_name: return 'RadioItems'
    if 'Slider' in simple_name: return 'Slider'
    if 'DatePicker' in simple_name: return 'DatePicker'
    if 'Upload' in simple_name: return 'Upload'
    if 'DataTable' in simple_name: return 'Table'

    return simple_name


class TreeNode:
    def __init__(self, name, node_id=None):
        self.name = name
        self.id = node_id
        self.children = []

    def __repr__(self):
        id_str = f" id={self.id}" if self.id else ""
        return f"<{self.name}{id_str}>"


# ==========================================
# 2. 动态布局提取 & 智能树构建
# ==========================================

def load_layout_dynamically(code_content):
    """动态执行字符串代码，提取 app.layout"""
    module_name = "dynamic_temp_module"
    module = types.ModuleType(module_name)
    try:
        exec(code_content, module.__dict__)
    except Exception as e:
        # print(f"[Warning] Code execution parsing error: {e}")
        return None

    if 'app' in module.__dict__:
        app = module.app
        # 兼容 app.layout 是函数的情况
        layout = app.layout() if callable(app.layout) else app.layout
        return layout
    return None


def extract_nodes_recursive(dash_obj):
    if isinstance(dash_obj, (str, int, float)):
        if str(dash_obj).strip():
            return [TreeNode("Text")]
        return []

    if dash_obj is None:
        return []

    raw_type = getattr(dash_obj, '_type', type(dash_obj).__name__)
    simple_name = raw_type.split('.')[-1]

    # -------------------------------------------------
    # 【新增逻辑】直接丢弃噪音组件
    # -------------------------------------------------
    if simple_name in TYPES_TO_IGNORE:
        return []  # 直接返回空，树里不会有这个节点
    norm_name = normalize_type(raw_type)
    node_id = getattr(dash_obj, 'id', None)

    # 3. 递归处理子节点
    children_objs = getattr(dash_obj, 'children', [])
    if not isinstance(children_objs, list):
        children_objs = [children_objs]

    processed_children = []
    for child in children_objs:
        processed_children.extend(extract_nodes_recursive(child))

    # -------------------------------------------------
    # 4. 剪枝逻辑 (Pruning) - 逻辑优化
    # -------------------------------------------------
    # 只有当它是容器类型，且没有ID时，才剪枝。
    if simple_name in CONTAINER_TYPES_TO_PRUNE and not node_id:
        return processed_children

    # 5. 正常构建节点
    node = TreeNode(norm_name, node_id)
    node.children = processed_children
    return [node]


def build_layout_tree(code_content):
    layout_obj = load_layout_dynamically(code_content)
    if not layout_obj:
        return None

    nodes = extract_nodes_recursive(layout_obj)

    if not nodes:
        return None

    # 如果根节点被剪枝变成了多个平级节点，创建虚拟根
    if len(nodes) > 1:
        root = TreeNode("VirtualRoot")
        root.children = nodes
        return root
    else:
        return nodes[0]


# ==========================================
# 3. 鲁棒的树编辑距离 (Robust TED - DP)
# ==========================================

def get_node_cost(node1, node2):
    if node1.name != node2.name:
        return 1.0
    return 0.0


def tree_edit_distance(root1, root2):
    """
    基于 Zhang-Shasha 思想的简化版 (DP处理子节点序列)
    """
    if root1 is None and root2 is None: return 0
    if root1 is None: return count_nodes(root2)
    if root2 is None: return count_nodes(root1)

    # 1. 根节点差异
    root_cost = get_node_cost(root1, root2)

    # 2. 子节点序列差异 (Levenshtein Distance)
    children1 = root1.children
    children2 = root2.children
    n1 = len(children1)
    n2 = len(children2)

    # dp[i][j]
    dp = [[0.0] * (n2 + 1) for _ in range(n1 + 1)]

    for i in range(1, n1 + 1):
        dp[i][0] = dp[i - 1][0] + count_nodes(children1[i - 1])
    for j in range(1, n2 + 1):
        dp[0][j] = dp[0][j - 1] + count_nodes(children2[j - 1])

    for i in range(1, n1 + 1):
        for j in range(1, n2 + 1):
            cost_delete = dp[i - 1][j] + count_nodes(children1[i - 1])
            cost_insert = dp[i][j - 1] + count_nodes(children2[j - 1])
            # 递归比较子树
            cost_substitute = dp[i - 1][j - 1] + tree_edit_distance(children1[i - 1], children2[j - 1])

            dp[i][j] = min(cost_delete, cost_insert, cost_substitute)

    return root_cost + dp[n1][n2]


def count_nodes(node):
    if not node: return 0
    cnt = 1
    for c in node.children:
        cnt += count_nodes(c)
    return cnt


# ==========================================
# 4. F1 Score 计算 (基于 Counter 统计数量)
# ==========================================

def get_component_counts(node):
    """
    递归遍历树，统计各类组件出现的次数。
    返回: Counter({'Button': 2, 'Graph': 1, ...})
    """
    if not node: return Counter()

    # 虚拟根节点不参与计数
    cnt = Counter([node.name]) if node.name != "VirtualRoot" else Counter()

    for child in node.children:
        cnt += get_component_counts(child)

    return cnt


def calculate_component_f1(gt_root, gen_root):
    # 1. 获取组件计数器
    gt_counter = get_component_counts(gt_root)
    gen_counter = get_component_counts(gen_root)

    # 2. 计算总实例数
    total_gt = sum(gt_counter.values())
    total_gen = sum(gen_counter.values())

    # 边界情况处理
    if total_gt == 0 and total_gen == 0: return 1.0, 1.0, 1.0, {}, {}
    if total_gt == 0: return 0.0, 0.0, 0.0, dict(gt_counter), dict(gen_counter)
    if total_gen == 0: return 0.0, 0.0, 0.0, dict(gt_counter), dict(gen_counter)

    # 3. 计算交集数量 (Multiset Intersection)
    # 对于每一类组件，取 min(GT数量, Gen数量) 作为匹配成功数
    intersection_count = 0
    all_types = set(gt_counter.keys()) | set(gen_counter.keys())

    for t in all_types:
        intersection_count += min(gt_counter[t], gen_counter[t])

    # 4. 计算指标
    precision = intersection_count / total_gen
    recall = intersection_count / total_gt

    if precision + recall > 0:
        f1 = 2 * (precision * recall) / (precision + recall)
    else:
        f1 = 0.0

    return f1, precision, recall, dict(gt_counter), dict(gen_counter)


# ==========================================
# 5. 主程序
# ==========================================
def static_evaluate(gt_code, gen_code):
    gt_root = build_layout_tree(gt_code)
    gen_root = build_layout_tree(gen_code)

    if not gt_root or not gen_root:
        return 0, 0, None, None

    # TED
    ted_cost = tree_edit_distance(gt_root, gen_root)
    max_nodes = max(count_nodes(gt_root), count_nodes(gen_root))
    struct_score = max(0.0, 1.0 - (ted_cost / max_nodes)) if max_nodes > 0 else 0

    # F1 (Quantity Aware)
    f1, prec, rec, gt_counts, gen_counts = calculate_component_f1(gt_root, gen_root)

    print("-" * 60)
    print(f"Structure Score (TED):   {struct_score:.2%}")
    print(f"Component F1 Score:      {f1:.2%} (Quantity Aware)")
    print(f"  - Precision:           {prec:.2%}")
    print(f"  - Recall:              {rec:.2%}")
    print("-" * 60)
    # 打印格式美化一下，按组件名排序
    print(f"GT Components (Count):   {dict(sorted(gt_counts.items()))}")
    print(f"Gen Components (Count):  {dict(sorted(gen_counts.items()))}")
    print("-" * 60)

    return struct_score, f1, gt_root, gen_root


if __name__ == "__main__":
    try:
        # 这里你可以替换成实际的文件路径
        with open("gt.py", 'r', encoding='utf-8') as f:
            gt_code = f.read()
        with open("gen.py", 'r', encoding='utf-8') as f:
            gen_code = f.read()

        struct_score, f1_score, gt_root, gen_root = static_evaluate(gt_code, gen_code)

        # 可视化 (如果文件存在)
        try:
            visualize_tree(gt_root, "gt_tree_opt.png")
            visualize_tree(gen_root, "gen_tree_opt.png")
            print("Tree visualizations saved as .png files.")
        except Exception:
            pass

    except FileNotFoundError:
        print("Please ensure 'gt.py' and 'gen.py' exist.")