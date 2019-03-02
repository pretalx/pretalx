import pytest

from pretalx.submission.models import Review


@pytest.mark.django_db
@pytest.mark.parametrize('score,override,expected', (
    (0, None, '0'),
    (1, None, '1'),
    (None, None, 'ø'),
    (None, True, 'Positive override'),
    (None, False, 'Negative override (Veto)'),
))
def test_review_score_display(submission, score, override, expected, speaker):
    r = Review.objects.create(submission=submission, user=speaker, score=score, override_vote=override)
    assert submission.title in str(r)
    assert r.display_score == expected
