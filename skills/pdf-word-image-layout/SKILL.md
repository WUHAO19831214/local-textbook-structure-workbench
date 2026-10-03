---
name: pdf-word-image-layout
description: Preserve figure positions when exporting a scanned or OCR PDF dataset to editable Word, and verify image coordinates against the source PDF. Use when Word images drift, jump pages, or overlap OCR text.
---

# PDF to Word image placement

For a scanned PDF, keep the source PDF page size and read each figure's page number and bounding box from the dataset JSON. Docling boxes may use a bottom-left origin: convert `top = page_height - bbox.t`. Insert each figure into DOCX as a floating `wp:anchor` whose horizontal and vertical positions are relative to the page, with its dimensions taken from the same box. Put the anchors in a short paragraph at the start of their source page so editable text reflow does not move the images. Ignore picture objects no longer referenced by the document tree after OCR corrections.

Choose the output deliberately. A full-page raster image can reproduce the PDF visually but is not independently editable. Page-anchored figures with OCR text keep images in place and text editable; text fonts, formulas, and line breaks can still differ from the PDF. Do not promise pixel-perfect editable reconstruction without verifying it.

After export, render the DOCX to PDF and run `scripts/verify_image_positions.py` with the dataset directory, DOCX, and rendered PDF. Confirm every referenced picture appears once, page count matches, and position error is within a suitable tolerance (normally 0.5 pt). Inspect pages with crowded figures and revise before delivery. If the dataset lacks reliable picture boxes, stop claiming coordinate accuracy and use page-image facsimile for visual fidelity.

Example:

```bash
python3 scripts/verify_image_positions.py \
  /absolute/path/to/dataset \
  /absolute/path/to/dataset/exports/name_layout_editable.docx \
  --rendered-pdf /absolute/path/to/rendered.pdf
```
