#!/usr/bin/env python

from setuptools import setup, find_packages
from io import open
import os

import pywebdav

README = open(os.path.join(os.path.dirname(__file__), 'README.md'), 'r', encoding='utf-8').read()

setup(name='PyWebDAV3',
    description=pywebdav.__doc__,
    author=pywebdav.__author__,
    author_email=pywebdav.__email__,
    maintainer=pywebdav.__author__,
    maintainer_email=pywebdav.__email__,
    use_git_versioner="gitlab:desc:snapshot",
    url='https://github.com/andrewleech/PyWebDAV3',
    platforms=['Unix', 'Windows'],
    license=pywebdav.__license__,
    version=pywebdav.__version__,
    long_description=README,
    classifiers=[
      'Development Status :: 5 - Production/Stable',
      'Environment :: Console',
      'Environment :: Web Environment',
      'Intended Audience :: Developers',
      'Intended Audience :: System Administrators',
      'License :: OSI Approved :: GNU General Public License (GPL)',
      'Operating System :: MacOS :: MacOS X',
      'Operating System :: POSIX',
      'Programming Language :: Python',
      'Topic :: Software Development :: Libraries',
      ],
    keywords=['webdav',
              'server',
              'dav',
              'standalone',
              'library',
              'gpl',
              'http',
              'rfc2518',
              'rfc 2518'
              ],
    packages=find_packages(),
    entry_points={
      'console_scripts': ['davserver = pywebdav.server.server:run']
      },
    install_requires = ['six'],
    setup_requires=['git-versioner'],
    )
