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
"""The notification module."""

import abc
import copy
import traceback

from octavia.common import rpc
from octavia.i18n import _
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class EndNotification(object):
    @property
    def _notifier(self):
        """Returns the notification for Octavia API."""
        return (self.context.notification)

    def __init__(self, context, **kwargs):
        self.context = context
        self.context.notification.payload.update(kwargs)

    def __enter__(self):
        return self.context.notification

    def __exit__(self, etype, value, tb):
        if etype:
            message = str(value)
            exception = traceback.format_exception(etype, value, tb)
            self._notifier.notify_exc_info(message, exception)
        else:
            self._notifier.notify_end()


class StartNotification(EndNotification):
    def __enter__(self):
        self.context.notification.notify_start()
        return super(StartNotification, self).__enter__()


class OctaviaAPINotification(object):
    event_type_format = 'octavia.%s.%s'
    notify_callback = None

    @classmethod
    def register_notify_callback(cls, callback):
        """Callback when a notification is sent out."""
        cls.notify_callback = callback

    @abc.abstractmethod
    def event_type(self):
        'Returns the event type (like "create" for octavia.create.start)'
        pass

    @abc.abstractmethod
    def required_start_traits(self):
        'Returns list of required traits for start notification'
        pass

    def optional_start_traits(self):
        'Returns list of optional traits for start notification'
        return []

    def required_end_traits(self):
        'Returns list of required traits for end notification'
        return []

    def optional_end_traits(self):
        'Returns list of optional traits for end notification'
        return []

    def required_error_traits(self):
        'Returns list of required traits for error notification'
        return ['message', 'exception']

    def optional_error_traits(self):
        'Returns list of optional traits for error notification'
        return ['id']

    def required_base_traits(self):
        return ['tenant_id']

    def __init__(self, context, **kwargs):
        self.context = context
        self.needs_end_notification = True

        self.payload = {}
        self.payload.update({'tenant_id': context.tenant})
        self.payload.update(kwargs)

    def serialize(self, context):
        return self.payload

    def validate(self, required_traits):
        required_keys = set(required_traits)
        provided_keys = set(self.payload.keys())
        if not required_keys.issubset(provided_keys):
            msg = (_("The following required keys not defined for"
                     " notification %(name)s: %(keys)s") % {
                         'name': self.__class__.__name__,
                         'keys': list(required_keys - provided_keys)
                     })
            raise Exception(msg)

    def _notify(self, event_qualifier, required_traits, optional_traits,
                **kwargs):
        self.payload.update(kwargs)
        self.validate(self.required_base_traits() + required_traits)
        available_values = self.serialize(self.context)
        payload = {
            k: available_values[k]
            for k in self.required_base_traits() + required_traits
        }
        for k in optional_traits:
            if k in available_values:
                payload[k] = available_values[k]

        qualified_event_type = (OctaviaAPINotification.event_type_format %
                                (self.event_type(), event_qualifier))
        LOG.debug('Sending event: %(event_type)s, %(payload)s', {
            'event_type': qualified_event_type,
            'payload': payload
        })

        context = copy.copy(self.context)
        del context.notification
        notifier = rpc.get_notifier()
        notifier.info(context, qualified_event_type, self.payload)
        if self.notify_callback:
            self.notify_callback(event_qualifier)

    def notify_start(self, **kwargs):
        self._notify('start', self.required_start_traits(),
                     self.optional_start_traits(), **kwargs)

    def notify_end(self, **kwargs):
        if self.needs_end_notification:
            self._notify('end', self.required_end_traits(),
                         self.optional_end_traits(), **kwargs)

    def notify_exc_info(self, message, exception):
        self.payload.update({'message': message, 'exception': exception})
        self._notify('error', self.required_error_traits(),
                     self.optional_error_traits())


class LoadBalancerCreate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'provider']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'provider']


class LoadBalancerDelete(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status']


class LoadBalancerUpdate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_update'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'provider']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'provider']
