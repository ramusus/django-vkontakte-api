from django.dispatch import Signal

#vkontake_api_pre_fetch = Signal(providing_args=["instance"])#, "raw", "using", "fetch_fields"])
vkontakte_api_post_fetch = Signal(providing_args=["instance", "created"])#, "raw", "using", "fetch_fields"])
