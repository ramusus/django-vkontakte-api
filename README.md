# Django Vkontakte API

<a href="https://travis-ci.org/#!/ramusus/django-vkontakte-api" title="Django Vkontakte API Travis Status"><img src="https://secure.travis-ci.org/ramusus/django-vkontakte-api.png?branch=master"></a>

Приложение позволяет взаимодействовать с объектами Вконтакте API используя стандартные модели Django

## Установка

    pip install django-vkontakte-api

В `settings.py` необходимо добавить:

    INSTALLED_APPS = (
        ...
        'vkontakte_api',
    )

## Примеры использования

### Запрос API

    >>> from vkontakte_api.utils import api_call
    >>> api_call('resolveScreenName', **{'screen_name': 'durov'})
    {u'object_id': 1, u'type': u'user'}
    >>> api_call('resolveScreenName', **{'screen_name': 'cocacola'})
    {u'object_id': 16297716, u'type': u'group'}