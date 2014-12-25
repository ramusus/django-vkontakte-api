# -*- coding: utf-8 -*-
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from . models import VkontakteManager, VkontakteTimelineManager


class CountOffsetManagerMixin(VkontakteManager):

    def fetch(self, count=100, offset=0, **kwargs):
        count = int(count)
        if count > 100:
            raise ValueError("Attribute 'count' can not be more than 100")

        # count количество элементов, которое необходимо получить.
        if count:
            kwargs['count'] = count

        # offset смещение, необходимое для выборки определенного подмножества. По умолчанию — 0.
        # положительное число
        offset = int(offset)
        if offset:
            kwargs['offset'] = offset

        return super(CountOffsetManagerMixin, self).fetch(**kwargs)


class AfterBeforeManagerMixin(VkontakteTimelineManager):

    def fetch(self, before=None, after=None, **kwargs):
        if before and not after:
            raise ValueError("Attribute `before` should be specified with attribute `after`")
        if before and before < after:
            raise ValueError("Attribute `before` should be later, than attribute `after`")

        # special parameters
        if after:
            kwargs['after'] = after
        if before:
            kwargs['before'] = before

        return super(AfterBeforeManagerMixin, self).fetch(**kwargs)


class OwnerableModelMixin(models.Model):
    owner_content_type = models.ForeignKey(ContentType, null=True, related_name='content_type_owners_%(class)ss')
    owner_id = models.BigIntegerField(null=True, db_index=True)
    owner = generic.GenericForeignKey('owner_content_type', 'owner_id')

    class Meta:
        abstract = True

    def _get_or_create_group_or_user(self, remote_id):
        if remote_id > 0:
            Model = ContentType.objects.get(app_label='vkontakte_users', model='user').model_class()
        elif remote_id < 0:
            Model = ContentType.objects.get(app_label='vkontakte_groups', model='group').model_class()
        else:
            raise ValueError("remote_id shouldn't be equal to 0")

        object, _created = Model.objects.get_or_create(remote_id=abs(remote_id))

        return object

    @property
    def owner_remote_id(self):
        if self.owner_content_type.model == 'user':
            return self.owner_id
        else:
            return -1 * self.owner_id

    def parse(self, response):
        self.owner = self._get_or_create_group_or_user(response.pop('owner_id'))

        super(OwnerableModelMixin, self).parse(response)
