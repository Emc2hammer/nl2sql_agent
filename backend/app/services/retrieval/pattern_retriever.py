"""Retrieve SQL pattern knowledge for hard NL2SQL questions."""

from dataclasses import dataclass

from app.services.knowledge.knowledge_base import SQL_PATTERNS_PATH, lexical_score, load_json_list


@dataclass(frozen=True)
class SQLPattern:
    """Reusable SQL reasoning pattern."""

    name: str
    keywords: list[str]
    description: str
    template_hint: str


class PatternRetriever:
    """Retrieve SQL pattern hints by keyword/lexical score."""

    def __init__(self) -> None:
        self.patterns = [
            SQLPattern(
                name=item.get("name", ""),
                keywords=item.get("keywords", []) or [],
                description=item.get("description", ""),
                template_hint=item.get("template_hint", ""),
            )
            for item in load_json_list(SQL_PATTERNS_PATH)
        ]

    def retrieve(self, question: str, max_patterns: int = 3) -> list[SQLPattern]:
        scored = []
        for pattern in self.patterns:
            doc = f"{pattern.name} {pattern.description} {pattern.template_hint}"
            keyword_hits = sum(1 for keyword in pattern.keywords if keyword and keyword.lower() in question.lower())
            if not keyword_hits:
                continue
            score = lexical_score(question, doc, pattern.keywords) + keyword_hits * 10
            if score:
                scored.append((score, pattern))
        scored.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        return [pattern for _, pattern in scored[:max_patterns]]
