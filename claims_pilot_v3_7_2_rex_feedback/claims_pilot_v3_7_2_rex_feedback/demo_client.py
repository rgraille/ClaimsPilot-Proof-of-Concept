from __future__ import annotations

import json
import hashlib
from html import escape
from datetime import datetime
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
CARBON_CSV = ROOT / "data" / "Referentiel-emission complet-4_5.csv"
APP_VERSION = "V3.7.2"

st.set_page_config(page_title="ClaimsPilot V3.7.2 - Démo Qualification", page_icon="🧭", layout="wide", initial_sidebar_state="collapsed")

CSS = """
<style>
.main .block-container { padding-top:2rem; max-width:1160px; }
.hero { border-radius:24px; padding:28px 30px; background:linear-gradient(135deg,#f8fbff 0%,#eef4ff 100%); border:1px solid #e5eaf5; margin-bottom:1rem; }
.hero h1 { margin:0 0 .25rem 0; font-size:2rem; }
.hero p { margin:.2rem 0; color:#4b5563; }
.card { border:1px solid #e5e7eb; border-radius:18px; padding:18px; background:#ffffff !important; color:#0f172a !important; height:100%; }
.card * { color:inherit !important; opacity:1 !important; }
.metric-value { font-size:1.08rem; font-weight:700; line-height:1.25; white-space:normal; overflow-wrap:anywhere; color:#0f172a !important; opacity:1 !important; }
.muted { color:#64748b !important; font-size:.9rem; opacity:1 !important; }
.big-answer { border-left:5px solid #1d4ed8; background:#f8fbff !important; color:#0f172a !important; padding:18px 20px; border-radius:14px; margin:.7rem 0 1rem 0; }
.big-answer * { color:#0f172a !important; opacity:1 !important; }
.pill { display:inline-block; padding:5px 10px; border-radius:999px; font-size:.82rem; font-weight:650; margin:0 .25rem .3rem 0; }
.pill-blue { background:#e8f0ff; color:#1d4ed8; }
.pill-green { background:#e8f7ee; color:#047857; }
.pill-orange { background:#fff4e5; color:#b45309; }
.pill-red { background:#feecec; color:#b91c1c; }

.result-card { border:1px solid #d1d5db; border-radius:22px; padding:18px 20px; background:#ffffff !important; color:#0f172a !important; min-height:132px; display:flex; align-items:center; gap:18px; box-shadow:0 1px 2px rgba(15,23,42,.06); }
.result-card .left { flex:1; min-width:0; }
.result-card .label { color:#64748b !important; font-size:.96rem; margin-bottom:.45rem; }
.result-card .main { color:#0f172a !important; font-size:1.18rem; font-weight:760; line-height:1.25; white-space:normal; overflow-wrap:anywhere; }
.result-card .divider { width:2px; align-self:stretch; background:#2563eb; opacity:.95; border-radius:2px; }
.result-card .score { min-width:92px; text-align:left; }
.result-card .score-value { color:#0f172a !important; font-size:1.25rem; font-weight:780; line-height:1; }
.result-card .score-label { color:#111827 !important; font-size:.86rem; margin-top:5px; line-height:1.05; }
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


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "Non chiffré"
    return f"{value:,.0f} € TTC".replace(",", " ")


def _safe_list(values: List[str], empty: str = "Aucun élément détecté.") -> str:
    if not values:
        return f"- {empty}"
    return "\n".join(f"- {v}" for v in values)


def _reset_analysis() -> None:
    """Vide explicitement toute trace du dossier précédent.

    La V3.6.8 privilégie la sécurité : le widget d'upload est régénéré,
    l'ancien résultat est effacé et aucune analyse antérieure ne peut être
    réutilisée silencieusement.
    """
    for key in [
        "claims_result",
        "claims_input_signature",
        "claims_input_summary",
        "claims_last_displayed_signature",
        "claims_upload_cleared_for_result",
        "claims_analysis_counter",
        "show_trace",
    ]:
        st.session_state.pop(key, None)
    st.session_state["upload_widget_nonce"] = st.session_state.get("upload_widget_nonce", 0) + 1


def _input_signature(files, manual_text: str, vat_choice: str) -> str:
    """Empreinte stable du dossier réellement présenté à l'analyse.

    Elle empêche l'interface d'afficher une réponse issue d'un ancien dossier
    lorsque l'utilisateur vient de changer les pièces ou le texte.
    """
    h = hashlib.sha256()
    h.update((manual_text or "").strip().encode("utf-8", errors="ignore"))
    h.update((vat_choice or "").encode("utf-8", errors="ignore"))
    for uf in files or []:
        data = uf.getvalue()
        h.update(uf.name.encode("utf-8", errors="ignore"))
        h.update(str(len(data)).encode("ascii"))
        h.update(hashlib.sha256(data).digest())
    return h.hexdigest()


def _input_summary(files, manual_text: str) -> Dict[str, Any]:
    return {
        "files": [getattr(uf, "name", "fichier") for uf in files or []],
        "file_count": len(files or []),
        "manual_text_chars": len((manual_text or "").strip()),
    }


def _run_pipeline(files, manual_text: str, forced_vat: float | None) -> Dict[str, Any]:
    texts: List[str] = []
    file_summaries: List[Dict[str, Any]] = []
    image_findings = []
    previews: List[Dict[str, Any]] = []
    pending_images: List[tuple[str, bytes]] = []
    for uf in files or []:
        data = uf.getvalue()
        suffix = Path(uf.name).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            pending_images.append((uf.name, data))
            previews.append({"name": uf.name, "bytes": data})
            continue
        parsed = parse_uploaded_file_detailed(uf.name, data)
        summary = parsed.to_summary()
        if is_reference_output_document(uf.name, parsed.text):
            summary["ignored_for_qualification"] = True
            summary["reason"] = "Document final ou livrable de référence : non utilisé pour qualifier la déclaration."
        else:
            texts.append(f"\n\n=== FICHIER : {uf.name} ===\n{parsed.text}")
        file_summaries.append(summary)
        image_findings.extend(parsed.image_findings)
    if manual_text.strip():
        texts.append("\n\n=== TEXTE COMPLEMENTAIRE ===\n" + manual_text.strip())
    image_context = normalize_text("\n".join(texts))
    for name, data in pending_images:
        parsed = parse_uploaded_file_detailed(name, data, context_text=image_context)
        texts.append(f"\n\n=== FICHIER : {name} ===\n{parsed.text}")
        file_summaries.append(parsed.to_summary())
        image_findings.extend(parsed.image_findings)
    raw_text = normalize_text("\n".join(texts))
    if not raw_text:
        raise ValueError("Aucun contenu exploitable n'a été fourni.")
    facts = extract_facts(raw_text)
    evidence = assess_evidence(facts, raw_text, file_summaries=file_summaries)
    focus_text = claim_focus_text(raw_text, facts)
    retrieved = retrieve_sources(focus_text, top_k=5)
    decision = decide(facts, retrieved, mode_options=evidence.auto_options, forced_vat=forced_vat, raw_text=raw_text)
    expertal = build_expertal_analysis(facts, retrieved, decision, raw_text=raw_text, evidence=evidence, image_findings=image_findings)
    factors = load_saretec_factors(CARBON_CSV)
    qualification = build_qualification_view(facts, expertal, decision, evidence, raw_text, factors)
    agent_pack = generate_agent_pack(facts, retrieved, decision, raw_text=raw_text, evidence=evidence, expertal=expertal)
    return {
        "raw_text": raw_text,
        "facts": facts.to_dict(),
        "evidence": evidence.to_dict(),
        "sources": [r.to_dict() for r in retrieved],
        "decision": decision.to_dict(),
        "expertal": expertal.to_dict(),
        "qualification": qualification.to_dict(),
        "agent_pack": agent_pack,
        "image_findings": [f.to_dict() for f in image_findings],
        "uploaded_previews": previews,
    }


def _client_markdown(result: Dict[str, Any]) -> str:
    q = result["qualification"]
    d = result["decision"]
    lines = [
        "# Réponse ClaimsPilot V3.7.2 — Qualification",
        f"Date d'analyse : {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "",
        "> Réponse de démonstration : aide à l'instruction, soumise à validation humaine.",
        "",
        "## Décision proposée",
        f"- {q['decision_label']}",
        f"- Validation : {q['validation_label']}",
        f"- Robustesse garantie : {d['garantie_score']}/100",
        f"- Robustesse quantum : {d['quantum_score']}/100",
        "",
    ]
    ms = q.get("missing_summary", {})
    if ms:
        lines.extend(["## Éléments manquants à demander", f"- Déclaration constituée : {'OUI' if ms.get('declaration_constituee') else 'NON'}", f"- Robustesse constitution : {ms.get('constitution_score', 0)}%", f"- Robustesse technique : {ms.get('technical_score', 0)}%", ""] )
        for x in ms.get("constitution_missing", [])[:8]:
            lines.append(f"- Constitution : {x}")
        for x in ms.get("technical_missing", [])[:8]:
            lines.append(f"- Technique : {x}")
        for x in ms.get("useful_documents", [])[:10]:
            lines.append(f"- Document utile : {x}")
        lines.append("")
    for key in ["description", "technical_opinion", "warranty_opinion", "remedy_estimate"]:
        sec = q[key]
        lines.append(f"## {sec['title']}")
        lines.extend(f"- {x}" for x in sec["lines"])
        lines.append("")
    carbon = q.get("carbon", {})
    lines.append("## Bilan carbone")
    lines.append(f"- Statut : {carbon.get('status')}")
    lines.append(f"- Total : {carbon.get('total_kgco2e', 'non calculé')} kgCO₂e")
    for line in carbon.get("lines", []):
        lines.append(f"- {line['poste']} : {line['kgco2e']} kgCO₂e ({line['code']})")
    return "\n".join(lines)


def _metric(label: str, value: str) -> None:
    st.markdown(f"<div class='card'><div class='muted'>{escape(label)}</div><div class='metric-value'>{escape(value)}</div></div>", unsafe_allow_html=True)


def _demo_rex_text(result: Dict[str, Any], feedback: str, expert_answer: str, suggested_rule: str) -> str:
    raw_text = result.get("raw_text") or ""
    case_hash = hashlib.sha256(raw_text.encode("utf-8", errors="ignore")).hexdigest()[:16]
    q = result.get("qualification", {})
    d = result.get("decision", {})
    response_md = _client_markdown(result)
    trace = {k: v for k, v in result.items() if k != "uploaded_previews"}
    parts = [
        "CLAIMSPILOT - FICHE REX / FEEDBACK",
        "=" * 40,
        f"Version app : {APP_VERSION}",
        f"Date export : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Identifiant technique dossier : {case_hash}",
        "",
        "COMMENTAIRE UTILISATEUR SUR L'ERREUR OU LA LIMITE",
        "-" * 40,
        feedback.strip() or "(non renseigne)",
        "",
        "REPONSE EXPERT IDEALE / ATTENDUE",
        "-" * 40,
        expert_answer.strip() or "(non renseignee)",
        "",
        "REGLE GENERALE A AJOUTER OU CORRIGER DANS L'ALGO",
        "-" * 40,
        suggested_rule.strip() or "(non renseignee)",
        "",
        "REPONSE DE L'APPLICATION",
        "-" * 40,
        response_md,
        "",
        "SYNTHESE TECHNIQUE APP",
        "-" * 40,
        f"Decision : {q.get('decision_label')}",
        f"Validation : {q.get('validation_label')}",
        f"Robustesse garantie : {d.get('garantie_score')}",
        f"Robustesse quantum : {d.get('quantum_score')}",
        "",
        "TEXTE SOURCE REELLEMENT ANALYSE PAR L'APPLICATION",
        "-" * 40,
        raw_text.strip() or "(vide)",
        "",
        "TRACE JSON COMPLETE",
        "-" * 40,
        json.dumps(trace, ensure_ascii=False, indent=2, default=str),
        "",
        "FIN FICHE REX",
    ]
    return "\n".join(parts)


def _result_card(label: str, value: str, score: int, score_label: str = "robustesse") -> None:
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


def _status_card(label: str, value: str) -> None:
    st.markdown(
        f"<div class='status-card'><div class='label'>{escape(label)}</div><div class='main'>{escape(value)}</div></div>",
        unsafe_allow_html=True,
    )



def _render_missing_summary(summary: Dict[str, Any]) -> None:
    if not summary:
        return
    declaration = "OUI" if summary.get("declaration_constituee") else "NON"
    constitution_missing = summary.get("constitution_missing") or []
    technical_missing = summary.get("technical_missing") or []
    useful_docs = summary.get("useful_documents") or []

    def lis(values, empty):
        vals = values[:6] if values else [empty]
        return "".join(f"<li>{escape(str(v))}</li>" for v in vals)

    st.markdown(
        f"""
        <div class='completeness'>
          <h3>Éléments manquants à demander au déclarant</h3>
          <div class='grid'>
            <div class='sub'>
              <div class='scoreline'>Déclaration constituée : {escape(declaration)} — {int(summary.get('constitution_score', 0))}%</div>
              <div class='muted'>Premier niveau : informations pouvant justifier une demande de régularisation.</div>
              <ul>{lis(constitution_missing, 'Aucun manque bloquant de constitution détecté automatiquement.')}</ul>
            </div>
            <div class='sub'>
              <div class='scoreline'>Technique / qualification : {int(summary.get('technical_score', 0))}%</div>
              <div class='muted'>Second niveau : compléments utiles pour fiabiliser la réponse et améliorer la robustesse.</div>
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

def _render_section(sec: Dict[str, Any]) -> None:
    st.markdown(f"### {sec['title']}")
    for line in sec["lines"]:
        st.write("- " + line)


st.markdown(
    """
    <div class="hero">
      <h1>ClaimsPilot V3.7.2 — Qualification</h1>
      <p>Démo de qualification DO à partir d'une déclaration et de ses pièces. La V3.6.8 est volontairement stateless et recentrée sur la démarche expertale : aucune ancienne analyse n'est conservée en mémoire.</p>
      <p class="muted">Version de démonstration : ne pas déposer de données confidentielles non anonymisées.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info(
    "Mode anti-mélange strict : l'application ne garde pas le résultat précédent. "
    "Pour chaque démo, déposez les pièces du dossier puis cliquez sur Analyser. "
    "Si vous changez de dossier, la réponse précédente disparaît automatiquement au rerun."
)

# La V3.6.8 évite volontairement st.form : sur Streamlit Cloud, le couple
# file_uploader + form pouvait conserver un état instable et imposer un reboot.
if "upload_widget_nonce" not in st.session_state:
    st.session_state["upload_widget_nonce"] = 0

left_reset, right_reset = st.columns([1, 3])
with left_reset:
    if st.button("Nouvelle analyse / reset", use_container_width=True):
        _reset_analysis()
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
        except Exception:
            pass
        st.rerun()
with right_reset:
    st.caption("Ce bouton remplace le reboot Streamlit : il vide l’état de page et recrée le dépôt de pièces.")

upload_key = f"claim_files_stateless_{st.session_state.get('upload_widget_nonce', 0)}"
text_key = f"manual_text_stateless_{st.session_state.get('upload_widget_nonce', 0)}"
vat_key = f"vat_choice_stateless_{st.session_state.get('upload_widget_nonce', 0)}"
trace_key = f"show_trace_stateless_{st.session_state.get('upload_widget_nonce', 0)}"

files = st.file_uploader(
    "Déclaration et pièces utiles",
    type=["eml", "pdf", "txt", "md", "docx", "jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    key=upload_key,
    help="Déposez uniquement les pièces du dossier à analyser. Aucune analyse antérieure n'est réutilisée.",
)
manual_text = st.text_area("Texte complémentaire éventuel", height=120, key=text_key)
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    vat_choice = st.selectbox("TVA", ["Automatique", "10 %", "20 %"], index=0, key=vat_key)
with c2:
    show_trace = st.checkbox("Afficher la traçabilité", value=True, key=trace_key)
with c3:
    st.caption("TVA auto : 10 % si habitation achevée depuis plus de 2 ans, sinon 20 % par défaut.")

submitted = st.button("Analyser le dossier", type="primary", use_container_width=True)

if not submitted:
    st.warning(
        "Aucune analyse n'est affichée tant que vous n'avez pas cliqué sur **Analyser le dossier**. "
        "Cela évite qu'une réponse d'un ancien dossier reste visible."
    )
    st.stop()

current_signature = _input_signature(files, manual_text, vat_choice) if (files or manual_text.strip()) else ""
current_summary = _input_summary(files, manual_text)

if not current_signature:
    st.error("Ajoutez au moins une déclaration, une pièce ou un texte à analyser.")
    st.stop()

forced_vat = None if vat_choice == "Automatique" else (0.10 if vat_choice == "10 %" else 0.20)

try:
    with st.spinner("Qualification en cours..."):
        result = _run_pipeline(files, manual_text, forced_vat)
        result["input_signature"] = current_signature
        result["input_summary"] = current_summary
except Exception as exc:
    st.error(f"Analyse impossible : {exc}")
    st.info("Aucune ancienne analyse n'est affichée : rechargez la page ou redéposez les pièces du dossier.")
    st.stop()

# Garde-fou de cohérence : l'analyse affichée doit correspondre au dossier qui vient d'être soumis.
if result.get("input_signature") != current_signature:
    st.error("Sécurité anti-mélange : l'empreinte du résultat ne correspond pas aux pièces soumises. Analyse bloquée.")
    st.stop()

q = result["qualification"]
d = result["decision"]
summary = result.get("input_summary", {})
files_label = ", ".join(summary.get("files", [])) or "texte collé uniquement"

st.caption(
    f"Dossier analysé maintenant : {files_label} — texte complémentaire : {summary.get('manual_text_chars', 0)} caractères — empreinte : {str(current_signature)[:12]}"
)

with st.expander("Contrôle anti-mélange / texte réellement analysé", expanded=True):
    st.write("Fichiers réellement analysés :")
    for name in summary.get("files", []) or ["Texte collé uniquement"]:
        st.write("- " + name)
    st.write("Aperçu du texte analysé :")
    st.code((result.get("raw_text") or "")[:3500])

st.subheader("Réponse de l'application")
q_amount = d.get("montant_ttc")
c1, c2, c3 = st.columns([1.35, .9, 1.0])
with c1:
    _result_card("Décision proposée", q["decision_label"], int(d["garantie_score"]))
with c2:
    _status_card("Validation", q["validation_label"])
with c3:
    _result_card("Quantum", _fmt_money(q_amount), int(d["quantum_score"]))

if q.get("warnings"):
    for w in q["warnings"]:
        st.warning(w)

st.markdown("<div class='big-answer'>", unsafe_allow_html=True)
_render_missing_summary(q.get("missing_summary", {}))
_render_section(q["description"])
_render_section(q["technical_opinion"])
_render_section(q["warranty_opinion"])
_render_section(q["remedy_estimate"])
st.markdown("</div>", unsafe_allow_html=True)

with st.expander("Éléments reçus / à vérifier / à obtenir", expanded=False):
    ev = result["evidence"]
    e1, e2, e3 = st.columns(3)
    with e1:
        st.markdown("<span class='pill pill-green'>Reçus / extraits</span>", unsafe_allow_html=True)
        for item in ev.get("received", []) or ["Aucun élément probant détecté automatiquement."]:
            st.write("- " + item)
    with e2:
        st.markdown("<span class='pill pill-orange'>À vérifier</span>", unsafe_allow_html=True)
        for item in ev.get("to_verify", []) or ["Aucun point spécifique détecté."]:
            st.write("- " + item)
    with e3:
        st.markdown("<span class='pill pill-red'>À obtenir</span>", unsafe_allow_html=True)
        missing = list(dict.fromkeys(ev.get("missing", []) + result["expertal"].get("elements_to_obtain", [])))
        for item in missing or ["Aucun élément bloquant détecté."]:
            st.write("- " + item)

with st.expander("Analyse des photos", expanded=False):
    if result.get("uploaded_previews"):
        cols = st.columns(min(3, len(result["uploaded_previews"])))
        for idx, item in enumerate(result["uploaded_previews"][:6]):
            with cols[idx % len(cols)]:
                st.image(item["bytes"], caption=item["name"], use_container_width=True)
    if result.get("image_findings"):
        for img in result["image_findings"]:
            st.write(f"**{img['image_name']}** — {img['status']} — confiance {img['confidence']}/100")
            for obs in img.get("observations", []):
                st.write("- " + obs)
    else:
        st.info("Aucune photo exploitable détectée.")

with st.expander("Bilan carbone", expanded=False):
    carbon = q.get("carbon", {})
    st.write(f"Statut : **{carbon.get('status')}**")
    if carbon.get("total_kgco2e") is not None:
        st.metric("Total indicatif", f"{carbon['total_kgco2e']} kgCO₂e")
    st.caption(carbon.get("note", ""))
    if carbon.get("lines"):
        st.dataframe(carbon["lines"], use_container_width=True, hide_index=True)

md = _client_markdown(result)
st.download_button("Télécharger la réponse (.md)", md.encode("utf-8"), file_name="reponse_claimspilot_v372.md", mime="text/markdown", use_container_width=True)

with st.expander("REX / feed-back pour améliorer l'algorithme", expanded=False):
    st.write("Commentez la réponse de l'app, ajoutez la réponse expert attendue, puis téléchargez le REX à partager pour correction de l'algorithme.")
    rex_feedback = st.text_area("Commentaire sur la réponse de l'application", height=120, key="demo_rex_feedback")
    rex_expert = st.text_area("Réponse expert idéale / attendue", height=220, key="demo_rex_expert")
    rex_rule = st.text_area("Règle générale à ajouter ou corriger", height=100, key="demo_rex_rule")
    rex_text = _demo_rex_text(result, rex_feedback, rex_expert, rex_rule)
    rex_hash = hashlib.sha256((result.get("raw_text") or "").encode("utf-8", errors="ignore")).hexdigest()[:12]
    st.download_button("Télécharger le REX du cas d'usage (.txt)", rex_text, file_name=f"rex_claimspilot_{rex_hash}.txt", mime="text/plain", use_container_width=True)

if show_trace:
    with st.expander("Traçabilité technique complète"):
        st.json({k: v for k, v in result.items() if k != "uploaded_previews"})
