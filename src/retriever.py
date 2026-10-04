import chromadb
from embedder import model
from knowledge_base import load_pdf_with_pages, split_into_chunks_with_pages

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="policies")

# ==== FRAMEWORK KNOWLEDGE (ثابتة، مُعرّفة من الكود فقط - Mapping خبير مسبق) ====
POLICIES = {
    "OWASP": "data/LLMAll_en-US_FINAL.pdf",
    "NIST": "data/nist.ai.100-1.pdf",
    "ISO42001": "data/iso42001_summary.txt",
    "EU_AI_ACT": "data/eu_ai_act_summary.txt",
    "GDPR": "data/gdpr_summary.txt",
}

# سياسات قانونية ملزمة (Regulatory) مقابل سياسات إرشادية (Best-practice)
REGULATORY_POLICIES = {"EU_AI_ACT", "GDPR"}

RISK_CATEGORIES = {
    "prompt_injection": {
        "query": "prompt injection jailbreak ignore previous instructions system prompt extraction instruction override adversarial prompt",
        "policies": ["OWASP"],
    },
    "sensitive_data_exposure": {
        "query": "sensitive data exposure credential leakage confidential information disclosure API keys database credentials",
        "policies": ["OWASP", "GDPR"],
    },
    "privacy_data_protection": {
        "query": "personal data privacy PII data minimization consent transparency data protection third-party sharing anonymization",
        "policies": ["NIST", "OWASP", "ISO42001", "GDPR"],
    },
    "bias_fairness": {
        "query": "bias fairness discrimination protected characteristics disparate impact proxy variables",
        "policies": ["NIST", "ISO42001", "EU_AI_ACT"],
    },
    "human_oversight": {
        "query": "human oversight human review human-in-the-loop accountability override accept recommendation blindly",
        "policies": ["NIST", "ISO42001", "EU_AI_ACT", "GDPR"],
    },
    "transparency_explainability": {
        "query": "transparency explainability disclosure explainable AI users informed",
        "policies": ["NIST", "EU_AI_ACT"],
    },
    "hallucination_reliability": {
        "query": "hallucination reliability accuracy robustness overreliance misinformation",
        "policies": ["NIST", "OWASP"],
    },
    "security_misconfiguration": {
        "query": "security misconfiguration access control excessive agency insecure output handling unauthorized access",
        "policies": ["OWASP"],
    },
    "data_governance_minimization": {
        "query": "data governance data minimization retention policy data quality lawful basis",
        "policies": ["NIST", "ISO42001", "GDPR"],
    },
    "violence_harmful_content": {
        "query": "violence physical harm weapons instructions to hurt or kill someone dangerous illegal activities",
        "policies": ["OWASP", "NIST"],
    },
    "self_harm_content": {
        "query": "self-harm suicide risk vulnerable user safety content moderation duty of care",
        "policies": ["OWASP", "NIST"],
    },
}


def build_policy(policy_name, file_path):
    print(f"بدأت بناء سياسة: {policy_name}")
    if file_path.lower().endswith(".pdf"):
        pages_text = load_pdf_with_pages(file_path)
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        pages_text = [(1, content)]

    chunks = split_into_chunks_with_pages(pages_text)
    texts_only = [c["text"] for c in chunks]
    embeddings = model.encode(texts_only).tolist()

    ids = [f"{policy_name}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"policy": policy_name, "page": c["page"], "is_company_policy": False} for c in chunks]

    collection.add(
        embeddings=embeddings,
        documents=texts_only,
        ids=ids,
        metadatas=metadatas
    )
    print(f"تم تخزين {len(chunks)} قطعة من سياسة {policy_name}")


def build_all_policies():
    for policy_name, file_path in POLICIES.items():
        build_policy(policy_name, file_path)


def list_available_policies():
    """
    بترجع فقط الـ Company Policies المرفوعة (مش الـ Frameworks الثابتة) -
    عشان الواجهة تعرض بس اللي المستخدم يقدر يتحكم فيه (يضيف/يحذف).
    """
    return list_company_policies()


def list_company_policies():
    try:
        all_metadata = collection.get()["metadatas"]
        names = sorted(set(
            m.get("policy") for m in all_metadata
            if m.get("policy") and m.get("is_company_policy") is True
        ))
        return names
    except Exception:
        return []


def list_risk_categories():
    return list(RISK_CATEGORIES.keys())


def is_regulatory(policy_name):
    return policy_name in REGULATORY_POLICIES


def delete_policy(policy_name):
    """
    بتحذف أي سياسة بالاسم - لكن الواجهة بتستدعيها بس على Company Policies
    (مش بتعرض زرار حذف للـ 5 Frameworks الثابتة أصلًا).
    """
    collection.delete(where={"policy": policy_name})


def add_company_policy_from_file(policy_name, file_path):
    """
    ترفع سياسة خاصة بالشركة (Company Policy) - مش Framework.
    بتتفحص تلقائيًا مقابل كل Finding من غير حاجة لـ Mapping مسبق.
    """
    existing = collection.get(where={"policy": policy_name})
    if existing["ids"]:
        delete_policy(policy_name)

    if file_path.lower().endswith(".pdf"):
        pages_text = load_pdf_with_pages(file_path)
    elif file_path.lower().endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        pages_text = [(1, content)]
    else:
        raise ValueError("الملف لازم يكون PDF أو TXT")

    chunks = split_into_chunks_with_pages(pages_text)
    texts_only = [c["text"] for c in chunks]
    embeddings = model.encode(texts_only).tolist()

    ids = [f"{policy_name}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"policy": policy_name, "page": c["page"], "is_company_policy": True} for c in chunks]

    collection.add(
        embeddings=embeddings,
        documents=texts_only,
        ids=ids,
        metadatas=metadatas
    )
    return len(chunks)


def search(query, n_results=3, policy_name=None):
    query_embedding = model.encode([query]).tolist()
    where_filter = {"policy": policy_name} if policy_name else None
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        where=where_filter
    )
    if not results or not results['documents'] or not results['documents'][0]:
        return []
    documents = results['documents'][0]
    metadatas = results['metadatas'][0]
    return [{"text": doc, "page": meta.get("page"), "policy": meta.get("policy")} for doc, meta in zip(documents, metadatas)]


def search_by_category(category, n_results=3, policy_name=None):
    """
    بتدور في:
    1. كل الـ Framework policies المرتبطة بالفئة (Mapping ثابت من الكود)
    2. + أي Company Policy مرفوعة (تلقائيًا، بدون Mapping مسبق - لأنها ديناميكية)
    """
    if category not in RISK_CATEGORIES:
        return [], None

    category_info = RISK_CATEGORIES[category]
    search_query = category_info["query"]

    # إذا تم تحديد سياسة معينة، نبحث فيها فقط
    if policy_name:
        chunks_with_pages = search(search_query, n_results=n_results, policy_name=policy_name)
        return chunks_with_pages, policy_name

    target_policies = list(category_info.get("policies", []))

    # نضيف أي Company Policies مرفوعة تلقائيًا لكل فئة (بدون Mapping مسبق)
    company_policies = list_company_policies()
    target_policies.extend(company_policies)

    if not target_policies:
        return [], None

    MIN_CHUNKS_PER_POLICY = 2
    per_policy_n = max(MIN_CHUNKS_PER_POLICY, n_results // len(target_policies))

    all_chunks = []
    policy_sources = []

    for pol in target_policies:
        res = search(search_query, n_results=per_policy_n, policy_name=pol)
        if res:
            all_chunks.extend(res)
            policy_sources.append(pol)

    combined_sources = ", ".join(policy_sources) if policy_sources else target_policies[0]
    return all_chunks, combined_sources


if __name__ == "__main__":
    for policy_name, file_path in POLICIES.items():
        existing = collection.get(where={"policy": policy_name})
        if not existing["ids"]:
            build_policy(policy_name, file_path)

    print("\nالسياسات المتاحة (Frameworks):", list(POLICIES.keys()))
    print("سياسات الشركة المرفوعة:", list_company_policies())
    print("فئات المخاطر المتاحة:", list_risk_categories())