from __future__ import annotations

import re
from typing import List

from app.extractors.base import ExtractContext, Extractor, find_nearest_image, strip_markdown
from app.models import ExtractCard


SECTION_HEADING_PATTERN = re.compile(r"^(?P<marks>#{2,3})\s+(?P<title>.+?)\s*$", re.MULTILINE)


class GenericQaExtractor(Extractor):
    def extract(self, context: ExtractContext) -> List[ExtractCard]:
        matches = list(SECTION_HEADING_PATTERN.finditer(context.markdown))
        cards: list[ExtractCard] = []

        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(context.markdown)
            title = strip_markdown(match.group("title"))
            body = context.markdown[start:end].strip()
            body_text = strip_markdown(body)
            if not title or not body_text:
                continue
            cards.append(
                ExtractCard(
                    front=title,
                    back=body_text,
                    image=find_nearest_image(context.markdown, match.start()),
                    tags=["generic_qa"],
                    meta={"heading_level": str(len(match.group("marks")))},
                )
            )

        return cards
