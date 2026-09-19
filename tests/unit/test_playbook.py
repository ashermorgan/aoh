import os
import unittest
from unittest.mock import mock_open, patch

import aoh.playbook
from aoh.playbook import PlaybookFileError, get_playbook


class TestPlaybookGetPlaybook(unittest.TestCase):
    @patch.object(aoh.playbook, 'open', mock_open(read_data='main.yml:'))
    def test_default_values(self):
        pb = get_playbook('main.yml')

        self.assertEqual(pb.name, 'main.yml')
        self.assertEqual(pb.path, os.path.abspath('main.yml'))
        self.assertEqual(pb.host, None)
        self.assertEqual(pb.groups, [])
        self.assertEqual(pb.env, {})
        self.assertEqual(pb.limit, True)
        self.assertEqual(pb.password, False)
        self.assertEqual(pb.output, True)
        self.assertEqual(pb.allow_opts, [])
        self.assertEqual(pb.block_opts, [])
        self.assertEqual(pb.jinja_args, False)
        self.assertEqual(pb.extra_args, [])
        self.assertEqual(pb.web_description, None)


    @patch.object(aoh.playbook, 'open', mock_open(read_data='x: ['))
    def test_invalid_yaml(self):
        with self.assertRaisesRegex(PlaybookFileError, 'Failed to parse'):
            get_playbook('main.yml')


    @patch.object(aoh.playbook, 'open', mock_open(read_data='other.yml:'))
    def test_missing_playbook(self):
        self.assertEqual(get_playbook('main.yml'), None)


    @patch.object(aoh.playbook, 'open',
                  mock_open(read_data='main.yml:\n  allow_opts: [--step]'))
    def test_unsupported_opts(self):
        with self.assertRaisesRegex(PlaybookFileError, 'not supported'):
            get_playbook('main.yml')


    @patch.object(aoh.playbook, 'open',
                  mock_open(read_data='main.yml:\n  allow_opts: [--limit]'))
    def test_limit_opt_enabled(self):
        with self.assertRaisesRegex(PlaybookFileError, 'if limit is true'):
            get_playbook('main.yml')


    @patch.object(aoh.playbook, 'open',
                  mock_open(read_data='main.yml:\n  limit: false\n'
                  '  allow_opts: [--limit]'))
    def test_limit_opt_disabled(self):
        pb = get_playbook('main.yml')
        self.assertEqual(pb.limit, False)
        self.assertEqual(pb.allow_opts, ['--limit'])


    @patch.object(aoh.playbook, 'open',
                  mock_open(read_data='main.yml:\n  limit: asdf'))
    def test_bad_bool_type(self):
        with self.assertRaisesRegex(PlaybookFileError, 'must be of type'):
            get_playbook('main.yml')


    @patch.object(aoh.playbook, 'open',
                  mock_open(read_data='main.yml:\n  limit: false'))
    def test_good_bool_type(self):
        self.assertEqual(get_playbook('main.yml').limit, False)


    @patch.object(aoh.playbook, 'open',
                  mock_open(read_data='main.yml:\n  groups: asdf'))
    def test_bad_array_type(self):
        with self.assertRaisesRegex(PlaybookFileError, 'must be of type'):
            get_playbook('main.yml')


    @patch.object(aoh.playbook, 'open',
                  mock_open(read_data='main.yml:\n  groups: [one, two]'))
    def test_good_array_type(self):
        self.assertEqual(get_playbook('main.yml').groups, ['one', 'two'])
