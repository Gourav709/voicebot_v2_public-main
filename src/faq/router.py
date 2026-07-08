from typing import List, Dict
from src.rag.rag_search import search


class FAQRouter:
    def __init__(self, faqs: list):
        self.faqs = faqs

    def get_kb_context(self, user_text: str, k: int = 2) -> List[Dict]:

        print("\nRAG SEARCH:", user_text)

        faqs = search(user_text)

        if not faqs:
            return []

        # Print retrieved FAQs
        for faq in faqs:
            print(" ->", faq["faq_id"], "-", faq["title"])

        return [
            {
                "faq_id": faq.get("faq_id", ""),
                "question": faq.get("title", ""),
                "answer": faq.get("answer", "")
            }
            for faq in faqs
        ]