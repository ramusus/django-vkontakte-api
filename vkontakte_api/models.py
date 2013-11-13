# -*- coding: utf-8 -*-
from django.db import models
from django.core.exceptions import ImproperlyConfigured
from django.db.models.fields import FieldDoesNotExist
from django.db.models.query import QuerySet
from datetime import datetime, date
from vkontakte_api.utils import api_call, VkontakteError
from vkontakte_api import fields
import logging
import re

log = logging.getLogger('vkontakte_api')

class VkontakteDeniedAccessError(Exception):
    pass

class VkontakteContentError(Exception):
    pass

class VkontakteManager(models.Manager):
    '''
    Vkontakte Ads API Manager for RESTful CRUD operations
    '''
    def __init__(self, methods=None, remote_pk=None, *args, **kwargs):
        if methods and len(methods.items()) < 1:
            raise ValueError('Argument methods must contains at least 1 specified method')

        self.methods = methods or {}
        self.remote_pk = remote_pk or tuple()

        super(VkontakteManager, self).__init__(*args, **kwargs)

    def get_by_url(self, url):
        '''
        Return vkonakte object by url
        '''
        m = re.findall(r'(?:http://)?vk.com/(.+)/?', url)
        if not len(m):
            raise ValueError("Url should be started with http://vk.com/")

        return self.get_by_slug(m[0])

    def get_by_slug(self, slug):
        '''
        Return existed User, Group, Application by slug or new intance with empty pk
        '''
        try:
            assert self.model.slug_prefix and slug.startswith(self.model.slug_prefix)
            remote_id = int(re.findall(r'^%s(\d+)$' % self.model.slug_prefix, slug)[0])
        except (AssertionError, ValueError, IndexError):
            try:
                return self.model.objects.get(screen_name=slug)
            except self.model.DoesNotExist:
                try:
                    response = api_call('resolveScreenName', **{'screen_name': slug})
                except VkontakteError, e:
                    log.error("Method get_by_slug returned error instead of response. Slug: '%s'. Error: %s" % (slug, e))
                    return None
                try:
                    assert self.model._meta.module_name == response['type']
                    remote_id = int(response['object_id'])
                except TypeError:
                    log.error("Method get_by_slug returned response in strange format: %s. Slug is '%s'" % (response, slug))
                    return None
                except ValueError:
                    return None
                except AssertionError:
                    log.error("Method get_by_slug returned instance with wrong type '%s', not '%s'. Slug is '%s'" % (response['type'], self.model._meta.module_name, slug))
                    return None

        try:
            object = self.model.objects.get(remote_id=remote_id)
            object.screen_name = slug
        except self.model.DoesNotExist:
            object = self.model(remote_id=remote_id, screen_name=slug)

        return object

    def get_or_create_from_instance(self, instance):

        remote_pk_dict = {}
        for field_name in self.remote_pk:
            remote_pk_dict[field_name] = getattr(instance, field_name)

        if remote_pk_dict:
            try:
                old_instance = self.model.objects.get(**remote_pk_dict)
                instance._substitute(old_instance)
                instance.save()
            except self.model.DoesNotExist:
                instance.save()
                log.debug('Fetch and create new object %s with remote pk %s' % (self.model, remote_pk_dict))
        else:
            instance.save()
            log.debug('Fetch and create new object %s without remote pk' % (self.model,))

        return instance

    def get_or_create_from_resource(self, resource):

        instance = self.model()
        instance.parse(dict(resource))

        return self.get_or_create_from_instance(instance)

    def api_call(self, method='get', **kwargs):
        if self.model.methods_access_tag:
            kwargs['methods_access_tag'] = self.model.methods_access_tag

        method = self.methods[method]
        if self.model.methods_namespace:
            method = self.model.methods_namespace + '.' + method

        return api_call(method, **kwargs)

    def fetch(self, *args, **kwargs):
        '''
        Retrieve and save object to local DB
        Return queryset with respect to '_after' parameter, excluding all items before.
        Decision about each item based on field in '_after_field_name' optional parameter ('date' by default)
        '''
        after = kwargs.pop('_after', None)
        after_field_name = kwargs.pop('_after_field_name', 'date')

        result = self.get(*args, **kwargs)
        if isinstance(result, list):
            instances = self.model.objects.none()
            for instance in result:

                if after and after > getattr(instance, after_field_name):
                    break

                instance = self.get_or_create_from_instance(instance)
                instances |= instance.__class__.objects.filter(pk=instance.pk)
            return instances
        elif isinstance(result, QuerySet):
            return result
        else:
            return self.get_or_create_from_instance(result)

    def get(self, *args, **kwargs):
        '''
        Retrieve objects from remote server
        TODO: rename everywhere extra_fields to _extra_fields
        '''
        extra_fields = kwargs.pop('extra_fields', {})
        extra_fields['fetched'] = datetime.now()

        response = self.api_call(*args, **kwargs)

        return self.parse_response(response, extra_fields)

    def parse_response(self, response, extra_fields=None):
        if isinstance(response, (list, tuple)):
            return self.parse_response_list(response, extra_fields)
        elif isinstance(response, dict):
            return self.parse_response_dict(response, extra_fields)
        else:
            raise VkontakteContentError('Vkontakte response should be list or dict, not %s' % response)

    # TODO: rename to parse_response_object
    def parse_response_dict(self, resource, extra_fields=None):

        instance = self.model()
        # important to do it before calling parse method
        if extra_fields:
            instance.__dict__.update(extra_fields)
        instance.parse(resource)

        return instance

    def parse_response_list(self, response_list, extra_fields=None):

        instances = []
        for resource in response_list:

            # in response with stats there is extra array inside each element
            if isinstance(resource, list) and len(resource):
                resource = resource[0]

            # in some responses first value is `count` of all values:
            # http://vk.com/developers.php?oid=-1&p=groups.search
            if isinstance(resource, int):
                continue

            try:
                resource = dict(resource)
            except (TypeError, ValueError), e:
                log.error("Resource %s is not dictionary" % resource)
                raise e

            instance = self.parse_response_dict(resource, extra_fields)
            instances += [instance]

        return instances

class VkontakteModel(models.Model):
    class Meta:
        abstract = True

    remote_pk_field = 'id'
    methods_access_tag = ''
    methods_namespace = ''

    fetched = models.DateTimeField(u'Обновлено', null=True, blank=True, db_index=True)

    objects = models.Manager()

    def _substitute(self, old_instance):
        '''
        Substitute new instance with old one while updating in method Manager.get_or_create_from_instance()
        Can be overrided in child models
        '''
        self.pk = old_instance.pk

    def parse(self, response):
        '''
        Parse API response and define fields with values
        '''
        for key, value in response.items():
            if key == self.remote_pk_field:
                key = 'remote_id'
                value = int(value)

            try:
                field = self._meta.get_field(key)
            except FieldDoesNotExist:
                log.debug('Field with name "%s" doesn\'t exist in the model %s' % (key, type(self)))
                continue

            if isinstance(field, models.IntegerField) and value:
                try:
                    value = int(value)
                except:
                    pass
            if isinstance(field, models.FloatField) and value:
                try:
                    value = float(value)
                except:
                    pass
            elif isinstance(field, models.DateTimeField):
                try:
                    value = int(value)
                    assert value > 0
                    value = datetime.fromtimestamp(value)
                except:
                    value = None
            elif isinstance(field, models.DateField):
                try:
                    value = date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
                except:
                    value = None

            elif isinstance(field, models.OneToOneField) and value:
                rel_instance = field.rel.to()
                rel_instance.parse(dict(value))
                value = rel_instance

            if isinstance(field, (fields.CommaSeparatedCharField, models.CommaSeparatedIntegerField)) and isinstance(value, list):
                value = ','.join([unicode(v) for v in value])

            setattr(self, key, value)

    @property
    def slug(self):
        raise NotImplementedError("You must specify slug for model")

    def get_url(self):
        return 'http://vk.com/%s' % self.slug

    def fetch_likes(self, owner_id, item_id, offset=0, count=1000, filter='likes', *args, **kwargs):
        if count > 1000:
            raise ValueError("Parameter 'count' can not be more than 1000")
        if filter not in ['likes','copies']:
            raise ValueError("Parameter 'filter' should be equal to 'likes' or 'copies'")
        if self.likes_type is None:
            raise ImproperlyConfigured("'likes_type' attribute should be specified")

        # type
        # тип Like-объекта. Подробнее о типах объектов можно узнать на странице Список типов Like-объектов.
        kwargs['type'] = self.likes_type
        # owner_id
        # идентификатор владельца Like-объекта (id пользователя или id приложения). Если параметр type равен sitepage, то в качестве owner_id необходимо передавать id приложения. Если параметр не задан, то считается, что он равен либо идентификатору текущего пользователя, либо идентификатору текущего приложения (если type равен sitepage).
        kwargs['owner_id'] = owner_id
        # item_id
        # идентификатор Like-объекта. Если type равен sitepage, то параметр item_id может содержать значение параметра page_id, используемый при инициализации виджета «Мне нравится».
        kwargs['item_id'] = item_id
        # page_url
        # url страницы, на которой установлен виджет «Мне нравится». Используется вместо параметра item_id.

        # filter
        # указывает, следует ли вернуть всех пользователей, добавивших объект в список "Мне нравится" или только тех, которые рассказали о нем друзьям. Параметр может принимать следующие значения:
        # likes – возвращать всех пользователей
        # copies – возвращать только пользователей, рассказавших об объекте друзьям
        # По умолчанию возвращаются все пользователи.
        kwargs['filter'] = filter
        # friends_only
        # указывает, необходимо ли возвращать только пользователей, которые являются друзьями текущего пользователя. Параметр может принимать следующие значения:
        # 0 – возвращать всех пользователей в порядке убывания времени добавления объекта
        # 1 – возвращать только друзей текущего пользователя в порядке убывания времени добавления объекта
        # Если метод был вызван без авторизации или параметр не был задан, то считается, что он равен 0.
        kwargs['friends_only'] = 0
        # offset
        # смещение, относительно начала списка, для выборки определенного подмножества. Если параметр не задан, то считается, что он равен 0.
        kwargs['offset'] = int(offset)
        # count
        # количество возвращаемых идентификаторов пользователей.
        # Если параметр не задан, то считается, что он равен 100, если не задан параметр friends_only, в противном случае 10.
        # Максимальное значение параметра 1000, если не задан параметр friends_only, в противном случае 100.
        kwargs['count'] = int(count)

        response = api_call('likes.getList', **kwargs)
        return response['users']

class VkontakteIDModel(VkontakteModel):
    class Meta:
        abstract = True

    remote_id = models.BigIntegerField(u'ID', help_text=u'Уникальный идентификатор', unique=True)

    @property
    def slug(self):
        return self.slug_prefix + str(self.remote_id)