from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from claims_pilot.parser import parse_uploaded_file_detailed, normalize_text
from claims_pilot.extractor import extract_facts, claim_focus_text
from claims_pilot.retrieval import retrieve_sources
from claims_pilot.decision import decide
from claims_pilot.evidence import assess_evidence
from claims_pilot.expertal import build_expertal_analysis
from claims_pilot.qualification import build_qualification_view
from claims_pilot.generator import generate_agent_pack
from claims_pilot.carbon import load_saretec_factors
from claims_pilot.input_filter import is_reference_output_document

ROOT = Path(__file__).parent
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)
CARBON_CSV = ROOT / "data" / "Referentiel-emission complet-4_5.csv"

st.set_page_config(page_title="ClaimsPilot V3.6.7 - Expert", page_icon="🧭", layout="wide")

CSS = """
<style>
.block-container { padding-top: 2rem; }
.metric-card { border:1px solid #e5e7eb; border-radius:16px; padding:14px 16px; background:#ffffff !important; color:#0f172a !important; min-height:100px; }
.metric-card * { color:inherit !important; opacity:1 !important; }
.metric-card .label { color:#64748b !important; font-size:.88rem; margin-bottom:.35rem; opacity:1 !important; }
.metric-card .value { font-size:1.05rem; font-weight:700; line-height:1.25; white-space:normal; overflow-wrap:anywhere; color:#0f172a !important; opacity:1 !important; }
.section-card { border:1px solid #e5e7eb; border-radius:18px; padding:18px; background:#ffffff !important; color:#0f172a !important; margin-bottom:1rem; }
.section-card * { color:#0f172a !important; opacity:1 !important; }
.section-card h3 { margin-top:0; color:#0f172a !important; opacity:1 !important; }
.badge { display:inline-block; padding:5px 10px; border-radius:999px; font-weight:650; font-size:.85rem; background:#eef2ff; color:#3730a3; }
.result-card { border:1px solid #d1d5db; border-radius:22px; padding:18px 20px; background:#ffffff !important; color:#0f172a !important; min-height:132px; display:flex; align-items:center; gap:18px; box-shadow:0 1px 2px rgba(15,23,42,.06); }
.result-card .left { flex:1; min-width:0; }
.result-card .label { color:#64748b !important; font-size:.96rem; margin-bottom:.45rem; }
.result-card .main { color:#0f172a !important; font-size:1.18rem; font-weight:760; line-height:1.25; white-space:normal; overflow-wrap:anywhere; }
.result-card .divider { width:2px; align-self:stretch; background:#2563eb; opacity:.95; border-radius:2px; }
.result-card .score { min-width:92px; text-align:left; }
.result-card .score .score-value { color:#0f172a !important; font-size:1.25rem; font-weight:780; line-height:1; }
.result-card .score .score-label { color:#111827 !important; font-size:.86rem; margin-top:5px; line-height:1.05; }
.status-card { border:1px solid #d1d5db; border-radius:22px; padding:18px 20px; background:#ffffff !important; color:#0f172a !important; min-height:132px; display:flex; flex-direction:column; justify-content:center; box-shadow:0 1px 2px rgba(15,23,42,.06); }
.status-card .label { color:#64748b !important; font-size:.96rem; margin-bottom:.45rem; }
.status-card .main { color:#0f172a !important; font-size:1.18rem; font-weight:760; line-height:1.25; }

.completeness { border:1px solid #c7d2fe; border-radius:18px; padding:18px 20px; background:#f8fbff !important; color:#0f172a !important; margin:1rem 0; }
.completeness * { color:#0f172a !important; opacity:1 !important; }
.completeness h3 { margin:.1rem 0 .7rem 0; }
.completeness .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.completeness .sub { background:#ffffff !important; border:1px solid #e5e7eb; border-radius:14px; padding:14px; }
.completeness .scoreline { font-weight:800; font-size:1.05rem; margin-bottom:.35rem; }
.completeness ul { margin:.35rem 0 0 1.2rem; }
.completeness li { margin:.15rem 0; }

</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.title("ClaimsPilot V3.6.7 - Interface expert")

with st.sidebar:
    st.header("Paramètres")
    vat_choice = st.radio("TVA", ["Automatique", "10 %", "20 %"], index=0)
    forced_vat = None if vat_choice == "Automatique" else (0.10 if vat_choice == "10 %" else 0.20)
    st.info("TM retenu : 1 960 € TTC")
    st.caption("V3.6.7 : interface expert complète. La démo client est séparée.")

uploaded_files = st.file_uploader(
    "Dépose la déclaration et les pièces utiles (.eml, .pdf, .txt, .docx, images)",
    type=["eml", "pdf", "txt", "md", "docx", "jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)
manual = st.text_area("Ou colle directement le texte de la déclaration", height=170)

texts: List[str] = []
file_summaries: List[Dict[str, Any]] = []
image_findings = []
if uploaded_files:
    for uf in uploaded_files:
        data = uf.read()
        parsed = parse_uploaded_file_detailed(uf.name, data)
        summary = parsed.to_summary()
        if is_reference_output_document(uf.name, parsed.text):
            summary["ignored_for_qualification"] = True
            summary["reason"] = "Document final ou livrable de référence : non utilisé pour qualifier la déclaration."
        else:
            texts.append(f"\n\n=== FICHIER : {uf.name} ===\n{parsed.text}")
        file_summaries.append(summary)
        image_findings.extend(parsed.image_findings)
if manual.strip():
    texts.append("\n\n=== SAISIE MANUELLE ===\n" + manual.strip())

raw_text = normalize_text("\n".join(texts))
if not raw_text:
    st.warning("Ajoute une déclaration ou colle un texte pour lancer la qualification.")
    st.stop()

with st.expander("Texte extrait", expanded=False):
    st.text_area("Contenu analysé", raw_text, height=260)

facts = extract_facts(raw_text)
evidence = assess_evidence(facts, raw_text, file_summaries=file_summaries)
focus_text = claim_focus_text(raw_text, facts)
retrieved = retrieve_sources(focus_text, top_k=5)
decision = decide(facts, retrieved, mode_options=evidence.auto_options, forced_vat=forced_vat, raw_text=raw_text)
expertal = build_expertal_analysis(facts, retrieved, decision, raw_text=raw_text, evidence=evidence, image_findings=image_findings)
factors = load_saretec_factors(CARBON_CSV)
qualification = build_qualification_view(facts, expertal, decision, evidence, raw_text, factors)
agent_pack = generate_agent_pack(facts, retrieved, decision, raw_text=raw_text, evidence=evidence, expertal=expertal)


def metric_card(label: str, value: str) -> None:
    st.markdown(f"<div class='metric-card'><div class='label'>{escape(label)}</div><div class='value'>{escape(value)}</div></div>", unsafe_allow_html=True)


def result_card(label: str, value: str, score: int, score_label: str = "robustesse") -> None:
    st.markdown(
        f"""
        <div class='result-card'>
          <div class='left'>
            <div class='label'>{escape(label)}</div>
            <div class='main'>{escape(value)}</div>
          </div>
          <div class='divider'></div>
          <div class='score'>
            <div class='score-value'>{int(score)}%</div>
            <div class='score-label'>{escape(score_label)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_card(label: str, value: str) -> None:
    st.markdown(f"<div class='status-card'><div class='label'>{escape(label)}</div><div class='main'>{escape(value)}</div></div>", unsafe_allow_html=True)


def fmt_money(value: float | None) -> str:
    if value is None:
        return "Non chiffré"
    return f"{value:,.0f} € TTC".replace(",", " ")

q_amount = decision.montant_ttc
c1, c2, c3 = st.columns([1.35, .9, 1.0])
with c1:
    result_card("Décision proposée", qualification.decision_label, int(decision.garantie_score))
with c2:
    status_card("Validation", qualification.validation_label)
with c3:
    result_card("Quantum", fmt_money(q_amount), int(decision.quantum_score))

if qualification.warnings:
    for w in qualification.warnings:
        st.warning(w)



def render_missing_summary(summary: Dict[str, Any]) -> None:
    if not summary:
        return
    declaration = "OUI" if summary.get("declaration_constituee") else "NON"
    constitution_missing = summary.get("constitution_missing") or []
    technical_missing = summary.get("technical_missing") or []
    useful_docs = summary.get("useful_documents") or []

    def lis(values, empty):
        vals = values[:8] if values else [empty]
        return "".join(f"<li>{escape(str(v))}</li>" for v in vals)

    st.markdown(
        f"""
        <div class='completeness'>
          <h3>Éléments manquants à demander au déclarant</h3>
          <div class='grid'>
            <div class='sub'>
              <div class='scoreline'>Déclaration constituée : {escape(declaration)} — {int(summary.get('constitution_score', 0))}%</div>
              <div class='label'>Premier niveau : informations pouvant justifier une demande de régularisation.</div>
              <ul>{lis(constitution_missing, 'Aucun manque bloquant de constitution détecté automatiquement.')}</ul>
            </div>
            <div class='sub'>
              <div class='scoreline'>Technique / qualification : {int(summary.get('technical_score', 0))}%</div>
              <div class='label'>Second niveau : compléments utiles pour fiabiliser la réponse et améliorer la robustesse.</div>
              <ul>{lis(technical_missing, 'Aucun complément technique prioritaire détecté automatiquement.')}</ul>
            </div>
          </div>
          <div class='sub' style='margin-top:14px'>
            <div class='scoreline'>Documents utiles à demander</div>
            <ul>{lis(useful_docs, 'Aucun document complémentaire prioritaire.')}</ul>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_section(section) -> None:
    st.markdown(f"<div class='section-card'><h3>{section.title}</h3>", unsafe_allow_html=True)
    for line in section.lines:
        st.markdown(f"- {line}")
    st.markdown("</div>", unsafe_allow_html=True)

tabs = st.tabs(["Qualification", "Éléments reçus / à obtenir", "Analyse photos", "Sources métier", "Carbone", "Pack agent", "Exports"])

with tabs[0]:
    render_missing_summary(qualification.missing_summary)
    render_section(qualification.description)
    render_section(qualification.technical_opinion)
    render_section(qualification.warranty_opinion)
    render_section(qualification.remedy_estimate)

with tabs[1]:
    ms = qualification.missing_summary
    if ms:
        st.write("### Constitution de la déclaration")
        cst1, cst2 = st.columns(2)
        cst1.metric("Déclaration constituée", "OUI" if ms.get("declaration_constituee") else "NON")
        cst2.metric("Score constitution", f"{ms.get('constitution_score', 0)}%")
        if ms.get("constitution_items"):
            st.dataframe(ms["constitution_items"], use_container_width=True, hide_index=True)
        st.write("### Technique / qualification")
        st.metric("Score technique", f"{ms.get('technical_score', 0)}%")
        if ms.get("technical_items"):
            st.dataframe(ms["technical_items"], use_container_width=True, hide_index=True)
        st.write("### Documents utiles")
        for doc in ms.get("useful_documents", []) or ["Aucun document complémentaire prioritaire."]:
            st.write("- " + str(doc))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Éléments reçus", len(evidence.received))
    m2.metric("Objectivés", sum(1 for i in evidence.items if i.status == "OBJECTIVE"))
    m3.metric("À vérifier", len(evidence.to_verify))
    m4.metric("Manquants", len(evidence.missing))
    st.write("### Éléments reçus / extraits")
    for item in evidence.received or ["Aucun élément reçu automatiquement."]:
        st.success(item)
    st.write("### Éléments à vérifier")
    for item in evidence.to_verify or ["Aucun point spécifique à vérifier."]:
        st.warning(item)
    st.write("### Éléments à obtenir")
    merged_missing = list(dict.fromkeys(evidence.missing + expertal.elements_to_obtain))
    for item in merged_missing or ["Aucun élément bloquant détecté."]:
        st.error(item) if item != "Aucun élément bloquant détecté." else st.success(item)

with tabs[2]:
    if not image_findings:
        st.info("Aucune image exploitable ou pièce visuelle extraite.")
    else:
        for f in image_findings:
            with st.expander(f"{f.image_name} — {f.status} — confiance {f.confidence}/100", expanded=True):
                st.write(f"Source : {f.source_file}")
                st.write(f"Dimensions : {f.width} x {f.height}px")
                st.write("Tags : " + (", ".join(f.tags) if f.tags else "—"))
                for obs in f.observations:
                    st.write("- " + obs)
                st.caption(f.technical_note)

with tabs[3]:
    if not retrieved:
        st.info("Aucune fiche fortement corrélée.")
    for r in retrieved:
        c = r.card
        with st.expander(f"{c.famille} — score {r.score}", expanded=True):
            st.write(f"**Source :** {c.source}")
            st.write(c.source_detail)
            st.write("**Mots-clés reconnus :** " + ", ".join(r.matched_keywords))
            st.write("**Signes à rechercher**")
            st.write(c.signes)
            st.write("**Causes possibles**")
            st.write(c.causes_possibles)
            st.write("**Points à vérifier**")
            st.write(c.points_a_verifier)
            st.write("**Logique garantie**")
            st.write(c.logique_garantie)

with tabs[4]:
    st.write(f"Statut : **{qualification.carbon.get('status')}**")
    if qualification.carbon.get("total_kgco2e") is not None:
        st.metric("Total indicatif", f"{qualification.carbon['total_kgco2e']} kgCO₂e")
    st.caption(qualification.carbon.get("note", ""))
    if qualification.carbon.get("lines"):
        st.dataframe(qualification.carbon["lines"], use_container_width=True, hide_index=True)
    else:
        st.info("Aucune correspondance carbone exploitable.")

with tabs[5]:
    st.markdown(agent_pack)

with tabs[6]:
    payload = {
        "facts": facts.to_dict(),
        "evidence": evidence.to_dict(),
        "decision": decision.to_dict(),
        "qualification": qualification.to_dict(),
        "expertal": expertal.to_dict(),
        "sources": [r.to_dict() for r in retrieved],
    }
    st.download_button("Trace décision V3.6.7 (.json)", json.dumps(payload, ensure_ascii=False, indent=2), file_name="trace_qualification_v367.json", mime="application/json")
    st.download_button("Pack agent (.md)", agent_pack, file_name="pack_agent_v367.md", mime="text/markdown")
    OUTPUTS.joinpath("derniere_trace_qualification_v367.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
