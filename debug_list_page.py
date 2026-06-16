import argparse
import json
import sys

from crawler_common import (
    close_browser_page,
    create_browser_page,
    detect_block_or_login,
    load_config,
    log,
    open_url,
    pause_for_manual_check,
    resolve_path,
    save_debug_json,
)
from mafengwo_list_crawler import extract_list_cards


def configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="调试当前马蜂窝列表页解析")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--url", default="", help="可选，直接打开指定列表 URL")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-headless", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    headless = None
    if args.headless:
        headless = True
    elif args.no_headless:
        headless = False

    page = None
    try:
        page = create_browser_page(cfg, headless=False if headless is None else headless)
        start_url = args.url or cfg.get("site", {}).get("start_url") or cfg.get("site", {}).get("home_url", "https://www.mafengwo.cn/")
        open_url(page, start_url, timeout=int(cfg.get("browser", {}).get("page_load_timeout", 60)))
        reason = detect_block_or_login(page)
        if reason:
            pause_for_manual_check(page, reason)
        log("请手动筛选到“热门游记 + 山西”列表页，确认后按回车开始解析当前页。")
        input()
        records = extract_list_cards(page, cfg, list_page=1)
        for rec in records:
            log(
                f"卡片：{rec.get('title', '')} | {rec.get('url', '')} | "
                f"作者={rec.get('author_name', '')} | 浏览={rec.get('views', 0)} | 顶={rec.get('ding_count', 0)}"
            )
        out_path = "./data/debug/debug_list_page.json"
        save_debug_json(out_path, {"records": records})
        log(f"✅ 共解析 {len(records)} 条，结果已保存：{resolve_path(out_path)}")
    finally:
        close_browser_page(page)


if __name__ == "__main__":
    main()

