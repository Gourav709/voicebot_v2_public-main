import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

index = faiss.read_index("faq.index")

with open("faq_meta.json", "r", encoding="utf-8") as f:
    faqs = json.load(f)


def search(query):

    query_embedding = model.encode([query])

    distances, indices = index.search(
        np.array(query_embedding, dtype=np.float32),
        3
    )
    print("DISTANCES:", distances)
    print("INDICES:", indices)

    results = []

    for i, idx in enumerate(indices[0]):
       distance = distances[0][i]

       if distance < 1.5:
        results.append(faqs[idx])

    return results