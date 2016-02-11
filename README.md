Django Vkontakte API
====================

[![PyPI version](https://badge.fury.io/py/django-vkontakte-api.png)](http://badge.fury.io/py/django-vkontakte-api) [![Build Status](https://travis-ci.org/ramusus/django-vkontakte-api.png?branch=master)](https://travis-ci.org/ramusus/django-vkontakte-api) [![Coverage Status](https://coveralls.io/repos/ramusus/django-vkontakte-api/badge.png?branch=master)](https://coveralls.io/r/ramusus/django-vkontakte-api)

Application for interaction with objects of VK API using Django ORM

Installation
------------

    pip install django-vkontakte-api

Add into `settings.py` lines:

    INSTALLED_APPS = (
        ...
        'oauth_tokens',
        'taggit',
        'vkontakte_api',
    )

    # oauth-tokens settings
    OAUTH_TOKENS_HISTORY = True                                                     # to keep in DB expired access tokens
    OAUTH_TOKENS_VKONTAKTE_CLIENT_ID = ''                                           # application ID
    OAUTH_TOKENS_VKONTAKTE_CLIENT_SECRET = ''                                       # application secret key
    OAUTH_TOKENS_VKONTAKTE_SCOPE = ['ads', 'wall' ,'photos', 'friends', 'stats']    # application scopes
    OAUTH_TOKENS_VKONTAKTE_USERNAME = ''                                            # user login
    OAUTH_TOKENS_VKONTAKTE_PASSWORD = ''                                            # user password
    OAUTH_TOKENS_VKONTAKTE_PHONE_END = ''                                           # last 4 digits of user mobile phone

Coverage of API methods
-----------------------

* [resolveScreenName](http://vk.com/dev/resolveScreenName) – Detects a type of object (e.g., user, community, application) and its ID by screen name.

Usage examples
--------------

### Simple API request

    >>> from vkontakte_api.api import api_call
    >>> api_call('resolveScreenName', **{'screen_name': 'durov'})
    {u'object_id': 1, u'type': u'user'}
    >>> api_call('users.get', **{'user_ids': 'durov'})
    [{'first_name': u'Павел', 'last_name': u'Дуров', 'uid': 1}]
