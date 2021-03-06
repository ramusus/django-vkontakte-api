# -*- coding: utf-8 -*-
from django.conf import settings
from social_api.api import ApiAbstractBase, Singleton
from vkontakte import VKError as VkontakteError, API

__all__ = ['api_call', 'VkontakteError']


class VkontakteApi(ApiAbstractBase):
    __metaclass__ = Singleton

    provider = 'vkontakte'
    provider_social_auth = 'vk-oauth2'
    error_class = VkontakteError
    request_timeout = getattr(settings, 'VKONTAKTE_API_REQUEST_TIMEOUT', 1)

    def get_consistent_token(self):
        return getattr(settings, 'VKONTAKTE_API_ACCESS_TOKEN', None)

    def get_api(self, token):
        return API(token=token)

    def get_api_response(self, *args, **kwargs):
        return self.api.get(self.method, timeout=self.request_timeout, *args, **kwargs)

    def handle_error_code_5(self, e, *args, **kwargs):
        # code = 5, description = 'User authorization failed: invalid session.'
        # code = 5, description = 'User authorization failed: user revoke access for this token.'
        self.used_access_tokens += [self.api.token]
        return self.repeat_call(*args, **kwargs)

    def handle_error_code_6(self, e, *args, **kwargs):
        self.logger.info("Vkontakte error 'Too many requests per second' on method: %s, recursion count: %d" % (
            self.method, self.recursion_count))
        return self.repeat_call(*args, **kwargs)

    def handle_error_code_9(self, e, *args, **kwargs):
        self.logger.warning("Vkontakte flood control registered while executing method %s with params %s, \
            recursion count: %d" % (self.method, kwargs, self.recursion_count))
        self.used_access_tokens += [self.api.token]
        return self.sleep_repeat_call(*args, **kwargs)

    def handle_error_code_10(self, e, *args, **kwargs):
        self.logger.warning("Internal server error: Database problems, try later. Error registered while executing \
            method %s with params %s, recursion count: %d" % (self.method, kwargs, self.recursion_count))
        return self.sleep_repeat_call(*args, **kwargs)

    def handle_error_code_17(self, e, *args, **kwargs):
        # code = 17, description = 'Validation required: please open redirect_uri in browser'
        self.used_access_tokens += [self.api.token]
        return self.repeat_call(*args, **kwargs)
        # # TODO: cover with tests
        # from oauth_tokens.models import AccessToken
        # self.logger.warning("Request error: %s. Error registered while executing \
        #     method %s with params %s, recursion count: %d" % (e, self.method, kwargs, self.recursion_count))
        #
        # user = AccessToken.objects.get(access_token=self.api.token).user_credentials
        # auth_request = AccessToken.objects.get_token_for_user('vkontakte', user).auth_request
        # auth_request.form_action_domain = 'https://m.vk.com'
        #
        # response = auth_request.session.get(e.redirect_uri)
        # try:
        #     method, action, data = auth_request.get_form_data_from_content(response.content)
        # except:
        #     raise Exception("There is no any form in response: %s" % response.content)
        # data = {'code': auth_request.additional}
        # response = getattr(auth_request.session, method)(url=action, headers=auth_request.headers, data=data)
        #
        # if 'success' not in response.url:
        #     raise Exception("Wrong response. Can not handle VK error 17. response: %s" % response.content)
        #
        # return self.sleep_repeat_call(*args, **kwargs)

    def handle_error_code_500(self, e, *args, **kwargs):
        # strange HTTP error appears sometimes
        return self.sleep_repeat_call(*args, **kwargs)

    def handle_error_code_501(self, e, *args, **kwargs):
        # strange HTTP error appears sometimes
        return self.sleep_repeat_call(*args, **kwargs)

    def handle_error_code_502(self, e, *args, **kwargs):
        # strange HTTP error appears sometimes
        return self.sleep_repeat_call(*args, **kwargs)

    def handle_error_code_504(self, e, *args, **kwargs):
        # strange HTTP error appears sometimes
        return self.sleep_repeat_call(*args, **kwargs)


def api_call(*args, **kwargs):
    api = VkontakteApi()
    return api.call(*args, **kwargs)
