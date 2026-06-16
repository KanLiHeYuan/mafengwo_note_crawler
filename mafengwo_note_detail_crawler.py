from typing import Any, Dict, List, Optional, Set

from crawler_common import (
    append_detail_csv,
    append_jsonl,
    build_failed_record,
    clean_text,
    close_browser_page,
    collect_failed_detail_ids,
    collect_success_detail_ids,
    create_browser_page,
    detect_block_or_login,
    download_file,
    extract_note_id,
    get_current_url,
    human_like_scroll,
    load_progress,
    log,
    maybe_random_sleep,
    normalize_url,
    now_str,
    open_url,
    parse_count_before_word,
    parse_num,
    parse_views_comments,
    pause_for_manual_check,
    read_jsonl,
    run_js,
    save_progress,
    short_title,
    simulate_reading_by_word_count,
)


DETAIL_EXTRACT_JS = r"""
return (() => {
  const base = 'https://www.mafengwo.cn';
  const regionKeyword = '山西';
  const clean = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\u3000/g, ' ').replace(/[ \t\r\f\v]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
  const oneLine = (s) => clean(s).replace(/\n+/g, ' ');
  const absUrl = (u) => {
    if (!u) return '';
    u = String(u).trim();
    if (!u || /^javascript:/i.test(u) || /^data:/i.test(u)) return '';
    if (u.startsWith('//')) return 'https:' + u;
    if (u.startsWith('/')) return base + u;
    try { return new URL(u, base + '/').href; } catch (e) { return u; }
  };
  const textBySelectors = (selectors, root = document) => {
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      const text = clean(el && el.innerText);
      if (text) return text;
    }
    return '';
  };
  const attrBySelectors = (selectors, attrs, root = document) => {
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      if (!el) continue;
      for (const a of attrs) {
        const v = el.getAttribute(a);
        if (v) return v;
      }
    }
    return '';
  };
  const bodyText = clean(document.body ? document.body.innerText : '');
  const title = textBySelectors(['h1', '.view_title', '.note_title', 'div[class*="title"] h1', 'title']);

  let author = textBySelectors([
    '.view_info a[href*="/u/"]',
    '.view_info a[href*="/home/"]',
    'a[href*="/u/"]',
    '.author',
    '.name',
    '.user_name'
  ]);
  author = author.replace(/\s*LV\.?\s*\d+.*/i, '').replace(/\s*\+关注.*/i, '').trim();
  const levelMatch = bodyText.match(/LV\.?\s*\d+/i);
  const publishMatch = bodyText.match(/20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}/);

  const schedule = {departure_date: '', travel_days: '', people_type: '', avg_cost: ''};
  const dir = document.querySelector('div.travel_directory._j_exscheduleinfo, div.travel_directory, div.travel_dir_list.clearfix');
  const valueAfterSlash = (text, labels) => {
    let t = oneLine(text);
    t = t.replace(/^[^/／]*[\/／]\s*/, '');
    for (const label of labels) t = t.replace(new RegExp(label, 'g'), '');
    return oneLine(t);
  };
  if (dir) {
    const time = dir.querySelector('li.time');
    const day = dir.querySelector('li.day');
    const people = dir.querySelector('li.people');
    const cost = dir.querySelector('li.cost');
    if (time) schedule.departure_date = valueAfterSlash(time.innerText, ['出发时间']);
    if (day) schedule.travel_days = valueAfterSlash(day.innerText, ['出行天数']);
    if (people) schedule.people_type = valueAfterSlash(people.innerText, ['人物']);
    if (cost) schedule.avg_cost = valueAfterSlash(cost.innerText, ['人均费用', '费用']);
    if (!schedule.departure_date) {
      const m = clean(dir.innerText).match(/出发时间\s*[\/／]?\s*(20\d{2}-\d{1,2}-\d{1,2})/);
      if (m) schedule.departure_date = m[1];
    }
  }

  const article = document.querySelector('div.va_con._j_master_content, div.vc_article div.va_con, div._j_master_content, div.vc_article');
  const blocks = [];
  const imageUrls = [];
  const videoUrls = [];
  const seenImages = new Set();
  const seenVideos = new Set();
  const dropText = (s) => {
    const t = oneLine(s);
    if (!t) return true;
    if (/^(举报|回复|评论|赞|收藏|分享|展开|收起|加载更多)$/.test(t)) return true;
    if (/^[|/\\\-_=·•。.，,\s]+$/.test(t)) return true;
    return false;
  };
  const pushText = (type, text) => {
    const t = oneLine(text);
    if (dropText(t)) return;
    const last = blocks[blocks.length - 1];
    if (last && last.type === type) {
      last.text = oneLine(last.text + '\n' + t);
    } else {
      blocks.push({type, text: t});
    }
  };
  const mediaUrl = (el) => {
    const attrs = ['data-src', 'data-original', 'data-actualsrc', 'data-url', 'data-full', 'data-ks-lazyload', 'src', 'href'];
    for (const a of attrs) {
      const v = el.getAttribute && el.getAttribute(a);
      if (v && !/^data:/i.test(v)) return absUrl(v);
    }
    if (el.dataset) {
      for (const key of Object.keys(el.dataset)) {
        const v = el.dataset[key];
        if (v && /https?:|^\/|^\/\//.test(v)) return absUrl(v);
      }
    }
    return '';
  };
  const captionFor = (el) => {
    if (!el) return '';
    let parent = el.parentElement;
    for (let i = 0; i < 3 && parent; i++) {
      const cap = parent.querySelector('figcaption, .caption, .pic-desc, .photo-desc, .desc');
      const t = oneLine(cap && cap.innerText);
      if (t && t.length <= 160) return t;
      parent = parent.parentElement;
    }
    const next = el.nextElementSibling;
    const nt = oneLine(next && next.innerText);
    return nt && nt.length <= 120 ? nt : '';
  };
  const pushImage = (img) => {
    const url = mediaUrl(img);
    if (!url || seenImages.has(url)) return;
    seenImages.add(url);
    imageUrls.push(url);
    blocks.push({type: 'image', url, alt: oneLine(img.getAttribute('alt') || ''), caption: captionFor(img)});
  };
  const pushVideo = (el) => {
    let url = mediaUrl(el);
    if (!url && el.querySelector) {
      const source = el.querySelector('source[src], source[data-src]');
      if (source) url = mediaUrl(source);
    }
    const poster = absUrl(el.getAttribute && (el.getAttribute('poster') || el.getAttribute('data-poster')));
    if (!url && !poster) return;
    const key = url || poster;
    if (seenVideos.has(key)) return;
    seenVideos.add(key);
    if (url) videoUrls.push(url);
    blocks.push({type: 'video', url, poster, caption: captionFor(el)});
  };
  const shouldSkipElement = (el) => {
    const tag = el.tagName;
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'LINK', 'META'].includes(tag)) return true;
    const idClass = `${el.id || ''} ${el.className || ''}`.toLowerCase();
    return /(reply|comment|vc_total|help_total|sidebar|side_bar|right|recommend|relate|toolbar|footer|bottomreply|_j_reply)/i.test(idClass);
  };
  const walk = (node) => {
    if (!node) return;
    if (node.nodeType === Node.TEXT_NODE) {
      pushText('text', node.nodeValue);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node;
    if (shouldSkipElement(el)) return;
    const tag = el.tagName;
    if (/^H[1-6]$/.test(tag)) {
      pushText('heading', el.innerText);
      return;
    }
    if (tag === 'IMG') {
      pushImage(el);
      return;
    }
    if (tag === 'VIDEO' || tag === 'IFRAME' || tag === 'EMBED') {
      pushVideo(el);
      if (tag !== 'VIDEO') return;
    }
    if (tag === 'SOURCE' && el.parentElement && el.parentElement.tagName === 'VIDEO') {
      pushVideo(el);
      return;
    }
    for (const child of Array.from(el.childNodes)) walk(child);
  };
  if (article) {
    for (const child of Array.from(article.childNodes)) walk(child);
  }
  const fullText = blocks.filter(b => b.type === 'text' || b.type === 'heading').map(b => b.text).join('\n');
  const favoriteText = textBySelectors(['[class*="collect"]', '[class*="favorite"]', '.view_collect', '.vc_collect']) || bodyText;
  const shareText = textBySelectors(['[class*="share"]', '.view_share', '.vc_share']) || bodyText;
  const dingText = textBySelectors(['[class*="ding"]', '[class*="support"]', '.view_ding', '.vc_ding']) || bodyText.slice(0, 2000);
  return {
    title,
    author_name: author,
    author_level: levelMatch ? levelMatch[0].replace(/\s+/g, '') : '',
    publish_time: publishMatch ? publishMatch[0] : '',
    destination: bodyText.includes(regionKeyword) ? regionKeyword : '',
    schedule,
    ordered_blocks: blocks,
    full_text: fullText,
    image_urls: imageUrls,
    video_urls: videoUrls,
    raw_text: bodyText,
    favorite_text: favoriteText,
    share_text: shareText,
    ding_text: dingText,
    page_title: document.title || '',
    article_found: !!article
  };
})();
"""


def merge_ordered_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并相邻同类型文本块，降低正文 JSON 噪声。"""
    merged: List[Dict[str, Any]] = []
    seen_images: Set[str] = set()
    seen_videos: Set[str] = set()
    for block in blocks or []:
        btype = block.get("type")
        if btype in {"text", "heading"}:
            text = clean_text(block.get("text", ""))
            if not text:
                continue
            if merged and merged[-1].get("type") == btype:
                merged[-1]["text"] = clean_text(merged[-1].get("text", "") + "\n" + text)
            else:
                merged.append({"type": btype, "text": text})
        elif btype == "image":
            url = normalize_url(block.get("url", ""))
            if not url or url in seen_images:
                continue
            seen_images.add(url)
            merged.append(
                {
                    "type": "image",
                    "url": url,
                    "alt": clean_text(block.get("alt", "")),
                    "caption": clean_text(block.get("caption", "")),
                }
            )
        elif btype == "video":
            url = normalize_url(block.get("url", ""))
            poster = normalize_url(block.get("poster", ""))
            key = url or poster
            if not key or key in seen_videos:
                continue
            seen_videos.add(key)
            merged.append(
                {
                    "type": "video",
                    "url": url,
                    "poster": poster,
                    "caption": clean_text(block.get("caption", "")),
                }
            )
    return merged


def parse_detail_page(page: Any, cfg: Dict[str, Any], source: Optional[Dict[str, Any]] = None, strict: bool = True) -> Dict[str, Any]:
    """解析当前详情页，字段缺失时用列表记录兜底。"""
    source = source or {}
    data = run_js(page, DETAIL_EXTRACT_JS, default={}) or {}
    url = normalize_url(get_current_url(page) or source.get("url", ""))
    note_id = extract_note_id(url) or str(source.get("note_id", ""))
    raw_text = clean_text(data.get("raw_text", ""))
    if re_is_404(raw_text, data.get("page_title", "")):
        raise RuntimeError("详情页 404 或页面不存在")

    views, comments = parse_views_comments(raw_text)
    if not views and source.get("views"):
        views = int(source.get("views") or 0)
    if not comments and source.get("comments"):
        comments = int(source.get("comments") or 0)
    ordered_blocks = merge_ordered_blocks(data.get("ordered_blocks", []))
    full_text = clean_text("\n".join(
        b.get("text", "") for b in ordered_blocks if b.get("type") in {"text", "heading"}
    )) or clean_text(data.get("full_text", ""))
    image_urls = []
    video_urls = []
    for b in ordered_blocks:
        if b.get("type") == "image" and b.get("url"):
            image_urls.append(b["url"])
        if b.get("type") == "video" and b.get("url"):
            video_urls.append(b["url"])
    if not image_urls:
        image_urls = [normalize_url(u) for u in data.get("image_urls", []) if normalize_url(u)]
    if not video_urls:
        video_urls = [normalize_url(u) for u in data.get("video_urls", []) if normalize_url(u)]

    schedule = data.get("schedule", {}) or {}
    record = {
        "note_id": note_id,
        "url": url,
        "title": clean_text(data.get("title", "")) or clean_text(source.get("title", "")),
        "author_name": clean_text(data.get("author_name", "")) or clean_text(source.get("author_name", "")),
        "author_level": clean_text(data.get("author_level", "")),
        "publish_time": clean_text(data.get("publish_time", "")),
        "views": views,
        "comments": comments,
        "favorite_count": parse_count_before_word(data.get("favorite_text", ""), "收藏"),
        "share_count": parse_count_before_word(data.get("share_text", ""), "分享"),
        "ding_count": parse_count_before_word(data.get("ding_text", ""), "顶") or int(source.get("ding_count") or 0),
        "destination": clean_text(data.get("destination", "")) or clean_text(source.get("region", "")) or cfg.get("site", {}).get("region_keyword", ""),
        "departure_date": clean_text(schedule.get("departure_date", "")),
        "travel_days": clean_text(schedule.get("travel_days", "")),
        "people_type": clean_text(schedule.get("people_type", "")),
        "avg_cost": clean_text(schedule.get("avg_cost", "")),
        "full_text": full_text,
        "ordered_blocks": ordered_blocks,
        "image_urls": image_urls,
        "video_urls": video_urls,
        "image_count": len(image_urls),
        "video_count": len(video_urls),
        "word_count": len(clean_text(full_text).replace(" ", "").replace("\n", "")),
        "article_found": bool(data.get("article_found")),
        "crawl_time": now_str(),
        "status": "success",
        "error": "",
    }
    if strict and not data.get("article_found"):
        raise RuntimeError("正文容器不存在")
    if strict and not record["full_text"] and not record["image_urls"] and not record["video_urls"]:
        raise RuntimeError("正文为空")
    return record


def re_is_404(raw_text: str, page_title: str) -> bool:
    text = f"{page_title}\n{raw_text[:1000]}"
    return any(flag in text for flag in ["404", "页面不存在", "找不到页面", "该游记不存在"])


def append_media_index_and_download(cfg: Dict[str, Any], record: Dict[str, Any]) -> None:
    output = cfg.get("output", {})
    media_path = output.get("media_index", "./data/media_index.jsonl")
    download = bool(output.get("download_media", False))
    media_dir = output.get("media_dir", "./data/media")
    note_id = record.get("note_id", "")
    for idx, url in enumerate(record.get("image_urls", []), start=1):
        item = {
            "note_id": note_id,
            "source_url": record.get("url", ""),
            "media_type": "image",
            "media_url": url,
            "rank": idx,
            "local_path": "",
            "crawl_time": now_str(),
        }
        if download:
            try:
                item["local_path"] = download_file(url, media_dir, prefix=f"{note_id}_image_{idx}")
            except Exception as e:
                item["download_error"] = str(e)
        append_jsonl(media_path, item)
    for idx, url in enumerate(record.get("video_urls", []), start=1):
        item = {
            "note_id": note_id,
            "source_url": record.get("url", ""),
            "media_type": "video",
            "media_url": url,
            "rank": idx,
            "local_path": "",
            "crawl_time": now_str(),
        }
        if download:
            try:
                item["local_path"] = download_file(url, media_dir, prefix=f"{note_id}_video_{idx}")
            except Exception as e:
                item["download_error"] = str(e)
        append_jsonl(media_path, item)


def load_detail_sources(cfg: Dict[str, Any], retry_failed: bool = False) -> List[Dict[str, Any]]:
    if retry_failed:
        failed = [
            rec for rec in read_jsonl(cfg["output"]["failed_file"])
            if rec.get("stage") == "detail" and rec.get("url")
        ]
        dedup: Dict[str, Dict[str, Any]] = {}
        for rec in failed:
            note_id = rec.get("note_id") or extract_note_id(rec.get("url", ""))
            if note_id:
                dedup[note_id] = {"note_id": note_id, "url": rec["url"]}
        return list(dedup.values())
    return read_jsonl(cfg["output"]["list_jsonl"])


def crawl_detail(cfg: Dict[str, Any], retry_failed: bool = False, headless: Optional[bool] = None) -> None:
    page = None
    output = cfg["output"]
    progress = load_progress(cfg)
    success_ids: Set[str] = set(progress["detail"].get("finished_note_ids") or [])
    success_ids |= collect_success_detail_ids(output["detail_jsonl"])
    if retry_failed:
        retry_ids = collect_failed_detail_ids(output["failed_file"])
        log(f"🔁 retry-failed 模式：发现失败 note_id {len(retry_ids)} 个")

    sources = load_detail_sources(cfg, retry_failed=retry_failed)
    if not sources:
        log("⚠️ 没有可爬取的详情 URL。请先运行列表阶段，或使用 --retry-failed。")
        return

    limit = int(cfg.get("crawl", {}).get("detail_limit", 0) or 0)
    todo: List[Dict[str, Any]] = []
    for rec in sources:
        url = normalize_url(rec.get("url", ""))
        note_id = str(rec.get("note_id") or extract_note_id(url))
        if not url or not note_id:
            continue
        if note_id in success_ids:
            continue
        item = dict(rec)
        item["url"] = url
        item["note_id"] = note_id
        todo.append(item)
        if limit and len(todo) >= limit:
            break

    if not todo:
        log("✅ 详情阶段没有待爬取记录")
        return

    try:
        page = create_browser_page(cfg, headless=headless)
        retry_times = int(cfg.get("crawl", {}).get("retry_times", 3))
        for idx, source in enumerate(todo, start=1):
            url = source["url"]
            note_id = source["note_id"]
            if idx > 1:
                maybe_random_sleep(cfg, "open_next_note_pause_min", "open_next_note_pause_max", "打开下一篇前")
            log(f"🌐 打开游记详情 [{idx}/{len(todo)}]：{url}")
            last_error = ""
            for attempt in range(1, retry_times + 1):
                try:
                    open_url(page, url, timeout=int(cfg.get("browser", {}).get("page_load_timeout", 60)))
                    reason = detect_block_or_login(page)
                    if reason:
                        pause_for_manual_check(page, reason)
                    maybe_random_sleep(cfg, "detail_pause_min", "detail_pause_max", "详情页加载后")
                    if cfg.get("anti_ban", {}).get("scroll_article_before_parse", True):
                        human_like_scroll(page, cfg, max_rounds=120)
                    record = parse_detail_page(page, cfg, source=source)
                    log("✅ 基础信息：标题、作者、发布时间提取完成")
                    log("✅ 行程信息：出发时间/出行天数/人物/费用提取完成")
                    simulate_reading_by_word_count(page, cfg, record["word_count"])
                    append_jsonl(output["detail_jsonl"], record)
                    append_detail_csv(output["detail_csv"], record)
                    append_media_index_and_download(cfg, record)
                    success_ids.add(note_id)
                    progress["detail"]["finished_note_ids"] = sorted(success_ids)
                    progress["detail"]["last_finished_note_id"] = note_id
                    failed_ids = set(progress["detail"].get("failed_note_ids") or [])
                    failed_ids.discard(note_id)
                    progress["detail"]["failed_note_ids"] = sorted(failed_ids)
                    save_progress(cfg, progress)
                    log(f"✅ 正文解析完成：{record['word_count']}字，{record['image_count']}张图片，{record['video_count']}个视频")
                    log("💾 已写入 notes_detail.jsonl / notes_detail.csv")
                    break
                except KeyboardInterrupt:
                    log("⚠️ 用户中断，已保留当前已写入数据和进度")
                    raise
                except Exception as e:
                    last_error = str(e)
                    log(f"⚠️ 详情解析失败：{note_id} {short_title(source.get('title', ''))}，第 {attempt}/{retry_times} 次，原因：{e}")
                    if attempt < retry_times:
                        maybe_random_sleep(cfg, "scroll_pause_min", "scroll_pause_max", "重试前")
            else:
                failed = build_failed_record(note_id, url, "detail", "详情解析失败", last_error)
                append_jsonl(output["failed_file"], failed)
                failed_ids = set(progress["detail"].get("failed_note_ids") or [])
                failed_ids.add(note_id)
                progress["detail"]["failed_note_ids"] = sorted(failed_ids)
                save_progress(cfg, progress)
                log(f"❌ 详情失败已记录：{note_id} {last_error}")
        log("✅ 详情阶段结束")
    finally:
        close_browser_page(page)
