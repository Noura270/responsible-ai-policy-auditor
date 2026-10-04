'''print("EMBEDDER FILE STARTED")
from sentence_transformers import SentenceTransformer

# تحميل نموذج embeddings
model = SentenceTransformer("all-MiniLM-L6-v2")


def get_embeddings(chunks):
    """
    تحويل النصوص (chunks) إلى embeddings
    """
    embeddings = model.encode(chunks)
    return embeddings


# 🟢 اختبار سريع للتأكد أن الملف شغال
if __name__ == "__main__":
    test_chunks = [
        "AI is transforming the world",
        "OWASP Top 10 for LLM Applications"
    ]

    embeddings = get_embeddings(test_chunks)

    print("Number of chunks:", len(test_chunks))
    print("Number of embeddings:", len(embeddings))
    print("Embedding dimension:", len(embeddings[0]))'''
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

def get_embeddings(chunks):
    embeddings = model.encode(chunks)
    return embeddings

if __name__ == "__main__":
    sample_chunks = ["مرحبا بالعالم", "كيف الحال", "OWASP security risks"]
    result = get_embeddings(sample_chunks)
    print(f"شكل النتيجة: {result.shape}")
    print("أول embedding:")
    print(result[0][:10])