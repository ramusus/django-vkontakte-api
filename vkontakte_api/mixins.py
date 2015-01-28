# -*- coding: utf-8 -*-
import logging

from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from m2m_history.fields import ManyToManyHistoryField
from vkontakte_users.models import User

from . import fields
from .models import VkontakteManager, VkontakteTimelineManager


log = logging.getLogger('vkontakte_api')


def get_or_create_group_or_user(remote_id):
    if remote_id > 0:
        Model = ContentType.objects.get(app_label='vkontakte_users', model='user').model_class()
    elif remote_id < 0:
        Model = ContentType.objects.get(app_label='vkontakte_groups', model='group').model_class()
    else:
        raise ValueError("remote_id shouldn't be equal to 0")

    return Model.objects.get_or_create(remote_id=abs(remote_id))[0]


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


class ActionableModelMixin(models.Model):

    actions_count = models.PositiveIntegerField(null=True, help_text='The number of total actions with this item')

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.actions_count = sum([getattr(self, field, None) or 0
                                  for field in ['likes_count', 'reposts_count', 'comments_count']])
        super(ActionableModelMixin, self).save(*args, **kwargs)


class AuthorableModelMixin(models.Model):

    author_content_type = models.ForeignKey(
        ContentType, null=True, related_name='content_type_authors_%(app_label)s_%(class)ss')
    author_id = models.BigIntegerField(null=True, db_index=True)
    author = generic.GenericForeignKey('author_content_type', 'author_id')

    class Meta:
        abstract = True

    @property
    def by_group(self):
        return self.author_content_type.model == 'group' and self.author_content_type.app_label == 'vkontakte_groups'

    @property
    def by_user(self):
        return self.author_content_type.model == 'user' and self.author_content_type.app_label == 'vkontakte_users'

    def parse(self, response):
        if 'from_id' in response:
            self.author = get_or_create_group_or_user(response.pop('from_id'))
        super(AuthorableModelMixin, self).parse(response)


class OwnerableModelMixin(models.Model):

    owner_content_type = models.ForeignKey(
        ContentType, null=True, related_name='content_type_owners_%(app_label)s_%(class)ss')
    owner_id = models.BigIntegerField(null=True, db_index=True)
    owner = generic.GenericForeignKey('owner_content_type', 'owner_id')

    class Meta:
        abstract = True

    @property
    def on_group_wall(self):
        from vkontakte_groups.models import Group
        return isinstance(self.owner, Group)

    @property
    def on_user_wall(self):
        from vkontakte_users.models import User
        return isinstance(self.owner, User)

    @property
    def owner_remote_id(self):
        return self.get_owner_remote_id(self.owner)

    @classmethod
    def get_owner_remote_id(cls, owner):
        from vkontakte_users.models import User
        from vkontakte_groups.models import Group

        if isinstance(owner, User):
            return owner.remote_id
        elif isinstance(owner, Group):
            return -1 * owner.remote_id
        else:
            raise ValueError("Field owner should store User of Group, not %s" % owner.__class__)

    def parse(self, response):
        if 'owner_id' in response:
            self.owner = get_or_create_group_or_user(response.pop('owner_id'))
        super(OwnerableModelMixin, self).parse(response)


class LikableModelMixin(models.Model):

    likes_users = ManyToManyHistoryField(User, related_name='like_%(class)ss')
    likes_count = models.PositiveIntegerField(u'Likes', null=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def likes_remote_type(self):
        raise NotImplementedError()

    @transaction.commit_on_success
    def fetch_likes(self, *args, **kwargs):

        kwargs['likes_type'] = self.likes_remote_type
        kwargs['item_id'] = self.remote_id_short
        kwargs['owner_id'] = self.owner_remote_id

        log.debug('Fetching likes of %s %s of owner "%s"' % (self._meta.module_name, self.remote_id, self.owner))

        ids = User.remote.fetch_likes_user_ids(*args, **kwargs)
        self.likes_users = User.remote.fetch(ids=ids, only_expired=True)

        # update self.likes_count
        likes_count = self.likes_users.count()
        if likes_count < self.likes_count:
            log.warning('Fetched ammount of like users less, than attribute `likes` of post "%s": %d < %d' % (
                self.remote_id, likes_count, self.likes_count))
        elif likes_count > self.likes_count:
            self.likes_count = likes_count
            self.save()

        return self.likes_users.all()

    def parse(self, response):
        if 'likes' in response:
            value = response.pop('likes')
            if isinstance(value, int):
                response['likes_count'] = value
            elif isinstance(value, dict) and 'count' in value:
                response['likes_count'] = value['count']
        super(LikableModelMixin, self).parse(response)


class RawModelMixin(models.Model):

    raw_json = fields.JSONField(default={}, null=True)

    class Meta:
        abstract = True

    def parse(self, response):
        self.raw_json = dict(response)
        super(RawModelMixin, self).parse(response)
