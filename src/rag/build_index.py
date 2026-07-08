import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

with open("data/faqs.json", "r", encoding="utf-8") as f:
    faqs = json.load(f)

texts = []

for faq in faqs:
    examples = " ".join(faq.get("examples", []))

    text = (
        faq["title"] + " "
         + examples + " "
        + faq["answer"]
)
    texts.append(text)

embeddings = model.encode(texts)

index = faiss.IndexFlatL2(embeddings.shape[1])
index.add(np.array(embeddings, dtype=np.float32))

faiss.write_index(index, "faq.index")

with open("faq_meta.json", "w", encoding="utf-8") as f:
    json.dump(faqs, f)

print("Index created successfully")