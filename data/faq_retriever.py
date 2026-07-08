import json
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)

with open("faq.json", "r") as f:
    faqs = json.load(f)

questions = []

for faq in faqs:
    questions.append(faq["title"])

embeddings = model.encode(
    questions,
    convert_to_numpy=True
)

def get_answer(user_question):

    query_embedding = model.encode(
        [user_question],
        convert_to_numpy=True
    )

    similarities = cosine_similarity(
        query_embedding,
        embeddings
    )[0]

    best_idx = similarities.argmax()
    best_score = similarities[best_idx]

    if best_score < 0.5:
        return None

    return faqs[best_idx]["answer"]