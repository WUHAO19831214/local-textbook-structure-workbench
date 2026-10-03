#!/usr/bin/env python3
"""Check page-anchored DOCX figures against referenced Docling picture boxes."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

EMUS_PER_POINT = 12700
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def dataset_json(directory: Path) -> dict:
    preferred = directory / f"{directory.name}.json"
    for path in [preferred, *sorted(directory.glob("*.json"))]:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data.get("pages"), dict) and isinstance(data.get("pictures"), list):
            return data
    raise ValueError("No Docling JSON with pages and pictures was found")


def picture_refs(data: dict) -> set[int]:
    body = data.get("body") or {}
    children = body.get("children")
    if not isinstance(children, list):
        return set(range(len(data["pictures"])))
    found: set[int] = set()
    visited: set[str] = set()

    def visit(ref: str) -> None:
        if ref in visited or not ref.startswith("#/"):
            return
        visited.add(ref)
        parts = ref[2:].split("/")
        if len(parts) != 2:
            return
        kind, number = parts
        try:
            index = int(number)
            node = data[kind][index]
        except (KeyError, IndexError, TypeError, ValueError):
            return
        if kind == "pictures":
            found.add(index)
        for child in node.get("children", []):
            if isinstance(child, dict) and isinstance(child.get("$ref"), str):
                visit(child["$ref"])

    for child in children:
        if isinstance(child, dict) and isinstance(child.get("$ref"), str):
            visit(child["$ref"])
    return found


def expected_boxes(data: dict) -> dict[tuple[int, int], tuple[float, float, float, float]]:
    result = {}
    for index in picture_refs(data):
        picture = data["pictures"][index]
        provenance = picture.get("prov") or []
        if not provenance:
            continue
        page = provenance[0].get("page_no")
        bbox = provenance[0].get("bbox") or {}
        if page is None or not all(key in bbox for key in ("l", "t", "r", "b")):
            continue
        size = data["pages"].get(str(page), {}).get("size", {})
        width, height = float(size.get("width") or 595), float(size.get("height") or 841)
        left, right = max(0.0, float(bbox["l"])), min(width, float(bbox["r"]))
        if bbox.get("coord_origin") == "BOTTOMLEFT":
            top, bottom = height - float(bbox["t"]), height - float(bbox["b"])
        else:
            top, bottom = float(bbox["t"]), float(bbox["b"])
        top, bottom = max(0.0, top), min(height, bottom)
        if right > left and bottom > top:
            result[(int(page), index)] = (left, top, right, bottom)
    return result


def anchored_boxes(docx_path: Path) -> dict[tuple[int, int], tuple[float, float, float, float]]:
    with ZipFile(docx_path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    result = {}
    for anchor in root.findall(f".//{{{WP}}}anchor"):
        doc_pr = anchor.find(f"{{{WP}}}docPr")
        description = doc_pr.get("descr", "") if doc_pr is not None else ""
        try:
            page_text, index_text = description.split(";")
            key = (int(page_text.split("=")[1]), int(index_text.split("=")[1]))
            x = int(anchor.find(f"{{{WP}}}positionH/{{{WP}}}posOffset").text) / EMUS_PER_POINT
            y = int(anchor.find(f"{{{WP}}}positionV/{{{WP}}}posOffset").text) / EMUS_PER_POINT
            extent = anchor.find(f"{{{WP}}}extent")
            width = int(extent.get("cx")) / EMUS_PER_POINT
            height = int(extent.get("cy")) / EMUS_PER_POINT
        except (AttributeError, IndexError, TypeError, ValueError):
            raise ValueError(f"Unidentified or incomplete image anchor: {description!r}") from None
        if key in result:
            raise ValueError(f"Duplicate image anchor: {key}")
        result[key] = (x, y, x + width, y + height)
    return result


def max_difference(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    return max(abs(a - b) for a, b in zip(first, second))


def formula_fallback_counts(docx_path: Path) -> dict[int, int]:
    with ZipFile(docx_path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    counts: dict[int, int] = {}
    for image in root.findall(f".//{{{WP}}}inline"):
        description = image.find(f"{{{WP}}}docPr")
        value = description.get("descr", "") if description is not None else ""
        if not value.endswith(";OCR-formula-fallback"):
            continue
        try:
            page = int(value.split(";")[0].split("=")[1])
        except (IndexError, ValueError):
            raise ValueError(f"Invalid formula fallback description: {value!r}") from None
        counts[page] = counts.get(page, 0) + 1
    return counts


def rendered_errors(
    path: Path, expected: dict, fallback_counts: dict[int, int],
    page_count: int, tolerance: float,
) -> tuple[list[str], float]:
    import pymupdf

    errors = []
    maximum = 0.0
    with pymupdf.open(path) as pdf:
        if pdf.page_count != page_count:
            errors.append(f"Rendered page count {pdf.page_count} differs from source {page_count}")
        for page_number in range(1, min(pdf.page_count, page_count) + 1):
            boxes = [box for (page, _), box in expected.items() if page == page_number]
            actual = [tuple(info["bbox"]) for info in pdf[page_number - 1].get_image_info(xrefs=True)]
            expected_total = len(boxes) + fallback_counts.get(page_number, 0)
            if len(actual) != expected_total:
                errors.append(f"Page {page_number}: expected {expected_total} images, rendered {len(actual)}")
                continue
            for box in boxes:
                match = min(actual, key=lambda candidate: sum(abs(a - b) for a, b in zip(box, candidate)))
                actual.remove(match)
                difference = max_difference(box, match)
                maximum = max(maximum, difference)
                if difference > tolerance:
                    errors.append(f"Page {page_number}: rendered image differs by {difference:.2f} pt")
    return errors, maximum


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--rendered-pdf", type=Path)
    parser.add_argument("--tolerance-pt", type=float, default=0.5)
    args = parser.parse_args()
    data = dataset_json(args.dataset)
    expected = expected_boxes(data)
    actual = anchored_boxes(args.docx)
    errors = []
    for key in sorted(expected.keys() - actual.keys()):
        errors.append(f"Missing anchor for page {key[0]} picture {key[1]}")
    for key in sorted(actual.keys() - expected.keys()):
        errors.append(f"Unexpected anchor for page {key[0]} picture {key[1]}")
    maximum = 0.0
    for key in expected.keys() & actual.keys():
        difference = max_difference(expected[key], actual[key])
        maximum = max(maximum, difference)
        if difference > args.tolerance_pt:
            errors.append(f"Page {key[0]} picture {key[1]} differs by {difference:.2f} pt")
    rendered_maximum = None
    if args.rendered_pdf:
        rendered_problems, rendered_maximum = rendered_errors(
            args.rendered_pdf, expected, formula_fallback_counts(args.docx),
            len(data["pages"]), args.tolerance_pt
        )
        errors.extend(rendered_problems)
    print(json.dumps({"pictures": len(expected), "max_docx_error_pt": round(maximum, 3),
                      "max_rendered_error_pt": round(rendered_maximum, 3) if rendered_maximum is not None else None,
                      "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
