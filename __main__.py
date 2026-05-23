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

def clean_metadata_line(text):
    text = clean_text(text)
    text = re.sub(r'([А-Яа-яЁёA-Za-z])\d+$', r'\1', text)

    return text.strip()

def normalize_authors(authors):
    result = []

    if not isinstance(authors, list):
        return result

    for author in authors:
        if isinstance(author, str):
            result.append(author.strip())

        elif isinstance(author, dict):
            name = author.get("name", "")

            if name:
                result.append(name.strip())

    return result


def ask_qwen_for_metadata(lines):
    lines_text = json.dumps(lines, ensure_ascii=False, indent=2)

    prompt = f"""
Ты извлекаешь метаданные русскоязычной научной статьи.

Тебе дан список строк с первой страницы PDF.
У каждой строки есть:
- line_number
- text
- font_size
- x
- y

Нужно найти:
1. Название статьи.
2. Автора или авторов статьи.

Очень важные правила:
- Верни только JSON.
- Не придумывай данные.
- Бери данные только из переданных строк.
- Автор — это человек: фамилия и инициалы.
- Примеры автора: "И. А. Горбунов", "Д.В. Зайцев", "Зайцев Д. В.", "И.Е. Малова".
- Название статьи НЕ может состоять только из имени автора.
- Если строка выглядит как "Д.В. Зайцев", это автор, а не название.
- Название статьи обычно находится рядом с автором: выше или ниже.
- Название может быть написано заглавными буквами.
- Не бери УДК.
- Не бери название журнала.
- Не бери название университета.
- Не бери слова "Аннотация" и "Ключевые слова".
- Не бери должности, степени и звания как часть имени автора.
- Если в строке есть автор, запятая и должность, оставь только имя автора.
- authors должен быть списком строк, а не списком объектов.
- Если первая строка самая крупная и не похожа на имя человека, почти всегда это название статьи.
- Если следующая строка похожа на ФИО, это автор.
- Удали сноски из названия, например "логики1" -> "логики".

Верни строго в таком формате:

{{
  "title": "",
  "authors": []
}}

Строки первой страницы:
{lines_text}
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
            print("Ошибка Ollama:", response.status_code)
            print(response.text)

            return {
                "title": "",
                "authors": []
            }

        answer = response.json()["response"].strip()
        data = json.loads(answer)

        title = data.get("title", "")
        authors = normalize_authors(data.get("authors", []))

        return {
            "title": title.strip(),
            "authors": authors
        }

    except Exception as error:
        print("Ошибка при обращении к Qwen:", error)

        return {
            "title": "",
            "authors": []
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
            x0, y0, x1, y1 = line["bbox"]

            for span in line["spans"]:
                text += span["text"]
                max_size = max(max_size, span["size"])

            text = clean_metadata_line(text)

            if text:
                lines.append({
                    "text": text,
                    "font_size": round(max_size, 2),
                    "x": round(x0, 2),
                    "y": round(y0, 2)
                })

    lines = sorted(lines, key=lambda item: (item["y"], item["x"]))

    useful_lines = []

    for index, line in enumerate(lines[:40], start=1):
        text_lower = line["text"].lower()

        if "аннотация" in text_lower or "ключевые слова" in text_lower:
            break

        useful_lines.append({
            "line_number": index,
            "text": line["text"],
            "font_size": line["font_size"],
            "x": line["x"],
            "y": line["y"]
        })

    return ask_qwen_for_metadata(useful_lines)


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
            "text": block_text,
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

        article_metadata = extract_article_metadata(doc)

        article_title = article_metadata.get("title", "")
        article_authors = article_metadata.get("authors", [])

        for page_num, page in enumerate(doc):
            text = page.get_text()

            blocks = extract_blocks(text)

            for block in blocks:
                all_results.append({
                    "file": file,
                    "article_title": article_title,
                    "article_authors": article_authors,
                    "page": page_num + 1,
                    "type": block["type"],
                    "text": block["text"],
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