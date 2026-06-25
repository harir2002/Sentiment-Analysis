from app.models.schemas import SolutionOption
from app.providers.registry import SOLUTION_CONFIG, get_all_solutions


def test_four_solutions_configured():
    assert len(SOLUTION_CONFIG) == 4
    assert set(SOLUTION_CONFIG.keys()) == set(SolutionOption)


def test_get_all_solutions_yields_models():
    solutions = list(get_all_solutions())
    assert len(solutions) == 4
    ids = {s["solution_id"] for s in solutions}
    assert SolutionOption.SARVAM_SARVAM.value in ids
    assert SolutionOption.GROQ_GROQ.value in ids
    for s in solutions:
        assert s["stt_model"]
        assert s["llm_model"]
        assert s["label"]
