# -*- coding: utf-8 -*-
from abc import abstractmethod
from datetime import datetime, date
import logging
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models, transaction, IntegrityError
from django.db.models.fields import FieldDoesNotExist
from django.db.models.query import QuerySet
from django.utils import timezone

from . import fields
from .api import api_call, VkontakteError
from .exceptions import VkontakteDeniedAccessError, VkontakteContentError, VkontakteParseError, WrongResponseType
from .signals import vkontakte_api_post_fetch


log = logging.getLogger('vkontakte_api')

COMMIT_REMOTE = getattr(settings, 'VKONTAKTE_API_COMMIT_REMOTE', True)
MASTER_DATABASE = getattr(settings, 'VKONTAKTE_API_MASTER_DATABASE', 'default')


class VkontakteManager(models.Manager):
    methods_namespace = None
    methods = {}
    remote_pk = ()
    version = None

    '''
    Vkontakte Ads API Manager for RESTful CRUD operations
    '''

    def __init__(self, methods_namespace=None, methods=None, remote_pk=None, version=None, *args, **kwargs):
        if methods and len(methods.items()) < 1:
            raise ValueError('Argument methods must contains at least 1 specified method')

        if methods_namespace:
            self.methods_namespace = methods_namespace

        if methods:
            self.methods = methods

        if remote_pk:
            self.remote_pk = remote_pk

        if version:
            self.version = version

        super(VkontakteManager, self).__init__(*args, **kwargs)

    def get_by_url(self, url):
        '''
        Return vkonakte object by url
        '''
        m = re.findall(r'^(?:https?://)?vk.com/([^/\?]+)', url)
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
                response = api_call('resolveScreenName', **{'screen_name': slug})
            except VkontakteError, e:
                log.error("Method get_by_slug returned error instead of response. Slug: '%s'. Error: %s" % (slug, e))
                return None

            if response['type'] not in self.model.resolve_screen_name_types:
                raise WrongResponseType("Method get_by_slug returned instance with wrong type '%s', not '%s'. Slug is '%s'" % (
                    response['type'], self.model.resolve_screen_name_types, slug))

            try:
                remote_id = int(response['object_id'])
            except (KeyError, TypeError, ValueError), e:
                # TODO: raise error
                log.error("Method get_by_slug returned response in strange format: %s. Slug is '%s'" %
                          (response, slug))
                return None

        try:
            object = self.model.objects.get(remote_id=remote_id)
            object.screen_name = slug
        except self.model.DoesNotExist:
            object = self.model(remote_id=remote_id, screen_name=slug)

        return object

    def get_or_create_from_instance(self, instance):

        old_instance = None
        remote_pk_dict = {}
        for field_name in self.remote_pk:
            remote_pk_dict[field_name] = getattr(instance, field_name)

        if remote_pk_dict:
            try:
                old_instance = self.model.objects.using(MASTER_DATABASE).get(**remote_pk_dict)
                instance._substitute(old_instance)
                instance.save()
            except self.model.DoesNotExist:
                instance.save()
                log.debug('Fetch and create new object %s with remote pk %s' % (self.model, remote_pk_dict))
        else:
            instance.save()
            log.debug('Fetch and create new object %s without remote pk' % (self.model,))

        vkontakte_api_post_fetch.send(sender=instance.__class__, instance=instance, created=(not old_instance))
        return instance

    def get_or_create_from_resource(self, resource):

        instance = self.model()
        instance.parse(dict(resource))

        return self.get_or_create_from_instance(instance)

    def api_call(self, method='get', methods_namespace=None, **kwargs):
        if self.model.methods_access_tag:
            kwargs['methods_access_tag'] = self.model.methods_access_tag

        # Priority importance of defining version:
        # 1. per call (kwargs)
        # 2. per method (self.methods[method][1])
        # 3. per manager (self.version)
        version = self.version

        if method in self.methods:
            method = self.methods[method]

        if isinstance(method, tuple):
            method, version = method

        version = kwargs.pop('v', version)
        if version:
            kwargs['v'] = float(version)

        # methods namespace
        if methods_namespace:
            pass
        elif self.methods_namespace:
            methods_namespace = self.methods_namespace
        elif self.model.methods_namespace:
            methods_namespace = self.model.methods_namespace
            log.warning("Property Model.methods_namespace is deprecated, use Manager.methods_namespace instead")

        if methods_namespace:
            method = methods_namespace + '.' + method

        response = api_call(method, **kwargs)

        if version >= 4.93:
            if isinstance(response, dict) and 'items' in response:
                response = response['items']

        return response

    @transaction.commit_on_success
    def fetch(self, *args, **kwargs):
        '''
        Retrieve and save object to local DB
        '''
        result = self.get(*args, **kwargs)
        if isinstance(result, list):
            # python 2.6 compatibility
            return self.model.objects.filter(pk__in=set([self.get_or_create_from_instance(instance).pk for instance in result]))
#         return
#         self.model.objects.filter(pk__in={self.get_or_create_from_instance(instance).pk
#         for instance in result})
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
        extra_fields['fetched'] = timezone.now()

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
            for k, v in extra_fields.items():
                setattr(instance, k, v)
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


class VkontakteTimelineManager(VkontakteManager):

    '''
    Manager class, child of VkontakteManager for fetching objects with arguments `after`, `before`
    '''
    timeline_cut_fieldname = 'date'
    timeline_force_ordering = False

    def get_timeline_date(self, instance):
        return getattr(instance, self.timeline_cut_fieldname, datetime(1970, 1, 1).replace(tzinfo=timezone.utc))

    @transaction.commit_on_success
    def fetch(self, *args, **kwargs):
        '''
        Retrieve and save object to local DB
        Return queryset with respect to parameters:
         * 'after' - excluding all items before.
         * 'before' - excluding all items after.
        '''
        after = kwargs.pop('after', None)
        before = kwargs.pop('before', None)

        result = self.get(*args, **kwargs)
        if isinstance(result, list):
            instances = self.model.objects.none()

            if self.timeline_force_ordering:
                result.sort(key=self.get_timeline_date, reverse=True)

            for instance in result:

                timeline_date = self.get_timeline_date(instance)

                if timeline_date and isinstance(timeline_date, datetime):

                    if after and after > timeline_date:
                        break

                    if before and before < timeline_date:
                        continue

                instance = self.get_or_create_from_instance(instance)
                instances |= instance.__class__.objects.filter(pk=instance.pk)
            return instances
        elif isinstance(result, QuerySet):
            return result
        else:
            return self.get_or_create_from_instance(result)


class VkontakteModel(models.Model):

    # TODO: capitalize names of model settings
    # or use here some app for defining config of models
    resolve_screen_name_types = []
    remote_pk_field = 'id'
    remote_pk_local_field = 'remote_id'
    methods_access_tag = ''
    methods_namespace = ''

    fetched = models.DateTimeField(u'Обновлено', null=True, blank=True, db_index=True)

    objects = models.Manager()

    class Meta:
        abstract = True

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
                key = self.remote_pk_local_field
                value = int(value)

            try:
                field = self._meta.get_field(key)
            except FieldDoesNotExist:
                log.debug('Field with name "%s" doesn\'t exists in the model %s' % (key, self.__class__.__name__))
                continue

            if isinstance(field, models.IntegerField) and value:
                try:
                    value = int(value)
                except:
                    pass
            elif isinstance(field, models.FloatField) and value:
                try:
                    value = float(value)
                except:
                    pass
            elif isinstance(field, models.CharField):
                if isinstance(value, bool):
                    value = ''
                else:
                    try:
                        value = unicode(value)
                    except:
                        pass

            elif isinstance(field, models.DateTimeField):
                try:
                    value = int(value)
                    assert value > 0
                    value = datetime.utcfromtimestamp(value).replace(tzinfo=timezone.utc)
                except:
                    value = None
            elif isinstance(field, models.DateField):
                try:
                    # TODO: define tzinfo here
                    value = date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
                except:
                    value = None

            if isinstance(field, models.OneToOneField) and value:
                rel_class = field.rel.to
                if isinstance(value, int):
                    try:
                        rel_instance = rel_class.objects.get(pk=value)
                    except rel_class.DoesNotExist:
                        raise VkontakteParseError("OneToOne relation of model %s (PK=%s) does not exist" %
                                                  (rel_class.__name__, value))
                else:
                    rel_instance = rel_class().parse(dict(value))
                value = rel_instance

            if isinstance(field, (fields.CommaSeparatedCharField, models.CommaSeparatedIntegerField)) and isinstance(value, list):
                value = ','.join([unicode(v) for v in value])

            setattr(self, key, value)

    def refresh(self):
        """
        Refresh current model with remote data
        """
        objects = self.__class__.remote.fetch(**self.refresh_kwargs)
        if len(objects) == 1:
            self.__dict__.update(objects[0].__dict__)
        else:
            raise VkontakteContentError(
                "Remote server returned more objects, than expected - %d instead of one. Object details: %s, request details: %s" % (len(objects), self.__dict__, kwargs))

    def get_url(self):
        return 'http://vk.com/%s' % self.slug

    @property
    def refresh_kwargs(self):
        raise NotImplementedError("Property %s.refresh_kwargs should be specified" % self.__class__.__name__)

    @property
    def slug(self):
        raise NotImplementedError("Property %s.slug should be specified" % self.__class__.__name__)


class RemoteIdModelMixin:

    @property
    def slug(self):
        return self.slug_prefix + str(self.remote_id)

    @property
    def remote_id_short(self):
        return str(self.remote_id).split('_')[-1]


class VkontakteIDModel(RemoteIdModelMixin, VkontakteModel):

    remote_id = models.BigIntegerField(u'ID', help_text=u'Уникальный идентификатор', unique=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        '''
        In case of IntegrityError, caused by `remote_id` field make substitution and save again
        '''
        try:
            return super(VkontakteIDModel, self).save(*args, **kwargs)
        except IntegrityError, e:
            try:
                assert self.remote_id and 'remote_id' in unicode(e)
                instance = self.__class__.objects.get(remote_id=self.remote_id)
                self._substitute(instance)
                kwargs['force_insert'] = False
                return super(VkontakteIDModel, self).save(*args, **kwargs)
            except (AssertionError, self.__class__.DoesNotExist):
                raise e


class VkontakteIDStrModel(RemoteIdModelMixin, VkontakteModel):

    remote_id = models.CharField(u'ID', max_length=20, help_text=u'Уникальный идентификатор', unique=True)

    class Meta:
        abstract = True


class VkontaktePKModel(RemoteIdModelMixin, VkontakteModel):

    remote_id = models.BigIntegerField(u'ID', help_text=u'Уникальный идентификатор', primary_key=True)

    class Meta:
        abstract = True


class VkontakteCRUDManager(models.Manager):

    def create(self, *args, **kwargs):
        instance = self.model(**kwargs)
        instance.save()
        return instance


class VkontakteCRUDModel(models.Model):

    # list of required number of fields for updating model remotely
    fields_required_for_update = []

    # flag should we update model remotely on save() and delete() methods
    _commit_remote = True

    archived = models.BooleanField(u'В архиве', default=False)

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        self._commit_remote = kwargs.pop('commit_remote', self._commit_remote)
        super(VkontakteCRUDModel, self).__init__(*args, **kwargs)

    def delete(self, commit_remote=None, *args, **kwargs):
        if not self.archived:
            self.delete_remote(commit_remote)

    def restore(self, commit_remote=None, *args, **kwargs):
        if self.archived:
            self.restore_remote(commit_remote)

    def save(self, commit_remote=None, *args, **kwargs):
        '''
        Update remote version of object before saving if data is different
        '''
        commit_remote = commit_remote if commit_remote is not None else self._commit_remote
        if commit_remote and COMMIT_REMOTE:
            if not self.pk and not self.fetched:
                self.create_remote(**kwargs)
            elif self.pk and self.fields_changed:
                self.update_remote(**kwargs)
        super(VkontakteCRUDModel, self).save(*args, **kwargs)

    def create_remote(self, **kwargs):
        params = self.prepare_create_params(**kwargs)
        if 'method' not in params:
            params['method'] = 'create'
        response = self.__class__.remote.api_call(**params)
        self.remote_id = self.parse_remote_id_from_response(response)
        log.info("Remote object %s was created successfully with ID %s" % (self._meta.object_name, self.remote_id))

    def update_remote(self, **kwargs):
        params = self.prepare_update_params_distinct(**kwargs)
        if 'method' not in params:
            params['method'] = 'update'
        # sometimes response contains 1, sometimes remote_id
        response = self.__class__.remote.api_call(**params)
        if not response:
            message = "Error response '%s' while saving remote %s with ID %s and data '%s'" % (
                response, self._meta.object_name, self.remote_id, params)
            log.error(message)
            raise VkontakteContentError(message)
        log.info("Remote object %s with ID=%s was updated with fields '%s' successfully" %
                 (self._meta.object_name, self.remote_id, params))

    def delete_remote(self, commit_remote=None):
        '''
        Delete objects remotely and mark it archived localy
        '''
        commit_remote = commit_remote if commit_remote is not None else self._commit_remote
        if commit_remote and self.remote_id:
            params = self.prepare_delete_params()
            if 'method' not in params:
                params['method'] = 'delete'
            success = self.__class__.remote.api_call(**params)
            model = self._meta.object_name
            if not success:
                message = "Error response '%s' while deleting remote %s with ID %s" % (success, model, self.remote_id)
                log.error(message)
                raise VkontakteContentError(message)
            log.info("Remote object %s with ID %s was deleted successfully" % (model, self.remote_id))

        self.archived = True
        self.save(commit_remote=False)

    def restore_remote(self, commit_remote=None):
        '''
        Restore objects remotely and unmark it archived localy
        '''
        commit_remote = commit_remote if commit_remote is not None else self._commit_remote
        if commit_remote and self.remote_id:
            params = self.prepare_restore_params()
            if 'method' not in params:
                params['method'] = 'restore'
            success = self.__class__.remote.api_call(**params)
            model = self._meta.object_name
            if not success:
                message = "Error response '%s' while restoring remote %s with ID %s" % (success, model, self.remote_id)
                log.error(message)
                raise VkontakteContentError(message)
            log.info("Remote object %s with ID %s was restored successfully" % (model, self.remote_id))

        self.archived = False
        self.save(commit_remote=False)

    @property
    def fields_changed(self):
        old = self.__class__.objects.get(remote_id=self.remote_id)
        return old.__dict__ != self.__dict__

    def prepare_update_params_distinct(self, **kwargs):
        '''
        Return dict with distinct set of fields for update
        '''
        old = self.__class__.objects.get(remote_id=self.remote_id)
        fields_new = self.prepare_update_params(**kwargs).items()
        fields_old = old.prepare_update_params(**kwargs).items()
        fields = dict(set(fields_new).difference(set(fields_old)))
        fields.update(dict([(k, v) for k, v in fields_new if k in self.fields_required_for_update]))
        return fields

    @abstractmethod
    def prepare_create_params(self, **kwargs):
        """
        Prepare params for remote create object.
        Incoming params:
            **kwargs - fields, which model instance hasn't

        return {param_key: val, ....}
        """
        raise NotImplementedError

    @abstractmethod
    def prepare_update_params(self, **kwargs):
        """
        Prepare params for remote update object.
        Incoming params:
            **kwargs - fields, which model instance hasn't

        return {param_key: val, ....}
        """
        raise NotImplementedError

    @abstractmethod
    def prepare_delete_params(self):
        """
        Prepar params for remote delete object.

        return {param_key: val, ....}
        """
        raise NotImplementedError

    @abstractmethod
    def prepare_restore_params(self):
        """
        Prepar params for remote restore object.

        return {param_key: val, ....}
        """
        return self.prepare_delete_params()

    @abstractmethod
    def parse_remote_id_from_response(self, response):
        """
        Extract remote_id from response from API create call.
        Incoming param:
            response - API crete call response

        return 'some_id'
        """
        raise NotImplementedError

    def check_remote_existance(self, *args, **kwargs):
        self.refresh(*args, **kwargs)
        if self.archived:
            self.archive(commit_remote=False)
            return False
        else:
            return True
