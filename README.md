Django Vkontakte API [![Build Status](https://travis-ci.org/ramusus/django-vkontakte-api.png?branch=master)](https://travis-ci.org/ramusus/django-vkontakte-api)
====================

Приложение позволяет взаимодействовать с объектами Вконтакте API используя стандартные модели Django

Установка
---------

    pip install django-vkontakte-api

В `settings.py` необходимо добавить:

    INSTALLED_APPS = (
        ...
        'oauth_tokens',
        'vkontakte_api',
    )

    # oauth-tokens settings
    OAUTH_TOKENS_HISTORY = True                                         # to keep in DB expired access tokens
    OAUTH_TOKENS_VKONTAKTE_CLIENT_ID = ''                               # application ID
    OAUTH_TOKENS_VKONTAKTE_CLIENT_SECRET = ''                           # application secret key
    OAUTH_TOKENS_VKONTAKTE_SCOPE = ['ads,wall,photos,friends,stats']    # application scopes
    OAUTH_TOKENS_VKONTAKTE_USERNAME = ''                                # user login
    OAUTH_TOKENS_VKONTAKTE_PASSWORD = ''                                # user password
    OAUTH_TOKENS_VKONTAKTE_PHONE_END = ''                               # last 4 digits of user mobile phone

Покрытие методов API
--------------------

* [resolveScreenName](http://vk.com/developers.php?oid=-1&p=resolveScreenName) – определяет тип объекта (пользователь, группа, приложение) и его идентификатор по короткому имени screen_name;

В планах:

* [likes.getList](http://vk.com/developers.php?oid=-1&p=likes.getList) – возвращает список пользователей, которые добавили объект в список «Мне нравится»;

Примеры использования
---------------------

### Запрос API

    >>> from vkontakte_api.utils import api_call
    >>> api_call('resolveScreenName', **{'screen_name': 'durov'})
    {u'object_id': 1, u'type': u'user'}
    >>> api_call('resolveScreenName', **{'screen_name': 'cocacola'})
    {u'object_id': 16297716, u'type': u'group'}