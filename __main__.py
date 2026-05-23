import os
import json
import fitz
import re
import requests

from natasha import Segmenter
from natasha import Doc

segmenter = Segmenter()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b"


def clean_text(text):
    text = re.sub(r'(\w)-\s+(\w)', r'\1\2', text)
    text = text.replace("\n", " ")
    text = text.replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(text):
    doc = Doc(text)
    doc.segment(segmenter)

    clean = ""

    for token in doc.tokens:
        clean += token.text + " "

    return clean.strip()


def ask_qwen_for_metadata(text):
    prompt = f"""
Ты извлекаешь метаданные из научной статьи.

Нужно найти только:
1. название статьи
2. автора или авторов

Нельзя придумывать данные.
Нельзя брать название раздела как название статьи.
Нельзя брать abstract, ключевые слова, введение, предисловие как название.

Верни строго JSON:
{{
  "title": "",
  "authors": []
}}

Текст:
{text}
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0
                }
            },
            timeout=180
        )

        if response.status_code != 200:
            return {
                "title": "",
                "authors": [],
                "ollama_error": response.text
            }

        answer = response.json()["response"].strip()

        return json.loads(answer)

    except Exception as error:
        return {
            "title": "",
            "authors": [],
            "ollama_error": str(error)
        }

def extract_article_metadata(doc):
    page = doc[0]

    page_dict = page.get_text("dict")

    lines = []

    for block in page_dict["blocks"]:
        if block.get("type") != 0:
            continue

        for line in block["lines"]:
            text = ""

            max_size = 0
            y = line["bbox"][1]

            for span in line["spans"]:
                text += span["text"]
                max_size = max(max_size, span["size"])

            text = clean_text(text)

            if text:
                lines.append({
                    "text": text,
                    "font_size": max_size,
                    "y": y
                })

    lines = sorted(lines, key=lambda item: item["y"])

    candidates = []

    for line in lines[:15]:
        text = line["text"]

        if len(text) < 3:
            continue

        if text.lower() in ["abstract", "аннотация", "ключевые слова"]:
            continue

        candidates.append(line)

    title = ""
    authors = []

    for item in candidates:
        text = item["text"]

        if not title and item["font_size"] >= 13:
            title = re.sub(r"\d+$", "", text).strip()
            continue

        if title and not authors:
            if re.search(r"[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*[А-ЯЁ][а-яё]+", text):
                authors.append(text.strip())
                break

    if title or authors:
        return {
            "title": title,
            "authors": authors
        }

    first_pages_text = ""

    max_pages = min(2, len(doc))

    for page_num in range(max_pages):
        first_pages_text += doc[page_num].get_text() + "\n"

    first_pages_text = clean_text(first_pages_text)

    if len(first_pages_text) > 3000:
        first_pages_text = first_pages_text[:3000]

    return ask_qwen_for_metadata(first_pages_text)


def extract_blocks(text):
    text = clean_text(text)

    pattern = (
        r'('
        r'(Теорема|Лемма)'
        r'(?:\s+\d+(?:\.\d+)*)?'
        r'\s*[.\-—:]'
        r'\s*'
        r'.*?'
        r')'
        r'(?='
        r'\s+(?:Теорема|Лемма|Доказательство|Следствие|Определение|Замечание|Пример)'
        r'(?:\s+\d+(?:\.\d+)*)?'
        r'\s*[.\-—:]'
        r'|$'
        r')'
    )

    matches = re.finditer(pattern, text, flags=re.IGNORECASE)

    results = []

    for match in matches:
        block_text = match.group(1).strip()
        block_type_word = match.group(2).lower()

        if "теорема" in block_type_word:
            block_type = "theorem"
        elif "лемма" in block_type_word:
            block_type = "lemma"
        else:
            continue

        results.append({
            "type": block_type,
            "text": normalize_text(block_text),
            "raw_text": block_text,
            "start_index": match.start(),
            "end_index": match.end()
        })

    return results


folder = "pdf_files"

all_results = []

for file in os.listdir(folder):
    if file.endswith(".pdf"):
        path = os.path.join(folder, file)

        print(f"Обрабатываю файл: {file}")

        doc = fitz.open(path)

        pdf_metadata = doc.metadata

        article_metadata = extract_article_metadata(doc)

        pdf_author = pdf_metadata.get("author", "")

        article_title = article_metadata.get("title", "")
        article_authors = article_metadata.get("authors", [])

        for page_num, page in enumerate(doc):
            text = page.get_text()

            blocks = extract_blocks(text)

            for block in blocks:
                all_results.append({
                    "file": file,
                    "pdf_author_metadata": pdf_author,
                    "article_title": article_title,
                    "article_authors": article_authors,
                    "page": page_num + 1,
                    "type": block["type"],
                    "text": block["text"],
                    "raw_text": block["raw_text"],
                    "start_index": block["start_index"],
                    "end_index": block["end_index"]
                })

with open("result.json", "w", encoding="utf-8") as f:
    json.dump(
        all_results,
        f,ensure_ascii=False,
        indent=4
    )

print("Готово")