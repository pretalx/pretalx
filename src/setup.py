from codecs import open
from os import path

from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
try:
    with open(path.join(here, '../README.rst'), encoding='utf-8') as f:
        long_description = f.read()
except:  # noqa
    long_description = ''

setup(
    name='pretalx',
    version='0.0.0',
    description='Conference organization: CfPs, scheduling, much more',
    long_description=long_description,
    url='http://pretalx.org',
    author='Tobias Kunze',
    author_email='rixx@cutebit.de',
    license='Apache License 2.0',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Other Audience',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Environment :: Web Environment',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.6',
        'Framework :: Django :: 1.11'
    ],

    keywords='tickets web shop ecommerce',
    install_requires=[
        'bleach==2.*',
        'celery==4.0.*',
        'csscompressor==0.9.*',
        'Django==1.11.*',
        'django-compressor==2.1.*',
        'django-csp==3.3.*',
        'django-formtools==2.0.*',
        'django-hierarkey==1.0.*',
        'django-i18nfield==1.1.*',
        'django-libsass==0.7',
        'Markdown==2.6.*',
        'pytz',
        'requests',
        'urlman==1.1.*',
        'whitenoise==3.3.*',
        'reportlab==3.4.*',
        'vobject==0.9.*',
    ],
    dependency_links=[
        'git@github.com/GabrielUlici/django-bootstrap4.git#egg=django-bootstrap4',
    ],
    extras_require={
        'dev': [
            'beautifulsoup4',
            'isort',
            'lxml',
            'pylama',
            'pytest',
            'pytest-cov',
            'pytest-django',
            'pytest-mock',
        ],
        'mysql': ['mysqlclient'],
        'postgres': ['psycopg2'],
    },

    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
)
