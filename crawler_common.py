import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
import yaml


PROJECT_ROOT = Path(__file__).resolve().parent
MFW_HOME = "https://www.mafengwo.cn"


def resolve_path(path: str) -> Path:
    """把配置中的相对路径解析到项目根目录，保证 Windows/Linux 行为一致。"""
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    """统一日志函数：实时输出并 flush，适合 nohup tail -f 查看。"""
    print(f"[{now_str()}] {message}", flush=True)


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    path = resolve_path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    ensure_output_dirs(cfg)
    return cfg


def ensure_output_dirs(cfg: Dict[str, Any]) -> None:
    output = cfg.get("output", {})
    browser = cfg.get("browser", {})
    for key in ["data_dir", "media_dir"]:
        if output.get(key):
            resolve_path(output[key]).mkdir(parents=True, exist_ok=True)
    if output.get("data_dir"):
        (resolve_path(output["data_dir"]) / "logs").mkdir(parents=True, exist_ok=True)
        (resolve_path(output["data_dir"]) / "debug").mkdir(parents=True, exist_ok=True)
    if browser.get("user_data_path"):
        resolve_path(browser["user_data_path"]).mkdir(parents=True, exist_ok=True)


def clean_text(text: Any) -> str:
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\u00a0", " ").replace("\u3000", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def should_drop_article_text(text: str) -> bool:
    """过滤明显不是正文的短噪声，避免把评论操作词混进 full_text。"""
    s = clean_text(text)
    if not s:
        return True
    if s in {"举报", "回复", "评论", "赞", "收藏", "分享", "展开", "收起", "加载更多"}:
        return True
    if re.fullmatch(r"[|/\\\-_=·•。.，,\s]+", s):
        return True
    return False


def normalize_url(url: Any, base: str = MFW_HOME) -> str:
    if not url:
        return ""
    s = str(url).strip()
    if not s or s.lower().startswith(("javascript:", "data:")):
        return ""
    if s.startswith("//"):
        return "https:" + s
    if s.startswith("/"):
        return urljoin(base, s)
    if not re.match(r"^https?://", s, re.I):
        return urljoin(base + "/", s)
    return s


def extract_note_id(url: str) -> str:
    m = re.search(r"/i/(\d+)\.html", url or "")
    return m.group(1) if m else ""


def parse_num(value: Any) -> int:
    """解析 5、5,871、1.2万 等数字文本。解析失败返回 0。"""
    if value is None:
        return 0
    s = str(value).strip()
    if not s:
        return 0
    s = s.replace(",", "").replace("，", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*万", s)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if m:
        return int(float(m.group(1)))
    return 0


def parse_views_comments(text: str) -> Tuple[int, int]:
    s = clean_text(text)
    matches = re.findall(r"(\d+(?:\.\d+)?\s*万?|\d[\d,]*)\s*/\s*(\d+(?:\.\d+)?\s*万?|\d[\d,]*)", s)
    if not matches:
        return 0, 0
    views, comments = matches[0]
    return parse_num(views), parse_num(comments)


def parse_count_before_word(text: str, word: str) -> int:
    s = clean_text(text)
    patterns = [
        rf"(\d+(?:\.\d+)?\s*万?|\d[\d,]*)\s*{re.escape(word)}",
        rf"{re.escape(word)}\s*(\d+(?:\.\d+)?\s*万?|\d[\d,]*)",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return parse_num(m.group(1))
    return 0


def safe_json_loads(line: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    p = resolve_path(path)
    if not p.exists():
        return []
    records: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = safe_json_loads(line)
            if obj is not None:
                records.append(obj)
    return records


def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    """逐条写 JSONL 并 fsync，优先保证中断时不丢数据。"""
    p = resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def write_json(path: str, data: Dict[str, Any]) -> None:
    """原子写 JSON，避免进度文件写一半损坏。"""
    p = resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def default_progress() -> Dict[str, Any]:
    return {
        "list": {
            "last_finished_page": 0,
            "finished_note_ids": [],
            "current_url": "",
            "last_page_signature": "",
        },
        "detail": {
            "finished_note_ids": [],
            "failed_note_ids": [],
            "last_finished_note_id": "",
        },
    }


def load_progress(cfg: Dict[str, Any]) -> Dict[str, Any]:
    path = cfg["output"]["progress_file"]
    p = resolve_path(path)
    progress = default_progress()
    if p.exists():
        try:
            with p.open("r", encoding="utf-8") as f:
                old = json.load(f)
            for stage in progress:
                if isinstance(old.get(stage), dict):
                    progress[stage].update(old[stage])
        except Exception as e:
            log(f"⚠️ progress.json 读取失败，将使用默认进度：{e}")
    progress["list"]["finished_note_ids"] = sorted(
        set(progress["list"].get("finished_note_ids") or []) | collect_note_ids(cfg["output"]["list_jsonl"])
    )
    progress["detail"]["finished_note_ids"] = sorted(
        set(progress["detail"].get("finished_note_ids") or []) | collect_success_detail_ids(cfg["output"]["detail_jsonl"])
    )
    return progress


def save_progress(cfg: Dict[str, Any], progress: Dict[str, Any]) -> None:
    write_json(cfg["output"]["progress_file"], progress)


def reset_progress(cfg: Dict[str, Any], stage: str) -> None:
    progress = load_progress(cfg)
    base = default_progress()
    if stage in {"list", "all"}:
        progress["list"] = base["list"]
    if stage in {"detail", "all"}:
        progress["detail"] = base["detail"]
    save_progress(cfg, progress)


def collect_note_ids(jsonl_path: str) -> Set[str]:
    ids: Set[str] = set()
    for rec in read_jsonl(jsonl_path):
        note_id = rec.get("note_id") or extract_note_id(rec.get("url", ""))
        if note_id:
            ids.add(str(note_id))
    return ids


def collect_success_detail_ids(jsonl_path: str) -> Set[str]:
    ids: Set[str] = set()
    for rec in read_jsonl(jsonl_path):
        if rec.get("status") == "success":
            note_id = rec.get("note_id") or extract_note_id(rec.get("url", ""))
            if note_id:
                ids.add(str(note_id))
    return ids


def collect_failed_detail_ids(jsonl_path: str) -> Set[str]:
    ids: Set[str] = set()
    for rec in read_jsonl(jsonl_path):
        note_id = rec.get("note_id") or extract_note_id(rec.get("url", ""))
        if note_id:
            ids.add(str(note_id))
    return ids


DETAIL_CSV_FIELDS = [
    "note_id",
    "url",
    "title",
    "author_name",
    "publish_time",
    "views",
    "comments",
    "destination",
    "departure_date",
    "travel_days",
    "people_type",
    "avg_cost",
    "image_count",
    "video_count",
    "word_count",
    "full_text",
]


def append_detail_csv(path: str, record: Dict[str, Any]) -> None:
    p = resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    exists = p.exists() and p.stat().st_size > 0
    with p.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DETAIL_CSV_FIELDS)
        if not exists:
            writer.writeheader()
        row = {field: record.get(field, "") for field in DETAIL_CSV_FIELDS}
        writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())


def random_sleep(min_seconds: float, max_seconds: float, reason: str = "") -> None:
    seconds = random.uniform(float(min_seconds), float(max_seconds))
    if reason:
        log(f"⏳ {reason}等待 {seconds:.1f} 秒")
    time.sleep(seconds)


def maybe_random_sleep(cfg: Dict[str, Any], min_key: str, max_key: str, reason: str = "") -> None:
    if not cfg.get("anti_ban", {}).get("enable_random_delay", True):
        return
    crawl = cfg.get("crawl", {})
    random_sleep(crawl.get(min_key, 1), crawl.get(max_key, 3), reason)


def short_title(title: str, max_len: int = 36) -> str:
    s = clean_text(title)
    return s if len(s) <= max_len else s[:max_len] + "..."


def page_signature(records: Sequence[Dict[str, Any]]) -> str:
    text = "|".join([str(r.get("note_id") or r.get("url") or r.get("title")) for r in records[:5]])
    return hashlib.md5(text.encode("utf-8")).hexdigest() if text else ""


def build_failed_record(note_id: str, url: str, stage: str, error_type: str, error: str) -> Dict[str, Any]:
    return {
        "note_id": note_id,
        "url": url,
        "stage": stage,
        "error_type": error_type,
        "error": str(error),
        "crawl_time": now_str(),
    }


def download_file(url: str, out_dir: str, prefix: str = "") -> str:
    """可选媒体下载。默认配置关闭，开启时只按 URL 顺序慢速下载。"""
    real_url = normalize_url(url)
    if not real_url:
        return ""
    out = resolve_path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    suffix = Path(urlparse(real_url).path).suffix or ".bin"
    name = hashlib.md5(real_url.encode("utf-8")).hexdigest() + suffix
    if prefix:
        name = prefix + "_" + name
    target = out / name
    if target.exists() and target.stat().st_size > 0:
        return str(target)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari/537.36",
        "Referer": MFW_HOME + "/",
    }
    with requests.get(real_url, headers=headers, timeout=60, stream=True) as resp:
        resp.raise_for_status()
        with target.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)
    return str(target)


def create_browser_page(cfg: Dict[str, Any], headless: Optional[bool] = None):
    """创建 DrissionPage ChromiumPage，复用固定 user_data_path 保存登录状态。"""
    try:
        from DrissionPage import ChromiumOptions, ChromiumPage
    except Exception as e:
        raise RuntimeError("未安装 DrissionPage，请先执行：pip install -r requirements.txt") from e

    browser_cfg = cfg.get("browser", {})
    user_data_path = str(resolve_path(browser_cfg.get("user_data_path", "./profiles/mafengwo_profile")))
    width = int(browser_cfg.get("window_width", 1400))
    height = int(browser_cfg.get("window_height", 900))
    use_headless = browser_cfg.get("headless", False) if headless is None else headless

    co = ChromiumOptions()
    # DrissionPage 不同小版本 API 略有差异，这里用多种写法兜底。
    try:
        co.set_user_data_path(user_data_path)
    except Exception:
        try:
            co.set_paths(user_data_path=user_data_path)
        except Exception:
            pass
    for arg in [
        f"--window-size={width},{height}",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--lang=zh-CN",
    ]:
        try:
            co.set_argument(arg)
        except Exception:
            pass
    if use_headless:
        try:
            co.headless(True)
        except Exception:
            try:
                co.set_argument("--headless=new")
            except Exception:
                pass
    page = ChromiumPage(co)
    try:
        page.set.window.size(width, height)
    except Exception:
        pass
    return page


def close_browser_page(page: Any) -> None:
    if page is None:
        return
    for method in ("quit", "close"):
        try:
            fn = getattr(page, method, None)
            if callable(fn):
                fn()
                return
        except Exception:
            continue


def open_url(page: Any, url: str, timeout: int = 60) -> None:
    log(f"🌐 打开页面：{url}")
    last_error: Optional[Exception] = None
    for kwargs in ({"timeout": timeout, "retry": 2, "interval": 2}, {"timeout": timeout}, {}):
        try:
            page.get(url, **kwargs)
            wait_document_ready(page, timeout=timeout)
            return
        except TypeError:
            continue
        except Exception as e:
            last_error = e
            time.sleep(2)
    if last_error:
        raise last_error
    page.get(url)
    wait_document_ready(page, timeout=timeout)


def wait_document_ready(page: Any, timeout: int = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            state = page.run_js("return document.readyState")
            if state in {"interactive", "complete"}:
                return
        except Exception:
            pass
        time.sleep(0.5)


def get_current_url(page: Any) -> str:
    try:
        return str(page.url)
    except Exception:
        try:
            return str(page.run_js("return location.href"))
        except Exception:
            return ""


def detect_block_or_login(page: Any) -> str:
    """检测登录、验证码、安全校验等情况；不绕过，只提示人工处理。"""
    try:
        url = get_current_url(page)
        text = clean_text(page.run_js("return document.body ? document.body.innerText.slice(0, 3000) : ''"))
    except Exception as e:
        return f"页面状态读取失败：{e}"
    if re.search(r"(passport|login|sso|verify|captcha)", url, re.I):
        return f"疑似登录/校验页面：{url}"
    keywords = ["验证码", "安全验证", "访问异常", "滑块", "拖动", "过于频繁", "请登录后", "账号登录"]
    for kw in keywords:
        if kw in text:
            return f"页面出现“{kw}”，需要人工处理"
    return ""


def pause_for_manual_check(page: Any, reason: str) -> None:
    log(f"⚠️ {reason}")
    log("请在浏览器中手动完成登录/验证码/安全校验，完成后回到终端按回车继续。")
    input()
    wait_document_ready(page, timeout=30)


def run_js(page: Any, js: str, default: Any = None) -> Any:
    try:
        value = page.run_js(js)
        return default if value is None else value
    except Exception as e:
        log(f"⚠️ JS 执行失败：{e}")
        return default


def human_like_scroll(page: Any, cfg: Dict[str, Any], max_rounds: int = 80) -> None:
    """慢速滚动页面，触发懒加载并模拟正常阅读。"""
    if not cfg.get("anti_ban", {}).get("human_like_scroll", True):
        return
    crawl = cfg.get("crawl", {})
    pause_min = float(crawl.get("scroll_pause_min", 2))
    pause_max = float(crawl.get("scroll_pause_max", 5))
    last_y = -1
    same_count = 0
    for _ in range(max_rounds):
        y = run_js(page, "return window.scrollY || document.documentElement.scrollTop || 0", 0)
        height = run_js(
            page,
            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)",
            0,
        )
        viewport = run_js(page, "return window.innerHeight || document.documentElement.clientHeight", 800)
        if height and y + viewport >= height - 10:
            break
        step = max(360, int(float(viewport or 800) * random.uniform(0.55, 0.9)))
        run_js(page, f"window.scrollBy(0, {step}); return true;", True)
        time.sleep(random.uniform(pause_min, pause_max))
        if y == last_y:
            same_count += 1
            if same_count >= 3:
                break
        else:
            same_count = 0
        last_y = y


def simulate_reading_by_word_count(page: Any, cfg: Dict[str, Any], word_count: int) -> None:
    anti = cfg.get("anti_ban", {})
    if not anti.get("detail_reading_simulation", True) or word_count <= 0:
        return
    min_per = float(anti.get("min_read_seconds_per_1000_chars", 8))
    max_per = float(anti.get("max_read_seconds_per_1000_chars", 20))
    seconds = (word_count / 1000.0) * random.uniform(min_per, max_per)
    seconds = min(max(seconds, 0), 180)
    if seconds > 1:
        log(f"⏳ 根据正文长度模拟阅读 {seconds:.1f} 秒")
        time.sleep(seconds)


def save_debug_json(path: str, data: Dict[str, Any]) -> None:
    p = resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

