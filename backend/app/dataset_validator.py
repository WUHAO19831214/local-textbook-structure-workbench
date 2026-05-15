from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


class DatasetValidationResult(BaseModel):
    valid: bool
    dataset_name: str
    dataset_path: str
    markdown_file: Optional[str] = None
    json_file: Optional[str] = None
    images_dir: str = "images"
    image_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    def to_api_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def validate_dataset(dataset_path: Path) -> DatasetValidationResult:
    warnings: list[str] = []
    errors: list[str] = []

    dataset_path = dataset_path.expanduser().resolve()
    dataset_name = dataset_path.name

    if not dataset_path.is_absolute():
        errors.append("数据集路径必须是本地绝对路径。")
    if not dataset_path.exists():
        errors.append("数据集路径不存在。")
    if dataset_path.exists() and not dataset_path.is_dir():
        errors.append("数据集路径必须是目录。")

    if errors:
        return DatasetValidationResult(
            valid=False,
            dataset_name=dataset_name,
            dataset_path=str(dataset_path),
            warnings=warnings,
            errors=errors,
        )

    markdown_file = _resolve_markdown_file(dataset_path)
    if markdown_file is None:
        errors.append("未在数据集根目录找到 Markdown 文件，例如 xxx.md。")

    json_file: Path | None = None
    if markdown_file is not None:
        expected_json = dataset_path / f"{markdown_file.stem}.json"
        if expected_json.exists() and expected_json.is_file():
            json_file = expected_json
        else:
            warnings.append(f"未找到 {markdown_file.stem}.json；MVP-1 仅提示，不阻断加载。")
    else:
        expected_json = dataset_path / f"{dataset_name}.json"
        if expected_json.exists() and expected_json.is_file():
            json_file = expected_json
        else:
            warnings.append("未找到 xxx.json；MVP-1 仅提示，不阻断加载。")

    images_path = dataset_path / "images"
    image_count = 0
    if images_path.exists() and images_path.is_dir():
        image_count = sum(
            1
            for item in images_path.rglob("*")
            if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
        )
    else:
        warnings.append("未找到 images/ 目录，Markdown 中的本地图片可能无法显示。")

    return DatasetValidationResult(
        valid=len(errors) == 0,
        dataset_name=dataset_name,
        dataset_path=str(dataset_path),
        markdown_file=markdown_file.name if markdown_file else None,
        json_file=json_file.name if json_file else None,
        image_count=image_count,
        warnings=warnings,
        errors=errors,
    )


def _resolve_markdown_file(dataset_path: Path) -> Path | None:
    preferred = dataset_path / f"{dataset_path.name}.md"
    if preferred.exists() and preferred.is_file():
        return preferred

    markdown_files = sorted(
        item for item in dataset_path.glob("*.md") if item.is_file()
    )
    if not markdown_files:
        return None
    return markdown_files[0]
