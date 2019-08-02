#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from mock import Mock
from mock import patch

from octavia.common import context
from octavia.common import rpc
from octavia.common import notification
from octavia.common.notification import EndNotification
from octavia.common.notification import StartNotification
import octavia.tests.unit.base as base

class TestEndNotification(base.TestCase):
    def setUp(self):
        super(TestEndNotification, self).setUp()
        self.context = OctaviaTestContext(self)

    def test_call(self):
        with patch.object(self.context, "notification") as notification:
            with EndNotification(self.context):
                pass
            self.assertTrue(notification.notify_end.called)

    def server_exception(self, server_type):
        with patch.object(self.context, "notification") as notification:
            try:
                with EndNotification(self.context):
                    raise Exception
            except Exception:
                self.assertTrue(notification.notify_exc_info.called)


class TestStartNotification(base.TestCase):

    def setUp(self):
        super(TestStartNotification, self).setUp()
        self.context = OctaviaTestContext(self)

    def test_call(self):
        with patch.object(self.context, "notification") as notification:
            with StartNotification(self.context):
                pass
            self.assertTrue(notification.notify_start.called)


class OctaviaTestContext(context.Context):
    def __init__(self, test_case, **kwargs):
        # diltram: this one must be removed after fixing issue in oslo.config
        # https://bugs.launchpad.net/oslo.config/+bug/1645868
        context.CONF.__call__(args=[])
        super(OctaviaTestContext, self).__init__(user_id='11111',
                                                project_id='2222')
        self.notification = OctaviaTestNotification(
            self)


class OctaviaTestNotification(notification.OctaviaAPINotification):

    def event_type(self):
        return 'notification_test'

    def required_start_traits(self):
        return ['provider']

    def optional_start_traits(self):
        return ['parameters']

    def required_end_traits(self):
        return ['provider']


class TestOctaviaNotification(base.TestCase):

    def setUp(self):
        super(TestOctaviaNotification, self).setUp()
        self.test_notification = OctaviaTestNotification(Mock())

    def test_missing_required_start_traits(self):
        self.assertRaisesRegex(Exception,
                               self.test_notification.required_start_traits()[0],
                               self.test_notification.notify_start)

    def test_invalid_start_traits(self):
        self.assertRaisesRegex(Exception,
                               "The following required keys",
                               self.test_notification.notify_start, test='test')

    def test_missing_required_end_traits(self):
        self.assertRaisesRegex(Exception,
                               self.test_notification.required_end_traits()[0],
                               self.test_notification.notify_end)

    def test_invalid_end_traits(self):
        self.assertRaisesRegex(Exception,
                               "The following required keys",
                               self.test_notification.notify_end, test='test')

    def test_missing_required_error_traits(self):
        self.assertRaisesRegex(Exception,
                               self.test_notification.required_error_traits()[0],
                               self.test_notification._notify, 'error',
                               self.test_notification.required_error_traits(), [])

    @patch.object(rpc, 'get_notifier')
    def test_start_event(self, notifier):
        self.test_notification.notify_start(provider='test', id='111', provisioning_status='active')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        self.assertEqual('octavia.notification_test.start', a[1])

    @patch.object(rpc, 'get_notifier')
    def test_end_event(self, notifier):
        self.test_notification.notify_end(provider='test', id='111', provisioning_status='active')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        self.assertEqual('octavia.notification_test.end', a[1])

    @patch.object(rpc, 'get_notifier')
    def test_verify_base_values(self, notifier):
        self.test_notification.notify_start(provider='test', id='111', provisioning_status='active')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('tenant_id', payload)
        self.assertIn('id', payload)
        self.assertIn('provisioning_status', payload)

    @patch.object(rpc, 'get_notifier')
    def test_verify_required_start_args(self, notifier):
        self.test_notification.notify_start(provider='foo', id='111', provisioning_status='active')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('provider', payload)

    @patch.object(rpc, 'get_notifier')
    def test_verify_optional_start_args(self, notifier):
        self.test_notification.notify_start(provider='test', parameters="test", id='111', provisioning_status='active')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('parameters', payload)

    @patch.object(rpc, 'get_notifier')
    def test_verify_required_end_args(self, notifier):
        self.test_notification.notify_end(provider='test', id='111', provisioning_status='active')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('provider', payload)

    def _test_notify_callback(self, fn, *args, **kwargs):
        with patch.object(rpc, 'get_notifier') as notifier:
            mock_callback = Mock()
            self.test_notification.register_notify_callback(mock_callback)
            mock_context = Mock()
            mock_context.notification = Mock()
            self.test_notification.context = mock_context
            fn(*args, **kwargs)
            self.assertTrue(notifier().info.called)
            self.assertTrue(mock_callback.called)
            self.test_notification.register_notify_callback(None)

    def test_notify_callback(self):
        required_keys = {
            'name': 'aaa',
            'parameters': 'parameters',
            'id': '1111',
            'provisioning_status': 'active',
            'provider': 'test'
        }
        self._test_notify_callback(self.test_notification.notify_start,
                                   **required_keys)
        self._test_notify_callback(self.test_notification.notify_end,
                                   **required_keys)
        self._test_notify_callback(self.test_notification.notify_exc_info,
                                   'error', 'exc')