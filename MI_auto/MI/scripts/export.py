#!/usr/bin/env python3
"""
export.py — 报告导出脚本
将 generate_report.py 生成的 HTML 报告转换为 PDF 或 PPT 格式。

用法：
    python export.py <html_path> --format pdf   # 输出同名 .pdf
    python export.py <html_path> --format ppt   # 输出同名 .pptx
    python export.py <html_path> --format all   # 同时输出 .pdf 和 .pptx
"""

import argparse
import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path


# ==================== PDF 导出 ====================

def export_pdf(html_path: str, output_path: str = None) -> str:
    """使用 weasyprint 将 HTML 转换为 PDF。"""
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        print("[ERROR] 缺少 weasyprint，请运行：pip install weasyprint")
        sys.exit(1)

    if output_path is None:
        output_path = str(Path(html_path).with_suffix('.pdf'))

    print(f"  正在生成 PDF：{output_path}")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    # weasyprint 直接读取本地 HTML（含 base64 内嵌图片）
    HTML(filename=html_path).write_pdf(
        output_path,
        stylesheets=[CSS(string="""
            @page { size: A4 landscape; margin: 1cm; }
            body { font-size: 11pt; }
            .section-card { page-break-inside: avoid; }
        """)]
    )
    print(f"  ✓ PDF 已保存：{output_path}")
    return output_path


# ==================== PPT 导出 ====================

def _strip_html_tags(text: str) -> str:
    """去除 HTML 标签，保留纯文本。"""
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract_sections_from_html(html_path: str):
    """
    从 HTML 报告中提取各 section 的标题、图表图片（base64）和文字内容。
    返回列表：[{"title": str, "en": str, "images": [bytes,...], "text": str}, ...]
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    sections = []

    # 提取报告标题
    title_match = re.search(r'<h1[^>]*class="[^"]*report-title[^"]*"[^>]*>(.*?)</h1>', html, re.DOTALL)
    report_title = _strip_html_tags(title_match.group(1)) if title_match else "市场洞察报告"

    # 按 section-card 分割
    card_pattern = re.compile(
        r'<div[^>]+class="[^"]*section-card[^"]*"[^>]*id="([^"]+)"[^>]*>(.*?)</div>\s*</div>\s*</section>',
        re.DOTALL
    )
    # 更宽松的匹配：找到所有 section
    section_pattern = re.compile(
        r'<section[^>]+id="([^"]+)"[^>]*>(.*?)</section>',
        re.DOTALL
    )

    for m in section_pattern.finditer(html):
        sec_id   = m.group(1)
        sec_html = m.group(2)

        # 提取中文标题
        zh_match = re.search(r'<h2[^>]*class="[^"]*section-title[^"]*"[^>]*>(.*?)</h2>', sec_html, re.DOTALL)
        if not zh_match:
            zh_match = re.search(r'<h2[^>]*>(.*?)</h2>', sec_html, re.DOTALL)
        zh_title = _strip_html_tags(zh_match.group(1)) if zh_match else sec_id

        # 提取英文副标题
        en_match = re.search(r'<p[^>]*class="[^"]*section-en[^"]*"[^>]*>(.*?)</p>', sec_html, re.DOTALL)
        en_title = _strip_html_tags(en_match.group(1)) if en_match else ""

        # 提取所有 base64 图片
        images = []
        for img_m in re.finditer(r'<img[^>]+src="data:image/png;base64,([^"]+)"', sec_html):
            try:
                img_data = base64.b64decode(img_m.group(1))
                images.append(img_data)
            except Exception:
                pass

        # 提取文字（insight card 内容）
        insight_match = re.search(
            r'<div[^>]+class="[^"]*insight-card[^"]*"[^>]*>(.*?)</div>',
            sec_html, re.DOTALL
        )
        text_content = ""
        if insight_match:
            text_content = _strip_html_tags(insight_match.group(1))
        else:
            # fallback：提取所有 <p> 文字
            p_texts = re.findall(r'<p[^>]*>(.*?)</p>', sec_html, re.DOTALL)
            text_content = '\n'.join(_strip_html_tags(p) for p in p_texts if _strip_html_tags(p))

        sections.append({
            "id":     sec_id,
            "title":  zh_title,
            "en":     en_title,
            "images": images,
            "text":   text_content[:1200],  # PPT 文字限制
        })

    return report_title, sections


def export_ppt(html_path: str, output_path: str = None) -> str:
    """将 HTML 报告转换为 PPT（每个 section 对应一张幻灯片）。"""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        import io
    except ImportError:
        print("[ERROR] 缺少 python-pptx，请运行：pip install python-pptx")
        sys.exit(1)

    if output_path is None:
        output_path = str(Path(html_path).with_suffix('.pptx'))

    print(f"  正在生成 PPT：{output_path}")

    report_title, sections = _extract_sections_from_html(html_path)

    prs = Presentation()
    prs.slide_width  = Inches(13.33)   # 宽屏 16:9
    prs.slide_height = Inches(7.5)

    # 配色
    COLOR_NAVY  = RGBColor(0x0F, 0x17, 0x2A)
    COLOR_BLUE  = RGBColor(0x1D, 0x4E, 0xD8)
    COLOR_GRAY  = RGBColor(0x47, 0x55, 0x69)
    COLOR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    COLOR_BG    = RGBColor(0xF8, 0xFA, 0xFC)

    blank_layout = prs.slide_layouts[6]  # 完全空白

    def add_rect(slide, left, top, width, height, fill_rgb=None, line_rgb=None):
        from pptx.util import Emu
        shape = slide.shapes.add_shape(
            1,  # MSO_SHAPE_TYPE.RECTANGLE
            Inches(left), Inches(top), Inches(width), Inches(height)
        )
        if fill_rgb:
            shape.fill.solid()
            shape.fill.fore_color.rgb = fill_rgb
        else:
            shape.fill.background()
        if line_rgb:
            shape.line.color.rgb = line_rgb
        else:
            shape.line.fill.background()
        return shape

    def add_text(slide, text, left, top, width, height,
                 font_size=18, bold=False, color=None, align=PP_ALIGN.LEFT, wrap=True):
        from pptx.util import Pt
        txBox = slide.shapes.add_textbox(
            Inches(left), Inches(top), Inches(width), Inches(height)
        )
        tf = txBox.text_frame
        tf.word_wrap = wrap
        p = tf.paragraphs[0]
        p.alignment = align
        run = p.add_run()
        run.text = text
        run.font.size = Pt(font_size)
        run.font.bold = bold
        if color:
            run.font.color.rgb = color
        return txBox

    # ── 封面幻灯片 ──────────────────────────────────────────────────────────
    slide = prs.slides.add_slide(blank_layout)
    add_rect(slide, 0, 0, 13.33, 7.5, fill_rgb=COLOR_NAVY)
    add_rect(slide, 0, 5.8, 13.33, 1.7, fill_rgb=COLOR_BLUE)
    add_text(slide, report_title,
             0.8, 2.5, 11.5, 1.5,
             font_size=36, bold=True, color=COLOR_WHITE, align=PP_ALIGN.CENTER)
    add_text(slide, "Market Insight Report",
             0.8, 4.0, 11.5, 0.6,
             font_size=18, bold=False, color=RGBColor(0x94, 0xA3, 0xB8), align=PP_ALIGN.CENTER)
    add_text(slide, "Powered by Market Insight",
             0.8, 6.1, 11.5, 0.6,
             font_size=12, bold=False, color=COLOR_WHITE, align=PP_ALIGN.CENTER)

    # ── 各 section 幻灯片 ───────────────────────────────────────────────────
    for sec in sections:
        if not sec["title"]:
            continue

        slide = prs.slides.add_slide(blank_layout)
        # 背景
        add_rect(slide, 0, 0, 13.33, 7.5, fill_rgb=COLOR_BG)
        # 顶部标题栏
        add_rect(slide, 0, 0, 13.33, 1.1, fill_rgb=COLOR_NAVY)
        add_text(slide, sec["title"],
                 0.3, 0.05, 10, 0.6,
                 font_size=22, bold=True, color=COLOR_WHITE)
        if sec["en"]:
            add_text(slide, sec["en"],
                     0.3, 0.62, 10, 0.35,
                     font_size=11, bold=False, color=RGBColor(0x94, 0xA3, 0xB8))

        images = sec["images"]
        text   = sec["text"]

        if images and text:
            # 左图右文布局
            # 图片区域（左侧）
            img_left = 0.3
            img_top  = 1.25
            img_w    = 7.8
            img_h    = 5.8
            try:
                img_io = io.BytesIO(images[0])
                slide.shapes.add_picture(img_io, Inches(img_left), Inches(img_top),
                                         Inches(img_w), Inches(img_h))
            except Exception:
                pass
            # 文字区域（右侧）
            add_rect(slide, 8.3, 1.25, 4.7, 5.8,
                     fill_rgb=RGBColor(0xFF, 0xFF, 0xFF))
            add_text(slide, "DATA INSIGHT",
                     8.45, 1.35, 4.4, 0.35,
                     font_size=9, bold=True, color=COLOR_BLUE)
            add_text(slide, text,
                     8.45, 1.75, 4.4, 5.1,
                     font_size=10, bold=False, color=COLOR_GRAY)

        elif images and not text:
            # 纯图布局（居中）
            try:
                img_io = io.BytesIO(images[0])
                slide.shapes.add_picture(img_io, Inches(0.5), Inches(1.25),
                                         Inches(12.3), Inches(5.9))
            except Exception:
                pass
            # 若有第二张图
            if len(images) > 1:
                try:
                    img_io2 = io.BytesIO(images[1])
                    slide.shapes.add_picture(img_io2, Inches(6.5), Inches(1.25),
                                             Inches(6.3), Inches(5.9))
                    # 调整第一张图宽度
                    slide.shapes[-2].width = Inches(6.0)
                except Exception:
                    pass

        elif text and not images:
            # 纯文字布局
            add_rect(slide, 0.5, 1.25, 12.3, 5.9,
                     fill_rgb=RGBColor(0xFF, 0xFF, 0xFF))
            add_text(slide, text,
                     0.7, 1.45, 11.9, 5.5,
                     font_size=12, bold=False, color=COLOR_GRAY)

    prs.save(output_path)
    print(f"  ✓ PPT 已保存：{output_path}")
    return output_path


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(description='Market Insight 报告导出工具')
    parser.add_argument('html_path', help='HTML 报告文件路径')
    parser.add_argument('--format', choices=['pdf', 'ppt', 'all'], default='pdf',
                        help='导出格式：pdf / ppt / all（默认 pdf）')
    parser.add_argument('--output', default=None,
                        help='输出文件路径（不含扩展名），默认与 HTML 同名同目录')
    args = parser.parse_args()

    html_path = os.path.abspath(args.html_path)
    if not os.path.exists(html_path):
        print(f"[ERROR] HTML 文件不存在：{html_path}")
        sys.exit(1)

    base = args.output or str(Path(html_path).with_suffix(''))

    if args.format in ('pdf', 'all'):
        export_pdf(html_path, base + '.pdf')
    if args.format in ('ppt', 'all'):
        export_ppt(html_path, base + '.pptx')


if __name__ == '__main__':
    main()
