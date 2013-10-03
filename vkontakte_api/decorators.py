# -*- coding: utf-8 -*-
from django.utils.functional import wraps
from django.db.models.query import QuerySet

def opt_arguments(func):
    '''
    Meta-decorator for ablity use decorators with optional arguments
    from here http://www.ellipsix.net/blog/2010/08/more-python-voodoo-optional-argument-decorators.html
    '''
    def meta_wrapper(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            # No arguments, this is the decorator
            # Set default values for the arguments
            return func(args[0])
        else:
            def meta_func(inner_func):
                return func(inner_func, *args, **kwargs)
            return meta_func
    return meta_wrapper

@opt_arguments
def fetch_all(func, return_all=None, kwargs_offset='offset', kwargs_count='count', default_count=None):
    """
    Class method decorator for fetching all items. Add parameter `all=False` for decored method.
    If `all` is True, method runs as many times as it returns any results.
    Decorator receive 2 parameters:
      * callback method `return_all`. It's called with the same parameters
        as decored method after all itmes are fetched.
      * `kwargs_offset` - name of offset parameter among kwargs
    Usage:

        @fetch_all(return_all=lambda self,instance,*a,**k: instance.items.all())
        def fetch_something(self, ..., *kwargs):
        ....
    """
    def wrapper(self, all=False, instances_all=None, *args, **kwargs):
        if all:
            if not instances_all:
                instances_all = QuerySet().none()

            instances = func(self, *args, **kwargs)
            instances_all |= instances
            instances_count = len(instances)

            if instances_count > 0 and (not default_count or instances_count == kwargs.get(kwargs_count, default_count)):
                # TODO: make protection somehow from endless loop in case
                # where `kwargs_offset` argument is not make any sense for `func`
                kwargs[kwargs_offset] = kwargs.get(kwargs_offset, 0) + instances_count
                return wrapper(self, all=all, instances_all=instances_all, *args, **kwargs)

            if return_all:
                return return_all(self, *args, **kwargs)
            else:
                return instances_all
        else:
            return func(self, *args, **kwargs)

    return wraps(func)(wrapper)

def opt_generator(func):
    """
    Class method or function decorator makes able to call generator methods as usual methods.
    Usage:

        @method_decorator(opt_generator)
        def some_method(self, ...):
            ...
            for count in some_another_method():
                yield (count, total)

    It's possible to call this method 2 different ways:

        * instance.some_method() - it will return nothing
        * for count, total in instance.some_method(as_generator=True):
            print count, total
    """
    def wrapper(*args, **kwargs):
        as_generator = kwargs.pop('as_generator', False)
        result = func(*args, **kwargs)
        return result if as_generator else list(result)
    return wraps(func)(wrapper)