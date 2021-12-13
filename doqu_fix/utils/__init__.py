# -*- coding: utf-8 -*-
#
#    Doqu is a lightweight schema/query framework for doqument databases.
#    Copyright © 2009—2010  Andrey Mikhaylenko
#
#    This file is part of Doqu.
#
#    Doqu is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Doqu is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with Doqu.  If not, see <http://gnu.org/licenses/>.

"""
Utilities
=========

Various useful functions. Some can be imported from :mod:`doqu.utils`, some
are available directly at :mod:`doqu`.

These utilities are either stable and well-tested or possible changes in their
API are not considered harmful (i.e. they are marginal). Important functions
which design is likely to change or which lack proper tests are located in
:mod:`doqu.future`.
"""

import os
import pkg_resources
import re
import sys
from functools import wraps

from doqu import validators


__all__ = ['dump_doc', 'get_db', 'camel_case_to_underscores', 'load_fixture']


def get_db(settings_dict=None, **settings_kwargs):
    """
    Storage adapter factory. Expects path to storage backend module and
    optional backend-specific settings. Returns storage adapter instance.
    If required underlying library is not found, exception
    `pkg_resources.DistributionNotFound` is raised with package name and
    version as the message.

    :param backend:
        string, dotted path to a Doqu storage backend (e.g.
        `doqu.ext.tokyo_tyrant`). See :doc:`ext` for a list of bundled backends
        or :doc:`backend_base` for backend API reference.

    Usage::

        import doqu

        db = doqu.get_db(backend='doqu.ext.shelve', path='test.db')

        query = SomeDocument.objects(db)

    Settings can be also passed as a dictionary::

        SETTINGS = {
            'backend': 'doqu.ext.tokyo_cabinet',
            'path': 'test.tct',
        }

        db = doqu.get_db(SETTINGS)

    The two methods can be combined to override certain settings::

        db = doqu.get_db(SETTINGS, path='another_db.tct')


    """
    # copy the dictionary because we'll modify it below
    settings = dict(settings_dict or {})
    settings.update(settings_kwargs)

    # extract the dot-delimited path to the Doqu-compatible backend
    backend_path = settings.pop('backend')

    # import the backend module
    entry_points = pkg_resources.iter_entry_points('db_backends')
    named_entry_points = dict((x.module_name, x) for x in entry_points)
    if backend_path in named_entry_points:
        entry_point = named_entry_points[backend_path]
        module = entry_point.load()
    else:
        __import__(backend_path)
        module = sys.modules[backend_path]

    # instantiate the storage provided by the backend module
    StorageAdapter = module.StorageAdapter
    return StorageAdapter(**settings)

def camel_case_to_underscores(class_name):
    """
    Returns a pretty readable name based on the class name. For example,
    "SomeClass" is translated to "some_class".
    """
    # This is derived from Django:
    # Calculate the verbose_name by converting from InitialCaps to "lowercase with spaces".
    return re.sub('(((?<=[a-z])[A-Z])|([A-Z](?![A-Z]|$)))', ' \\1',
                  class_name).lower().strip().replace(' ', '_')

def load_fixture(path, db=None):
    """
    Reads given file (assuming it is in a known format), loads it into given
    storage adapter instance and returns that instance.

    :param path:
        absolute or relative path to the fixture file; user constructions
        ("~/foo") will be expanded.
    :param db:
        a storage adapter instance (its class must conform to the
        :class:`~doqu.backend_base.BaseStorageAdapter` API). If not provided, a
        memory storage will be created.

    Usage::

        import doqu

        db = doqu.load_fixture('account.csv')

        query = SomeDocument.objects(db)

    """
    db = db or get_db(backend='doqu.ext.shove_db', store_uri='memory://')
    path = os.path.expanduser(path) if '~' in path else os.path.abspath(path)
    if not os.path.isfile(path):
        raise ValueError('could not find file {0}'.format(path))
    loader = _get_fixture_loader(path)
    f = open(path)
    items = loader(f)
    for item in items:
        db.save(None, item)
    return db

def _get_fixture_loader(filename):
    if filename.endswith('.yaml'):
        import yaml
        loader = yaml.load
    elif filename.endswith('.json'):
        import json
        loader = json.load
    elif filename.endswith('.csv'):
        import csv
        loader = csv.DictReader
    else:
        raise ValueErrori('unknown data file type: {0}'.format(filename))
    return loader

def cached_property(function):
    "A simple read-only cached property"
    @wraps(function)
    def inner(self):
        if not hasattr(self, '__cached_values'):
            self.__cached_values = {}
        if not function.__name__ in self.__cached_values:
            value = function(self)
            self.__cached_values[function.__name__] = value
        return self.__cached_values[function.__name__]
    return property(inner)

def dump_doc(self, raw=False, as_repr=False, align=True, keys=None, exclude=None):
    """Returns a multi-line string with document keys and values nicely
    formatted and aligned.

    :param raw:
        If `True`, uses "raw" values, as fetched from the database (note that
        this will fail for unsaved documents). If not, the values are obtained
        in the normal way, i.e. by `__getitem__()`. Default is `False`.
    :prarm as_repr:
        If `True`, uses `repr()` for values; if not, coerces them to Unicode.
        Default if `False`.
    :param align:
        If `True`, the keys and values are aligned into two columns of equal
        width. If `False`, no padding is used. Default is `True`.
    :param keys:
        a list of document keys to show. By default all existing keys are
        included.
    :param exclude:
        a list of keys to exclude. By default no keys are excluded.

    """
    def _gen():
        width = max(len(k) for k in self.keys())
        template = u' {key:>{width}} : {value}' if align else u'{key}: {value}'
        if raw:
            assert self._saved_state
            data = self._saved_state.data
        else:
            data = self
        for key in sorted(data):
            if keys and key not in keys:
                continue
            if exclude and key in exclude:
                continue
            value = data[key]
            if as_repr:
                value = repr(value)
            yield template.format(key=key, value=value, width=width)
    return '\n'.join(_gen())

def is_doc_valid(doc):
    try:
        doc.validate()
    except validators.ValidationError:
        return False
    else:
        return True

def safe_unicode(value, force_string=False):
    """Returns a Unicode version of given string. If given value is not a
    string, it is returned as is.

    :param force_string:

        if `True`, non-string values are coerced to strings. Default is
        `False`.

    """
    if isinstance(value, unicode):
        return value
    elif isinstance(value, basestring):
        return value.decode('utf-8', 'replace')
    else:
        if force_string:
            return unicode(value)
        else:
            return value
