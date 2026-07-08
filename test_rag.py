from src.rag.rag_search import search

result = search("How do I stop my SIP permanently?")

print(result["title"])
print(result["answer"])


from src.rag.rag_search import search

result = search("How do I stop SIP forever?")

print(result)