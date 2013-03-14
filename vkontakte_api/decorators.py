# -*- coding: utf-8 -*-
from django.utils.functional import wraps

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
def fetch_all(func, return_all, kwargs_offset='offset'):
    """
    Class method decorator for fetching all items. Add parameter `all=False` for decored method.
    If `all` is True, method runs as many times as it returns any results.
    Decorator receive 2 parameters:
      * callback method `return_all`. It's called with the same parameters
        as decored method after all itmes are fetched.
      * `kwargs_offset` - name of offset parameter among kwargs
    Usage:

    @fetch_all(return_all=lambda instance,*a,**k: instance.items.all())
    def fetch_something(self, ..., *kwargs):
        ....
    """
    def wrapper(self, all=False, *args, **kwargs):
        if all:
            instances = func(self, *args, **kwargs)
            instances_count = len(instances)

            if instances_count != 0:
                # TODO: make protection somehow from endless loop in case
                # where `kwargs_offset` argument is not make any sense for `func`
                kwargs[kwargs_offset] = kwargs.get(kwargs_offset, 0) + instances_count
                return wrapper(self, all=True, *args, **kwargs)
            else:
                # do something
                pass
            return return_all(*args, **kwargs)
        else:
            return func(self, *args, **kwargs)

    return wraps(func)(wrapper)