import os
import json
import fitz
import re

from natasha import Segmenter
from natasha import Doc

segmenter = Segmenter()

def normalize_text(text):

    doc = Doc(text)
    doc.segment(segmenter)

    clean_text = ""

    for token in doc.tokens:
        clean_text += token.text + " "

    return clean_text

def extract_blocks(text):

    text = text.replace("\n", " ")

    # обработка Natasha
    text = normalize_text(text)

    pattern = r'(Теорема(?:\s+\d+)?\s*\.\s.*?\.)|(Лемма(?:\s+\d+)?\s*\.\s.*?\.)'

    matches = re.findall(pattern, text)

    results = []

    for theorem, lemma in matches:

        if theorem:
            results.append(theorem.strip())

        if lemma:
            results.append(lemma.strip())

    return results

folder = "pdf_files"

all_results = []

for file in os.listdir(folder):

    if file.endswith(".pdf"):

        path = os.path.join(folder, file)

        doc = fitz.open(path)

        text = ""

        for page in doc:
            text += page.get_text()

        blocks = extract_blocks(text)

        for block in blocks:

            all_results.append({
                "file": file,
                "text": block
            })

with open("result.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print("Готово")