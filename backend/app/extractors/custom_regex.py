from __future__ import annotations

import re
from typing import List

from app.extractors.base import ExtractContext, Extractor, find_nearest_image, strip_markdown
from app.models import ExtractCard


class CustomRegexExtractor(Extractor):
    def extract(self, context: ExtractContext) -> List[ExtractCard]:
        if not context.custom_regex:
            return []

        pattern = re.compile(context.custom_regex, re.MULTILINE | re.DOTALL)
        cards: list[ExtractCard] = []

        for match in pattern.finditer(context.markdown):
            groups = match.groupdict()
            if groups:
                front = groups.get("front") or groups.get("Front") or ""
                back = groups.get("back") or groups.get("Back") or ""
                image = groups.get("image") or groups.get("Image")
            else:
                front = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                back = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
                image = match.group(3) if match.lastindex and match.lastindex >= 3 else None

            front = strip_markdown(front)
            back = strip_markdown(back)
            if not front or not back:
                continue

            cards.append(
                ExtractCard(
                    front=front,
                    back=back,
                    image=(image or find_nearest_image(context.markdown, match.start())),
                    tags=["custom_regex"],
                )
            )

        return cards
