# Django Vkontakte API

[![Build Status](https://travis-ci.org/ramusus/django-vkontakte-api.png?branch=master)](https://travis-ci.org/ramusus/django-vkontakte-api)

Приложение позволяет взаимодействовать с объектами Вконтакте API используя стандартные модели Django

## Установка

    pip install django-vkontakte-api

В `settings.py` необходимо добавить:

    INSTALLED_APPS = (
        ...
        'oauth_tokens',
        'vkontakte_api',
    )

    # настройки oauth-tokens
    OAUTH_TOKENS_HISTORY = True                                         # хранить старые токены в БД
    OAUTH_TOKENS_VKONTAKTE_CLIENT_ID = ''                               # ID приложения Вконтакте
    OAUTH_TOKENS_VKONTAKTE_CLIENT_SECRET = ''                           # secret key приложения Вконтакте
    OAUTH_TOKENS_VKONTAKTE_SCOPE = ['ads,wall,photos,friends,stats']    # права доступа приложения Вконтакте
    OAUTH_TOKENS_VKONTAKTE_USERNAME = ''                                # логин пользователя Вконтакте
    OAUTH_TOKENS_VKONTAKTE_PASSWORD = ''                                # пароль пользователя Вконтакте
    OAUTH_TOKENS_VKONTAKTE_PHONE_END = ''                               # последние 4 цифры телефона пользователя Вконтакте

## Примеры использования

### Запрос API

    >>> from vkontakte_api.utils import api_call
    >>> api_call('resolveScreenName', **{'screen_name': 'durov'})
    {u'object_id': 1, u'type': u'user'}
    >>> api_call('resolveScreenName', **{'screen_name': 'cocacola'})
    {u'object_id': 16297716, u'type': u'group'}