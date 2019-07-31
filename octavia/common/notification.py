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

class StartNotification(object):
    def __init__(self, context, **kwargs):
        self.context = context
        self.context.notification.payload.update(kwargs)

    def __enter__(self):
        self.context.notification.notify_start()
        return self.context.notification

    def __exit__(self, etype, value, tb):
        if etype:
            message = str(value)
            exception = traceback.format_exception(etype, value, tb)
            self.context.notification.notify_exc_info(message, exception)

class DoNothing():
    def __init__(self):
        pass

    def __enter__(self):
        pass

    def __exit__(self, etype, value, tb):
        pass

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
        self._notify('end', self.required_end_traits(),
                         self.optional_end_traits(), **kwargs)

    def notify_exc_info(self, message, exception):
        self.payload.update({'message': message, 'exception': exception})
        self._notify('error', self.required_error_traits(),
                     self.optional_error_traits())


class LoadBalancerCreate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer.create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'provider']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'provider']


class LoadBalancerDelete(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer.delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status']


class LoadBalancerUpdate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer.update'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'provider']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'provider']


class ListenerCreate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_listener.create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'protocol', 'protocol_port', 'connection_limit']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'protocol', 'protocol_port', 'connection_limit']

class ListenerUpdate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_listener.update'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'protocol', 'protocol_port', 'connection_limit']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'protocol', 'protocol_port', 'connection_limit']

class ListenerDelete(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_listener.delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'protocol', 'protocol_port', 'connection_limit']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'protocol', 'protocol_port', 'connection_limit']
    

class PoolCreate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_pool.create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'listeners', 'lb_algorithm']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'listeners', 'lb_algorithm']


class PoolUpdate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_pool.update'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'listeners', 'lb_algorithm']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'listeners', 'lb_algorithm']


class PoolDelete(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_pool.delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'listeners', 'lb_algorithm']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'load_balancer', 'listeners', 'lb_algorithm']


class MemberCreate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_member.create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'ip_address']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'ip_address']

class MemberUpdate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_member.update'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'ip_address']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'ip_address']


class MemberDelete(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_member.delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'ip_address']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'ip_address']


class MonitorCreate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_monitor.create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'pool', 'timeout', 'delay']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'pool', 'timeout', 'delay']


class MonitorUpdate(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_monitor.update'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'pool', 'timeout', 'delay']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'pool', 'timeout', 'delay']


class MonitorDelete(OctaviaAPINotification):
    @abc.abstractmethod
    def event_type(self):
        return 'loadbalancer_monitor.delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['id', 'name', 'provisioning_status', 'pool', 'timeout', 'delay']

    def required_end_traits(self):
        return ['id', 'name', 'provisioning_status', 'pool', 'timeout', 'delay']

def send_lb_start_notification(context, lb_data, provisioning_status=None):
    return StartNotification(context, id=lb_data.get('id'), 
                                      name=lb_data.get('name'), 
                                      provisioning_status=(provisioning_status if provisioning_status else lb_data.get('provisioning_status')),
                                      provider=lb_data.get('provider'))

def send_lb_end_notification(context, lb_data, provisioning_status=None):
    return EndNotification(context, id=lb_data.get('id'), 
                                      name=lb_data.get('name'), 
                                      provisioning_status=(provisioning_status if provisioning_status else lb_data.get('provisioning_status')),
                                      provider=lb_data.get('provider'))

def send_listener_start_notification(context, listener_data, provisioning_status=None):
    return StartNotification(context, id=listener_data.get('id'),
                                      name=listener_data.get('name'),
                                      provisioning_status=(provisioning_status if provisioning_status else listener_data.get('provisioning_status')),
                                      load_balancer=listener_data.get('load_balancer_id'),
                                      protocol=listener_data.get('protocol'),
                                      protocol_port=listener_data.get('protocol_port'),
                                      connection_limit=listener_data.get('connection_limit'))
                            
def send_listener_end_notification(context, listener_data, provisioning_status=None):
    return EndNotification(context, id=listener_data.get('id'),
                                      name=listener_data.get('name'),
                                      provisioning_status=(provisioning_status if provisioning_status else listener_data.get('provisioning_status')),
                                      load_balancer=listener_data.get('load_balancer_id'),
                                      protocol=listener_data.get('protocol'),
                                      protocol_port=listener_data.get('protocol_port'),
                                      connection_limit=listener_data.get('connection_limit'))

def send_pool_start_notification(context, pool_data, provisioning_status=None, listeners=None):
    return  StartNotification(context, id=pool_data.get('id'),
                                    name=pool_data.get('name'),
                                    provisioning_status=(provisioning_status if provisioning_status else pool_data.get('provisioning_status')),
                                    load_balancer=pool_data.get('load_balancer_id'),
                                    listeners=listeners,
                                    lb_algorithm=pool_data.get('lb_algorithm'))

def send_pool_end_notification(context, pool_data, provisioning_status=None, listeners=None):
    return  EndNotification(context, id=pool_data.get('id'),
                                    name=pool_data.get('name'),
                                    provisioning_status=(provisioning_status if provisioning_status else pool_data.get('provisioning_status')),
                                    load_balancer=pool_data.get('load_balancer_id'),
                                    listeners=listeners,
                                    lb_algorithm=pool_data.get('lb_algorithm'))

def send_member_start_notification(context, member_data, provisioning_status=None):
    return  StartNotification(context, id=member_data.get('id'),
                                    name=member_data.get('name'),
                                    provisioning_status=(provisioning_status if provisioning_status else member_data.get('provisioning_status')),
                                    ip_address=member_data.get('ip_address'))

def send_member_end_notification(context, member_data, provisioning_status=None):
    return  EndNotification(context, id=member_data.get('id'),
                                    name=member_data.get('name'),
                                    provisioning_status=(provisioning_status if provisioning_status else member_data.get('provisioning_status')),
                                    ip_address=member_data.get('ip_address'))

def send_monitor_start_notification(context, monitor_data, provisioning_status=None):
    return StartNotification(context, id=monitor_data.get('id'),
                                    name=monitor_data.get('name'),
                                    provisioning_status=(provisioning_status if provisioning_status else monitor_data.get('provisioning_status')),
                                    pool=monitor_data.get('pool_id'),
                                    timeout=monitor_data.get('timeout'),
                                    delay=monitor_data.get('delay'))

def send_monitor_end_notification(context, monitor_data, provisioning_status=None):
    return EndNotification(context, id=monitor_data.get('id'),
                                    name=monitor_data.get('name'),
                                    provisioning_status=(provisioning_status if provisioning_status else monitor_data.get('provisioning_status')),
                                    pool=monitor_data.get('pool_id'),
                                    timeout=monitor_data.get('timeout'),
                                    delay=monitor_data.get('delay'))




