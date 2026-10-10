"""Reuse local answers only when the current question still matches."""
import hashlib
import json

from ai.questions import answer_record, model_question


def question_fingerprint(question):
    material = model_question(question)
    material = {key: material[key] for key in (
        "type_id", "title", "context", "options", "blank_count", "paper_id", "paper_sub_id", "raw_options")}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def saved_answers(report):
    result, seen = [], set()
    for item in report.get("answers", []) + report.get("resume_answers", []):
        if not isinstance(item, dict):
            continue
        key = item.get("question_fingerprint") or json.dumps(item.get("record"), sort_keys=True)
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def matching_answer(saved, question):
    fingerprint = question_fingerprint(question)
    for item in saved:
        if item.get("question_fingerprint") == fingerprint:
            return item
        # Older reports did not store context/type fingerprints. Reuse only
        # standalone answers whose visible material AND encoded record match.
        if (item.get("question_fingerprint") or question["paper_sub_id"] or question["context"]
                or item.get("error") or "record" not in item):
            continue
        if item.get("title") != question["title"] or item.get("options") != model_question(question)["options"]:
            continue
        try:
            if item["record"] == answer_record(question, item.get("answer")):
                return item
        except (ValueError, TypeError):
            continue
    return None
