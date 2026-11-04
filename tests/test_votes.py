"""Zeitfenster: Mehrheit, Gleichstand, eine Person eine Stimme."""

from cave_dig.votes import VoteAggregator


def test_majority_after_window():
    agg = VoteAggregator(2.5, one_per_user=True)
    agg.reset(0)
    agg.add("Nora", "left", 0.2)
    agg.add("Kenji", "left", 1.0)
    agg.add("Omar", "right", 1.4)
    assert agg.close_due(2.4) == []
    assert agg.left == 2
    assert agg.right == 1
    closed = agg.close_due(2.5)
    assert len(closed) == 1
    result = closed[0]
    assert result.winner == "left"
    assert result.left == 2
    assert result.right == 1
    assert result.credit_names() == ["Kenji", "Nora"]


def test_tie_has_no_winner_but_credits_everyone():
    agg = VoteAggregator(2.5, True)
    agg.reset(0)
    agg.add("Nora", "left", 0.1)
    agg.add("Omar", "right", 0.2)
    result = agg.close_due(2.5)[0]
    assert result.winner is None
    assert result.credit_names() == ["Nora", "Omar"]


def test_one_vote_per_user_last_direction_wins():
    agg = VoteAggregator(2.5, True)
    agg.reset(0)
    agg.add("Nora", "left", 0.1)
    agg.add("Nora", "left", 0.2)
    agg.add("Nora", "right", 0.4)
    assert agg.left == 0
    assert agg.right == 1


def test_repeat_votes_count_when_allowed():
    agg = VoteAggregator(2.5, one_per_user=False)
    agg.reset(0)
    agg.add("Nora", "left", 0.1)
    agg.add("Nora", "left", 0.2)
    assert agg.left == 2
    result = agg.close_due(2.5)[0]
    assert result.left == 2
    assert result.voters_left == ("Nora",)


def test_next_window_starts_empty():
    agg = VoteAggregator(2.5, True)
    agg.reset(0)
    agg.add("Nora", "left", 0.2)
    agg.close_due(2.5)
    agg.add("Omar", "right", 2.6)
    result = agg.close_due(5.0)[0]
    assert result.winner == "right"
    assert result.left == 0
    assert result.right == 1


def test_progress_moves_from_zero_to_one():
    agg = VoteAggregator(2.0, True)
    agg.reset(10)
    assert agg.progress(10) == 0
    assert agg.progress(11) == 0.5
    assert agg.progress(13) == 1
