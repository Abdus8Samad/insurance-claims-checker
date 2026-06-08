from claims.models import ClaimCategory


def test_per_claim_ceiling_rule(policy):
    # Consultation binds on the global per-claim limit (sub_limit 2000 < 5000).
    assert policy.effective_claim_ceiling(ClaimCategory.CONSULTATION) == 5000
    assert policy.ceiling_source(ClaimCategory.CONSULTATION) == "per_claim_limit"
    # Dental binds on its own larger sub-limit.
    assert policy.effective_claim_ceiling(ClaimCategory.DENTAL) == 10000
    assert policy.ceiling_source(ClaimCategory.DENTAL) == "sub_limit"


def test_network_hospital_match(policy):
    assert policy.is_network_hospital("Apollo Hospitals")
    assert policy.is_network_hospital("apollo hospitals, bengaluru")
    assert not policy.is_network_hospital("City Clinic")
    assert not policy.is_network_hospital(None)


def test_financial_params(policy):
    assert policy.copay_percent(ClaimCategory.CONSULTATION) == 10
    assert policy.network_discount_percent(ClaimCategory.CONSULTATION) == 20
    assert policy.copay_percent(ClaimCategory.DENTAL) == 0
