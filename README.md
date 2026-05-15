# Local Textbook Structure Workbench

“本地教材 / 文档结构化工作台”用于加载本地教材导出目录，整合 Markdown、图片和 JSON 元信息，提供阅读、章节整理、动态脑图、规则抽取和 Anki CSV 导出能力。

当前实现范围聚焦本地结构化阅读与规则化提取；没有实现 RAG、ChromaDB、Embedding 或 BBox 坐标高亮。

## Features

- 本地数据集加载：校验 Markdown、JSON 和 `images/` 目录，并动态挂载静态图片资源。
- Markdown 阅读器：渲染 Markdown 正文与相对路径图片，支持章节点击滚动定位。
- 章节标题整理：结合 Markdown 标题、字号线索与 JSON 页码信息，整理一级/二级标题，可按课时、单词、文型、例文、会话、文法和练习筛选。
- 动态脑图：从章节层级生成 Markmap 脑图，支持拖拽、滚轮缩放、放大、缩小和归正。
- 规则抽取与制卡：支持日语词汇模板、通用问答模板和自定义正则模板，按目录范围预览并导出 UTF-8-SIG Anki CSV。

## Directory

```text
backend/
  app/
    __init__.py
    dataset_validator.py
    models.py
    main.py
    extractors/
      __init__.py
      base.py
      custom_regex.py
      generic_qa.py
      japanese_vocab.py
  requirements.txt
frontend/
  index.html
  package.json
  postcss.config.js
  tailwind.config.js
  vite.config.js
  src/
    App.vue
    main.js
    style.css
examples/
  sample_dataset/
```

## Run

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`.

## Dataset Shape

```text
your_dataset/
  lesson.md
  lesson.json
  images/
    page_001.png
```

在顶部输入数据集目录的绝对路径，点击“加载目录”即可开始阅读和抽取。
