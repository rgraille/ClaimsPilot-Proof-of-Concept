from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Any


@dataclass
class CarbonFactor:
    code: str
    label: str
    unit: str
    value: float
    raw: Dict[str, str]

    def to_dict(self):
        return asdict(self)


def _float(s: str):
    if not s:
        return None
    try:
        return float(str(s).replace(" ", "").replace(",", "."))
    except Exception:
        return None


def load_saretec_factors(csv_path: str | Path) -> List[CarbonFactor]:
    path = Path(csv_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        factors: List[CarbonFactor] = []
        for row in reader:
            keys = {k.lower().strip(): k for k in row.keys() if k}
            code_key = next((keys[k] for k in keys if "code" in k), None)
            label_key = next((keys[k] for k in keys if any(x in k for x in ["libelle", "libellé", "designation", "désignation", "prestation"])), None)
            unit_key = next((keys[k] for k in keys if "unite" in k or "unité" in k), None)
            val_key = next((keys[k] for k in keys if any(x in k for x in ["emission", "émission", "ges", "co2", "co²", "cycle de vie"])), None)
            if not label_key or not val_key:
                continue
            val = _float(row.get(val_key, ""))
            if val is None:
                continue
            factors.append(CarbonFactor(
                code=(row.get(code_key, "") if code_key else "").strip(),
                label=(row.get(label_key, "") or "").strip(),
                unit=(row.get(unit_key, "u") if unit_key else "u").strip(),
                value=val,
                raw=row,
            ))
        return factors


def search_factors(factors: List[CarbonFactor], query: str, limit: int = 10) -> List[CarbonFactor]:
    q = query.lower().strip()
    if not q:
        return []
    tokens = [t for t in q.replace("-", " ").split() if len(t) > 2]
    scored = []
    for f in factors:
        hay = (f.label + " " + f.code).lower()
        score = sum(2 if t in hay else 0 for t in tokens)
        if q in hay:
            score += 5
        if score:
            scored.append((score, f))
    return [f for _, f in sorted(scored, key=lambda x: x[0], reverse=True)[:limit]]


def carbon_from_aliases(factors: List[CarbonFactor], aliases: List[str]) -> Dict[str, Any]:
    results = []
    total = 0.0
    for alias in aliases:
        hits = search_factors(factors, alias, limit=1)
        if hits:
            f = hits[0]
            results.append({"alias": alias, "factor": f.to_dict(), "quantity": 1, "kgco2e": f.value})
            total += f.value
        else:
            results.append({"alias": alias, "factor": None, "quantity": None, "kgco2e": None})
    return {"status": "approché" if total else "non calculable", "total_kgco2e": round(total, 2), "details": results}
