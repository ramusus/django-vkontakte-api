# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, date
import re

from bs4 import BeautifulSoup
from django.conf import settings
from django.utils import timezone
import requests
import simplejson as json


def isalambda(v):
    return isinstance(v, type(lambda: None)) and v.__name__ == '<lambda>'


class VkontakteParseError(Exception):
    pass


class VkontakteParser(object):

    content = ''

    def __init__(self, content=''):
        self.content = content

    @property
    def html(self):
        content = self.content
        # fix parsing html for audio tags in http://vk.com/wall-16297716_87985, http://vk.com/wall-16297716_182282?reply=182342
        # <!-- ->-> <!-- -<>-> <!-- -->
        content = re.sub(r'<!--.+?(?:->)?->', '', content)

        parts = content.split('<!>')

        for part in parts[5:]:
            if part[:4] == '<div':
                content = part
                break

        # concatenate preload container
        for part in parts[6:]:
            if part[:7] == '<!json>' and 'preload' in part:
                data = json.loads(part.replace('<!json>', ''))
                if not isinstance(data['preload'], bool):
                    content += data['preload'][0]
                break

        return content

    @property
    def content_bs(self):
        return BeautifulSoup(self.html)

    def request(self, *args, **kwargs):
        kwargs['headers'] = {'Accept-Language': 'ru-RU,ru;q=0.8'}

        args = list(args)
        if 'http' not in args[0]:
            args[0] = 'http://vk.com' + args[0]

        if 'method' in kwargs and kwargs.pop('method') == 'get':
            response = requests.get(*args, **kwargs)
        else:
            response = requests.post(*args, **kwargs)

        self.content = response.content.decode('windows-1251')
        return self

    def parse_time(self, text):
        return [int(v) for v in text.split(':')]

    def parse_date(self, date_text):
        date_words = date_text.split(' ')
        months = (u'', u'янв', u'фев', u'мар', u'апр', u'мая', u'июн', u'июл', u'авг', u'сен', u'окт', u'ноя', u'дек')
        hours = (u'', u'час', u'два', u'три', u'четыре', u'пять')
        minutes = (u'', u'минуту', u'две', u'три', u'четыре', u'пять')
        now = date.today()
        if u'сегодня в' in date_text:
            h, m = self.parse_time(date_words[-1])
            return datetime(now.year, now.month, now.day, h, m)
        elif u'вчера в' in date_text:
            h, m = self.parse_time(date_words[-1])
            return datetime(now.year, now.month, now.day, h, m) - timedelta(days=1)
        elif u'назад' == date_words[-1]:
            try:
                value = int(date_words[0])
            except:
                value = 0
            if date_words[-2].startswith(u'час'):
                # три часа назад
                # час назад
                return now - timedelta(hours=value or hours.index(date_words[0]))
            elif date_words[-2].startswith(u'минут'):
                # 4 минуты назад
                # минуту назад
                return now - timedelta(minutes=value or minutes.index(date_words[0]))
            elif date_words[-2].startswith(u'секунд'):
                # 10 секунд назад
                return now - timedelta(minutes=value)
        elif u'только что' == date_text:
            return now
        elif len(date_words) > 1:
            month = date_words[1][:3]
            if len(date_words) == 4:
                # 15 мая в 10:12
                h, m = self.parse_time(date_words[-1])
                value = datetime(now.year, months.index(month), int(date_words[0]), h, m)
                return value if value < now else datetime(now.year - 1, months.index(month), int(date_words[0]), h, m)

            elif len(date_words) == 3:
                # 31 дек 2011
                return datetime(int(date_words[2]), months.index(month), int(date_words[0]))

    def parse_container_likes(self, container, classname):
        try:
            value = container.find('span', {'class': classname}).text
            return value and int(value) or 0
        except Exception, e:
            raise VkontakteParseError("Error while parsing post likes value: %s" % e)

    def add_users(self, users, user_link, user_photo, user_add):
        if 'vkontakte_users' not in settings.INSTALLED_APPS:
            raise ImproperlyConfigured("Application 'vkontakte_users' not in INSTALLED_APPS")

        from vkontakte_users.models import User

        items = self.content_bs.findAll(*users)
        for item in items:
            user_link_container = user_link(item) if isalambda(user_link) else item.find(*user_link)
            user_photo_container = user_photo(item) if isalambda(user_photo) else item.find(*user_photo)

            user = User.remote.get_by_slug(user_link_container['href'][1:])
            if user:
                user.set_name(user_link_container.text)
                user.photo = user_photo_container['src']
                user.save()
                if isalambda(user_add):
                    user_add(user)
                else:
                    raise ValueError("Argument 'user_add' should be a lambda function, not %s" % user_add)

        return items
