import streamlit as st
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from evaluator import evaluate_content, evaluate_system
from db import init_db, log_evaluation
from retriever import list_available_policies, add_company_policy_from_file, delete_policy
from dashboard import render_dashboard

init_db()

st.set_page_config(page_title="Responsible AI Policy Auditor", layout="centered")
st.title("Responsible AI Policy Auditor")

page = st.sidebar.radio("Navigation", ["Review", "Dashboard"])

if page == "Dashboard":
    render_dashboard()
    st.stop()

with st.expander("ℹ️ منهجية تقييم الخطورة (Risk Matrix)"):
    st.markdown("""
    **Risk Score = Likelihood (1-5) × Impact (1-5)**
    - 1–4 → **Low**
    - 5–9 → **Medium**
    - 10–19 → **High**
    - 20–25 → **Critical**

    **الـ Risk Level والـ Decision محسوبين بشكل مستقل تمامًا عن بعض:**
    - **Risk Level** = مبني على Likelihood × Impact بس (جسامة الموقف)
    - **Decision** = مبني على قوة الدليل بس (🟢 Compliant / 🟡 Evidence Required / 🔴 Non-Compliant)
    """)

language = st.radio("لغة التقرير / Report language:", ["Arabic", "English"], horizontal=True)

mode = st.radio("اختار نوع المراجعة:", ["مراجعة محتوى", "تقييم نظام"])

st.divider()


def _render_bullet_lines(text):
    lines = [line.strip("-•* ").strip() for line in text.split("\n") if line.strip()]
    return lines if len(lines) > 1 else [text]


def display_result(result):
    st.divider()

    decision = result.get("decision", "")
    risk_level = result.get("risk_level", "")

    decision_colors = {"Compliant": "green", "Violation": "red", "Needs Review": "orange", "Partially Compliant": "blue"}
    color = decision_colors.get(decision, "gray")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Decision:** :{color}[{decision}]")
    with col2:
        st.markdown(f"**Risk Level:** {risk_level}")

    if result.get("summary_justification"):
        st.markdown("**Summary:**")
        st.info(result["summary_justification"])

    findings = result.get("findings", [])

    if not findings:
        st.success("لا توجد نتائج (Findings) مرصودة." if language == "Arabic" else "No findings identified.")
        return

    st.markdown(f"**عدد النتائج (Findings): {len(findings)}**")

    for i, finding in enumerate(findings):
        severity = finding.get("severity", "")
        severity_colors = {"Low": "blue", "Medium": "orange", "High": "red", "Critical": "red"}
        s_color = severity_colors.get(severity, "gray")
        violations = finding.get("policy_violations", [])
        finding_compliance = finding.get("compliance_status", "")

        header = f"Finding {i+1}: {finding.get('category', '')} — Risk: :{s_color}[{severity}]"
        if finding_compliance:
            header += f" | Compliance: {finding_compliance}"
        if violations:
            header += f" ({len(violations)} policy note{'s' if len(violations) != 1 else ''})"

        with st.expander(header):
            has_controls = finding.get("has_controls", False)
            if has_controls:
                st.markdown("🛡️ _Controls detected in the description_")

            likelihood = finding.get("likelihood")
            impact = finding.get("impact")
            risk_score = finding.get("risk_score")
            if likelihood is not None and impact is not None:
                lcol, icol, scol = st.columns(3)
                with lcol:
                    st.metric("Likelihood", f"{likelihood}/5")
                with icol:
                    st.metric("Impact", f"{impact}/5")
                with scol:
                    st.metric("Risk Score", f"{risk_score}/25")

            st.markdown("**Justification:**")
            st.info(finding.get("justification", ""))

            if violations:
                st.markdown(f"**Policy Assessments ({len(violations)}):**")
                for v_idx, v in enumerate(violations):
                    policy_name = v.get("policy", "Unknown")
                    source = v.get("source", "")
                    page_num = v.get("page")
                    page_str = f", p. {page_num}" if page_num else ""
                    compliance = v.get("compliance_status", "")
                    status_icons = {"Non-Compliant": "🔴", "Evidence Required": "🟡", "Compliant": "🟢"}
                    status_icon = status_icons.get(compliance, "⚪")
                    st.markdown("---")
                    st.markdown(f"**{v_idx + 1}. {policy_name}** _(Source: {source}{page_str})_ — {status_icon} {compliance}")
                    for e in v.get("evidence", []):
                        st.write(f"   • {e}")
            else:
                st.caption("لا توجد مخالفة سياسة محددة موثّقة لهذه الفئة." if language == "Arabic" else "No specific policy note documented for this category.")

            st.markdown("**Recommendation:**")
            for line in _render_bullet_lines(finding.get("recommendation", "")):
                st.success(f"• {line}")

    if result.get("summary_recommendation"):
        st.markdown("**Overall Recommendation:**")
        st.warning(result["summary_recommendation"])


if mode == "مراجعة محتوى":
    content_type_options = {
        "رسالة مستخدم (Prompt)": "User Prompt",
        "رد AI": "AI Response",
        "محادثة كاملة": "Full Conversation",
        "وصف نظام (System Description)": "System Description"
    }
    content_type_display = st.selectbox("نوع المحتوى", list(content_type_options.keys()))
    content_type = content_type_options[content_type_display]

    reason = st.text_input("سبب المراجعة", value="Routine review")
    content = st.text_area("المحتوى المراد فحصه", height=120)

    if st.button("قيّم المحتوى"):
        if content.strip() == "":
            st.warning("من فضلك اكتبي المحتوى الأول")
        else:
            with st.spinner("بنحلل المحتوى... (مرحلتين: تحديد المخاطر ثم مطابقة السياسات)"):
                result = evaluate_content(
                    content=content,
                    content_type=content_type,
                    reason=reason,
                    language=language
                )
                log_evaluation(result, mode="content", content_type=content_type, reason=reason, language=language)
            display_result(result)

else:
    st.markdown("### القسم 1: هوية النظام")
    system_name = st.text_input("اسم النظام")

    ai_type = st.radio("نوع الكيان المُقيَّم:", ["AI Model", "AI System"], horizontal=True)

    source_type = st.radio("مصدر النظام:", ["In-house (اتبنى داخليًا)", "Third-party (Vendor خارجي)"], horizontal=True)
    vendor_name = ""
    if source_type == "Third-party (Vendor خارجي)":
        vendor_name = st.text_input("اسم الـ Vendor")

    use_case = st.text_area("الغرض المقصود (Intended Purpose)", height=80)
    interacts_with = st.text_input("بيتفاعل مع أنظمة تانية؟ (لو موجود، اذكريها)", value="")

    st.markdown("### القسم 2: البيانات")
    data_used = st.text_input("البيانات المستخدمة")
    data_source = st.selectbox("مصدر البيانات", ["In-house", "عام (Public)", "طرف ثالث (Third-party)"])
    has_personal_data = "Yes" if st.checkbox("يحتوي على بيانات شخصية؟") else "No"
    has_sensitive_data = "Yes" if st.checkbox("يحتوي على بيانات حساسة (صحية/مالية/بيومترية)؟") else "No"

    st.markdown("### القسم 3: المراقبة والتحكم")
    automated_decision = "Yes" if st.checkbox("النظام بياخد قرار أوتوماتيكي يؤثر على المستخدم") else "No"
    affected_group = st.text_input("الفئة المتأثرة (موظفين/عملاء/الجمهور)", value="")
    human_oversight = "Yes" if st.checkbox("فيه مراجعة بشرية على القرار") else "No"
    oversight_type = ""
    if human_oversight == "Yes":
        oversight_type = st.selectbox("نوع الرقابة البشرية", ["مراجعة كل قرار", "مراجعة عينات", "مراجعة عند التصعيد فقط"])

    if st.button("قيّم النظام"):
        if system_name.strip() == "":
            st.warning("من فضلك اكتبي اسم النظام الأول")
        else:
            with st.spinner("بنحلل النظام... (مرحلتين: تحديد المخاطر ثم مطابقة السياسات)"):
                full_use_case = f"""Entity type: {ai_type}
Source: {source_type}{' - Vendor: ' + vendor_name if vendor_name else ''}
Intended purpose: {use_case}
Interacts with: {interacts_with if interacts_with else 'N/A'}
Data source: {data_source}
Contains personal data: {has_personal_data}
Contains sensitive data: {has_sensitive_data}
Affected group: {affected_group if affected_group else 'N/A'}
Human oversight type: {oversight_type if oversight_type else 'N/A'}"""

                result = evaluate_system(
                    system_name=system_name,
                    use_case=full_use_case,
                    data_used=data_used,
                    automated_decision=automated_decision,
                    human_oversight=human_oversight,
                    language=language
                )
                log_evaluation(result, mode="system", content_type=system_name, reason="System evaluation", language=language)
            display_result(result)


st.divider()
with st.expander("⚙️ سياسات الشركة الخاصة (Company Policies)"):
    st.caption(
        "هذا القسم لرفع سياسات خاصة بشركتك فقط (Company AI Policy مثلًا). "
        "الأطر العالمية الأساسية (OWASP, NIST, ISO42001, EU AI Act, GDPR) مُعرّفة مسبقًا في النظام."
    )
    st.markdown("**سياسات الشركة المضافة حاليًا:**")
    current_policies = list_available_policies()
    if current_policies:
        for p in current_policies:
            pcol, dcol = st.columns([4, 1])
            with pcol:
                st.write(f"📄 {p}")
            with dcol:
                if st.button("حذف", key=f"delete_{p}"):
                    delete_policy(p)
                    st.success(f"تم حذف سياسة {p}")
                    st.rerun()
    else:
        st.info("لا توجد سياسات مضافة حاليًا.")

    st.markdown("---")
    st.markdown("**إضافة سياسة شركة جديدة:**")

    if "uploader_version" not in st.session_state:
        st.session_state.uploader_version = 0
    if "pending_policy_add" not in st.session_state:
        st.session_state.pending_policy_add = None
    if "policy_add_success" not in st.session_state:
        st.session_state.policy_add_success = None

    new_policy_name = st.text_input("اسم السياسة الجديدة (مثال: Company_AI_Policy)", key="new_policy_name_input")
    uploaded_file = st.file_uploader(
        "ارفعي ملف السياسة (PDF أو TXT)",
        type=["pdf", "txt"],
        key=f"policy_file_uploader_{st.session_state.uploader_version}"
    )

    policy_exists = new_policy_name.strip() in current_policies if new_policy_name.strip() else False

    if st.button("مراجعة قبل الإضافة"):
        if not new_policy_name.strip():
            st.warning("من فضلك اكتبي اسم السياسة")
        elif uploaded_file is None:
            st.warning("من فضلك ارفعي ملف")
        else:
            st.session_state.pending_policy_add = {
                "name": new_policy_name.strip(),
                "filename": uploaded_file.name,
                "file_bytes": uploaded_file.getbuffer().tobytes(),
                "exists": policy_exists
            }

    if st.session_state.pending_policy_add:
        pending = st.session_state.pending_policy_add
        st.warning(
            f"**تأكيد الإضافة:**\n\n"
            f"- اسم السياسة: **{pending['name']}**\n"
            f"- اسم الملف المرفوع: **{pending['filename']}**\n"
            + (f"- ⚠️ سياسة **{pending['name']}** موجودة بالفعل وهتتحذف ويتم استبدالها بهذا الملف.\n" if pending["exists"] else "")
            + "\nتأكد أن اسم الملف هو فعلًا الملف الصحيح قبل التأكيد."
        )
        ccol, xcol = st.columns(2)
        with ccol:
            if st.button("✅ تأكيد وإضافة"):
                temp_path = os.path.join("data", pending["filename"])
                with open(temp_path, "wb") as f:
                    f.write(pending["file_bytes"])

                with st.spinner("جاري إضافة السياسة..."):
                    num_chunks = add_company_policy_from_file(pending["name"], temp_path)

                st.session_state.policy_add_success = f"تمت إضافة سياسة '{pending['name']}' بنجاح ({num_chunks} قطعة نصية) من ملف {pending['filename']}"
                st.session_state.pending_policy_add = None
                st.session_state.uploader_version += 1
                del st.session_state["new_policy_name_input"]
                st.rerun()
        with xcol:
            if st.button("❌ إلغاء"):
                st.session_state.pending_policy_add = None
                st.rerun()

    if st.session_state.policy_add_success:
        st.success(st.session_state.policy_add_success)
        st.session_state.policy_add_success = None