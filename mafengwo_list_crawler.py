from typing import Any, Dict, List, Optional, Set

from crawler_common import (
    append_jsonl,
    build_failed_record,
    clean_text,
    close_browser_page,
    create_browser_page,
    detect_block_or_login,
    extract_note_id,
    get_current_url,
    human_like_scroll,
    load_progress,
    log,
    maybe_random_sleep,
    normalize_url,
    page_signature,
    parse_count_before_word,
    parse_views_comments,
    pause_for_manual_check,
    run_js,
    save_progress,
    short_title,
    now_str,
    open_url,
)


LIST_EXTRACT_JS = r"""
return (() => {
  const regionKeyword = '山西';
  const base = 'https://www.mafengwo.cn';
  const clean = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const absUrl = (u) => {
    if (!u) return '';
    u = String(u).trim();
    if (!u || /^javascript:/i.test(u) || /^data:/i.test(u)) return '';
    if (u.startsWith('//')) return 'https:' + u;
    if (u.startsWith('/')) return base + u;
    try { return new URL(u, base + '/').href; } catch (e) { return u; }
  };
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const textBySelectors = (root, selectors) => {
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      const text = clean(el && el.innerText);
      if (text) return text;
    }
    return '';
  };
  const imgUrl = (img) => {
    if (!img) return '';
    const attrs = ['data-src', 'data-original', 'data-actualsrc', 'data-url', 'data-full', 'data-ks-lazyload', 'src'];
    for (const a of attrs) {
      const v = img.getAttribute(a);
      if (v && !/^data:/i.test(v)) return absUrl(v);
    }
    return '';
  };
  const detailLinks = (root) => Array.from(root.querySelectorAll('a[href*="/i/"]'))
    .filter(a => /\/i\/\d+\.html/.test(absUrl(a.getAttribute('href') || '')));
  const chooseTitleLink = (root) => {
    const links = detailLinks(root);
    if (!links.length) return null;
    const scored = links.map((a, idx) => {
      const title = clean(a.getAttribute('title')) || clean(a.innerText);
      return {a, idx, score: (title.length >= 4 ? 100 : 0) + Math.min(title.length, 80)};
    }).sort((x, y) => y.score - x.score || x.idx - y.idx);
    return scored[0].a;
  };
  const candidateNodes = [];
  const cardSelectors = [
    'div._j_notes_list > div',
    'div.tn-item',
    'div.feed-item',
    'div[class*="note"]',
    'div[class*="article"]'
  ];
  for (const sel of cardSelectors) {
    document.querySelectorAll(sel).forEach(el => {
      if (detailLinks(el).length && clean(el.innerText).length > 10) candidateNodes.push(el);
    });
  }
  document.querySelectorAll('a[href*="/i/"]').forEach(a => {
    let node = a;
    for (let i = 0; i < 7 && node && node !== document.body; i++) {
      if (detailLinks(node).length && clean(node.innerText).length > 20 && (node.querySelector('img') || i >= 2)) {
        candidateNodes.push(node);
        break;
      }
      node = node.parentElement;
    }
  });

  const seenUrls = new Set();
  const seenNodes = new Set();
  const records = [];
  for (const card of candidateNodes) {
    if (!card || seenNodes.has(card) || !visible(card)) continue;
    const link = chooseTitleLink(card);
    if (!link) continue;
    const url = absUrl(link.getAttribute('href'));
    if (!/\/i\/\d+\.html/.test(url) || seenUrls.has(url)) continue;
    seenUrls.add(url);
    seenNodes.add(card);

    let title = clean(link.getAttribute('title')) || clean(link.innerText);
    if (!title || title.length < 2) {
      title = textBySelectors(card, ['h2 a[href*="/i/"]', 'h3 a[href*="/i/"]', 'h2', 'h3', 'a[href*="/i/"][title]']);
    }
    const cover = imgUrl(card.querySelector('img[data-src], img[data-original], img[src]'));
    let summary = textBySelectors(card, [
      'div.tn-wrapper dl dd',
      'div[class*="summary"]',
      'div[class*="desc"]',
      'p'
    ]);
    if (summary && title && summary.includes(title)) summary = summary.replace(title, '').trim();
    if (!summary) {
      const texts = Array.from(card.querySelectorAll('p, dd, div'))
        .map(el => clean(el.innerText))
        .filter(t => t && (!title || !t.includes(title)) && !/^\d+\s*\/\s*\d+$/.test(t));
      texts.sort((a, b) => b.length - a.length);
      summary = texts[0] || '';
    }
    let author = '';
    const authorEls = Array.from(card.querySelectorAll('a[href*="/u/"], a[href*="/home/"], [class*="author"], [class*="user"], [class*="name"]'));
    for (const el of authorEls) {
      const t = clean(el.innerText);
      if (t && t.length <= 30 && !/山西|浏览|评论|顶|收藏/.test(t)) {
        author = t.replace(/^by\s*/i, '').trim();
        break;
      }
    }
    if (!author) {
      const raw = clean(card.innerText);
      const m = raw.match(/by\s+([^\s，,\/]+)\s+/i);
      if (m) author = m[1];
    }
    const rawText = clean(card.innerText);
    let dingText = textBySelectors(card, ['[class*="ding"]', '[class*="top"]', '.btn-ding', '.tn-ding']);
    if (!dingText) {
      const m = rawText.match(/(\d+(?:\.\d+)?万?)\s*顶/);
      if (m) dingText = m[0];
    }
    records.push({
      url,
      title,
      summary,
      region: rawText.includes(regionKeyword) ? regionKeyword : '',
      author_name: author,
      cover_image: cover,
      raw_text: rawText,
      ding_text: dingText
    });
  }
  return records;
})();
"""


NEXT_PAGE_JS = r"""
return (() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const candidates = Array.from(document.querySelectorAll('a, button, span'))
    .filter(el => /下一页|下一頁|Next/i.test(clean(el.innerText || el.textContent || '')));
  for (const el of candidates) {
    const cls = String(el.className || '');
    const text = clean(el.innerText || el.textContent || '');
    const disabled = el.disabled || /disabled|disable|unactive|gray|current/i.test(cls) || /没有下一页|末页/.test(text);
    if (disabled) continue;
    const href = el.href || el.getAttribute('href') || '';
    el.scrollIntoView({block: 'center', inline: 'center'});
    try { el.click(); return {clicked: true, href, text}; } catch (e) {
      if (href) { location.href = href; return {clicked: true, href, text, fallback: 'location'}; }
      return {clicked: false, error: String(e), text};
    }
  }
  return {clicked: false, error: '未找到下一页按钮'};
})();
"""


def extract_list_cards(page: Any, cfg: Dict[str, Any], list_page: int) -> List[Dict[str, Any]]:
    """解析当前列表页的游记卡片。JS 负责 DOM 候选，Python 负责字段清洗和数值解析。"""
    raw_records = run_js(page, LIST_EXTRACT_JS, default=[]) or []
    records: List[Dict[str, Any]] = []
    region_keyword = cfg.get("site", {}).get("region_keyword", "山西")
    for idx, raw in enumerate(raw_records, start=1):
        url = normalize_url(raw.get("url", ""))
        note_id = extract_note_id(url)
        if not note_id:
            continue
        raw_text = clean_text(raw.get("raw_text", ""))
        views, comments = parse_views_comments(raw_text)
        ding_count = parse_count_before_word(raw.get("ding_text", "") or raw_text, "顶")
        records.append(
            {
                "note_id": note_id,
                "url": url,
                "title": clean_text(raw.get("title", "")),
                "summary": clean_text(raw.get("summary", "")),
                "region": clean_text(raw.get("region", "")) or region_keyword,
                "author_name": clean_text(raw.get("author_name", "")),
                "views": views,
                "comments": comments,
                "ding_count": ding_count,
                "cover_image": normalize_url(raw.get("cover_image", "")),
                "list_page": list_page,
                "rank_in_page": idx,
                "crawl_time": now_str(),
            }
        )
    return records


def click_next_page(page: Any, cfg: Dict[str, Any], before_signature: str) -> bool:
    """点击下一页，并确认页面首批游记发生变化，防止死循环。"""
    retry_times = int(cfg.get("crawl", {}).get("retry_times", 3))
    timeout = int(cfg.get("browser", {}).get("page_load_timeout", 60))
    for attempt in range(1, retry_times + 1):
        log(f"🔍 尝试点击下一页...（第 {attempt}/{retry_times} 次）")
        maybe_random_sleep(cfg, "page_pause_min", "page_pause_max", "翻页前")
        result = run_js(page, NEXT_PAGE_JS, default={}) or {}
        if not result.get("clicked"):
            log(f"⚠️ 下一页点击失败：{result.get('error', '未知错误')}")
            return False
        stable_rounds = max(1, timeout // 3)
        for _ in range(stable_rounds):
            time_sleep = 3
            import time

            time.sleep(time_sleep)
            changed_records = extract_list_cards(page, cfg, list_page=0)
            new_signature = page_signature(changed_records)
            if new_signature and new_signature != before_signature:
                log("✅ 下一页加载成功")
                return True
        log("⚠️ 点击后页面内容未变化，准备重试")
    return False


def crawl_list(cfg: Dict[str, Any], manual: bool = False, headless: Optional[bool] = None) -> None:
    page = None
    progress = load_progress(cfg)
    output = cfg["output"]
    crawl_cfg = cfg.get("crawl", {})
    max_pages = int(crawl_cfg.get("max_pages", 233))
    max_notes = int(crawl_cfg.get("max_notes", 2794))
    finished_ids: Set[str] = set(progress["list"].get("finished_note_ids") or [])
    written_count = 0
    no_change_count = 0
    list_page = max(int(crawl_cfg.get("start_page", 1)), int(progress["list"].get("last_finished_page", 0)) + 1)

    try:
        page = create_browser_page(cfg, headless=False if manual else headless)
        start_url = (
            cfg.get("site", {}).get("start_url")
            or (progress["list"].get("current_url") if not manual else "")
            or cfg.get("site", {}).get("home_url")
            or "https://www.mafengwo.cn/"
        )
        log(f"🌐 打开马蜂窝列表页：{start_url}")
        open_url(page, start_url, timeout=int(cfg.get("browser", {}).get("page_load_timeout", 60)))
        reason = detect_block_or_login(page)
        if reason:
            pause_for_manual_check(page, reason)
        if manual:
            log("请在浏览器中手动切换到“热门游记”和地区“山西”，确认当前页是目标列表页后按回车。")
            input()
            reason = detect_block_or_login(page)
            if reason:
                pause_for_manual_check(page, reason)
            log(f"✅ 当前筛选地区：{cfg.get('site', {}).get('region_keyword', '山西')}")

        while list_page <= max_pages:
            log(f"📄 开始解析第 {list_page} 页")
            reason = detect_block_or_login(page)
            if reason:
                pause_for_manual_check(page, reason)
            if cfg.get("anti_ban", {}).get("human_like_scroll", True):
                human_like_scroll(page, cfg, max_rounds=8)

            records = extract_list_cards(page, cfg, list_page=list_page)
            signature = page_signature(records)
            if not records:
                failed = build_failed_record("", get_current_url(page), "list", "列表为空", "当前页未解析到游记卡片")
                append_jsonl(output["failed_file"], failed)
                log("⚠️ 当前页未解析到游记卡片，已记录 failed_urls.jsonl")
                if manual:
                    log("请检查筛选页面是否正确，处理后按回车重试当前页。")
                    input()
                    continue
                break

            if signature and signature == progress["list"].get("last_page_signature"):
                no_change_count += 1
                log(f"⚠️ 页面内容与上一页相同，连续 {no_change_count} 次")
            else:
                no_change_count = 0

            page_new_count = 0
            for rec in records:
                note_id = rec["note_id"]
                if note_id in finished_ids:
                    continue
                append_jsonl(output["list_jsonl"], rec)
                finished_ids.add(note_id)
                page_new_count += 1
                written_count += 1
                progress["list"]["finished_note_ids"] = sorted(finished_ids)
                save_progress(cfg, progress)
                log(f"✅ 列表记录写入：{note_id} {short_title(rec.get('title', ''))}")
                if max_notes and len(finished_ids) >= max_notes:
                    log(f"✅ 已达到 max_notes={max_notes}，停止列表爬取")
                    return

            progress["list"]["last_finished_page"] = list_page
            progress["list"]["current_url"] = get_current_url(page)
            progress["list"]["last_page_signature"] = signature
            progress["list"]["finished_note_ids"] = sorted(finished_ids)
            save_progress(cfg, progress)
            log(f"✅ 第 {list_page} 页完成，新写入 {page_new_count} 条，累计列表去重 {len(finished_ids)} 条")

            if cfg.get("crawl", {}).get("stop_when_no_change", True) and no_change_count >= 2:
                log("⚠️ 连续多页内容无变化，停止列表爬取以避免死循环")
                break
            if list_page >= max_pages:
                log("✅ 已达到 max_pages，列表阶段结束")
                break
            if not click_next_page(page, cfg, signature):
                failed = build_failed_record("", get_current_url(page), "list", "下一页点击失败", "点击或加载下一页失败")
                append_jsonl(output["failed_file"], failed)
                log("⚠️ 下一页失败，列表阶段停止")
                break
            list_page += 1
        log(f"✅ 列表阶段结束，本次写入 {written_count} 条")
    except KeyboardInterrupt:
        log("⚠️ 用户中断，已保留当前已写入数据和进度")
        raise
    except Exception as e:
        failed = build_failed_record("", get_current_url(page) if page else "", "list", type(e).__name__, str(e))
        append_jsonl(output["failed_file"], failed)
        log(f"❌ 列表阶段异常：{e}")
        raise
    finally:
        close_browser_page(page)

