import argparse
import json
import sys

from crawler_common import (
    close_browser_page,
    create_browser_page,
    detect_block_or_login,
    extract_note_id,
    load_config,
    log,
    open_url,
    pause_for_manual_check,
    resolve_path,
    save_debug_json,
)
from mafengwo_note_detail_crawler import parse_detail_page


def configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="调试单篇马蜂窝游记详情解析")
    parser.add_argument("--url", required=True, help="游记详情 URL，例如 https://www.mafengwo.cn/i/24846178.html")
    parser.add_argument("--config", default="config.yaml")
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
        page = create_browser_page(cfg, headless=headless)
        open_url(page, args.url, timeout=int(cfg.get("browser", {}).get("page_load_timeout", 60)))
        reason = detect_block_or_login(page)
        if reason:
            pause_for_manual_check(page, reason)
        record = parse_detail_page(page, cfg, source={"url": args.url, "note_id": extract_note_id(args.url)}, strict=False)
        note_id = record.get("note_id") or extract_note_id(args.url) or "unknown"
        out_path = f"./data/debug/debug_note_{note_id}.json"
        save_debug_json(out_path, record)

        log(f"标题：{record.get('title', '')}")
        log(f"作者：{record.get('author_name', '')} {record.get('author_level', '')}")
        log(f"发布时间：{record.get('publish_time', '')}")
        log(
            "行程信息："
            f"出发时间={record.get('departure_date', '')}，"
            f"出行天数={record.get('travel_days', '')}，"
            f"人物={record.get('people_type', '')}，"
            f"费用={record.get('avg_cost', '')}"
        )
        log("正文前 500 字：")
        print(record.get("full_text", "")[:500], flush=True)
        log("前 10 张图片 URL：")
        print(json.dumps(record.get("image_urls", [])[:10], ensure_ascii=False, indent=2), flush=True)
        log(f"✅ 调试结果已保存：{resolve_path(out_path)}")
    finally:
        close_browser_page(page)


if __name__ == "__main__":
    main()
