# -*- coding: utf-8 -*-
from django.contrib import admin

admin.ModelAdmin.save_on_top = True
admin.ModelAdmin.list_per_page = 50

class GenericRelationListFilter(admin.SimpleListFilter):
    separator = '-'
    ct_field_name = ''
    id_field_name = ''
    field_name = ''

    @property
    def parameter_name(self):
        return self.field_name

    def lookups(self, request, model_admin):
        return [('%s%s%s' % (getattr(instance, self.ct_field_name).id, self.separator, getattr(instance, self.id_field_name)), getattr(instance, self.field_name)) for instance in model_admin.model.objects.order_by().distinct(self.ct_field_name,self.id_field_name)]

    def queryset(self, request, queryset):
        if self.value() and self.separator in self.value():
            content_type, id = self.value().split(self.separator)
            return queryset.filter(**{self.ct_field_name: content_type, self.id_field_name: id})

class VkontakteModelAdmin(admin.ModelAdmin):

    def vk_link(self, obj):
        return u'<a href="%s" target="_blank">%s</a>' % (obj.get_url(), getattr(obj, 'slug', 'vk.com'))
    vk_link.short_description = u'vk.com'
    vk_link.allow_tags = True

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return [field.name for field in obj._meta.fields if field.name not in ['id']]
        return []