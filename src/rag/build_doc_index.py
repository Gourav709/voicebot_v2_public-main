import os
import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader
from docx import Document

model = SentenceTransformer("all-MiniLM-L6-v2")

chunks = []

for filename in os.listdir("docs"):

    path = os.path.join("docs", filename)

    if filename.endswith(".txt"):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

    elif filename.endswith(".pdf"):
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"

    elif filename.endswith(".docx"):
        doc = Document(path)
        text = "\n".join([para.text for para in doc.paragraphs])

    else:
        continue

    chunk_size = 300

    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]

        chunks.append({
            "source": filename,
            "text": chunk
        })

texts = [c["text"] for c in chunks]

embeddings = model.encode(texts)

index = faiss.IndexFlatL2(
    embeddings.shape[1]
)

index.add(
    np.array(embeddings, dtype=np.float32)
)

faiss.write_index(index, "doc.index")

with open(
    "doc_meta.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        chunks,
        f,
        ensure_ascii=False,
        indent=2
    )

print("Document index created")