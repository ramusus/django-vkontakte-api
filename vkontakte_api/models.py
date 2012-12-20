# -*- coding: utf-8 -*-
from django.db import models
from django.db.models.fields import FieldDoesNotExist
from datetime import datetime, date
from vkontakte_api.utils import api_call
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
        Return vkonakte group by group url
        '''
        m = re.findall(r'(?:http://)?vk.com/(.+)/?', url)
        if not len(m):
            raise ValueError("Url should be started with http://vk.com/")

        return self.get_by_slug(m[0])

    def get_by_slug(self, slug):
        '''
        Return User of Group by slug
        '''
        try:
            assert self.model.slug_prefix and slug.startswith(self.model.slug_prefix)
            remote_id = int(slug.replace(self.model.slug_prefix, ''))
        except (AssertionError, ValueError):
            try:
                return self.model.objects.get(screen_name=slug)
            except self.model.DoesNotExist:
                response = api_call('resolveScreenName', **{'screen_name': slug})
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
        return api_call(self.model.methods_namespace + '.' + self.methods[method], **kwargs)

    def get(self, *args, **kwargs):
        '''
        Retrieve objects from remote server
        '''
        response_list = self.api_call(*args, **kwargs)

        if isinstance(response_list, dict):
            response_list = [response_list]

        instances = []
        for resource in response_list:

            # in response with stats there is extra array inside each element
            if isinstance(resource, list) and len(resource):
                resource = resource[0]

            # in some responses first value is `count of all values:
            # http://vk.com/developers.php?oid=-1&p=groups.search
            if isinstance(resource, int):
                continue

            try:
                resource = dict(resource)
            except (TypeError, ValueError), e:
                log.error("Impossible to handle response of api call %s with parameters: %s" % (self.methods['get'], kwargs))
                raise e

            instance = self.model()
            instance.parse(resource)
            instances += [instance]

        return instances

    def fetch(self, **kwargs):
        '''
        Retrieve and save object to local DB
        '''
        instances = []
        for instance in self.get(**kwargs):
            instance.fetched = datetime.now()
            instances += [self.get_or_create_from_instance(instance)]

        return instances

class VkontakteModel(models.Model):
    class Meta:
        abstract = True

    remote_pk_field = 'id'

    fetched = models.DateTimeField(u'Обновлено', null=True, blank=True)

    objects = models.Manager()

    def _substitute(self, old_instance):
        '''
        Substitute new user with old one while updating in method Manager.get_or_create_from_instance()
        Can be overrided in child models
        '''
        self.id = old_instance.id

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
            elif isinstance(field, models.DateTimeField) and value:
                try:
                    value = int(value)
                    assert value > 0
                    value = datetime.fromtimestamp(value)
                except:
                    value = None
            elif isinstance(field, models.DateField) and value:
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

class VkontakteIDModel(VkontakteModel):
    class Meta:
        abstract = True

    remote_id = models.BigIntegerField(u'ID', help_text=u'Уникальный идентификатор', unique=True)

    @property
    def slug(self):
        return self.slug_prefix + str(self.remote_id)