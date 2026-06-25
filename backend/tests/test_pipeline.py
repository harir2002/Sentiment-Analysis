from app.services.pipeline import make_failed_result
from app.models.schemas import SolutionOption


def test_make_failed_result_structure():
    result = make_failed_result(SolutionOption.SARVAM_SARVAM, "test error")
    assert result.status == "failed"
    assert result.error == "test error"
    assert result.solution_id == SolutionOption.SARVAM_SARVAM.value
