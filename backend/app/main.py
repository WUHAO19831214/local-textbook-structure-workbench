from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.dataset_validator import validate_dataset
from app.extractors import get_extractor
from app.extractors.base import ExtractContext
from app.models import (
    AnkiExportRequest,
    AnkiExportResponse,
    ExtractPreviewRequest,
    ExtractPreviewResponse,
    MindmapGenerateRequest,
    MindmapGenerateResponse,
    OutlineGenerateRequest,
    OutlineGenerateResponse,
    OutlineItem,
)


app = FastAPI(title="Local Textbook Workspace API", version="0.1.0")
EXPORT_DIR = Path(__file__).resolve().parents[1] / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=str(EXPORT_DIR), check_dir=True), name="downloads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_mounted_dataset_ids: set[str] = set()


class DatasetLoadRequest(BaseModel):
    path: str = Field(..., min_length=1, description="本地数据集目录的绝对路径")


class DatasetLoadResponse(BaseModel):
    dataset_id: str
    static_base_url: str
    markdown: str
    validation: dict


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/dataset/load", response_model=DatasetLoadResponse)
def load_dataset(payload: DatasetLoadRequest, request: Request) -> DatasetLoadResponse:
    raw_path = Path(payload.path).expanduser()
    if not raw_path.is_absolute():
        raise HTTPException(status_code=400, detail="请提供本地绝对路径。")

    dataset_path = raw_path.resolve()
    validation = validate_dataset(dataset_path)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.to_api_dict())

    if validation.markdown_file is None:
        raise HTTPException(status_code=400, detail="未找到可读取的 Markdown 文件。")

    dataset_id = _dataset_id_for_path(dataset_path)
    _mount_dataset_static(dataset_id, dataset_path)

    markdown_path = dataset_path / validation.markdown_file
    markdown_text = markdown_path.read_text(encoding="utf-8")
    static_base_url = f"{str(request.base_url).rstrip('/')}/static/{dataset_id}"
    markdown_text = rewrite_markdown_image_urls(markdown_text, static_base_url)

    return DatasetLoadResponse(
        dataset_id=dataset_id,
        static_base_url=static_base_url,
        markdown=markdown_text,
        validation=validation.to_api_dict(),
    )


@app.post("/api/extract/preview", response_model=ExtractPreviewResponse)
def preview_extract(payload: ExtractPreviewRequest) -> ExtractPreviewResponse:
    markdown = _slice_markdown_by_ranges(
        payload.markdown,
        payload.ranges,
        payload.range_start,
        payload.range_end,
    )
    cards = _extract_cards(
        markdown=markdown,
        template=payload.template,
        custom_regex=payload.custom_regex,
    )
    return ExtractPreviewResponse(
        template=payload.template,
        total=len(cards),
        cards=cards[: payload.limit],
    )


@app.post("/api/anki/export", response_model=AnkiExportResponse)
def export_anki_csv(payload: AnkiExportRequest, request: Request) -> AnkiExportResponse:
    markdown = _slice_markdown_by_ranges(
        payload.markdown,
        payload.ranges,
        payload.range_start,
        payload.range_end,
    )
    cards = _extract_cards(
        markdown=markdown,
        template=payload.template,
        custom_regex=payload.custom_regex,
    )
    if not cards:
        raise HTTPException(status_code=400, detail="没有可导出的卡片，请先调整模板或正则。")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"anki_cards_{payload.template}_{timestamp}_{uuid4().hex[:8]}.csv"
    export_path = EXPORT_DIR / filename

    with export_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["Front", "Back", "Image", "Tags"])
        writer.writeheader()
        for card in cards:
            writer.writerow(
                {
                    "Front": card.front,
                    "Back": card.back,
                    "Image": card.image or "",
                    "Tags": " ".join(card.tags),
                }
            )

    return AnkiExportResponse(
        filename=filename,
        download_url=f"{str(request.base_url).rstrip('/')}/downloads/{quote(filename)}",
        total=len(cards),
    )


@app.post("/api/mindmap/generate", response_model=MindmapGenerateResponse)
def generate_mindmap(payload: MindmapGenerateRequest) -> MindmapGenerateResponse:
    outline_response = _build_outline(payload.markdown, payload.dataset_path, payload.json_file)
    if outline_response.heading_count < 2:
        return MindmapGenerateResponse(
            outline="",
            heading_count=outline_response.heading_count,
            suitable=False,
            message="当前文档层级较少，暂不适合生成脑图。",
        )

    return MindmapGenerateResponse(
        outline=outline_response.outline_markdown,
        heading_count=outline_response.heading_count,
        suitable=True,
        message="已根据整理后的章节目录生成脑图。",
    )


@app.post("/api/outline/generate", response_model=OutlineGenerateResponse)
def generate_outline(payload: OutlineGenerateRequest) -> OutlineGenerateResponse:
    return _build_outline(payload.markdown, payload.dataset_path, payload.json_file)


def _extract_cards(markdown: str, template: str, custom_regex: str | None = None):
    try:
        extractor = get_extractor(template)
        return extractor.extract(ExtractContext(markdown=markdown, custom_regex=custom_regex))
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"自定义正则无效：{exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _extract_markdown_headings(markdown: str) -> list[dict]:
    headings: list[dict] = []
    in_code_block = False

    for line_number, line in enumerate(markdown.splitlines()):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue

        title = re.sub(r"\s+#+\s*$", "", match.group(2)).strip()
        title = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", title)
        title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
        title = re.sub(r"`([^`]+)`", r"\1", title).strip()
        if title:
            headings.append(
                {
                    "title": title,
                    "level": len(match.group(1)),
                    "line": line_number,
                    "markdown_index": len(headings),
                }
            )

    return headings


def _build_outline(markdown: str, dataset_path: str | None, json_file: str | None) -> OutlineGenerateResponse:
    markdown_headings = _extract_markdown_headings(markdown)
    json_outline, page_count = _extract_json_outline(dataset_path, json_file, markdown_headings)
    if json_outline:
        items = _normalize_lesson_hierarchy(json_outline)
        source = "json"
    else:
        items = [
            OutlineItem(
                id=f"heading-{heading['markdown_index']}",
                title=heading["title"],
                level=heading["level"],
                category="other",
                category_label="其他",
                page=None,
                font_size=None,
                source="markdown",
                markdown_index=heading["markdown_index"],
                start_line=heading["line"],
            )
            for heading in markdown_headings
        ]
        source = "markdown"

    items = _assign_outline_ranges(items)
    outline_markdown = _outline_items_to_markdown(items)
    return OutlineGenerateResponse(
        items=items,
        outline_markdown=outline_markdown,
        heading_count=len(items),
        page_count=page_count,
        source=source,
        message="已根据 JSON 标题块整理章节目录。" if source == "json" else "已根据 Markdown 标题整理章节目录。",
    )


def _extract_json_outline(
    dataset_path: str | None,
    json_file: str | None,
    markdown_headings: list[dict],
) -> tuple[list[OutlineItem], int | None]:
    if not dataset_path or not json_file:
        return [], None

    json_path = (Path(dataset_path).expanduser().resolve() / json_file).resolve()
    if not json_path.exists() or not json_path.is_file():
        return [], None

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], None

    kids = data.get("kids") if isinstance(data, dict) else None
    if not isinstance(kids, list):
        return [], data.get("number of pages") if isinstance(data, dict) else None

    page_count = data.get("number of pages")
    heading_candidates = []
    for kid_index, kid in enumerate(kids):
        if not isinstance(kid, dict) or kid.get("type") != "heading":
            continue
        title = _clean_title(str(kid.get("content") or ""))
        if not _looks_like_outline_title(title):
            continue
        heading_candidates.append(
            {
                "kid_index": kid_index,
                "title": title,
                "page": kid.get("page number"),
                "font_size": kid.get("font size"),
                "raw_level": kid.get("heading level"),
            }
        )

    matched_items: list[OutlineItem] = []
    markdown_cursor = 0
    for candidate in heading_candidates:
        match = _match_markdown_heading(candidate["title"], markdown_headings, markdown_cursor)
        if match is None:
            continue
        markdown_cursor = match["markdown_index"] + 1
        level = _infer_outline_level(candidate["title"], int(candidate.get("raw_level") or match["level"]))
        matched_items.append(
            OutlineItem(
                id=f"heading-{match['markdown_index']}",
                title=candidate["title"],
                level=level,
                category="other",
                category_label="其他",
                page=candidate["page"] if isinstance(candidate["page"], int) else None,
                font_size=float(candidate["font_size"]) if isinstance(candidate["font_size"], (int, float)) else None,
                source="json",
                markdown_index=match["markdown_index"],
                start_line=match["line"],
            )
        )

    return matched_items, page_count if isinstance(page_count, int) else None


def _match_markdown_heading(title: str, headings: list[dict], start_index: int) -> dict | None:
    normalized_title = _normalize_title_for_match(title)
    for heading in headings[start_index:]:
        if _normalize_title_for_match(heading["title"]) == normalized_title:
            return heading
    for heading in headings[start_index:]:
        heading_title = _normalize_title_for_match(heading["title"])
        if normalized_title and (normalized_title in heading_title or heading_title in normalized_title):
            return heading
    return None


def _assign_outline_ranges(items: list[OutlineItem]) -> list[OutlineItem]:
    for index, item in enumerate(items):
        end_line = None
        for next_item in items[index + 1 :]:
            if next_item.level <= item.level:
                end_line = max(item.start_line, next_item.start_line - 1)
                break
        items[index] = item.model_copy(update={"end_line": end_line})
    return items


def _normalize_lesson_hierarchy(items: list[OutlineItem]) -> list[OutlineItem]:
    normalized: list[OutlineItem] = []
    current_lesson: OutlineItem | None = None
    for item in items:
        if _is_lesson_title(item.title):
            current_lesson = item.model_copy(
                update={
                    "level": 1,
                    "category": "lesson",
                    "category_label": "课",
                    "parent_id": None,
                    "parent_title": None,
                }
            )
            normalized.append(current_lesson)
            continue
        if current_lesson is not None:
            category, category_label = _classify_lesson_section(item.title)
            normalized.append(
                item.model_copy(
                    update={
                        "level": max(2, item.level),
                        "category": category,
                        "category_label": category_label,
                        "parent_id": current_lesson.id,
                        "parent_title": current_lesson.title,
                    }
                )
            )
            continue
        normalized.append(
            item.model_copy(
                update={
                    "level": 1,
                    "category": "intro",
                    "category_label": "引言",
                    "parent_id": None,
                    "parent_title": None,
                }
            )
        )
    return normalized


def _outline_items_to_markdown(items: list[OutlineItem]) -> str:
    if not items:
        return ""
    min_level = min(item.level for item in items)
    lines = []
    for item in items:
        level = max(1, item.level - min_level + 1)
        page = f" P{item.page}" if item.page is not None else ""
        lines.append(f"{'#' * min(level, 6)} {item.title}{page}")
    return "\n".join(lines)


def _slice_markdown_by_range(markdown: str, range_start: int | None, range_end: int | None) -> str:
    if range_start is None:
        return markdown
    lines = markdown.splitlines()
    if not lines:
        return markdown
    start = max(0, range_start)
    end = len(lines) - 1 if range_end is None else min(len(lines) - 1, range_end)
    if start > end:
        return markdown
    return "\n".join(lines[start : end + 1])


def _slice_markdown_by_ranges(
    markdown: str,
    ranges: list[dict] | None,
    range_start: int | None,
    range_end: int | None,
) -> str:
    if ranges:
        chunks = []
        for item in ranges:
            if not isinstance(item, dict):
                continue
            chunk = _slice_markdown_by_range(markdown, item.get("start"), item.get("end"))
            if chunk.strip():
                chunks.append(chunk)
        return "\n\n".join(chunks) if chunks else markdown
    return _slice_markdown_by_range(markdown, range_start, range_end)


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    title = title.strip("# ")
    return title


def _looks_like_outline_title(title: str) -> bool:
    if not title or len(title) > 90:
        return False
    if re.fullmatch(r"[\d\s.,:：/\\-]+", title):
        return False
    if title.lower().startswith(("http://", "https://", "www.")):
        return False
    return True


def _infer_outline_level(title: str, fallback_level: int) -> int:
    title = title.strip()
    if _is_lesson_title(title):
        return 1
    if re.match(r"^(前言|出版|目泉|目录|有效的使用方法|登人物|はじめに|致本学)", title):
        return 1
    if re.match(r"^[IVX]+[.．、]|^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+[.．、]", title):
        return 2
    if re.match(r"^\d+[.．、)]", title):
        return 3
    if re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩]", title):
        return 4
    if title in {"安型", "例妥", "例安", "箪語", "単司", "語法", "練習A", "練習B", "練習C"} or "練習" in title:
        return 2
    return max(1, min(6, fallback_level))


def _is_lesson_title(title: str) -> bool:
    return bool(re.search(r"第\s*\d+\s*課|第\s*[一二三四五六七八九十百]+\s*課", title.strip()))


def _classify_lesson_section(title: str) -> tuple[str, str]:
    compact = _normalize_title_for_match(title)
    if re.search(r"単語|单词|箪語|ことば|語彙|词汇", title, re.IGNORECASE):
        return "vocab", "单词"
    if re.search(r"文型|句型|安型", title, re.IGNORECASE):
        return "pattern", "文型/句型"
    if re.search(r"例文|例句|例妥|例安", title, re.IGNORECASE):
        return "examples", "例文"
    if re.search(r"会話|会话|会活|初めまして|お世話|あいさつ|挨拶", title, re.IGNORECASE):
        return "conversation", "会话"
    if re.search(r"練習\s*A|练习\s*A|練習A|练习A", title, re.IGNORECASE):
        return "exercise_a", "练习A"
    if re.search(r"練習\s*B|练习\s*B|練習B|练习B", title, re.IGNORECASE):
        return "exercise_b", "练习B"
    if re.search(r"練習\s*C|练习\s*C|練習C|练习C", title, re.IGNORECASE):
        return "exercise_c", "练习C"
    if re.search(r"問題|问题|もんだい", title, re.IGNORECASE):
        return "problem", "问题"
    if (
        re.search(r"文法|语法|語法|浯法", title, re.IGNORECASE)
        or re.search(r"名詞|動詞|形容詞|助詞|副詞|疑問|代替|アクセント|イントネーション", title)
        or re.search(r"これ|それ|あれ|この|その|あの|そうです|さん", title)
        or "〜" in title
        or "～" in title
        or bool(re.match(r"^\d+", compact))
    ):
        return "grammar", "文法"
    return "other", "其他"


def _normalize_title_for_match(title: str) -> str:
    title = _clean_title(title)
    title = re.sub(r"\s+", "", title)
    title = re.sub(r"[#*_`「」『』（）()，,。.:：；;、・\\-—]", "", title)
    return title.lower()


def _dataset_id_for_path(path: Path) -> str:
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:12]
    return f"ds-{digest}"


def _mount_dataset_static(dataset_id: str, dataset_path: Path) -> None:
    if dataset_id in _mounted_dataset_ids:
        return
    app.mount(
        f"/static/{dataset_id}",
        StaticFiles(directory=str(dataset_path), check_dir=True),
        name=f"dataset_static_{dataset_id}",
    )
    _mounted_dataset_ids.add(dataset_id)


def rewrite_markdown_image_urls(markdown: str, static_base_url: str) -> str:
    return re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda match: _rewrite_image_match(match, static_base_url),
        markdown,
    )


def _rewrite_image_match(match: re.Match[str], static_base_url: str) -> str:
    alt_text = match.group(1)
    original_url = match.group(2).strip()
    if original_url.startswith("<") and original_url.endswith(">"):
        original_url = original_url[1:-1].strip()

    if _is_external_or_absolute_url(original_url):
        return match.group(0)

    path_only, suffix = _split_markdown_url(original_url)
    rewritten_path = "/".join(quote(part) for part in path_only.split("/"))
    return f"![{alt_text}]({static_base_url}/{rewritten_path}{suffix})"


def _is_external_or_absolute_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme or parsed.netloc or url.startswith("/"))


def _split_markdown_url(url: str) -> tuple[str, str]:
    for separator in ("#", "?"):
        if separator in url:
            index = url.index(separator)
            return url[:index], url[index:]
    return url, ""
