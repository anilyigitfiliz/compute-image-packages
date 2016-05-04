#!/usr/bin/python
# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unittest for instance_setup.py module."""

import subprocess

from google_compute_engine.instance_setup import instance_setup
from google_compute_engine.test_compat import mock
from google_compute_engine.test_compat import unittest


class InstanceSetupTest(unittest.TestCase):

  def setUp(self):
    self.mock_instance_config = mock.Mock()
    self.mock_logger = mock.Mock()
    self.mock_setup = mock.create_autospec(instance_setup.InstanceSetup)
    self.mock_setup.instance_config = self.mock_instance_config
    self.mock_setup.logger = self.mock_logger

  @mock.patch('google_compute_engine.instance_setup.instance_setup.subprocess')
  def testRunScript(self, mock_subprocess):
    mock_readline = mock.Mock()
    mock_readline.side_effect = [bytes(b'a\n'), bytes(b'b\n'), bytes(b'')]
    mock_stdout = mock.Mock()
    mock_stdout.readline = mock_readline
    mock_process = mock.Mock()
    mock_process.poll.return_value = 0
    mock_process.stdout = mock_stdout
    mock_subprocess.Popen.return_value = mock_process
    script = '/tmp/script.py'

    instance_setup.InstanceSetup._RunScript(self.mock_setup, script)
    expected_calls = [mock.call('a'), mock.call('b')]
    self.assertEqual(self.mock_logger.info.mock_calls, expected_calls)
    mock_subprocess.Popen.assert_called_once_with(
        script, shell=True, stderr=mock_subprocess.STDOUT,
        stdout=mock_subprocess.PIPE)
    mock_process.poll.assert_called_once_with()

  def testGetInstanceId(self):
    self.mock_setup.metadata_dict = {'instance': {'attributes': {}, 'id': 123}}
    self.assertEqual(
        instance_setup.InstanceSetup._GetInstanceId(self.mock_setup), '123')
    self.mock_logger.warning.assert_not_called()

  def testGetInstanceIdNotFound(self):
    self.mock_setup.metadata_dict = {'instance': {'attributes': {}}}
    self.assertIsNone(
        instance_setup.InstanceSetup._GetInstanceId(self.mock_setup))
    self.assertEqual(self.mock_logger.warning.call_count, 1)

  @mock.patch('google_compute_engine.instance_setup.instance_setup.shutil.move')
  @mock.patch('google_compute_engine.instance_setup.instance_setup.subprocess.check_call')
  @mock.patch('google_compute_engine.instance_setup.instance_setup.tempfile.NamedTemporaryFile')
  def testGenerateSshKey(self, mock_tempfile, mock_call, mock_move):
    key_type = 'key-type'
    key_dest = '/key/dest'
    temp_dest = '/tmp/dest'
    mock_tempfile.return_value = mock_tempfile
    mock_tempfile.__enter__.return_value.name = temp_dest

    instance_setup.InstanceSetup._GenerateSshKey(
        self.mock_setup, key_type, key_dest)
    mock_tempfile.assert_called_once_with(prefix=key_type, delete=True)
    self.mock_logger.info.assert_called_once_with(mock.ANY, key_dest)
    mock_call.assert_called_once_with(
        ['ssh-keygen', '-t', key_type, '-f', temp_dest, '-N', '', '-q'])
    self.mock_logger.warning.assert_not_called()
    expected_calls = [
        mock.call(temp_dest, key_dest),
        mock.call('%s.pub' % temp_dest, '%s.pub' % key_dest),
    ]
    self.assertEqual(mock_move.mock_calls, expected_calls)

  @mock.patch('google_compute_engine.instance_setup.instance_setup.subprocess.check_call')
  def testGenerateSshKeyProcessError(self, mock_call):
    key_type = 'key-type'
    key_dest = '/key/dest'
    mock_call.side_effect = subprocess.CalledProcessError(1, 'Test')

    instance_setup.InstanceSetup._GenerateSshKey(
        self.mock_setup, key_type, key_dest)
    self.mock_logger.info.assert_called_once_with(mock.ANY, key_dest)
    self.mock_logger.warning.assert_called_once_with(mock.ANY, key_dest)

  @mock.patch('google_compute_engine.instance_setup.instance_setup.subprocess.call')
  @mock.patch('google_compute_engine.instance_setup.instance_setup.os.path.exists')
  def testStartSshdSysVinit(self, mock_exists, mock_call):
    mocks = mock.Mock()
    mocks.attach_mock(mock_exists, 'exists')
    mocks.attach_mock(mock_call, 'call')
    mock_exists.side_effect = [False, False, True]

    instance_setup.InstanceSetup._StartSshd(self.mock_setup)
    expected_calls = [
        mock.call.exists('/bin/systemctl'),
        mock.call.exists('/etc/init.d/ssh'),
        mock.call.exists('/etc/init/ssh.conf'),
        mock.call.call(['service', 'ssh', 'start']),
        mock.call.call(['service', 'ssh', 'reload']),
    ]
    self.assertEqual(mocks.mock_calls, expected_calls)

  @mock.patch('google_compute_engine.instance_setup.instance_setup.subprocess.call')
  @mock.patch('google_compute_engine.instance_setup.instance_setup.os.path.exists')
  def testStartSshdUpstart(self, mock_exists, mock_call):
    mocks = mock.Mock()
    mocks.attach_mock(mock_exists, 'exists')
    mocks.attach_mock(mock_call, 'call')
    mock_exists.side_effect = [False, False, False, False, True]

    instance_setup.InstanceSetup._StartSshd(self.mock_setup)
    expected_calls = [
        mock.call.exists('/bin/systemctl'),
        mock.call.exists('/etc/init.d/ssh'),
        mock.call.exists('/etc/init/ssh.conf'),
        mock.call.exists('/etc/init.d/sshd'),
        mock.call.exists('/etc/init/sshd.conf'),
        mock.call.call(['service', 'sshd', 'start']),
        mock.call.call(['service', 'sshd', 'reload']),
    ]
    self.assertEqual(mocks.mock_calls, expected_calls)

  @mock.patch('google_compute_engine.instance_setup.instance_setup.subprocess.call')
  @mock.patch('google_compute_engine.instance_setup.instance_setup.os.path.exists')
  def testStartSshdSystemd(self, mock_exists, mock_call):
    mocks = mock.Mock()
    mocks.attach_mock(mock_exists, 'exists')
    mocks.attach_mock(mock_call, 'call')
    mock_exists.return_value = True

    instance_setup.InstanceSetup._StartSshd(self.mock_setup)
    expected_calls = [mock.call.exists('/bin/systemctl')]
    self.assertEqual(mocks.mock_calls, expected_calls)

  def testSetSshHostKeys(self):
    self.mock_instance_config.GetOptionString.return_value = '123'
    mock_instance_id = mock.Mock()
    mock_instance_id.return_value = '123'
    self.mock_setup._GetInstanceId = mock_instance_id

    instance_setup.InstanceSetup._SetSshHostKeys(self.mock_setup)
    self.mock_instance_config.SetOptions.assert_not_called()
    self.mock_instance_config.WriteOptions.assert_not_called()

  @mock.patch('google_compute_engine.instance_setup.instance_setup.os.listdir')
  def testSetSshHostKeysFirstBoot(self, mock_listdir):
    self.mock_instance_config.GetOptionString.return_value = None
    mock_instance_id = mock.Mock()
    mock_instance_id.return_value = '123'
    self.mock_setup._GetInstanceId = mock_instance_id
    mock_generate_key = mock.Mock()
    self.mock_setup._GenerateSshKey = mock_generate_key
    mock_listdir.return_value = [
        'ssh_config',
        'ssh_host_rsa_key',
        'ssh_host_dsa_key.pub',
        'ssh_host_ed25519_key',
        'ssh_host_ed25519_key.pub',
        'ssh_host_rsa_key',
        'ssh_host_rsa_key.pub',
    ]

    instance_setup.InstanceSetup._SetSshHostKeys(self.mock_setup)
    expected_calls = [
        mock.call('rsa', '/etc/ssh/ssh_host_rsa_key'),
        mock.call('ed25519', '/etc/ssh/ssh_host_ed25519_key'),
        mock.call('rsa', '/etc/ssh/ssh_host_rsa_key'),
    ]
    self.assertEqual(mock_generate_key.mock_calls, expected_calls)
    self.mock_instance_config.SetOption.assert_called_once_with(
        'instance_id', '123')
    self.mock_instance_config.WriteConfig.assert_called_once_with()

  def testSetSshHostKeysFirstBootLocked(self):
    self.mock_instance_config.GetOptionString.return_value = None
    self.mock_instance_config.WriteConfig.side_effect = IOError('Test Error')

    instance_setup.InstanceSetup._SetSshHostKeys(self.mock_setup)
    self.mock_instance_config.WriteConfig.assert_called_once_with()
    self.mock_logger.warning.assert_called_once_with('Test Error')

  def testGetNumericProjectId(self):
    self.mock_setup.metadata_dict = {
        'project': {
            'attributes': {},
            'numericProjectId': 123,
        }
    }
    self.assertEqual(
        instance_setup.InstanceSetup._GetNumericProjectId(self.mock_setup),
        '123')
    self.mock_logger.warning.assert_not_called()

  def testGetNumericProjectIdNotFound(self):
    self.mock_setup.metadata_dict = {'project': {'attributes': {}}}
    self.assertIsNone(
        instance_setup.InstanceSetup._GetNumericProjectId(self.mock_setup))
    self.assertEqual(self.mock_logger.warning.call_count, 1)

  @mock.patch('google_compute_engine.instance_setup.instance_setup.boto_config.BotoConfig')
  def testSetupBotoConfig(self, mock_boto):
    mock_project_id = mock.Mock()
    mock_project_id.return_value = '123'
    self.mock_setup._GetNumericProjectId = mock_project_id
    instance_setup.InstanceSetup._SetupBotoConfig(self.mock_setup)
    mock_boto.assert_called_once_with('123')

  @mock.patch('google_compute_engine.instance_setup.instance_setup.boto_config.BotoConfig')
  def testSetupBotoConfigLocked(self, mock_boto):
    mock_boto.side_effect = IOError('Test Error')
    instance_setup.InstanceSetup._SetupBotoConfig(self.mock_setup)
    self.mock_logger.warning.assert_called_once_with('Test Error')


if __name__ == '__main__':
  unittest.main()
