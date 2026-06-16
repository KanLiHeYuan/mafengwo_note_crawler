import argparse
import sys
from typing import Optional

from crawler_common import close_browser_page, create_browser_page, load_config, log, open_url, reset_progress
from mafengwo_list_crawler import crawl_list
from mafengwo_note_detail_crawler import crawl_detail


def configure_stdout() -> None:
    """Windows 终端和 nohup 下尽量使用 UTF-8 输出中文日志。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def resolve_headless(args: argparse.Namespace) -> Optional[bool]:
    if args.headless:
        return True
    if args.no_headless:
        return False
    return None


def manual_login(cfg_path: str) -> None:
    cfg = load_config(cfg_path)
    page = None
    try:
        page = create_browser_page(cfg, headless=False)
        open_url(page, cfg.get("site", {}).get("home_url", "https://www.mafengwo.cn/"), timeout=60)
        log("请在浏览器中手动登录马蜂窝。登录完成并确认状态正常后，回到终端按回车退出。")
        input()
        log("✅ 手动登录流程结束，登录状态已保存在 profiles/mafengwo_profile")
    finally:
        close_browser_page(page)


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="马蜂窝山西游记爬虫")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--mode", choices=["list", "detail", "all"], default="all", help="运行阶段")
    parser.add_argument("--manual", action="store_true", help="列表阶段启用非 headless 手动筛选")
    parser.add_argument("--reset", action="store_true", help="重置对应阶段进度，不删除已有数据文件")
    parser.add_argument("--retry-failed", action="store_true", help="详情阶段只重试 failed_urls.jsonl 中失败的 URL")
    parser.add_argument("--headless", action="store_true", help="覆盖配置，强制 headless")
    parser.add_argument("--no-headless", action="store_true", help="覆盖配置，强制非 headless")
    parser.add_argument("--manual-login-only", action="store_true", help="只打开浏览器进行手动登录并保存 profile")
    args = parser.parse_args()

    if args.manual_login_only:
        manual_login(args.config)
        return

    cfg = load_config(args.config)
    headless = resolve_headless(args)

    if args.reset:
        stage = args.mode
        reset_progress(cfg, stage)
        log(f"✅ 已重置 {stage} 阶段进度。已有 JSONL/CSV 未删除，继续运行会自动去重。")

    if args.mode in {"list", "all"}:
        crawl_list(cfg, manual=args.manual, headless=headless)
    if args.mode in {"detail", "all"}:
        crawl_detail(cfg, retry_failed=args.retry_failed, headless=headless)


if __name__ == "__main__":
    main()

