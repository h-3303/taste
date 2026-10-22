from taste.library import vocabulary


def test_terms_are_65_unique_lowercase():
    assert len(vocabulary.TERMS) == 65 and len(set(vocabulary.TERMS)) == 65
    assert all(t == t.lower() for t in vocabulary.TERMS)
    assert vocabulary.TERMS[0] == "neumorphism" and "frutiger aero" in vocabulary.TERMS


def test_slugs():
    assert vocabulary.term_slug("Swiss International") == "swiss-international"
    assert vocabulary.slugify("Asphalt & Bitumen/Asphalt") == "asphalt-bitumen-asphalt"
    assert vocabulary.slugify("") == "untitled"
