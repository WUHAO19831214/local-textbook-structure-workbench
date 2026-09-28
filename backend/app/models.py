from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ExtractCard(BaseModel):
    front: str
    back: str
    image: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    meta: Dict[str, str] = Field(default_factory=dict)


class ExtractPreviewRequest(BaseModel):
    markdown: str = Field(..., min_length=1)
    template: str = Field(..., min_length=1)
    limit: int = Field(default=20, ge=1, le=200)
    custom_regex: Optional[str] = None
    ranges: Optional[List[Dict[str, Optional[int]]]] = None
    range_start: Optional[int] = None
    range_end: Optional[int] = None


class ExtractPreviewResponse(BaseModel):
    template: str
    total: int
    cards: List[ExtractCard]


class AnkiExportRequest(BaseModel):
    markdown: str = Field(..., min_length=1)
    template: str = Field(..., min_length=1)
    custom_regex: Optional[str] = None
    ranges: Optional[List[Dict[str, Optional[int]]]] = None
    range_start: Optional[int] = None
    range_end: Optional[int] = None


class AnkiExportResponse(BaseModel):
    filename: str
    download_url: str
    total: int


DocxExportMode = Literal["editable", "facsimile", "hybrid", "layout_editable"]


class DocxExportRequest(BaseModel):
    dataset_path: str = Field(..., min_length=1)
    mode: DocxExportMode = "editable"
    pdf_path: Optional[str] = None


class DocxExportResponse(BaseModel):
    ok: bool
    docx_path: str


class OpenPathRequest(BaseModel):
    path: str = Field(..., min_length=1)


class OpenPathResponse(BaseModel):
    ok: bool


class MindmapGenerateRequest(BaseModel):
    markdown: str = Field(..., min_length=1)
    dataset_path: Optional[str] = None
    json_file: Optional[str] = None


class MindmapGenerateResponse(BaseModel):
    outline: str
    heading_count: int
    suitable: bool
    message: str


class OutlineGenerateRequest(BaseModel):
    markdown: str = Field(..., min_length=1)
    dataset_path: Optional[str] = None
    json_file: Optional[str] = None


class OutlineItem(BaseModel):
    id: str
    title: str
    level: int
    category: str = "other"
    category_label: str = "其他"
    parent_id: Optional[str] = None
    parent_title: Optional[str] = None
    page: Optional[int] = None
    font_size: Optional[float] = None
    source: str
    markdown_index: int
    start_line: int
    end_line: Optional[int] = None


class OutlineGenerateResponse(BaseModel):
    items: List[OutlineItem]
    outline_markdown: str
    heading_count: int
    page_count: Optional[int] = None
    source: str
    message: str
