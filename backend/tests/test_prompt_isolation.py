import pytest

from app.services.conversation_service import ConversationService, ConversationMode


class DummyAffinity:
    def __init__(self):
        self.state = "acquaintance"
        self.new_score = 0.5


class DummySvc:
    def _translate_relation(self, relation_type: str) -> str:
        return relation_type


def test_graph_only_prompt_rejects_history():
    with pytest.raises(ValueError):
        ConversationService._build_prompt(
            DummySvc(),
            message="hi",
            memories=[],
            affinity=DummyAffinity(),
            emotion={"primary_emotion": "neutral", "valence": 0.0},
            entity_facts=[],
            conversation_history=[{"role": "user", "content": "x"}],
            mode=ConversationMode.GRAPH_ONLY,
        )
