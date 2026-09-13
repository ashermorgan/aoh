import unittest
from unittest.mock import mock_open, patch

import bcrypt

import aoh.security
from aoh.playbook import Playbook
from aoh.security import (
    PasswordFileError,
    get_required_passwords,
    validate_aoh_password,
    validate_args,
)


class TestSecurityGetRequiredPasswords(unittest.TestCase):
    def test_default_options(self):
        pb = Playbook('main.yml', {})

        self.assertEqual(
            set(get_required_passwords(pb, [])),
            set(),
        )
        self.assertEqual(
            set(get_required_passwords(pb, ['--ask-pass'])),
            {'connection_password'},
        )
        self.assertEqual(
            set(get_required_passwords(pb, ['--ask-pass', '-K'])),
            {'connection_password', 'become_password'},
        )


    def test_aoh_password(self):
        pb = Playbook('main.yml', {'password': True})

        self.assertEqual(
            set(get_required_passwords(pb, [])),
            {'aoh_password'},
        )
        self.assertEqual(
            set(get_required_passwords(pb, ['--ask-pass'])),
            {'aoh_password', 'connection_password'},
        )
        self.assertEqual(
            set(get_required_passwords(pb, ['--ask-pass', '-K'])),
            {'aoh_password', 'connection_password', 'become_password'},
        )


    @patch.object(aoh.security, 'get_config_values', return_value={
        'DEFAULT_ASK_PASS': False,
        'DEFAULT_BECOME_ASK_PASS': True,
        'DEFAULT_ASK_VAULT_PASS': False,
    })
    def test_config_file(self, _):
        pb = Playbook('main.yml', {})

        self.assertEqual(
            set(get_required_passwords(pb, [])),
            {'become_password'},
        )
        self.assertEqual(
            set(get_required_passwords(pb, ['--ask-pass'])),
            {'become_password', 'connection_password'},
        )
        self.assertEqual(
            set(get_required_passwords(pb, ['--ask-pass', '-K'])),
            {'become_password', 'connection_password'},
        )


    @patch.object(aoh.security, 'get_config_values', return_value={
        'DEFAULT_ASK_PASS': False,
        'DEFAULT_BECOME_ASK_PASS': True,
        'DEFAULT_ASK_VAULT_PASS': False,
    })
    def test_aoh_password_and_config_file(self, _):
        pb = Playbook('main.yml', {'password': True})

        self.assertEqual(
            set(get_required_passwords(pb, [])),
            {'aoh_password', 'become_password'},
        )
        self.assertEqual(
            set(get_required_passwords(pb, ['--ask-pass'])),
            {'aoh_password', 'become_password', 'connection_password'},
        )
        self.assertEqual(
            set(get_required_passwords(pb, ['--ask-pass', '-K'])),
            {'aoh_password', 'become_password', 'connection_password'},
        )


class TestSecurityValidateAohPassword(unittest.TestCase):
    hash = bcrypt.hashpw(b'hunter2', bcrypt.gensalt()).decode()

    def test_no_password_required(self):
        pb = Playbook('main.yml', {'password': False})

        self.assertTrue(validate_aoh_password(pb, 'asdf'))
        self.assertTrue(validate_aoh_password(pb, None))


    def test_null_password(self):
        pb = Playbook('main.yml', {'password': True})

        self.assertFalse(validate_aoh_password(pb, None))


    @patch.object(aoh.security, 'open', mock_open(read_data='other.yml: foo'))
    def test_missing_hash(self):
        pb = Playbook('main.yml', {'password': True})

        with self.assertRaisesRegex(PasswordFileError, 'not found'):
            validate_aoh_password(pb, 'asdf')


    @patch.object(aoh.security, 'open', mock_open(read_data='main.yml: foo'))
    def test_bad_hash(self):
        pb = Playbook('main.yml', {'password': True})

        with self.assertRaisesRegex(PasswordFileError, 'Invalid bcrypt hash'):
            validate_aoh_password(pb, 'asdf')


    @patch.object(aoh.security, 'open',
                  mock_open(read_data=f'main.yml: {hash}'))
    def test_bad_password(self):
        pb = Playbook('main.yml', {'password': True})

        self.assertFalse(validate_aoh_password(pb, 'asdf'))


    @patch.object(aoh.security, 'open',
                  mock_open(read_data=f'main.yml: {hash}'))
    def test_good_password(self):
        pb = Playbook('main.yml', {'password': True})

        self.assertTrue(validate_aoh_password(pb, 'hunter2'))


class TestSecurityValidateArgs(unittest.TestCase):
    def test_default_options(self):
        pb = Playbook('main.yml', {})

        self.assertTrue(validate_args(pb, ['--check']))
        self.assertTrue(validate_args(pb, ['-t', 'foo']))
        self.assertTrue(validate_args(pb, ['--tags=bar']))

        self.assertFalse(validate_args(pb, ['--verbose', '--version']))
        self.assertFalse(validate_args(pb, ['-e', 'foo=bar']))
        self.assertFalse(validate_args(pb, ['--check', '-v']))

        pb.allow_opts = ['--version']

        self.assertTrue(validate_args(pb, ['--check']))
        self.assertTrue(validate_args(pb, ['-t', 'foo']))
        self.assertTrue(validate_args(pb, ['--tags=bar']))

        self.assertFalse(validate_args(pb, ['--verbose', '--version']))
        self.assertFalse(validate_args(pb, ['-e', 'foo=bar']))
        self.assertFalse(validate_args(pb, ['--check', '-v']))


    def test_allowed_options(self):
        pb = Playbook('main.yml', {})

        self.assertFalse(validate_args(pb, ['--verbose', '--check']))

        pb.allow_opts = ['--verbose']

        self.assertTrue(validate_args(pb, ['--verbose', '--check']))


    def test_blocked_options(self):
        pb = Playbook('main.yml', {})

        self.assertTrue(validate_args(pb, ['--diff', '--check']))

        pb.block_opts = ['--check']

        self.assertFalse(validate_args(pb, ['--diff', '--check']))


    def test_jinja(self):
        pb = Playbook('main.yml', {})

        self.assertFalse(validate_args(pb, ['-t', '{{x}}']))
        self.assertFalse(validate_args(pb, ['-t', '{% x %}']))
        self.assertFalse(validate_args(pb, ['-t', '\u007b\x25 x %}']))

        pb.jinja_args = True

        self.assertTrue(validate_args(pb, ['-t', '{{x}}']))
        self.assertTrue(validate_args(pb, ['-t', '{% x %}']))
        self.assertTrue(validate_args(pb, ['-t', '\u007b\x25 x %}']))

        self.assertFalse(validate_args(pb, ['--verbose', '--version']))
        self.assertFalse(validate_args(pb, ['-e', 'foo=bar']))
        self.assertFalse(validate_args(pb, ['--check', '-v']))


    def test_unsupported_options(self):
        pb = Playbook('main.yml', {})

        self.assertFalse(validate_args(pb, ['--step']))

        pb.allow_opts = ['--step']

        self.assertFalse(validate_args(pb, ['--step']))
