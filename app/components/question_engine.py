import yaml
import os
from typing import Optional
from functools import lru_cache
from dataclasses import dataclass, field


QUESTIONS_PATH = os.path.join(
    os.path.dirname(__file__), "../config/questions.yaml"
)


@dataclass
class QuestionOption:
    label: str
    value: int


@dataclass
class Question:
    id: str
    text: str
    type: str          # "multiple_choice" or "likert"
    weight: float
    options: list[QuestionOption] = field(default_factory=list)


@dataclass
class Dimension:
    id: str
    label: str
    description: str
    weight: float
    questions: list[Question] = field(default_factory=list)


@dataclass
class QuestionBank:
    version: str
    total_questions: int
    dimensions: list[Dimension] = field(default_factory=list)

    def get_dimension(self, dimension_id: str) -> Optional[Dimension]:
        for dim in self.dimensions:
            if dim.id == dimension_id:
                return dim
        return None

    def get_question(self, question_id: str) -> Optional[Question]:
        for dim in self.dimensions:
            for q in dim.questions:
                if q.id == question_id:
                    return q
        return None

    def get_dimension_for_question(self, question_id: str) -> Optional[str]:
        for dim in self.dimensions:
            for q in dim.questions:
                if q.id == question_id:
                    return dim.id
        return None

    @property
    def dimension_ids(self) -> list[str]:
        return [d.id for d in self.dimensions]

    @property
    def dimension_labels(self) -> dict[str, str]:
        return {d.id: d.label for d in self.dimensions}


def _parse_question(raw: dict) -> Question:
    """Parse a raw YAML question dict into a Question dataclass."""
    q_type = raw.get("type", "multiple_choice")

    if q_type == "multiple_choice":
        options = [
            QuestionOption(label=o["label"], value=o["value"])
            for o in raw.get("options", [])
        ]
    elif q_type == "likert":
        scale = raw.get("scale", {})
        options = [
            QuestionOption(label=label, value=int(value))
            for value, label in scale.items()
        ]
        options.sort(key=lambda o: o.value)
    else:
        options = []

    return Question(
        id=raw["id"],
        text=raw["text"],
        type=q_type,
        weight=raw.get("weight", 1.0),
        options=options,
    )


def _parse_dimension(raw: dict) -> Dimension:
    """Parse a raw YAML dimension dict into a Dimension dataclass."""
    return Dimension(
        id=raw["id"],
        label=raw["label"],
        description=raw["description"],
        weight=raw.get("weight", 1.0),
        questions=[_parse_question(q) for q in raw.get("questions", [])],
    )


@lru_cache(maxsize=1)
def load_question_bank() -> QuestionBank:
    """
    Load and parse the question bank from YAML.
    Cached after first load — file is read once per process lifetime.
    """
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    meta = raw.get("metadata", {})
    dimensions = [_parse_dimension(d) for d in raw.get("dimensions", [])]

    bank = QuestionBank(
        version=str(meta.get("version", "1.0")),
        total_questions=sum(len(d.questions) for d in dimensions),
        dimensions=dimensions,
    )

    _validate_bank(bank)
    return bank


def _validate_bank(bank: QuestionBank) -> None:
    """
    Validate question bank integrity at load time.
    Raises ValueError on any structural problem.
    """
    seen_ids = set()

    for dim in bank.dimensions:
        if not dim.questions:
            raise ValueError(f"Dimension '{dim.id}' has no questions")

        for q in dim.questions:
            if q.id in seen_ids:
                raise ValueError(f"Duplicate question id: '{q.id}'")
            seen_ids.add(q.id)

            if not q.options:
                raise ValueError(f"Question '{q.id}' has no options")

            values = [o.value for o in q.options]
            if sorted(values) != list(range(1, len(values) + 1)):
                raise ValueError(
                    f"Question '{q.id}' option values must be sequential from 1. Got: {values}"
                )


def get_completion_status(
    bank: QuestionBank,
    answered_question_ids: list[str]
) -> dict:
    """
    Given a list of answered question IDs, return completion status
    per dimension and overall.
    """
    answered = set(answered_question_ids)
    status = {}

    for dim in bank.dimensions:
        dim_question_ids = {q.id for q in dim.questions}
        answered_in_dim = dim_question_ids & answered
        status[dim.id] = {
            "label": dim.label,
            "total": len(dim.questions),
            "answered": len(answered_in_dim),
            "complete": answered_in_dim == dim_question_ids,
            "percent": round(len(answered_in_dim) / len(dim.questions) * 100),
        }

    total_q = sum(s["total"] for s in status.values())
    total_answered = sum(s["answered"] for s in status.values())
    status["_overall"] = {
        "total": total_q,
        "answered": total_answered,
        "complete": total_answered == total_q,
        "percent": round(total_answered / total_q * 100) if total_q else 0,
    }

    return status