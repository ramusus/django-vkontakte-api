from setuptools import setup, find_packages

setup(
    name='django-vkontakte-api',
    version=__import__('vkontakte_api').__version__,
    description='Django implementation for vkontakte API',
    long_description=open('README.md').read(),
    author='ramusus',
    author_email='ramusus@gmail.com',
    url='https://github.com/ramusus/django-vkontakte-api',
    download_url='http://pypi.python.org/pypi/django-vkontakte-api',
    license='BSD',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,  # because we're including media that Django needs
    install_requires=[
        'django',
        'django-annoying',
        'django-picklefield',
        'django-oauth-tokens>=0.4.9',
        'vkontakte',
        'simplejson',
        'beautifulsoup4',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
