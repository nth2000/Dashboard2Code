"""
用于在PIL Image上标记坐标点的辅助模块
"""
from PIL import Image, ImageDraw, ImageFont
import numpy as np


def mark_point_on_image(pil_image, x, y):
    """
    在PIL Image上标记指定坐标点

    Args:
        pil_image: PIL Image对象
        x: X坐标
        y: Y坐标

    Returns:
        标记后的PIL Image对象
    """
    # 创建副本以避免修改原图
    img = pil_image.copy()
    draw = ImageDraw.Draw(img)

    width, height = img.size

    # 检查坐标是否在图像范围内
    if x < 0 or x >= width or y < 0 or y >= height:
        print(f"警告: 坐标 ({x}, {y}) 超出图像范围 ({width}x{height})！")

    # 绘制参数
    cross_size = 40
    circle_radius = 30
    dot_radius = 5
    color = (255, 0, 0)  # RGB格式，红色
    border_color = (255, 255, 255)  # 白色
    line_width = 3
    border_width = 5

    # 1. 绘制白色边框（外层）
    # 水平线
    draw.line([(x - cross_size, y), (x + cross_size, y)], fill=border_color, width=border_width)
    # 垂直线
    draw.line([(x, y - cross_size), (x, y + cross_size)], fill=border_color, width=border_width)
    # 圆圈
    draw.ellipse([x - circle_radius, y - circle_radius,
                  x + circle_radius, y + circle_radius],
                 outline=border_color, width=border_width)

    # 2. 绘制红色标记（覆盖在白色边框上）
    # 水平线
    draw.line([(x - cross_size, y), (x + cross_size, y)], fill=color, width=line_width)
    # 垂直线
    draw.line([(x, y - cross_size), (x, y + cross_size)], fill=color, width=line_width)
    # 圆圈
    draw.ellipse([x - circle_radius, y - circle_radius,
                  x + circle_radius, y + circle_radius],
                 outline=color, width=line_width)
    # 中心实心圆点
    draw.ellipse([x - dot_radius, y - dot_radius,
                  x + dot_radius, y + dot_radius],
                 fill=color, outline=color)

    # 3. 添加坐标文字标注
    text = f"({x},{y})"

    try:
        # 尝试使用更美观的字体，按优先级尝试
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # 清晰易读
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # 现代感
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",  # 圆润美观
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
            "C:\\Windows\\Fonts\\arialbd.ttf",  # Windows
        ]
        font = None
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, 32)  # 增大到32号字体
                break
            except:
                continue

        if font is None:
            # 如果都找不到，使用默认字体
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()

    # 获取文字边界框
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # 文字位置（在标记点的右上方）
    text_x = x + 45
    text_y = y - 45

    # 确保文字不超出图像边界
    if text_x + text_width > width:
        text_x = x - text_width - 45
    if text_y < 0:
        text_y = y + 45

    # 绘制文字背景（半透明黑色矩形）
    padding = 5
    bg_bbox = [
        text_x - padding,
        text_y - padding,
        text_x + text_width + padding,
        text_y + text_height + padding
    ]

    # 创建半透明背景
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(bg_bbox, fill=(0, 0, 0, 153))  # 60% 不透明度

    # 如果原图是RGB，转换为RGBA以支持alpha混合
    if img.mode == 'RGB':
        img = img.convert('RGBA')

    # 合成半透明背景
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # 绘制文字
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    # 转回RGB（如果需要）
    if img.mode == 'RGBA':
        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
        rgb_img.paste(img, mask=img.split()[3])  # 使用alpha通道作为mask
        img = rgb_img

    return img


def mark_multiple_points(pil_image, points):
    """
    在PIL Image上标记多个坐标点

    Args:
        pil_image: PIL Image对象
        points: 坐标点列表，如 [(x1, y1), (x2, y2), ...]

    Returns:
        标记后的PIL Image对象
    """
    img = pil_image.copy()
    for x, y in points:
        img = mark_point_on_image(img, x, y)
    return img

if __name__ == "__main__":
    input_path = r"/evaluation/task_execution_results\run_20251217_151045\App_12\step_2\screenshot.png"
    example_points = [
        (479, 273),
        (960, 300),
        (965, 340),
        (910, 300),
        (860, 270),
        (960, 385),
        (965, 290),
    ]

    base_img = Image.open(input_path).convert('RGB')
    marked_img = mark_multiple_points(base_img, example_points)
    output_path = "marked_image_output.png"
    try:
        marked_img.save(output_path)
        print(f"图像已保存到: {output_path}")
    except Exception as e:
        print(f"保存或显示图像失败: {e}")
        print("请检查PIL库是否正确安装，以及是否有写入权限。")