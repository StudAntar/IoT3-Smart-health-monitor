from backend.app import is_valid_cpr


def test_valid_cpr_numbers():
    assert is_valid_cpr("010203-1234")
    assert is_valid_cpr("3112991234")
    assert is_valid_cpr("010101-0000")


def test_invalid_cpr_wrong_format():
    # Forkert længde
    assert not is_valid_cpr("010203-123")
    assert not is_valid_cpr("010203-12345")

    # Forkerte tegn
    assert not is_valid_cpr("010203-12A4")
    assert not is_valid_cpr("abcdef-1234")

    # Forkert struktur
    assert not is_valid_cpr("01-02-03-1234")
    assert not is_valid_cpr("010203--1234")


def test_invalid_cpr_non_string():
    assert not is_valid_cpr(1234567890)
    assert not is_valid_cpr(None)
    assert not is_valid_cpr(3.14)
