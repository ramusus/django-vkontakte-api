from django.conf import settings
from oauth_tokens.models import AccessToken
from ssl import SSLError
import vkontakte
import time
import logging

log = logging.getLogger('vkontakte_api')

TIMEOUT = getattr(settings, 'VKONTAKTE_ADS_REQUEST_TIMEOUT', 1)

VkontakteError = vkontakte.VKError

def get_tokens():
    '''
    Get all vkontakte tokens list
    '''
    return AccessToken.objects.filter(provider='vkontakte')

def update_token():
    '''
    Update token from provider and return it
    '''
    return AccessToken.objects.get_from_provider('vkontakte')

def get_api():
    '''
    Return API instance with latest token from database
    '''
    tokens = get_tokens()
    if not tokens:
        update_token()
        tokens = get_tokens()
    t = tokens[0]
    return vkontakte.API(token=t.access_token)

def api_call(method, **kwargs):
    '''
    Call API using access_token
    '''
    vk = get_api()
    try:
        response = vk.get(method, timeout=TIMEOUT, **kwargs)
    except VkontakteError, e:
        if e.code == 5:
            log.debug("Updating vkontakte access token")
            update_token()
            vk = get_api()
            response = vk.get(method, timeout=TIMEOUT, **kwargs)
        elif e.code == 9:
            log.warning("Vkontakte flood control registered while executing method %s with params %s" % (method, kwargs))
            time.sleep(1)
            response = api_call(method, **kwargs)
        else:
            log.error("Unhandled vkontakte error raised: %s", e)
            raise e
    except SSLError, e:
        log.error("SSLError: '%s' registered while executing method %s with params %s" % (e, method, kwargs))
        time.sleep(1)
        response = api_call(method, **kwargs)
    except Exception, e:
        log.error("Unhandled error raised: %s" % e)
        raise e

    return response
