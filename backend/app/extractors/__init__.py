from app.extractors.base import Extractor
from app.extractors.custom_regex import CustomRegexExtractor
from app.extractors.generic_qa import GenericQaExtractor
from app.extractors.japanese_vocab import JapaneseVocabExtractor


EXTRACTORS = {
    "japanese_vocab": JapaneseVocabExtractor(),
    "generic_qa": GenericQaExtractor(),
    "custom_regex": CustomRegexExtractor(),
}


def get_extractor(template: str) -> Extractor:
    try:
        return EXTRACTORS[template]
    except KeyError as exc:
        raise ValueError(f"不支持的抽取模板：{template}") from exc
