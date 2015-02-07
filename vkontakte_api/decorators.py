# -*- coding: utf-8 -*-
from django.db.models.query import QuerySet
from django.utils.functional import wraps

try:
    from django.db.transaction import atomic
except ImportError:
    from django.db.transaction import commit_on_success as atomic


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
def fetch_all(func, return_all=None, always_all=False, kwargs_offset='offset', kwargs_count='count', default_count=None, max_extra_calls=0):
    """
    Class method decorator for fetching all items. Add parameter `all=False` for decored method.
    If `all` is True, method runs as many times as it returns any results.
    Decorator receive parameters:
      * callback method `return_all`. It's called with the same parameters
        as decored method after all itmes are fetched.
      * `kwargs_offset` - name of offset parameter among kwargs
      * `always_all` bool - return all instances in any case of argument `all`
        of decorated method
    Usage:

        @fetch_all(return_all=lambda self,instance,*a,**k: instance.items.all())
        def fetch_something(self, ..., *kwargs):
        ....
    """

    def wrapper(self, all=False, instances_all=None, extra_calls=0, *args, **kwargs):
        if always_all or all:

            instances = func(self, *args, **kwargs)

            if isinstance(instances, QuerySet):
                if not instances_all:
                    instances_all = QuerySet().none()
                instances_all |= instances
                instances_count = instances.count()
            elif isinstance(instances, list):
                if not instances_all:
                    instances_all = []
                instances_all += instances
                instances_count = len(instances)
            else:
                raise ValueError(
                    "Wrong type of response from func %s. It should be QuerySet or list, not a %s" % (func, type(instances)))

            if instances_count > 0 and (not default_count or instances_count == kwargs.get(kwargs_count, default_count)):
                # TODO: make protection somehow from endless loop in case
                # where `kwargs_offset` argument is not make any sense for `func`
                kwargs[kwargs_offset] = kwargs.get(kwargs_offset, 0) + instances_count
                return wrapper(self, all=all, instances_all=instances_all, *args, **kwargs)
            # попытка решить проблему получения репостов поста https://vk.com/wall-36948301_23383?w=shares%2Fwall-36948301_23383
            elif extra_calls < max_extra_calls - 1:
                kwargs[kwargs_offset] = kwargs.get(kwargs_offset, 0) + 1
                extra_calls += 1
                return wrapper(self, all=all, instances_all=instances_all, extra_calls=extra_calls, *args, **kwargs)

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

'''
From here http://stackoverflow.com/questions/815110/is-there-a-decorator-to-simply-cache-function-return-values
With modifications for properties
'''


def memoize(function):
    memo = {}

    def wrapper(*args, **kwargs):
        key = args
        if key in memo:
            return memo[key]
        else:
            result = function(*args, **kwargs) if hasattr(function, '__call__') else function
            memo[key] = result
            return result
    return wrapper
