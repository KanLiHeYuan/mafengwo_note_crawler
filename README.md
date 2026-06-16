# 马蜂窝山西游记爬虫

这是一个基于 Python 3 + DrissionPage 的马蜂窝游记爬虫项目，用于爬取 `https://www.mafengwo.cn/` 中“山西”地区的游记列表与详情正文。

项目原则：

- 不绕过验证码、安全校验或登录限制。
- 不并发、不高频请求，默认使用很慢的随机等待。
- 每条列表、每篇详情、每个失败 URL 都实时写入文件并 flush。
- 支持手动登录、手动筛选、断点续爬、失败重试和 nohup 后台运行。

## 目录结构

```text
mafengwo_note_crawler/
├── README.md
├── requirements.txt
├── config.yaml
├── start_mafengwo_notes_nohup.sh
├── manual_login_mafengwo_x11.sh
├── debug_one_note.py
├── debug_list_page.py
├── crawler_common.py
├── mafengwo_list_crawler.py
├── mafengwo_note_detail_crawler.py
├── mafengwo_runner.py
├── data/
│   ├── notes_list.jsonl
│   ├── notes_detail.jsonl
│   ├── notes_detail.csv
│   ├── media_index.jsonl
│   ├── failed_urls.jsonl
│   ├── progress.json
│   └── logs/
└── profiles/
    └── mafengwo_profile/
```

`notes_list.jsonl`、`notes_detail.jsonl`、`notes_detail.csv`、`media_index.jsonl` 和 `failed_urls.jsonl` 会在运行时自动创建。

## 安装环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

DrissionPage 需要本机或服务器可用的 Chromium/Chrome。Linux headless 环境建议先确认 Chrome 可正常启动。

## 配置说明

主要配置在 `config.yaml`：

- `browser.user_data_path`：固定浏览器用户目录，默认 `./profiles/mafengwo_profile`，用于复用登录状态。
- `browser.headless`：是否无头运行。首次登录或手动筛选时设为 `false`。
- `site.start_url`：可填写已经筛选好“热门游记 + 山西”的列表页 URL。为空时会打开首页，适合手动筛选。
- `crawl.page_pause_min/max`：列表翻页前等待，默认 25 到 60 秒。
- `crawl.detail_pause_min/max`：详情页加载后等待，默认 30 到 90 秒。
- `crawl.open_next_note_pause_min/max`：打开下一篇详情前等待，默认 45 到 120 秒。
- `output.download_media`：默认 `false`，只保存图片/视频 URL；改成 `true` 后才下载媒体文件。

## Windows 本地调试

首次建议先调列表页：

```powershell
python mafengwo_runner.py --mode list --manual --no-headless
```

程序会打开浏览器。你手动进入马蜂窝旅游攻略/游记页面，切换到“热门游记”，筛选地区“山西”，确认列表页正确后回到终端按回车。

调试当前列表页解析：

```powershell
python debug_list_page.py --no-headless
```

调试单篇游记详情：

```powershell
python debug_one_note.py --url https://www.mafengwo.cn/i/24846178.html --no-headless
```

调试结果会保存到 `data/debug/`。

## Linux 手动登录

有桌面或 X11 转发时：

```bash
chmod +x manual_login_mafengwo_x11.sh
./manual_login_mafengwo_x11.sh
```

登录成功后关闭脚本，后续爬虫会复用 `profiles/mafengwo_profile`。

如果服务器没有桌面，建议在本地完成登录和筛选，把 `profiles/mafengwo_profile` 目录迁移到服务器，或使用带 X11/VNC 的环境手动登录。

## 运行命令

只爬列表：

```bash
python mafengwo_runner.py --mode list --manual
```

只爬详情：

```bash
python mafengwo_runner.py --mode detail
```

列表 + 详情连续爬：

```bash
python mafengwo_runner.py --mode all --manual
```

重置列表阶段进度：

```bash
python mafengwo_runner.py --mode list --reset
```

重试失败详情：

```bash
python mafengwo_runner.py --mode detail --retry-failed
```

`--reset` 只重置 `progress.json` 中对应阶段的进度，不删除已有 JSONL/CSV。继续运行时会根据已有数据自动去重，优先避免误删数据。

## nohup 后台运行

```bash
chmod +x start_mafengwo_notes_nohup.sh
./start_mafengwo_notes_nohup.sh list
./start_mafengwo_notes_nohup.sh detail
./start_mafengwo_notes_nohup.sh all
```

脚本会把日志写到：

```text
data/logs/mafengwo_模式_时间.log
```

查看日志：

```bash
tail -f data/logs/mafengwo_detail_YYYYMMDD_HHMMSS.log
```

也可以追加参数，例如：

```bash
./start_mafengwo_notes_nohup.sh detail --headless
./start_mafengwo_notes_nohup.sh detail --retry-failed --headless
```

## 断点续爬

进度文件是 `data/progress.json`：

```json
{
  "list": {
    "last_finished_page": 0,
    "finished_note_ids": []
  },
  "detail": {
    "finished_note_ids": [],
    "failed_note_ids": []
  }
}
```

程序启动时会同时读取：

- `data/progress.json`
- `data/notes_list.jsonl`
- `data/notes_detail.jsonl`

因此即使上次异常中断，只要记录已经写入 JSONL，下次也不会重复写入成功记录。

## 输出字段

`data/notes_list.jsonl` 每行一条列表记录：

```json
{
  "note_id": "24846178",
  "url": "https://www.mafengwo.cn/i/24846178.html",
  "title": "晋刻出发之大同太原5日游玩攻略...",
  "summary": "...",
  "region": "山西",
  "author_name": "米饭帮主",
  "views": 5871,
  "comments": 5,
  "ding_count": 405,
  "cover_image": "...",
  "list_page": 1,
  "rank_in_page": 1,
  "crawl_time": "2026-06-10 21:00:00"
}
```

`data/notes_detail.jsonl` 每行一篇详情，包含：

- 基础信息：标题、URL、ID、作者、等级、发布时间、浏览/评论、收藏、分享、顶数、目的地。
- 行程信息：出发时间、出行天数、人物、人均费用。
- 正文信息：`ordered_blocks`、`full_text`、`image_urls`、`video_urls`、图片数、视频数、字数。

`data/notes_detail.csv` 保存简化字段，便于直接做 NLP 或表格分析；`ordered_blocks` 只保存在 JSONL。

`data/media_index.jsonl` 保存正文图片和视频 URL 索引。默认不下载媒体。

`data/failed_urls.jsonl` 保存失败记录：

```json
{
  "note_id": "24846178",
  "url": "https://www.mafengwo.cn/i/24846178.html",
  "stage": "detail",
  "error_type": "正文为空",
  "error": "...",
  "crawl_time": "2026-06-10 21:00:00"
}
```

## 正文解析策略

详情正文优先使用：

- `div.va_con._j_master_content`
- `div.vc_article div.va_con`
- `div._j_master_content`
- `div.vc_article`

解析时按 DOM 顺序遍历子节点，识别：

- `text`
- `heading`
- `image`
- `video`

并主动跳过评论区、回复区、相关推荐、右侧栏、底部工具区等明显非正文节点。

## 常见问题

### 1. 打开后出现验证码或安全验证怎么办？

程序不会绕过验证码。它会暂停并提示你在浏览器里人工处理，完成后回到终端按回车继续。

### 2. 列表页解析不到记录怎么办？

先运行：

```bash
python debug_list_page.py --no-headless
```

确认你当前页面确实是“热门游记 + 山西”的列表页。如果马蜂窝 DOM 变化较大，可以在 `mafengwo_list_crawler.py` 中补充候选选择器。

### 3. 详情正文为空怎么办？

先用：

```bash
python debug_one_note.py --url 目标URL --no-headless
```

查看 `data/debug/debug_note_xxx.json`。如果 `article_found=false`，说明正文容器选择器需要补充。

### 4. 如何完全重新爬？

为了避免误删数据，`--reset` 不删除输出文件。若确认要完全重抓，请先自行备份或删除 `data/notes_list.jsonl`、`data/notes_detail.jsonl`、`data/notes_detail.csv`、`data/media_index.jsonl`、`data/failed_urls.jsonl`，再运行 `--reset`。

### 5. 可以加速或并发吗？

不建议。当前项目按保守策略设计，不并发、不高频访问，优先保证账号和数据稳定。

