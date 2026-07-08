import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

index = faiss.read_index("doc.index")

with open(
    "doc_meta.json",
    "r",
    encoding="utf-8"
) as f:
    docs = json.load(f)

def search(query):

    query_embedding = model.encode([query])

    distances, indices = index.search(
        np.array(
            query_embedding,
            dtype=np.float32
        ),
        3
    )

    best_idx = indices[0][0]

    return docs[best_idx]