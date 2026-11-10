"""Shared runner compatibility and optional interval-tag routing, using synthetic input."""

import json
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from simulation.run_algorithm import load_tags, main, predict_frames


class AlgorithmRunnerTests(unittest.TestCase):
    def test_untagged_algorithms_still_receive_exactly_three_arguments(self):
        observations = pd.DataFrame({'frame': [0, 1]})
        algorithm = SimpleNamespace(predict=Mock(return_value=['D', 'H']))
        result = predict_frames(algorithm, observations, {}, {})
        algorithm.predict.assert_called_once_with(observations, {}, {})
        self.assertEqual(result.label.tolist(), ['D', 'H'])

    def test_tagged_variant_writes_separate_outputs_and_source_provenance(self):
        observations = pd.DataFrame({'frame': [0, 1]})
        algorithm = SimpleNamespace(predict=Mock(return_value=['D', 'H']), __file__=__file__)
        config = {'algorithm': 'tagged', 'params': {'a': 1},
                  'variants': {'complete': {'params': {'a': 2}}}}
        tags = [{'code': 'SET PIECES', 'start_frame': 0, 'end_frame': 2, 'team': 'H'}]
        with tempfile.TemporaryDirectory() as tmp, \
                patch('simulation.run_algorithm.io.REPO_ROOT', tmp), \
                patch('simulation.run_algorithm.load_config', return_value=config), \
                patch('simulation.run_algorithm.load_tags', return_value={'c001': tags}), \
                patch('simulation.run_algorithm.io.load_clips', return_value=[('c001', observations, {})]), \
                patch('simulation.run_algorithm.importlib.import_module', side_effect=lambda name:
                      algorithm if name == 'algorithms.tagged.predict' else import_module(name)), \
                patch('sys.argv', ['run', '--experiment', 'exp', '--dataset', 'synthetic',
                                   '--variant', 'complete', '--tags', 'synthetic.json']):
            main()
            out = Path(tmp) / 'outputs/exp/complete/simulation/synthetic'
            self.assertEqual(pd.read_csv(out / 'predictions.csv').label.tolist(), ['D', 'H'])
            metadata = json.loads((out / 'run_metadata.json').read_text())
            self.assertEqual(metadata['variant'], 'complete')
            self.assertIsNotNone(metadata['tags_sha256'])
            self.assertFalse((Path(tmp) / 'outputs/exp/simulation').exists())
        algorithm.predict.assert_called_once_with(observations, {}, {'a': 2}, tags=tags)

    def test_official_tag_adapter_can_be_checked_without_opening_match_files(self):
        event = {'start_frame': 0, 'end_frame': 2, 'code': 'SET PIECES',
                 'tags': {'Type': 'Free Kick', 'Team': 'Barcelona'}}
        with patch('starter.load_smart_tagging.load', return_value=[event]) as load:
            tags = load_tags('smart-tagging', 'synthetic-only')
        load.assert_called_once_with(data_dir='synthetic-only')
        self.assertEqual(tags, [{'start_frame': 0, 'end_frame': 2, 'code': 'SET PIECES',
                                 'type': 'Free Kick', 'team': 'H'}])


if __name__ == '__main__':
    unittest.main()
