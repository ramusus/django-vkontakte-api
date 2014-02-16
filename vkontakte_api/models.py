# -*- coding: utf-8 -*-
from abc import abstractmethod
from django.db import models, transaction, IntegrityError
from django.core.exceptions import ImproperlyConfigured
from django.db.models.fields import FieldDoesNotExist
from django.db.models.query import QuerySet
from django.conf import settings
from datetime import datetime, date
from vkontakte_api.utils import api_call, VkontakteError
from vkontakte_api import fields
import logging
import re

log = logging.getLogger('vkontakte_api')

COMMIT_REMOTE = getattr(settings, 'VKONTAKTE_API_COMMIT_REMOTE', True)


class VkontakteDeniedAccessError(Exception):
    pass


class VkontakteContentError(Exception):
    pass


class VkontakteParseError(Exception):
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

    @transaction.commit_on_success
    def fetch(self, *args, **kwargs):
        '''
        Retrieve and save object to local DB
        '''
        result = self.get(*args, **kwargs)
        if isinstance(result, list):
            instances = self.model.objects.none()
            for instance in result:
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


class VkontakteTimelineManager(VkontakteManager):
    '''
    Manager class, child of VkontakteManager for fetching objects with arguments `after`, `before`
    '''
    timeline_cut_fieldname = 'date'
    timeline_force_ordering = False

    def get_timeline_date(self, instance):
        return getattr(instance, self.timeline_cut_fieldname)

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
    class Meta:
        abstract = True

    remote_pk_field = 'id'
    remote_pk_local_field = 'remote_id'
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
                key = self.remote_pk_local_field
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
                    value = datetime.fromtimestamp(value)
                except:
                    value = None
            elif isinstance(field, models.DateField):
                try:
                    value = date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
                except:
                    value = None

            if isinstance(field, models.OneToOneField) and value:
                rel_class = field.rel.to
                if isinstance(value, int):
                    try:
                        rel_instance = rel_class.objects.get(pk=value)
                    except rel_class.DoesNotExist:
                        raise VkontakteParseError("OneToOne relation of model %s (PK=%s) does not exist" % (rel_class.__name__, value))
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
        objects = type(self).remote.fetch(**self.refresh_kwargs)
        if len(objects) == 1:
            self.__dict__.update(objects[0].__dict__)
        else:
            raise VkontakteContentError("Remote server returned more objects, than expected - %d instead of one. Object details: %s, request details: %s" % (len(objects), self.__dict__, kwargs))

    def get_url(self):
        return 'http://vk.com/%s' % self.slug

    @property
    def refresh_kwargs(self):
        raise NotImplementedError("Property %s.refresh_kwargs should be specified" % type(self))

    @property
    def slug(self):
        raise NotImplementedError("Property %s.slug should be specified" % type(self))


class VkontakteIDModel(VkontakteModel):
    class Meta:
        abstract = True

    remote_id = models.BigIntegerField(u'ID', help_text=u'Уникальный идентификатор', unique=True)

    @property
    def slug(self):
        return self.slug_prefix + str(self.remote_id)

    def save(self, *args, **kwargs):
        '''
        In case of IntegrityError, caused by `remote_id` field make substitution and save again
        '''
        try:
            return super(VkontakteIDModel, self).save(*args, **kwargs)
        except IntegrityError, e:
            try:
                assert self.remote_id and 'remote_id' in e.message
                instance = type(self).objects.get(remote_id=self.remote_id)
                self._substitute(instance)
                kwargs['force_insert'] = False
                return super(VkontakteIDModel, self).save(*args, **kwargs)
            except (AssertionError, type(self).DoesNotExist):
                raise e


class VkontaktePKModel(VkontakteModel):
    class Meta:
        abstract = True

    remote_id = models.BigIntegerField(u'ID', help_text=u'Уникальный идентификатор', primary_key=True)

    @property
    def slug(self):
        return self.slug_prefix + str(self.remote_id)


class VkontakteCRUDManager(models.Manager):

    def create(self, *args, **kwargs):
        instance = self.model(**kwargs)
        instance.save()
        return instance


class VkontakteCRUDModel(models.Model):
    class Meta:
        abstract = True

    # list of required number of fields for updating model remotely
    fields_required_for_update = []

    # flag should we update model remotely on save() and delete() methods
    _commit_remote = True

    archived = models.BooleanField(u'В архиве', default=False)

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
        response = type(self).remote.api_call(
                method='create', **self.prepare_create_params(**kwargs))
        self.remote_id = self.parse_remote_id_from_response(response)
        log.info("Remote object %s was created successfully with ID %s" \
                % (self._meta.object_name, self.remote_id))

    def update_remote(self, **kwargs):
        params = self.prepare_update_params_distinct(**kwargs)
        # sometimes response contains 1, sometimes remote_id
        response = type(self).remote.api_call(method='update', **params)
        if not response:
            message = "Error response '%s' while saving remote %s with ID %s and data '%s'" \
                    % (response, self._meta.object_name, self.remote_id, params)
            log.error(message)
            raise VkontakteContentError(message)
        log.info("Remote object %s with ID=%s was updated with fields '%s' successfully" \
                % (self._meta.object_name, self.remote_id, params))

    def delete_remote(self, commit_remote=None):
        '''
        Delete objects remotely and mark it archived localy
        '''
        commit_remote = commit_remote if commit_remote is not None else self._commit_remote
        if commit_remote and self.remote_id:
            params = self.prepare_delete_params()
            success = type(self).remote.api_call(method='delete', **params)
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
            success = type(self).remote.api_call(method='restore', **params)
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
        old = type(self).objects.get(remote_id=self.remote_id)
        return old.__dict__ != self.__dict__

    def prepare_update_params_distinct(self, **kwargs):
        '''
        Return dict with distinct set of fields for update
        '''
        old = type(self).objects.get(remote_id=self.remote_id)
        fields_new = self.prepare_update_params(**kwargs).items()
        fields_old = old.prepare_update_params(**kwargs).items()
        fields = dict(set(fields_new).difference(set(fields_old)))
        fields.update(dict([(k,v) for k,v in fields_new if k in self.fields_required_for_update]))
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
