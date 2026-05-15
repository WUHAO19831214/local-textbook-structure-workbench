from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
from typing import List, Optional

from app.models import ExtractCard


@dataclass
class ExtractContext:
    markdown: str
    custom_regex: Optional[str] = None


class Extractor(ABC):
    @abstractmethod
    def extract(self, context: ExtractContext) -> List[ExtractCard]:
        """Return Anki-like cards extracted from markdown."""


IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def find_nearest_image(markdown: str, position: int, radius: int = 1200) -> Optional[str]:
    candidates: list[tuple[int, str]] = []
    for match in IMAGE_PATTERN.finditer(markdown):
        distance = abs(match.start() - position)
        if distance <= radius:
            candidates.append((distance, match.group(1).strip()))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def strip_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[*_>#-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
