from django.conf import settings
from oauth_tokens.models import AccessToken, AccessTokenGettingError
from ssl import SSLError
import vkontakte
import time
import logging

__all__ = ['api_call']

log = logging.getLogger('vkontakte_api')

TIMEOUT = getattr(settings, 'VKONTAKTE_ADS_REQUEST_TIMEOUT', 1)
ACCESS_TOKEN = getattr(settings, 'VKONTAKTE_API_ACCESS_TOKEN', None)

VkontakteError = vkontakte.VKError

class NoActiveTokens(Exception):
    pass

def update_tokens(count=1):
    '''
    Update token from provider and return it
    '''
    try:
        return AccessToken.objects.fetch('vkontakte')
    except AccessTokenGettingError, e:
        if count <= 5:
            time.sleep(1)
            update_tokens(count+1)
        else:
            raise e

def get_api(used_access_tokens=None, *args, **kwargs):
    '''
    Return API instance with latest token from database
    '''
    if ACCESS_TOKEN:
        token = ACCESS_TOKEN
    else:
        tokens = AccessToken.objects.filter_active_tokens_of_provider('vkontakte', *args, **kwargs)
        if used_access_tokens:
            tokens = tokens.exclude(access_token__in=used_access_tokens)

        if len(tokens) == 0:
            raise NoActiveTokens("There is no active AccessTokens with args %s and kwargs %s" % (args, kwargs))
        else:
            token = tokens[0].access_token

    return vkontakte.API(token=token)

def api_call(method, recursion_count=0, methods_access_tag=None, used_access_tokens=None, **kwargs):
    '''
    Call API using access_token
    '''
    try:
        vk = get_api(tag=methods_access_tag, used_access_tokens=used_access_tokens)
    except NoActiveTokens, e:
        if used_access_tokens:
            # we should wait 1 sec and repeat with clear attribute used_access_tokens
            log.warning("Waiting 1 sec, because all active tokens are used, method: %s, recursion count: %d" % (method, recursion_count))
            time.sleep(1)
            return api_call(method, recursion_count+1, methods_access_tag, used_access_tokens=None, **kwargs)
        else:
            log.warning("Suddenly updating tokens, because no active access tokens and used_access_tokens empty, method: %s, recursion count: %d" % (method, recursion_count))
            update_tokens()
            return api_call(method, recursion_count+1, methods_access_tag, **kwargs)

    try:
        response = vk.get(method, timeout=TIMEOUT, **kwargs)
    except VkontakteError, e:
        if e.code == 5:
            log.info("Updating vkontakte access token, recursion count: %d" % recursion_count)
            update_tokens()
            ACCESS_TOKEN = None
            return api_call(method, recursion_count+1, methods_access_tag, **kwargs)
        elif e.code == 6:
            # try access_token of another user
            log.info("Vkontakte error 'Too many requests per second' on method: %s, recursion count: %d" % (method, recursion_count))
            used_access_tokens = [vk.token] + (used_access_tokens or [])
            return api_call(method, recursion_count+1, methods_access_tag, used_access_tokens=used_access_tokens, **kwargs)
        elif e.code == 9:
            log.warning("Vkontakte flood control registered while executing method %s with params %s, recursion count: %d" % (method, kwargs, recursion_count))
            time.sleep(1)
            return api_call(method, recursion_count+1, methods_access_tag, **kwargs)
        else:
            log.error("Unhandled vkontakte error raised: %s", e)
            raise e
    except SSLError, e:
        log.error("SSLError: '%s' registered while executing method %s with params %s, recursion count: %d" % (e, method, kwargs, recursion_count))
        time.sleep(1)
        return api_call(method, recursion_count+1, methods_access_tag, **kwargs)
    except Exception, e:
        log.error("Unhandled error: %s registered while executing method %s with params %s" % (e, method, kwargs))
        raise e

    return response