import json
from src.evaluation.metrics import (
    JsonComplianceMetric,
    HallucinationMetric,
    RiskKeywordMetric,
)
from src.models import UserViolationProfile


def test_json_compliance_metric():
    metric = JsonComplianceMetric()

    # Good case
    good_json = json.dumps({"risk": "r", "action": "a", "rationale": "r"})
    assert metric.evaluate(good_json, None)["score"] == 1.0

    # Bad case (missing key)
    bad_json = json.dumps({"risk": "r", "action": "a"})  # Missing rationale
    assert metric.evaluate(bad_json, None)["score"] == 0.0

    # Bad case (invalid syntax)
    invalid = "{ broken json "
    assert metric.evaluate(invalid, None)["score"] == 0.0


def test_hallucination_metric(profile_ana_p1: UserViolationProfile):
    metric = HallucinationMetric()

    # Ana has "PaymentsAdmin" and "TradingDesk"

    # Good case: Action mentions a real role
    good_resp = json.dumps({"action": "Revoke TradingDesk role"})
    res = metric.evaluate(good_resp, profile_ana_p1)
    assert res["score"] == 1.0

    # Bad case: Action mentions a fake role
    bad_resp = json.dumps({"action": "Revoke SuperUser role"})
    res = metric.evaluate(bad_resp, profile_ana_p1)
    assert res["score"] == 0.0
    assert "SuperUser" not in str(res["metadata"]["user_roles"])


def test_risk_keyword_metric():
    metric = RiskKeywordMetric()

    good_resp = json.dumps({"risk": "High risk of fraud and conflict of interest"})
    assert metric.evaluate(good_resp, None)["score"] == 1.0

    weak_resp = json.dumps({"risk": "This is not good."})
    assert metric.evaluate(weak_resp, None)["score"] == 0.5
