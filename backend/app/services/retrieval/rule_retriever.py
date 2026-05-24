"""Retrieve business rules that must be injected into NL2SQL prompts."""

from dataclasses import dataclass

from app.services.knowledge.knowledge_base import BUSINESS_RULES_PATH, lexical_score, load_json_list


@dataclass(frozen=True)
class BusinessRule:
    """A business rule relevant to SQL generation."""

    name: str
    keywords: list[str]
    condition: str
    required_joins: list[str]
    note: str = ""


class RuleRetriever:
    """Retrieve business rules from the local knowledge base."""

    def __init__(self) -> None:
        self.rules = [
            BusinessRule(
                name=item.get("name", ""),
                keywords=item.get("keywords", []) or [],
                condition=item.get("condition", ""),
                required_joins=item.get("required_joins", []) or [],
                note=item.get("note", ""),
            )
            for item in load_json_list(BUSINESS_RULES_PATH)
        ]

    def retrieve(self, question: str, max_rules: int = 5) -> list[BusinessRule]:
        scored = []
        for rule in self.rules:
            doc = f"{rule.name} {rule.condition} {rule.note} {' '.join(rule.required_joins)}"
            keyword_hits = sum(1 for keyword in rule.keywords if keyword and keyword.lower() in question.lower())
            if not keyword_hits:
                continue
            score = lexical_score(question, doc, rule.keywords) + keyword_hits * 10
            if score:
                scored.append((score, rule))
        scored.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        return [rule for _, rule in scored[:max_rules]]
