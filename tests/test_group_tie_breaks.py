"""Explicit ranking branches, using synthetic scores and no platform identity."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gamemaster-skill/scripts'))
import results_engine as engine


THREE_WAY = {('A', 'B'): (21, 0), ('A', 'C'): (30, 29), ('A', 'D'): (21, 10),
             ('B', 'C'): (21, 10), ('B', 'D'): (19, 21), ('C', 'D'): (21, 10)}
TWO_WAY = {('A', 'B'): (21, 19), ('A', 'C'): (21, 19), ('A', 'D'): (0, 21),
           ('B', 'C'): (21, 0), ('B', 'D'): (21, 0), ('C', 'D'): (21, 10)}


def rank(scores, two='criteria', scope='all', restart=True):
    ids = sorted({e for pair in scores for e in pair})
    policy = {'criteria': [{'metric': 'wins', 'scope': 'all'},
                           {'metric': 'game_diff', 'scope': 'all'},
                           {'metric': 'point_diff', 'scope': scope}],
              'restart_after_split': restart, 'two_entry_tie_break': two}
    matches = [{'match_id': f'M{n}', 'entry_ids': list(pair), 'status': 'completed',
                'winner_id': pair[0 if points[0] > points[1] else 1], 'scoring_mode': 'points',
                'statistics': {'games': [int(points[0] > points[1]), int(points[1] > points[0])],
                               'points': list(points)}} for n, (pair, points) in enumerate(scores.items())]
    return engine.rank_group({'id': 'G', 'project_id': 'P', 'entry_ids': ids, 'ranking': policy}, matches)


def order(report):
    return [r['entry_id'] for r in report['rows']]


class GroupTieBreaks(unittest.TestCase):
    def test_two_way_mutual_result_overrides_contrary_point_difference_only_if_enabled(self):
        self.assertEqual(order(rank(TWO_WAY)), ['B', 'A', 'D', 'C'])
        result = rank(TWO_WAY, 'head_to_head_wins')
        self.assertEqual(order(result), ['A', 'B', 'C', 'D'])
        self.assertEqual(sum(t['criterion']['metric'] == 'head_to_head_wins' for t in result['trace']), 2)

    def test_three_way_all_group_and_tied_subset_are_distinct(self):
        self.assertEqual(order(rank(THREE_WAY, 'head_to_head_wins')), ['A', 'C', 'B', 'D'])
        self.assertEqual(order(rank(THREE_WAY, 'head_to_head_wins', 'tied')), ['A', 'B', 'C', 'D'])

    def test_remaining_two_after_last_criterion_uses_mutual_result(self):
        scores = deepcopy(THREE_WAY)
        scores['A', 'B'] = (21, 10); scores['A', 'C'] = (21, 19); scores['A', 'D'] = (21, 19)
        for restart in (True, False):
            default = rank(scores, restart=restart)
            self.assertFalse(default['resolved'])
            result = rank(scores, 'head_to_head_wins', restart=restart)
            self.assertTrue(result['resolved'])
            self.assertEqual(order(result), ['A', 'B', 'C', 'D'])

    def test_circular_three_way_equality_is_not_broken_by_pairwise_sorting(self):
        scores = {('A', 'B'): (21, 10), ('B', 'C'): (21, 10), ('A', 'C'): (10, 21)}
        result = rank(scores, 'head_to_head_wins')
        self.assertFalse(result['resolved'])
        self.assertTrue(all(r['tied'] for r in result['rows']))

    def test_double_round_robin_mutual_wins_equal_falls_back(self):
        group = {'id': 'G', 'project_id': 'P', 'entry_ids': ['A', 'B'], 'expected_meetings': 2,
                 'ranking': {'criteria': [{'metric': 'wins', 'scope': 'all'}, {'metric': 'point_diff', 'scope': 'all'}],
                             'restart_after_split': True, 'two_entry_tie_break': 'head_to_head_wins'}}
        ms = [{'match_id': 'M1', 'entry_ids': ['A', 'B'], 'status': 'completed', 'winner_id': 'A',
               'statistics': {'games': [1, 0], 'points': [21, 10]}},
              {'match_id': 'M2', 'entry_ids': ['A', 'B'], 'status': 'completed', 'winner_id': 'B',
               'statistics': {'games': [0, 1], 'points': [19, 21]}}]
        self.assertEqual(order(engine.rank_group(group, ms)), ['A', 'B'])

    def test_unknown_rule_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'two_entry_tie_break'):
            rank(TWO_WAY, 'automatic')


if __name__ == '__main__':
    unittest.main()
