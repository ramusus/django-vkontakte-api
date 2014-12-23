# -*- coding: utf-8 -*-
from django.db import models, IntegrityError
from django.test import TestCase
import mock

from .api import api_call, VkontakteError, VkontakteApi
from .decorators import opt_generator
from .models import VkontakteIDModel, VkontaktePKModel, VkontakteManager
from .parser import VkontakteParser


class User(VkontaktePKModel):

    '''
    Test model should be on top level, otherwise table will not be created
    '''
    resolve_screen_name_types = ['user']
    screen_name = models.CharField(u'Короткое имя группы', max_length=50, unique=True)
    slug_prefix = 'id'

    remote = VkontakteManager(remote_pk=('remote_id',), version=5.27, methods={
        'get': 'users.get',
        'friends': ('friends.get', 5.02)
    })


class UserID(VkontakteIDModel):
    screen_name = models.CharField(u'Короткое имя группы', max_length=50, unique=True)


class VkontakteApiTest(TestCase):

    def test_api_instance_singleton(self):

        self.assertEqual(id(VkontakteApi()), id(VkontakteApi()))

    @mock.patch('vkontakte_api.models.api_call', side_effect=lambda *a, **kw: {'items': []})
    def test_api_call_versions(self, method):

        User.remote.api_call('get', v=5.01)
        self.assertEqual(method.call_args_list[0][0][0], 'users.get')
        self.assertEqual(method.call_args_list[0][1]['v'], 5.01)

        User.remote.api_call('get')
        self.assertEqual(method.call_args_list[1][0][0], 'users.get')
        self.assertEqual(method.call_args_list[1][1]['v'], 5.27)

        User.remote.api_call('friends')
        self.assertEqual(method.call_args_list[2][0][0], 'friends.get')
        self.assertEqual(method.call_args_list[2][1]['v'], 5.02)

        User.remote.api_call('friends', v=5.03)
        self.assertEqual(method.call_args_list[3][0][0], 'friends.get')
        self.assertEqual(method.call_args_list[3][1]['v'], 5.03)

    def test_save_user_integrity_error(self):

        user = UserID.objects.create(remote_id=1, screen_name='111')

        # test absence of IntgrityError while creating
        user_new = UserID.objects.create(remote_id=1, screen_name='222')
        self.assertEqual(user_new.id, user.id)

        # test absence of IntgrityError while saving
        user_new = UserID(remote_id=1, screen_name='333')
        user_new.save()
        self.assertEqual(user_new.id, user.id)

        # test IntgrityError by absence of remote_id
        try:
            user_new = UserID(screen_name='333')
            user_new.save()
            self.fail("IntegrityError didn't raised")
        except IntegrityError:
            pass

        # test IntgrityError by screen_name
        try:
            user_new = UserID(remote_id=2, screen_name='333')
            user_new.save()
            self.fail("IntegrityError didn't raised")
        except IntegrityError:
            pass

    def test_parse_page(self):

        parser = VkontakteParser()
        parser.content = '<!><!><!><!><!><div>%s</div>' % '1<!-- ->->2<!-- -<>->3<!-- -->4'

        self.assertEqual(parser.html, '<div>1234</div>')

    def test_resolvescreenname(self):

        response = api_call('resolveScreenName', screen_name='durov')
        self.assertEqual(response, {u'object_id': 1, u'type': u'user'})

    def test_get_by_url(self):

        instance = User.remote.get_by_url('https://vk.com/id1/')
        self.assertEqual(instance.screen_name, 'id1')

    def test_get_by_slug(self):

        instance = User.remote.get_by_slug('durov')
        self.assertEqual(instance.remote_id, 1)

#     @mock.patch('time.sleep')
#     def test_requests_limit_per_sec(self, sleep, *args, **kwargs):
#         for i in range(0, 30):
#             api_call('resolveScreenName', screen_name='durov')
#
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
