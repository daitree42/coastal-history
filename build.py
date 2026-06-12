#!/usr/bin/env python3
"""
沿海岸线的中国历史 · 静态站点生成器
从 /cities/ 下的 Markdown 文件生成课程网站到 _site/
"""

import os
import re
import json
import yaml
import shutil
import markdown
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

# ── 路径 ──
ROOT = Path(__file__).parent
CITIES_DIR = ROOT / "cities"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "_site"

# ── 站点配置 ──
with open(ROOT / "_config.yml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

SITE_TITLE = config["title"]
SITE_SUBTITLE = config["subtitle"]
SITE_DESCRIPTION = config["description"]
SITE_URL = config["base_url"]
# 从 base_url 提取子路径前缀，如 "/coastal-history"
from urllib.parse import urlparse
SITE_PREFIX = urlparse(SITE_URL).path.rstrip("/") or ""
CITY_ORDER = {c["slug"]: c["order"] for c in config["cities"]}
CITY_NAMES = {c["slug"]: c["name"] for c in config["cities"]}

# ── Markdown ──
MD = markdown.Markdown(extensions=[
    "extra",
    "codehilite",
    "toc",
    "sane_lists",
])
# frontmatter 分隔符
FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def parse_md(filepath: Path) -> tuple[dict, str]:
    """解析 Markdown 文件，返回 (frontmatter_dict, body_html)"""
    text = filepath.read_text(encoding="utf-8")
    m = FM_PATTERN.match(text)
    if not m:
        return {}, MD.convert(text)
    frontmatter = yaml.safe_load(m.group(1)) or {}
    body = text[m.end():].strip()
    html = MD.convert(body)
    MD.reset()
    return frontmatter, html


def load_cities() -> list[dict]:
    """加载所有城市数据"""
    cities = []
    for slug in sorted(CITY_ORDER, key=lambda s: CITY_ORDER[s]):
        city_dir = CITIES_DIR / slug
        index_file = city_dir / "_index.md"
        if not index_file.exists():
            continue
        fm, html = parse_md(index_file)

        # 加载章节
        chapters = []
        for ch_file in sorted(city_dir.glob("[0-9]*.md")):
            ch_fm, ch_html = parse_md(ch_file)
            ch_num = int(ch_fm.get("chapter", 0))
            chapters.append({
                "number": ch_num,
                "title": ch_fm.get("title", ch_file.stem),
                "slug": ch_file.stem,
                "url": f"/cities/{slug}/{ch_file.stem}/",
                "body_html": ch_html,
                "status": ch_fm.get("status", "outline"),
                "main_character": ch_fm.get("main_character", ""),
                "time_period": ch_fm.get("time_period", ""),
                "frontmatter": ch_fm,
            })

        # 提取关键词
        tags_raw = fm.get("keywords", fm.get("tags", ""))
        if isinstance(tags_raw, str):
            tags = [t.strip().lstrip("#") for t in tags_raw.replace("，", ",").split(",") if t.strip()]
        else:
            tags = tags_raw or []

        city = {
            "slug": slug,
            "name": CITY_NAMES.get(slug, slug),
            "order": CITY_ORDER.get(slug, 99),
            "title": fm.get("title", f"第{CITY_ORDER.get(slug)}站：{CITY_NAMES.get(slug, slug)}"),
            "theme": fm.get("theme", ""),
            "emoji": fm.get("emoji", "📍"),
            "main_character": fm.get("main_character", ""),
            "time_period": fm.get("time_period", ""),
            "latitude": fm.get("latitude"),
            "longitude": fm.get("longitude"),
            "tags": tags,
            "body_html": html,
            "chapters": chapters,
            "total_chapters": len(chapters),
            "url": f"/cities/{slug}/",
            "status": fm.get("status", "outline"),
        }
        cities.append(city)

    return cities


def build():
    """构建整个站点"""
    # 准备输出目录
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # 复制静态文件
    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, OUTPUT_DIR / "static", dirs_exist_ok=True)

    # 加载模板
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    # 加载数据
    cities = load_cities()

    ctx = {
        "site_title": SITE_TITLE,
        "site_subtitle": SITE_SUBTITLE,
        "site_description": SITE_DESCRIPTION,
        "site_url": SITE_URL,
        "prefix": SITE_PREFIX,
        "cities": cities,
        "year": datetime.now().year,
    }

    # ── 首页 ──
    index_html = env.get_template("index.html").render(**ctx)
    (OUTPUT_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print(f"  ✓ 首页")

    # ── 城市页面 ──
    for city in cities:
        city_dir = OUTPUT_DIR / "cities" / city["slug"]
        city_dir.mkdir(parents=True, exist_ok=True)

        html = env.get_template("city.html").render(city=city, **ctx)
        (city_dir / "index.html").write_text(html, encoding="utf-8")

        # 各章节页面
        for ch in city["chapters"]:
            ch_dir = city_dir / ch["slug"]
            ch_dir.mkdir(parents=True, exist_ok=True)

            # 上下章导航
            prev_ch = None
            next_ch = None
            for i, c in enumerate(city["chapters"]):
                if c["slug"] == ch["slug"]:
                    if i > 0:
                        prev_ch = city["chapters"][i - 1]
                    if i < len(city["chapters"]) - 1:
                        next_ch = city["chapters"][i + 1]
                    break

            html = env.get_template("chapter.html").render(
                city=city,
                chapter=ch,
                prev_chapter=prev_ch,
                next_chapter=next_ch,
                **ctx,
            )
            (ch_dir / "index.html").write_text(html, encoding="utf-8")

        print(f"  ✓ {city['name']}（{city['total_chapters']}章）")

    # ── 关于页 ──
    about_file = ROOT / "about.md"
    if about_file.exists():
        fm, about_html = parse_md(about_file)
        html = env.get_template("page.html").render(
            page_title=fm.get("title", "关于"),
            page_body=about_html,
            **ctx,
        )
        (OUTPUT_DIR / "about" / "index.html").parent.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "about" / "index.html").write_text(html, encoding="utf-8")
        print(f"  ✓ 关于")

    # ── 搜索索引 ──
    search_index = []
    for city in cities:
        for ch in city["chapters"]:
            plain = re.sub(r"<[^>]+>", "", ch["body_html"]).strip()
            excerpt = plain[:150].replace("\n", " ")
            search_index.append({
                "title": ch["title"],
                "city": city["name"],
                "url": f"cities/{city['slug']}/{ch['slug']}/",
                "chapter": ch["number"],
                "status": ch["status"],
                "excerpt": excerpt,
            })
    (OUTPUT_DIR / "search.json").write_text(
        json.dumps(search_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n✓ 构建完成：{len(cities)} 个城市，{sum(c['total_chapters'] for c in cities)} 章 → {OUTPUT_DIR}")


def serve(port: int = 8000):
    """本地预览服务器"""
    import http.server
    import socketserver

    os.chdir(str(OUTPUT_DIR))

    class Handler(http.server.SimpleHTTPRequestHandler):
        pass

    with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
        url = f"http://localhost:{port}/"
        print(f"✓ 预览服务器：{url}")
        print(f"  Ctrl+C 停止\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("  服务器已停止")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="沿海历史课程站点生成器")
    parser.add_argument("--serve", action="store_true", help="启动本地预览服务器")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    build()
    if args.serve:
        serve(args.port)
