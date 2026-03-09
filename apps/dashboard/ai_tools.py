from __future__ import annotations

import json
import os

from django.conf import settings


def _openai_json_response(*, system_prompt, user_prompt):
    api_key = (
        getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    ).strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None

    client = OpenAI(api_key=api_key)
    model = getattr(settings, "OPENAI_CBT_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini"
    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw_text = getattr(response, "output_text", "") or ""
    except Exception:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            raw_text = response.choices[0].message.content or ""
        except Exception:
            return None
    try:
        return json.loads(raw_text)
    except Exception:
        return None


def generate_lesson_plan_bundle(*, subject_name, topic, class_code, teaching_goal="", teacher_notes=""):
    payload = _openai_json_response(
        system_prompt=(
            "You are an academic lesson planner for a Nigerian secondary school. "
            "Return JSON with keys: objectives, outline, activity, assignment, quiz."
        ),
        user_prompt=(
            f"Subject: {subject_name}\n"
            f"Class: {class_code}\n"
            f"Topic: {topic}\n"
            f"Teaching goal: {teaching_goal or '-'}\n"
            f"Teacher notes: {teacher_notes or '-'}"
        ),
    )
    if payload:
        objectives = payload.get("objectives") or []
        outline = payload.get("outline") or []
        return {
            "objectives": "\n".join(f"- {row}" for row in objectives if str(row).strip()) or f"- Explain the key idea behind {topic}.",
            "outline": "\n".join(f"- {row}" for row in outline if str(row).strip()) or f"- Introduce {topic}\n- Guided examples\n- Quick recap",
            "activity": str(payload.get("activity") or f"Students solve a short guided task on {topic} in pairs.").strip(),
            "assignment": str(payload.get("assignment") or f"Answer five questions on {topic} and submit at the next lesson.").strip(),
            "quiz": str(payload.get("quiz") or f"1. Define {topic}.\n2. Give one example linked to {subject_name}.").strip(),
            "generator": "openai",
        }

    return {
        "objectives": (
            f"- Explain the meaning of {topic}.\n"
            f"- Connect {topic} to {subject_name} examples for {class_code}.\n"
            "- Check learner understanding with short practice."
        ),
        "outline": (
            "- Starter review of prior knowledge\n"
            f"- Teacher explanation of {topic}\n"
            "- Worked examples and guided correction\n"
            "- Pair discussion and recap"
        ),
        "activity": f"Students work in pairs to solve a short {subject_name} task on {topic}, then explain their reasoning to the class.",
        "assignment": f"Complete a take-home exercise on {topic} with five short questions and one applied example.",
        "quiz": f"1. What is {topic}?\n2. State one rule or fact about {topic}.\n3. Solve one short {subject_name} item on {topic}.",
        "generator": "deterministic",
    }


def answer_student_tutor_prompt(*, subject_name, question, class_code, weak_subjects=None):
    payload = _openai_json_response(
        system_prompt=(
            "You are a concise AI tutor for secondary school students. "
            "Return JSON with keys: answer, steps, practice_tip."
        ),
        user_prompt=(
            f"Class: {class_code}\n"
            f"Subject: {subject_name or 'General'}\n"
            f"Weak subjects: {', '.join(weak_subjects or []) or '-'}\n"
            f"Student question: {question}"
        ),
    )
    if payload:
        steps = payload.get("steps") or []
        return {
            "answer": str(payload.get("answer") or "Review the concept carefully and break it into smaller parts.").strip(),
            "steps": [str(row).strip() for row in steps if str(row).strip()],
            "practice_tip": str(payload.get("practice_tip") or "Try two extra practice questions immediately after reading this.").strip(),
            "generator": "openai",
        }

    weak_hint = " Focus extra attention there." if weak_subjects else ""
    return {
        "answer": (
            f"Break the question into the exact concept being tested, recall the rule, then apply it step by step in {subject_name or 'your subject'}.{weak_hint}"
        ).strip(),
        "steps": [
            "Underline the key term or operation in the question.",
            "Write the rule, formula, or definition from memory.",
            "Apply it to one worked example before solving the actual question.",
        ],
        "practice_tip": "Use one past question and one fresh practice question before moving on.",
        "generator": "deterministic",
    }
