"""Dockerfile matrix builder
See:
https://github.com/webplates/dockermatrix
"""

from setuptools import setup
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='dockermatrix',

    version='0.1.1',

    description='Build Dockerfiles from matrices automatically using templates',
    long_description=long_description,

    url='https://github.com/webplates/dockermatrix',

    author='Márk Sági-Kazár',
    author_email='mark.sagikazar@gmail.com',

    license='MIT',

    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3.5',
    ],

    keywords='docker hub matrix dockerfile',

    py_modules=["dockermatrix"],

    install_requires=[
        'jinja2',
        'semver>=2.7',
        'requests',
    ],
)
