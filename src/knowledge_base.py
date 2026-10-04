import fitz
import os


def load_pdf_with_pages(file_path):
    """
    بترجع قايمة من (رقم الصفحة، نص الصفحة) بدل نص واحد مدموج،
    عشان نقدر نتتبع كل جزء نص جه من أنهي صفحة.
    """
    doc = fitz.open(file_path)
    pages_text = []
    for page_num, page in enumerate(doc, start=1):
        pages_text.append((page_num, page.get_text()))
    return pages_text


def split_into_chunks_with_pages(pages_text, chunk_size=500, overlap=50):
    """
    بتقسم النص الكامل لقطع، وكل قطعة بترجع مع رقم الصفحة اللي بدأت فيها.
    """
    full_text = ""
    page_boundaries = []
    for page_num, page_text in pages_text:
        start_idx = len(full_text)
        full_text += page_text
        end_idx = len(full_text)
        page_boundaries.append((start_idx, end_idx, page_num))

    def get_page_for_index(idx):
        for start, end, page_num in page_boundaries:
            if start <= idx < end:
                return page_num
        return page_boundaries[-1][2] if page_boundaries else 1

    chunks = []
    start = 0
    while start < len(full_text):
        end = start + chunk_size
        chunk_text = full_text[start:end]
        page_num = get_page_for_index(start)
        chunks.append({"text": chunk_text, "page": page_num})
        start = end - overlap
    return chunks


# نسيب الدوال القديمة موجودة كـ backward compatibility لو حاجة تانية بتستخدمها
def load_pdf(file_path):
    pages_text = load_pdf_with_pages(file_path)
    return "".join(text for _, text in pages_text)


def split_into_chunks(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks


if __name__ == "__main__":
    pages_text = load_pdf_with_pages("data/LLMAll_en-US_FINAL.pdf")
    chunks = split_into_chunks_with_pages(pages_text)
    print(f"عدد القطع (chunks): {len(chunks)}")
    print("أول قطعة:")
    print(chunks[0])