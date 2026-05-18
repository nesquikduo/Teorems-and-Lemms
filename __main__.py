import os
import json
import fitz

def is_start(word):
    w = word.lower()
    if w == "теорема" or w == "лемма":
        return True
    return False

def extract_blocks(text):
    text = text.replace("\n", " ")
    words = text.split()
    results = []
    i = 0
    while i < len(words):
        if is_start(words[i]):
            block = words[i]
            i += 1
            if i < len(words):
                if words[i].replace(".", "").isdigit():
                    block += " " + words[i]
                    i += 1

            while i < len(words):
                block += " " + words[i]
                if "." in words[i]:
                    break
                i += 1
            results.append(block.strip())
        i += 1
    return results

folder = "pdf_files"
all_results = []

for file in os.listdir(folder):
    if file.endswith(".pdf"):
        doc = fitz.open(os.path.join(folder, file))
        text = ""
        for page in doc:
            text += page.get_text()
        blocks = extract_blocks(text)
        for b in blocks:
            all_results.append({
                "file": file,
                "text": b
            })

with open("result.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print("Готово")