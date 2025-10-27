from combo.link.registry import deterministic_id


def test_uuidv5_stability():
    a = deterministic_id('PERSON', 'jane doe')
    b = deterministic_id('PERSON', 'jane doe')
    c = deterministic_id('ORG', 'jane doe')
    assert a == b
    assert a != c

