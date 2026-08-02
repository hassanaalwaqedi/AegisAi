from aegis.semantic.query_engine import SemanticQueryEngine


def test_weapon_person_query_requires_an_association():
    engine = SemanticQueryEngine()
    tracks = [
        {"track_id": "person-1", "class_name": "person", "is_person": True, "risk_score": 0.1},
        {
            "track_id": "person-2", "class_name": "person", "is_person": True,
            "weapon_track_id": "weapon-7", "association_type": "near", "risk_score": 0.85,
            "verification_status": "confirmed", "reason_codes": ["WEAPON_NEAR_PERSON_STABLE"],
        },
    ]

    result = engine.search("find people carrying weapons", tracks, [], {})

    assert [item["track_id"] for item in result.results] == ["person-2"]
    assert result.results[0]["source"] == "track"


def test_crowd_query_returns_measured_statistics_only():
    engine = SemanticQueryEngine()

    result = engine.search("show crowd density risks", [], [], {"crowd_detected": True, "max_density": 7})

    assert len(result.results) == 1
    assert result.results[0]["track_id"] == "crowd-summary"
    assert result.results[0]["source"] == "statistics"


def test_unknown_query_does_not_fabricate_a_match():
    engine = SemanticQueryEngine()
    tracks = [{"track_id": "bag-1", "class_name": "backpack", "risk_score": 0.2}]

    result = engine.search("find a red backpack", tracks, [], {})

    assert result.results == []
