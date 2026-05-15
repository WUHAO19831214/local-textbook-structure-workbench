from __future__ import annotations

import re
from typing import List

from app.extractors.base import ExtractContext, Extractor, find_nearest_image, strip_markdown
from app.models import ExtractCard


class JapaneseVocabExtractor(Extractor):
    """Regex-based MVP extractor for common Japanese vocabulary lines."""

    patterns = [
        re.compile(
            r"(?P<term>[\u3400-\u9fff\u3040-\u30ff々〆ヶー]+)"
            r"[（(【\[](?P<reading>[\u3040-\u30ffー・]+)[）)】\]]"
            r"\s*(?P<pos>[名動形副連接助詞]+詞?|名|動|形|副)?"
            r"[:：\-\s]*(?P<meaning>[^\n|。]{2,80})"
        ),
        re.compile(
            r"^\s*[-*]?\s*(?P<term>[\u3400-\u9fff\u3040-\u30ff々〆ヶー]{2,})"
            r"\s*[|/／]\s*(?P<reading>[\u3040-\u30ffー・]+)"
            r"\s*[|/／]\s*(?P<pos>[^|/／\n]{1,12})"
            r"\s*[|/／]\s*(?P<meaning>[^\n]{2,80})",
            re.MULTILINE,
        ),
    ]

    def extract(self, context: ExtractContext) -> List[ExtractCard]:
        cards: list[ExtractCard] = []
        seen: set[tuple[str, str]] = set()

        for pattern in self.patterns:
            for match in pattern.finditer(context.markdown):
                term = strip_markdown(match.group("term"))
                reading = strip_markdown(match.group("reading"))
                pos = strip_markdown(match.groupdict().get("pos") or "")
                meaning = strip_markdown(match.group("meaning")).strip(" ：:-|")
                if not term or not reading or not meaning:
                    continue
                key = (term, reading)
                if key in seen:
                    continue
                seen.add(key)
                front = f"{term}（{reading}）"
                back_parts = [part for part in (pos, meaning) if part]
                cards.append(
                    ExtractCard(
                        front=front,
                        back=" / ".join(back_parts),
                        image=find_nearest_image(context.markdown, match.start()),
                        tags=["japanese_vocab"],
                        meta={"term": term, "reading": reading, "pos": pos},
                    )
                )

        return cards
