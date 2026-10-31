import uuid

from loyalty_api.security import generate_api_key


def test_api_key_entropy_and_prefix():
    a, b = generate_api_key(), generate_api_key()
    assert a.startswith("ile_")
    assert a != b
    assert len(a) > 40
