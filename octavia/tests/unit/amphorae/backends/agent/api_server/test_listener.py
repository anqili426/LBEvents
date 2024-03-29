# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import subprocess

import mock
from oslo_utils import uuidutils

from octavia.amphorae.backends.agent.api_server import listener
from octavia.amphorae.backends.agent.api_server import util as agent_util
from octavia.common import constants as consts
from octavia.common.jinja.haproxy import jinja_cfg
from octavia.tests.common import utils as test_utils
import octavia.tests.unit.base as base
from octavia.tests.unit.common.sample_configs import sample_configs

BASE_AMP_PATH = '/var/lib/octavia'
BASE_CRT_PATH = BASE_AMP_PATH + '/certs'
LISTENER_ID1 = uuidutils.generate_uuid()


class ListenerTestCase(base.TestCase):
    def setUp(self):
        super(ListenerTestCase, self).setUp()
        self.jinja_cfg = jinja_cfg.JinjaTemplater(
            base_amp_path=BASE_AMP_PATH,
            base_crt_dir=BASE_CRT_PATH)
        self.mock_platform = mock.patch("distro.id").start()
        self.mock_platform.return_value = "ubuntu"
        self.test_listener = listener.Listener()

    def test_parse_haproxy_config(self):
        # template_tls
        tls_tupe = sample_configs.sample_tls_container_tuple(
            id='tls_container_id',
            certificate='imaCert1', private_key='imaPrivateKey1',
            primary_cn='FakeCN')
        rendered_obj = self.jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_amphora_tuple(),
            sample_configs.sample_listener_tuple(proto='TERMINATED_HTTPS',
                                                 tls=True, sni=True),
            tls_tupe)

        path = agent_util.config_path(LISTENER_ID1)
        self.useFixture(test_utils.OpenFixture(path, rendered_obj))

        res = self.test_listener._parse_haproxy_file(LISTENER_ID1)
        self.assertEqual('TERMINATED_HTTPS', res['mode'])
        self.assertEqual('/var/lib/octavia/sample_listener_id_1.sock',
                         res['stats_socket'])
        self.assertEqual(
            '/var/lib/octavia/certs/sample_listener_id_1/tls_container_id.pem',
            res['ssl_crt'])

        # render_template_tls_no_sni
        rendered_obj = self.jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_amphora_tuple(),
            sample_configs.sample_listener_tuple(
                proto='TERMINATED_HTTPS', tls=True),
            tls_cert=sample_configs.sample_tls_container_tuple(
                id='tls_container_id',
                certificate='ImAalsdkfjCert',
                private_key='ImAsdlfksdjPrivateKey',
                primary_cn="FakeCN"))

        self.useFixture(test_utils.OpenFixture(path, rendered_obj))

        res = self.test_listener._parse_haproxy_file(LISTENER_ID1)
        self.assertEqual('TERMINATED_HTTPS', res['mode'])
        self.assertEqual(BASE_AMP_PATH + '/sample_listener_id_1.sock',
                         res['stats_socket'])
        self.assertEqual(
            BASE_CRT_PATH + '/sample_listener_id_1/tls_container_id.pem',
            res['ssl_crt'])

        # render_template_http
        rendered_obj = self.jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_amphora_tuple(),
            sample_configs.sample_listener_tuple())

        self.useFixture(test_utils.OpenFixture(path, rendered_obj))

        res = self.test_listener._parse_haproxy_file(LISTENER_ID1)
        self.assertEqual('HTTP', res['mode'])
        self.assertEqual(BASE_AMP_PATH + '/sample_listener_id_1.sock',
                         res['stats_socket'])
        self.assertIsNone(res['ssl_crt'])

        # template_https
        rendered_obj = self.jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_amphora_tuple(),
            sample_configs.sample_listener_tuple(proto='HTTPS'))
        self.useFixture(test_utils.OpenFixture(path, rendered_obj))

        res = self.test_listener._parse_haproxy_file(LISTENER_ID1)
        self.assertEqual('TCP', res['mode'])
        self.assertEqual(BASE_AMP_PATH + '/sample_listener_id_1.sock',
                         res['stats_socket'])
        self.assertIsNone(res['ssl_crt'])

        # Bogus format
        self.useFixture(test_utils.OpenFixture(path, 'Bogus'))
        try:
            res = self.test_listener._parse_haproxy_file(LISTENER_ID1)
            self.fail("No Exception?")
        except listener.ParsingError:
            pass

    @mock.patch('os.path.exists')
    @mock.patch('octavia.amphorae.backends.agent.api_server' +
                '.util.get_haproxy_pid')
    def test_check_listener_status(self, mock_pid, mock_exists):
        mock_pid.return_value = '1245'
        mock_exists.side_effect = [True, True]
        config_path = agent_util.config_path(LISTENER_ID1)
        file_contents = 'frontend {}'.format(LISTENER_ID1)
        self.useFixture(test_utils.OpenFixture(config_path, file_contents))
        self.assertEqual(
            consts.ACTIVE,
            self.test_listener._check_listener_status(LISTENER_ID1))

        mock_exists.side_effect = [True, False]
        self.assertEqual(
            consts.ERROR,
            self.test_listener._check_listener_status(LISTENER_ID1))

        mock_exists.side_effect = [False]
        self.assertEqual(
            consts.OFFLINE,
            self.test_listener._check_listener_status(LISTENER_ID1))

    @mock.patch('os.makedirs')
    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    @mock.patch('os.path.join')
    @mock.patch('octavia.amphorae.backends.agent.api_server.util.'
                'get_listeners')
    @mock.patch('octavia.amphorae.backends.agent.api_server.util'
                '.haproxy_sock_path')
    def test_vrrp_check_script_update(self, mock_sock_path, mock_get_listeners,
                                      mock_join, mock_listdir, mock_exists,
                                      mock_makedirs):
        mock_get_listeners.return_value = ['abc', LISTENER_ID1]
        mock_sock_path.return_value = 'listener.sock'
        mock_exists.return_value = False
        cmd = 'haproxy-vrrp-check ' + ' '.join(['listener.sock']) + '; exit $?'

        path = agent_util.keepalived_dir()
        m = self.useFixture(test_utils.OpenFixture(path)).mock_open

        self.test_listener.vrrp_check_script_update(LISTENER_ID1, 'stop')
        handle = m()
        handle.write.assert_called_once_with(cmd)

        mock_get_listeners.return_value = ['abc', LISTENER_ID1]
        cmd = ('haproxy-vrrp-check ' + ' '.join(['listener.sock',
                                                 'listener.sock']) + '; exit '
                                                                     '$?')

        m = self.useFixture(test_utils.OpenFixture(path)).mock_open
        self.test_listener.vrrp_check_script_update(LISTENER_ID1, 'start')
        handle = m()
        handle.write.assert_called_once_with(cmd)

    @mock.patch('os.path.exists')
    @mock.patch('octavia.amphorae.backends.agent.api_server' +
                '.util.get_haproxy_pid')
    def test_check_haproxy_status(self, mock_pid, mock_exists):
        mock_pid.return_value = '1245'
        mock_exists.side_effect = [True, True]
        self.assertEqual(
            consts.ACTIVE,
            self.test_listener._check_haproxy_status(LISTENER_ID1))

        mock_exists.side_effect = [True, False]
        self.assertEqual(
            consts.OFFLINE,
            self.test_listener._check_haproxy_status(LISTENER_ID1))

        mock_exists.side_effect = [False]
        self.assertEqual(
            consts.OFFLINE,
            self.test_listener._check_haproxy_status(LISTENER_ID1))

    @mock.patch('octavia.amphorae.backends.agent.api_server.listener.Listener.'
                '_check_haproxy_status')
    @mock.patch('octavia.amphorae.backends.agent.api_server.listener.Listener.'
                'vrrp_check_script_update')
    @mock.patch('os.path.exists')
    @mock.patch('octavia.amphorae.backends.agent.api_server.listener.Listener.'
                '_check_listener_exists')
    @mock.patch('subprocess.check_output')
    def test_start_stop_listener(self, mock_check_output, mock_list_exists,
                                 mock_path_exists, mock_vrrp_update,
                                 mock_check_status):
        listener_id = uuidutils.generate_uuid()

        mock_path_exists.side_effect = [False, True, True, False, False]
        mock_check_status.side_effect = ['bogus', consts.OFFLINE]

        # Happy path - No VRRP
        ref_command_split = ['/usr/sbin/service']
        ref_command_split.append('haproxy-{}'.format(listener_id))
        ref_command_split.append(consts.AMP_ACTION_START)

        result = self.test_listener.start_stop_listener(
            listener_id, consts.AMP_ACTION_START)

        mock_check_output.assert_called_once_with(ref_command_split,
                                                  stderr=subprocess.STDOUT)
        mock_list_exists.assert_called_once_with(listener_id)
        mock_vrrp_update.assert_not_called()
        self.assertEqual(202, result.status_code)
        self.assertEqual('OK', result.json['message'])
        ref_details = ('Configuration file is valid\n'
                       'haproxy daemon for {0} started'.format(listener_id))
        self.assertEqual(ref_details, result.json['details'])

        # Happy path - VRRP - RELOAD
        mock_list_exists.reset_mock()
        mock_vrrp_update.reset_mock()
        mock_check_output.reset_mock()

        ref_command_split = ['/usr/sbin/service']
        ref_command_split.append('haproxy-{}'.format(listener_id))
        ref_command_split.append(consts.AMP_ACTION_RELOAD)

        result = self.test_listener.start_stop_listener(
            listener_id, consts.AMP_ACTION_RELOAD)

        mock_check_output.assert_called_once_with(ref_command_split,
                                                  stderr=subprocess.STDOUT)
        mock_list_exists.assert_called_once_with(listener_id)
        mock_vrrp_update.assert_called_once_with(listener_id,
                                                 consts.AMP_ACTION_RELOAD)
        self.assertEqual(202, result.status_code)
        self.assertEqual('OK', result.json['message'])
        ref_details = ('Listener {0} {1}ed'.format(listener_id,
                                                   consts.AMP_ACTION_RELOAD))
        self.assertEqual(ref_details, result.json['details'])

        # Happy path - VRRP - RELOAD - OFFLINE
        mock_list_exists.reset_mock()
        mock_vrrp_update.reset_mock()
        mock_check_output.reset_mock()

        ref_command_split = ['/usr/sbin/service']
        ref_command_split.append('haproxy-{}'.format(listener_id))
        ref_command_split.append(consts.AMP_ACTION_START)

        result = self.test_listener.start_stop_listener(
            listener_id, consts.AMP_ACTION_RELOAD)

        mock_check_output.assert_called_once_with(ref_command_split,
                                                  stderr=subprocess.STDOUT)
        mock_list_exists.assert_called_once_with(listener_id)
        mock_vrrp_update.assert_called_once_with(listener_id,
                                                 consts.AMP_ACTION_RELOAD)
        self.assertEqual(202, result.status_code)
        self.assertEqual('OK', result.json['message'])
        ref_details = ('Configuration file is valid\n'
                       'haproxy daemon for {0} started'.format(listener_id))
        self.assertEqual(ref_details, result.json['details'])

        # Unhappy path - Not already running
        mock_list_exists.reset_mock()
        mock_vrrp_update.reset_mock()
        mock_check_output.reset_mock()

        ref_command_split = ['/usr/sbin/service']
        ref_command_split.append('haproxy-{}'.format(listener_id))
        ref_command_split.append(consts.AMP_ACTION_START)

        mock_check_output.side_effect = subprocess.CalledProcessError(
            output=b'bogus', returncode=-2, cmd='sit')

        result = self.test_listener.start_stop_listener(
            listener_id, consts.AMP_ACTION_START)

        mock_check_output.assert_called_once_with(ref_command_split,
                                                  stderr=subprocess.STDOUT)
        mock_list_exists.assert_called_once_with(listener_id)
        mock_vrrp_update.assert_not_called()
        self.assertEqual(500, result.status_code)
        self.assertEqual('Error {}ing haproxy'.format(consts.AMP_ACTION_START),
                         result.json['message'])
        self.assertEqual('bogus', result.json['details'])

        # Unhappy path - Already running
        mock_list_exists.reset_mock()
        mock_vrrp_update.reset_mock()
        mock_check_output.reset_mock()

        ref_command_split = ['/usr/sbin/service']
        ref_command_split.append('haproxy-{}'.format(listener_id))
        ref_command_split.append(consts.AMP_ACTION_START)

        mock_check_output.side_effect = subprocess.CalledProcessError(
            output=b'Job is already running', returncode=-2, cmd='sit')

        result = self.test_listener.start_stop_listener(
            listener_id, consts.AMP_ACTION_START)

        mock_check_output.assert_called_once_with(ref_command_split,
                                                  stderr=subprocess.STDOUT)
        mock_list_exists.assert_called_once_with(listener_id)
        mock_vrrp_update.assert_not_called()
        self.assertEqual(202, result.status_code)
        self.assertEqual('OK', result.json['message'])
        ref_details = ('Configuration file is valid\n'
                       'haproxy daemon for {0} started'.format(listener_id))
        self.assertEqual(ref_details, result.json['details'])

        # Invalid action
        mock_check_output.reset_mock()
        mock_list_exists.reset_mock()
        mock_path_exists.reset_mock()
        mock_vrrp_update.reset_mock()
        result = self.test_listener.start_stop_listener(listener_id, 'bogus')
        self.assertEqual(400, result.status_code)
        self.assertEqual('Invalid Request', result.json['message'])
        self.assertEqual('Unknown action: bogus', result.json['details'])
        mock_list_exists.assert_not_called()
        mock_path_exists.assert_not_called()
        mock_vrrp_update.assert_not_called()
        mock_check_output.assert_not_called()
