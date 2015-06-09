import factory


class DjangoModelNoCommitFactory(factory.DjangoModelFactory):

    @classmethod
    def _create(cls, *args, **kwargs):
        kwargs['commit_remote'] = False
        return super(DjangoModelNoCommitFactory, cls)._create(*args, **kwargs)

    class Meta:
        abstract = True
