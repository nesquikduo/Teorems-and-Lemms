import os
import json
import fitz
import re

from natasha import Segmenter
from natasha import Doc

segmenter = Segmenter()

def clean_text(text):
    text = re.sub(r'(\w)-\s+(\w)', r'\1\2', text)
    text = text.replace("\n", " ")
    text = text.replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    return text

def normalize_text(text):
    doc = Doc(text)
    doc.segment(segmenter)
    clean = ""
    for token in doc.tokens:
        clean += token.text + " "
    return clean.strip()

def extract_blocks(text):
    text = clean_text(text)
    pattern = r'(Теорема(?:\s+\d+)?\s*[.-]\s.*?\.)|(Лемма(?:\s+\d+)?\s*[.-]\s.*?\.)'
    matches = re.findall(pattern, text)
    results = []
    for theorem, lemma in matches:
        if theorem:
            results.append({
                "type": "theorem",
                "text": normalize_text(theorem)
            })
        if lemma:
            results.append({
                "type": "lemma",
                "text": normalize_text(lemma)
            })
    return results

folder = "pdf_files"

all_results = []

for file in os.listdir(folder):
    if file.endswith(".pdf"):
        path = os.path.join(folder, file)
        doc = fitz.open(path)
        metadata = doc.metadata
        author = metadata.get("author", "")
        for page_num, page in enumerate(doc):
            text = page.get_text()
            blocks = extract_blocks(text)
            for block in blocks:
                all_results.append({
                    "file": file,
                    "author": author,
                    "page": page_num + 1,
                    "type": block["type"],
                    "text": block["text"]
                })

with open("result.json", "w", encoding="utf-8") as f:

    json.dump(
        all_results,
        f,
        ensure_ascii=False,
        indent=4
    )

print("Готово")