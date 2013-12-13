import factory


class DjangoModelNoCommitFactory(factory.DjangoModelFactory):
    ABSTRACT_FACTORY = True

    @classmethod
    def _create(cls, *args, **kwargs):
        kwargs['commit_remote'] = False
        return super(DjangoModelNoCommitFactory, cls)._create(*args, **kwargs)
