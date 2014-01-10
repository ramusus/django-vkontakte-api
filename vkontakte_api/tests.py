# -*- coding: utf-8 -*-
from django.test import TestCase
from django.db import models
from decorators import opt_generator
from parser import VkontakteParser
from models import VkontaktePKModel, VkontakteManager
from utils import api_call, VkontakteError
import mock

class User(VkontaktePKModel):
    '''
    Test model should be on top level, otherwise table will not be created
    '''
    screen_name = models.CharField(u'Короткое имя группы', max_length=50, db_index=True)
    slug_prefix = ''

    remote = VkontakteManager()

class VkontakteApiTest(TestCase):
#    fixtures = ['oauth_tokens.usercredentials.json',]

    def test_parse_page(self):

        parser = VkontakteParser()
        parser.content = '<!><!><!><!><!><div>%s</div>' % '1<!-- ->->2<!-- -<>->3<!-- -->4'

        self.assertEqual(parser.html, '<div>1234</div>')

    def test_resolvescreenname(self):

        response = api_call('resolveScreenName', screen_name='durov')
        self.assertEqual(response, {u'object_id': 1, u'type': u'user'})
        # fail with VkontakteError, when call with integer screen_name
#         with self.assertRaises(VkontakteError):
#             response = api_call('resolveScreenName', screen_name='0x1337')

        instance = User.remote.get_by_slug('durov')
        self.assertEqual(instance.remote_id, 1)

#         instance = User.remote.get_by_slug('0x1337')
#         self.assertEqual(instance, None)

    @mock.patch('time.sleep')
    def test_requests_limit_per_sec(self, sleep, *args, **kwargs):
        for i in range(0,30):
            api_call('resolveScreenName', screen_name='durov')

#         self.assertTrue(sleep.called)
#         self.assertTrue(sleep.call_count >= 1)

    def test_generator_decorator(self):

        class GeneratorMethodClass(object):
            @opt_generator
            def some_method(self, total, *args, **kwargs):
                for count in range(total):
                    yield count, total

        instance = GeneratorMethodClass()
        self.assertTrue(isinstance(instance.some_method(10), list))

        i = 0
        for count, total in instance.some_method(10, as_generator=True):
            self.assertEqual((count, total), (i, 10))
            i += 1