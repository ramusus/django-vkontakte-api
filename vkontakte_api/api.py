# -*- coding: utf-8 -*-
import time

from django.conf import settings
from oauth_tokens.api import ApiAbstractBase, Singleton
from oauth_tokens.models import AccessToken
from vkontakte import VKError as VkontakteError, API

__all__ = ['api_call', 'VkontakteError']


class VkontakteApi(ApiAbstractBase):

    __metaclass__ = Singleton

    provider = 'vkontakte'
    error_class = VkontakteError
    request_timeout = getattr(settings, 'VKONTAKTE_API_REQUEST_TIMEOUT', 1)

    def get_consistent_token(self):
        return getattr(settings, 'VKONTAKTE_API_ACCESS_TOKEN', None)

    def get_tokens(self, **kwargs):
        return AccessToken.objects.filter_active_tokens_of_provider(self.provider, **kwargs)

    def get_api(self, **kwargs):
        return API(token=self.get_token(**kwargs))

    def get_api_response(self, *args, **kwargs):
        return self.api.get(self.method, timeout=self.request_timeout, *args, **kwargs)

    def handle_error_code_5(self, e, *args, **kwargs):
        self.logger.info("Updating vkontakte access token, recursion count: %d" % self.recursion_count)
        self.update_tokens()
        return self.repeat_call(*args, **kwargs)

    def handle_error_code_6(self, e, *args, **kwargs):
        # try access_token by another user
        self.logger.info(
            "Vkontakte error 'Too many requests per second' on method: %s, recursion count: %d" % (self.method, self.recursion_count))
        self.used_access_tokens += [self.api.token]
        return self.repeat_call(*args, **kwargs)

    def handle_error_code_9(self, e, *args, **kwargs):
        self.logger.warning("Vkontakte flood control registered while executing method %s with params %s, \
            recursion count: %d" % (self.method, kwargs, self.recursion_count))
        time.sleep(1)
        self.used_access_tokens += [self.api.token]
        return self.repeat_call(*args, **kwargs)

    def handle_error_code_10(self, e, *args, **kwargs):
        self.logger.warning("Internal server error: Database problems, try later. Error registered while executing \
            method %s with params %s, recursion count: %d" % (self.method, kwargs, self.recursion_count))
        time.sleep(1)
        return self.repeat_call(*args, **kwargs)

    def handle_error_code_501(self, e, *args, **kwargs):
        # strange HTTP error appears sometimes
        return self.repeat_call(*args, **kwargs)


def api_call(*args, **kwargs):
    api = VkontakteApi()
    return api.call(*args, **kwargs)
