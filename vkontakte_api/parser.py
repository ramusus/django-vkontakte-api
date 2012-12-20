# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from BeautifulSoup import BeautifulSoup
import requests

class VkontakteParseError(Exception):
    pass

class VkontakteParser(object):

    content = ''

    def __init__(self, content=''):
        self.content = content

    @property
    def html(self):
        start = self.content.find('<div')
        stop = self.content.find('<!>', start)
        return self.content[start:stop]

    @property
    def content_bs(self):
        return BeautifulSoup(self.html)

    def request(self, *args, **kwargs):
        kwargs['headers'] = {'Accept-Language':'ru-RU,ru;q=0.8'}

        args = list(args)
        if 'http' not in args[0]:
            args[0] = 'http://vk.com' + args[0]

        if 'method' in kwargs and kwargs.pop('method') == 'get':
            response = requests.get(*args, **kwargs)
        else:
            response = requests.post(*args, **kwargs)

        self.content = response.content.decode('windows-1251')
        # fix parsing html for audio tags in http://vk.com/post-16297716_87985
        self.content = self.content.replace('<!-- ->->','')
        return self

    def parse_time(self, text):
        return [int(v) for v in text.split(':')]

    def parse_date(self, date_text):
        date_words = date_text.split(' ')
        months = (u'',u'янв',u'фев',u'мар',u'апр',u'мая',u'июн',u'июл',u'авг',u'сен',u'окт',u'ноя',u'дек')
        hours = (u'',u'час',u'два',u'три',u'четыре',u'пять')
        minutes = (u'',u'минуту',u'две',u'три',u'четыре',u'пять')
        now = datetime.now()
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
        elif len(date_words) == 4:
            # 15 мая в 10:12
            h, m = self.parse_time(date_words[-1])
            return datetime(now.year, months.index(date_words[1]), int(date_words[0]), h, m)
        elif len(date_words) == 3:
            # 31 дек 2011
            return datetime(int(date_words[2]), months.index(date_words[1]), int(date_words[0]))

    def parse_container_likes(self, container, classname):
        try:
            value = container.find('span', {'class': classname}).text
            return value and int(value) or 0
        except Exception, e:
            raise VkontakteParseError("Error while parsing post likes value: %s" % e)