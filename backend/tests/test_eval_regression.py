from eval.runner import run_all_evaluations


def test_eval_regression_suite_passes():
    report = run_all_evaluations()
    assert report["failed"] == 0, report["results"]
