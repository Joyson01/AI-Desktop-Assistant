import re
from typing import Any, Dict, Iterable, List, Optional


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _match_candidates(query: str, matches: Optional[Iterable[Dict[str, Any]]], focused_text: str = "") -> List[Dict[str, Any]]:
    if not matches:
        return []
    query_norm = _normalize_text(query)
    focused_norm = _normalize_text(focused_text)
    item_list = []
    for item in matches:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        item_norm = _normalize_text(text)
        score = 0.0
        if query_norm and query_norm in item_norm:
            score += 2.0
        if query_norm and item_norm == query_norm:
            score += 2.0
        if focused_norm and focused_norm in item_norm:
            score += 0.5
        if item.get("confidence") is not None:
            try:
                score += float(item.get("confidence"))
            except Exception:
                pass
        item_list.append({**item, "_score": score})
    item_list.sort(key=lambda item: item["_score"], reverse=True)
    return item_list


def find_text_target(text: str, matches: Optional[Iterable[Dict[str, Any]]] = None, focused_text: str = "") -> Dict[str, Any]:
    """Return a safe OCR-result structure for a visible-text query.

    The result includes a status of exact, candidate, or ambiguous. It does not pretend to
    click or select anything by itself; this is intentionally a structured payload for the
    action layer to consume and verify, preserving the existing safety flow.
    """
    items = _match_candidates(text, matches, focused_text)
    if not items:
        return {"status": "not_found", "target": text, "matches": []}

    top = items[0]
    if len(items) == 1:
        return {"status": "exact", "target": text, "match": top, "matches": items}

    exact_matches = [item for item in items if _normalize_text(item.get("text") or "") == _normalize_text(text)]
    if len(exact_matches) > 1:
        return {"status": "ambiguous", "target": text, "match": top, "matches": exact_matches[:10]}
    if exact_matches:
        return {"status": "exact", "target": text, "match": exact_matches[0], "matches": exact_matches}

    # Multiple visible matches require explicit disambiguation or a focused UI context.
    return {"status": "ambiguous", "target": text, "match": top, "matches": items[:10]}


def select_text_target(text: str, matches: Optional[Iterable[Dict[str, Any]]] = None, focused_text: str = "") -> Dict[str, Any]:
    result = find_text_target(text, matches=matches, focused_text=focused_text)
    match = result.get("match")
    if not match:
        return {"action": "select_text", "target": text, "status": "not_found", "matches": []}
    payload = {
        "action": "select_text",
        "target": text,
        "status": result["status"],
        "match": match,
        "bbox": match.get("bbox"),
        "center": match.get("center"),
        "confidence": match.get("confidence", 0.0),
    }
    return payload


def select_text_range(start_text: str, end_text: str, matches: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    start_matches = (matches or {}).get("start") or []
    end_matches = (matches or {}).get("end") or []
    start_match = start_matches[0] if start_matches else {}
    end_match = end_matches[0] if end_matches else {}
    return {
        "action": "select_text_range",
        "start_text": start_text,
        "end_text": end_text,
        "status": "ready" if (start_match or end_match) else "not_found",
        "start_match": start_match,
        "end_match": end_match,
        "start_bbox": start_match.get("bbox"),
        "end_bbox": end_match.get("bbox"),
    }
