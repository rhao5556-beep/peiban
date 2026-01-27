import pytest

from app.services.temporal_extractor import TemporalExtractor
from app.services.temporal_query_service import TemporalQueryService


def test_temporal_extractor_ts_and_yesterday():
    t = TemporalExtractor()
    msg = "[D1:3 ts=2023-05-08T13:56:00Z] Caroline: I went to a LGBTQ support group yesterday."
    temporal = t.extract(msg)
    assert temporal["precision"] in ("date", "datetime")
    assert temporal["start_ts"].startswith("2023-05-07")


def test_temporal_query_date_answer():
    q = "When did Caroline go to the LGBTQ support group?"
    evidences = [
        {
            "id": "m1",
            "content": "[D1:3 ts=2023-05-08T13:56:00Z] Caroline: I went to a LGBTQ support group yesterday.",
            "temporal": TemporalExtractor().extract(
                "[D1:3 ts=2023-05-08T13:56:00Z] Caroline: I went to a LGBTQ support group yesterday."
            ),
        }
    ]
    ans = TemporalQueryService().try_answer(q, evidences)
    assert ans is not None
    assert ans.answer == "7 May 2023"


def test_temporal_query_duration_answer():
    q = "According to the record from August 15, 1969, how long did it take for the bus carrying the family to depart and finally arrive outside the Red House?"
    evidence = {
        "id": "r",
        "content": "\n".join(
            [
                "[id 5] 1969-08-15T09:00:00Z @ the bus departed with the family",
                "[id 35] 1969-08-15T09:08:40Z @ finally arrived outside the Red House",
            ]
        ),
        "temporal": {},
    }
    ans = TemporalQueryService().try_answer(q, [evidence])
    assert ans is not None
    assert ans.answer == "8 minutes 40 seconds"


def test_temporal_query_duration_space_timestamp():
    q = "How long did it take for the bus to depart and arrive outside the Red House?"
    evidence = {
        "id": "r",
        "content": "\n".join(
            [
                "[id 5] 1969-08-15 14:00:00 @ Rocky path: action: the bus departed",
                "[id 35] 1969-08-15 14:08:40 @ Red House: action: arrived outside the Red House",
            ]
        ),
        "temporal": {},
    }
    ans = TemporalQueryService().try_answer(q, [evidence])
    assert ans is not None
    assert ans.answer == "8 minutes 40 seconds"
