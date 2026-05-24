from claims_pilot.extractor import extract_facts, claim_focus_text
from claims_pilot.retrieval import retrieve_sources
from claims_pilot.decision import decide
from claims_pilot.generator import generate_agent_pack

text = """
Déclaration de sinistre : Dans la salle de bain de l'appartement équipée d'une douche italienne,
apparition de moisissures et de taches d'humidité à la base droite de la douche. Le problème persiste malgré une intervention antérieure.
Date de réception : 20/04/2022. Date de déclaration : 27/09/2025. Photos jointes. Montant estimé 1800 € TTC.
"""
facts = extract_facts(text)
focus_text = claim_focus_text(text, facts)
sources = retrieve_sources(focus_text)
decision = decide(facts, sources, {"materiality_observed": True, "humidity_measured": True, "quote_available": True, "photos_exploitable": True})
print(generate_agent_pack(facts, sources, decision, text))
