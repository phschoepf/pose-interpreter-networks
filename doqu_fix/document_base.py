# -*- coding: utf-8 -*-
#
#    Doqu is a lightweight schema/query framework for document databases.
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
Document API
============

:term:`Documents <document>` represent database records. Each document is a
(in)complete subset of :term:`fields <field>` contained in a :term:`record`.
Available data types and query mechanisms are determined by the :term:`storage`
in use.

The API was inspired by `Django`_, `MongoKit`_, `WTForms`_, `Svarga`_ and
several other projects. It was important to KISS (keep it simple, stupid), DRY
(do not repeat yourself) and to make the API as abstract as possible so that it
did not depend on backends and yet did not get in the way.

.. _Django: http://djangoproject.com
.. _MongoKit: http://pypi.python.org/pypi/mongokit/
.. _WTForms: http://wtforms.simplecodes.com
.. _Svarga: http://bitbucket.org/piranha/svarga/

"""

import abc
import copy
import logging
import types

import doqu.validators
from doqu.utils import camel_case_to_underscores
from doqu.utils.data_structures import DotDict, ReprMixin


__all__ = ['Document', 'Many']


RECURSIVE_RELATION_NAME = 'self'


log = logging.getLogger(__name__)


class DocumentSavedState(object):
    """
    Represents a database record associated with a storage. Useful to save the
    document back to the storage preserving the attributes that were discarded
    by the document schema.

    To check if the document (thinks that it) is saved to the database::

        if document._saved_saved_state:
            ...

    To check if two documents represent the same database record (even if they
    are instances of different classes)::

        if document_one == document_two:
            ...

        # same as:

        if document_one._saved_saved_state == document_two._saved_saved_state:
            ...

    """
    def __init__(self):
        self.storage = None
        self.key = None
        self.data = None

    def __eq__(self, other):
        if self.storage and self.key and other:
            if self.storage == other.storage and self.key == other.key:
                return True
        return False

    def __hash__(self):
        """
        Storage and primary key together make the hash; document class doesn't
        matter.

        Raises `TypeError` if storage or primary key is not defined.
        """
        if not self.storage or not self.key:
            raise TypeError('Document is unhashable: storage or primary key '
                            'is not defined')
        return hash(self.storage) | hash(self.key)

    def __nonzero__(self):
        # for exps like "if document._saved_state: ..."
        return bool(self.storage or self.key)

    def clone(self):
        c = type(self)()
        c.update(**self.__dict__)
        return c

    def update(self, storage=None, key=None, data=None):
        """
        Updates model state with given values. Empty values are *ignored*. You
        cannot reset the state or its parts by passing None or otherwise "false"
        values to update(). Do it by modifying the attributes directly.
        """
        if not any([storage, key, data]):
            # ignore empty values
            return
        self.storage = storage or self.storage
        self.key = key or self.key
        self.data = self.data if data is None else data.copy()


class DocumentMetadata(object):
    """
    Specifications of a document. They are defined in the document class but
    stored here for document isntances so that they don't interfere with
    document properties.

    :describe skip_type_conversion:
        A list of keys for which automatic type conversion (in backend) should
        be omitted.

    :describe get_item_processors:
        A dictionary of keys and functions. The function is applied to the
        given key's value on access (i.e. when ``__getitem__`` is called).

    :describe set_item_processors:
        A dictionary of keys and functions. The function is applied to a value
        before it is assigned to given key (i.e. when ``__setitem__`` is
        called). The validation is performed *after* the processing.

    :describe incoming_processors:
        A dictionary of keys and functions. The function is applied to a value
        after it is fetched from the database and transformed according to the
        backend-specific rules.

    :describe outgoing_processors:
        A dictionary of keys and functions. The function is applied to a value
        before it is saved to the database. The backend-specific machinery
        works *after* the processor is called.

    """
    # what attributes can be updated/inherited using methods
    # inherit() and update()
    CUSTOMIZABLE = ('structure', 'validators', 'defaults', 'labels',
                    'skip_type_conversion',
                    'incoming_processors', 'outgoing_processors',
                    'set_item_processors', 'get_item_processors',
                    'referenced_by',
                    'break_on_invalid_incoming_data',
                    'label', 'label_plural')

    def __init__(self, name):
        # this is mainly for URLs and such stuff:
        self.lowercase_name = camel_case_to_underscores(name)

        self.label = None
        self.label_plural = None

        # create instance-level safe copies of default
        #self.update_from(**self.__class__.__dict__)
        self.structure = {}    # field name => data type
        self.validators = {}   # field name => list of validator instances
        self.defaults = {}     # field name => value (if callable, then called)
        self.labels = {}       # field name => string
        self.skip_type_conversion = [] # field name
        self.set_item_processors = {}  # field name => func (on __setitem__)
        self.get_item_processors = {}  # field name => func (on __getitem__)
        self.incoming_processors = {}  # field name => func (deserializer)
        self.outgoing_processors = {}  # field name => func (serializer)
        self.referenced_by = {}
        #use_dot_notation = True
        self.break_on_invalid_incoming_data = False

    def get_label(self):
        return self.label or self.lowercase_name.replace('_', ' ')

    def get_label_plural(self):
        return self.label_plural or self.get_label() + 's'

    def inherit(self, doc_classes):
        """
        Inherits metadata from given sequence of Document classes. Extends
        dictionaries, replaces values of other types.
        """
        for parent in doc_classes:
            self.update(parent.meta.__dict__)

    def update(self, data, **kwargs):
        """
        Updates attributes from given dictionary. Yields keys which values were
        accepted.
        """
        attrs = dict(data, **kwargs)
        updated = []
        for attr, value in attrs.iteritems():
            if attr in self.CUSTOMIZABLE:
                setattr(self, attr, copy.copy(value))
                updated.append(attr)
        return updated

class DocumentMetaclass(abc.ABCMeta):
    """
    Metaclass for all models.
    """
    def __new__(cls, name, bases, attrs):

        # inherit metadata from parent document classes
        # (all attributes are inherited automatically except for those we
        #  move to the metadata container in this method)
        #
        parents = [b for b in bases if isinstance(b, cls)]

        # move special attributes to the metadata container
        # (extend existing attrs if they were already inherited)
        meta = DocumentMetadata(name)

        # inherit
        meta.inherit(parents)

        # reassign/extend
        moved_attrs = meta.update(attrs)
        for attr in moved_attrs:
            attrs.pop(attr)

        # process Field instances (syntax sugar)
        for attr, value in attrs.items():
            if hasattr(value, 'contribute_to_document_metadata'):
                value.contribute_to_document_metadata(meta, attr)
                del attrs[attr]

#...whoops, even if we declare Document as subclass of object, still it will be
# a subclass of DotDict by default, so we cannot fall back to ProxyDict.
# it is only possible to add DotDict on top of ProxyDict but we want to keep
# dot notation active by default, right?
#
#        # by default we use getitem, i.e. book['title'], but user can also opt
#        # to use getattr, i.e. book.title to access document properties
#        print 'cls', cls, 'name', name
#        print 'bases:', bases
#        for base in bases:
#            print 'base', base, ('is' if isinstance(base,cls) else 'isnt'), 'subclass of', cls
#        if not any(isinstance(x, cls) for x in bases):
#            #bases = (DotDict,) + bases
#            dict_cls = DotDict if meta.use_dot_notation else ProxyDict
#            print 'dict class is', dict_cls, meta.use_dot_notation
#            bases = (dict_cls,) + bases
##            bases += (DotDict,)

        attrs['meta'] = meta

        return type.__new__(cls, name, bases, attrs)


class Document(ReprMixin, DotDict):
    """A document/query object. Dict-like representation of a document stored
    in a database. Includes schema declaration, bi-directional validation
    (outgoing and query), handles relations and has the notion of the saved
    state, i.e. knows the storage and primary key of the corresponding record.
    """
    __metaclass__ = DocumentMetaclass
    supports_nested_data = False

    #--------------------+
    #  Magic attributes  |
    #--------------------+

    def __eq__(self, other):
        if not other:
            return False
        if not hasattr(other, '_saved_state'):
            return False
        return self._saved_state == other._saved_state

    def __getitem__(self, key):
        value = self._data[key]

        if key in self.meta.get_item_processors:
            value = self.meta.get_item_processors[key](value)

        # handle references to other documents    # XXX add support for nested structure?
        ref_doc_class = _get_related_document_class(self, key)
        if ref_doc_class:
            value = _get_document_by_ref(self, key, value)

            # FIXME changes internal state!!! bad, bad, baaad
            # we need to cache the instances but keep PKs intact.
            # this will affect cloning but it's another story.
            self[key] = value

            return value
        else:
            # the DotDict stuff
            return super(Document, self).__getitem__(key)

    def __hash__(self):
        return hash(self._saved_state)

    def __init__(self, **kw):
        # NOTE: state must be filled from outside
        self._saved_state = DocumentSavedState()

        self._data = dict.fromkeys(self.meta.structure)  # None per default

        for key, value in kw.iteritems():
            # this will validate the values against structure (if any) and
            # custom validators; will raise KeyError or ValidationError
            try:
                self[key] = value
            except validators.ValidationError as e:
                if self.meta.break_on_invalid_incoming_data:
                    raise
                log.warn(e)

        # add backward relation descriptors to related classes
        for field in self.meta.structure:
            ref_doc = _get_related_document_class(self, field)
            if ref_doc:
                descriptor = BackwardRelation(self, field)
                rel_name = self.meta.lowercase_name + '_set'
                setattr(ref_doc, rel_name, descriptor)

    def __setattr__(self, name, value):
        # FIXME this is already implemented in DotDict but that method doesn't
        # call *our* __setitem__ and therefore misses validation
        if self.meta.structure and name in self.meta.structure:
            self[name] = value
        else:
            super(Document, self).__setattr__(name, value)

    def __setitem__(self, key, value):
        if self.meta.structure and key not in self.meta.structure:
            raise KeyError('Unknown field "{0}"'.format(key))

        if key in self.meta.set_item_processors:
            value = self.meta.set_item_processors[key](value)

        _validate_value(self, key, value)  # will raise ValidationError if wrong
        super(Document, self).__setitem__(key, value)

    def __unicode__(self):
        return repr(self._data)

    #---------------------+
    #  Public attributes  |
    #---------------------+

    @classmethod
    def objects(cls, storage):
        import warnings
        warnings.warn('Document.objects(db) is deprecated, use '
                      'db.find(Document) instead', DeprecationWarning)
        return storage.find(cls)

    # XXX validation-related, move to a mixin within doqu.validation?
    @classmethod
    def contribute_to_query(cls, query):
        """Returns given query filtered by schema and validators defined for
        this document.
        """
        # use validators to filter the results to only yield records that
        # belong to this schema
        for name, validators in cls.meta.validators.iteritems():
            for validator in validators:
                if hasattr(validator, 'filter_query'):
                    query = validator.filter_query(query, name)

        #logging.debug(query._query._conditions)

        return query

    @classmethod
    def from_storage(cls, storage, key, data):
        """
        Returns a document instance filled with given `data` and bound to given
        `storage` and `key`. The instance can be safely saved back using
        :meth:`save`. If the concrete subclass defines the structure, then
        usused fields coming from the storage are hidden from the public API
        but nevertheless they will be saved back to the database as is.
        """
        if cls.meta.structure:
            pythonized_data = {}

            # NOTE: nested definitions are not supported here.
            for name, type_ in cls.meta.structure.iteritems():
                value = data.get(name, None)
                try:
                    # symmetric with doqu.document_base.Document.save
                    if not name in cls.meta.skip_type_conversion:
                        value = storage.value_from_db(type_, value)
                    if name in cls.meta.incoming_processors:
                        if value is not None:
                            processor = cls.meta.incoming_processors[name]
                            value = processor(value)
                except ValueError as e:
                    log.warn('could not convert %s.%s (primary key %s): %s'
                             % (cls.__name__, name, repr(key), e))
                    # If incoming value could not be converted to desired data
                    # type, it is left as is (and will cause invalidation of the
                    # model on save). However, user can choose to raise ValueError
                    # immediately when such broken record it retrieved:
                    if cls.meta.break_on_invalid_incoming_data:
                        raise
                pythonized_data[name] = value
        else:
            # if the structure is unknown, just populate the document as is.
            # copy.deepcopy is safer than dict.copy but more than 10× slower.
            pythonized_data = data.copy()

        instance = cls(**pythonized_data)
        instance._saved_state.update(storage=storage, key=key, data=data)
        return instance

    @property
    def pk(self):
        """
        Returns current primary key (if any) or None.
        """
        return self._saved_state.key

    def save(self, storage=None, keep_key=False):   #, sync=True):
        """
        Saves instance to given storage.

        :param storage:
            the storage to which the document should be saved. If not
            specified, default storage is used (the one from which the document
            was retrieved of to which it this instance was saved before).
        :param keep_key:
            if `True`, the primary key is preserved even when saving to another
            storage. This is potentially dangerous because existing unrelated
            records can be overwritten. You will only *need* this when copying
            a set of records that reference each other by primary key. Default
            is `False`.

        """

        # XXX what to do with related (referenced) docs when saving to another
        # database?

        if not storage and not self._saved_state.storage:
            raise AttributeError('cannot save model instance: storage is not '
                                 'defined neither in instance nor as argument '
                                 'for the save() method')

        if storage:
            assert hasattr(storage, 'save'), (
                'Storage %s does not define method save(). Storage must conform '
                'to the Doqu backend API.' % storage)
#            # XXX this should have been at the very end
#            self._saved_state.update(storage=storage)
        else:
            storage = self._saved_state.storage

        # fill defaults before validation
        for key, value in _collect_defaults(self):
            self[key] = value

        self.validate()    # will raise ValidationError if something is wrong

        # Dictionary self._data only keeps known properties. The database
        # record may contain other data. The original data is kept in the
        # dictionary self._saved_state.data. Now we copy the original record, update
        # its known properties and try to save that:

        data = self._saved_state.data.copy() if self._saved_state.data else {}

        # prepare (validate) properties defined in the model
        # XXX only flat structure is currently supported:
        if self.meta.structure:
            pairs = ((x, self._data.get(x)) for x in self.meta.structure)
        else:
            pairs = self._data.items()

        for name, value in pairs:
            # symmetric with docu.backend_base.BaseStorageAdapter._decorate
            if name in self.meta.outgoing_processors and value is not None:
                processor = self.meta.outgoing_processors[name]
                value = processor(value)

            if name in self.meta.skip_type_conversion:
                data[name] = value
            else:
                data[name] = storage.value_to_db(value)

        # TODO: make sure we don't overwrite any attrs that could be added to this
        # document meanwhile. The chances are rather high because the same document
        # can be represented as different model instances at the same time (i.e.
        # Person, User, etc.). We should probably fetch the data and update only
        # attributes that make sense for the model being saved. The storage must
        # not know these details as it deals with whole documents, not schemata.
        # This introduces a significant overhead (roughly ×2 on Tyrant) and user
        # should be able switch it off by "granular=False" (or "full_data=True",
        # or "per_property=False", or whatever).

        # primary key must *not* be preserved if saving to another storage
        # (unless explicitly told so)
        if keep_key or storage == self._saved_state.storage:
            primary_key = self.pk
        else:
            primary_key = None
        # let the storage backend prepare data and save it to the actual storage
        key = storage.save(
            key = primary_key,
            data = data,
            #doc_class = type(self),
        )
        assert key, 'storage must return primary key of saved item'
        # okay, update our internal representation of the record with what have
        # been just successfully saved to the database
        self._saved_state.update(key=key, storage=storage, data=data)
        # ...and return the key, yep
        assert key == self.pk    # TODO: move this to tests
        return key

    def delete(self):
        """
        Deletes the object from the associated storage.
        """
        if not self._saved_state.storage or not self._saved_state.key:
            raise ValueError('Cannot delete object: not associated with '
                             'a storage and/or primary key is not defined.')
        self._saved_state.storage.delete(self._saved_state.key)

    def validate(self):
        """
        Checks if instance data is valid. This involves a) checking whether all
        values correspond to the declated structure, and b) running all
        :doc:`validators` against the data dictionary.

        Raises :class:`~doqu.validators.ValidationError` if something is wrong.

        .. note::

            if the data dictionary does not contain some items determined by
            structure or validators, these items are *not* checked.

        .. note::

            The document is checked as is. There are no side effects. That is,
            if some required values are empty, they will be considered invalid
            even if default values are defined for them. The
            :meth:`~Document.save` method, however, fills in the default values
            before validating.

        """
        for key, value in self.iteritems():
            _validate_value(self, key, value)


class OneToManyRelation(object):
    """
    Wrapper for document classes in reference context. Basically just tells
    that the reference is not one-to-one but one-to-many. Usage::

        class Book(Document):
            title = Field(unicode)

        class Author(Document):
            name = Field(unicode)
            books = Field(Many(Book))

    In the example above the field `books` is interpreted as a list of primary
    keys. It is not a query, it's just a list. When the attribute is accessed,
    all related documents are dereferenced, i.e. fetched by primary key.
    """
    def __init__(self, document_class):
        self.document_class = document_class

Many = OneToManyRelation


# TODO: replace this with simple getitem filter + cache + registering
# "referenced_by" as it's already done in prev. versions (but not DRY there)
class BackwardRelation(object):
    """
    Prepares and returns a query on objects that reference given instance by
    given attribute. Basic usage::

        class Author(Model):
            name = Property()

        class Book(Model):
            name = Property()
            author = Reference(Author, related_name='books')

        john = Author(name='John Doe')
        book_one = Book(name='first book', author=john)
        book_two = Book(name='second book', author=john)

        # (...save them all...)

        print john.books   # -->   [<Book object>, <Book object>]

    """
    def __init__(self, related_model, attr_name):
        self.cache = {}
        self.related_model = related_model
        self.attr_name = attr_name

    def __get__(self, instance, owner):
        if not instance._saved_state.storage:
            raise ValueError(u'cannot fetch referencing objects for model'
                             ' instance which does not define a storage')

        if not instance.pk:
            raise ValueError(u'cannot search referencing objects for model'
                             ' instance which does not have primary key')

        query = self.related_model.objects(instance._saved_state.storage)
        return query.where(**{self.attr_name: instance.pk})

    def __set__(self, instance, new_references):
        # TODO: 1. remove all existing references, 2. set new ones.
        # (there may be validation issues)
        raise NotImplementedError('sorry')

#------------------------------+
#  Document-related functions  |
#------------------------------+

def _collect_defaults(doc):
    """
    Returns pairs of keys and respective default values if needed (i.e. if
    current value is empty).  Example::

        class Foo(Document):
            defaults = {
                # a value (non-callable)
                'text': 'no text provided',
                # a callable value but not a function, no args passed
                'date': datetime.date.today,  # not a simple function
                # a simple function, document instance passed as arg
                'slug': lambda doc: doc.text[:20].replace(' ','')
            }
            use_dot_notation = True

    The "simple function" is any instance of `types.FunctionType` including
    one created with ``def`` or with ``lambda``. Such functions will get a
    single argument: the document instance. All other callable objects are
    called without arguments. This may sound a bit confusing but it's not.
    """
    for name in doc.meta.defaults:
        current_value = doc.get(name)
        if current_value is None or current_value == '':
            value = doc.meta.defaults[name]
            if hasattr(value, '__call__'):
                if isinstance(value, types.FunctionType):
                    # functions are called with instance as argment, e.g.:
                    #   defaults = {'slug': lambda d: d.text.replace(' ','')
                    value = value(doc)
                else:
                    # methods, etc. are called without arguments, e.g.:
                    #   defaults = {'date': datetime.date.today}
                    value = value()
            yield name, value

def _get_document_by_ref(doc, field, value):
    if not value:
        return value

    # XXX needs refactoring:
    # cls._get_related_document_class is also called in __getitem__.
    document_class = _get_related_document_class(doc, field)
    if not document_class:
        return value

    def _resolve(ref, document_class):
        if isinstance(ref, Document):
            assert isinstance(ref, document_class), (
                'Expected {expected} instance, got {cls}'.format(
                    expected=document_class.__name__,
                    cls=ref.__class__.__name__))
            return ref
        if not doc._saved_state:
            raise RuntimeError(
                'Cannot resolve lazy reference {cls}.{name} {value} to'
                ' {ref}: storage is not defined'.format(
                cls=doc.__class__.__name__, name=key,
                value=repr(ref), ref=document_class.__name__))
        # retrieve the record and replace the PK in the data dictionary
        return doc._saved_state.storage.get(document_class, ref)

    datatype = doc.meta.structure.get(field)
    if isinstance(datatype, OneToManyRelation):
        # one-to-many (list of primary keys)
        assert isinstance(value, list)
        # NOTE: list is re-created; may be undesirable
        return [_resolve(v, document_class) for v in value]
    else:
        # "foreign key" (plain single reference)
        return _resolve(value, document_class)

def _get_related_document_class(cls, field):
    """
    Returns the relevant document class for given `field` depending on the
    declared document structure. (Field = property = column.)

    If the declared data type is a :class:`Document` subclass, it is
    returned. If the data type is a string, it is interpreted as a lazy
    import path (e.g. `myapp.models.Foo` or `cls`). If the import fails,
    `ImportError` is raised.  If the data type is unrelated, `None` is
    returned.
    """
    if not cls.meta.structure or not field in cls.meta.structure:
        return

    datatype = cls.meta.structure.get(field)

    # model class
    if issubclass(datatype, Document):
        return datatype

    if isinstance(datatype, OneToManyRelation):
        return datatype.document_class

    # dotted path to the model class (lazy import)
    if isinstance(datatype, basestring):
        return _resolve_model_path(datatype)

def _resolve_model_path(cls, path):
    # XXX make better docstring. For now see _get_related_document_class.
    if path == RECURSIVE_RELATION_NAME:
        return cls
    if '.' in path:
        module_path, attr_name = path.rsplit('.', 1)
    else:
        module_path, attr_name = cls.__module__, path
    module = __import__(module_path, globals(), locals(), [attr_name], -1)
    return getattr(module, attr_name)

def _validate_value(doc, key, value):
    # note: we intentionally provide the value instead of leaving the
    # method get it by key because the method is used to check both
    # existing values and values *to be set* (pre-check).
    _validate_value_type(doc, key, value)
    _validate_value_custom(doc, key, value)

def _validate_value_custom(doc, key, value):
    tests = doc.meta.validators.get(key, [])
    for test in tests:
        try:
            test(doc, value)
        except validators.StopValidation:
            break
        except validators.ValidationError:
            # XXX should preserve call stack and add sensible message
            msg = 'Value {value!r} is invalid for {cls}.{field} ({test})'
            raise validators.ValidationError(msg.format(
                value=value, cls=type(doc).__name__,
                field=key, test=test))

def _validate_value_type(cls, key, value):
    if value is None:
        return

    datatype = cls.meta.structure.get(key)

    if not datatype:
        return

    if isinstance(datatype, basestring):
        # A text reference, i.e. "cls" or document class name.
        return

    if issubclass(datatype, Document) and isinstance(value, basestring):
        # A class reference; value is the PK, not the document object.
        # This is a normal situation when a document instance is being
        # created from a database record. The reference will be resolved
        # later on __getitem__ call. We just skip it for now.
        return

    if isinstance(datatype, OneToManyRelation):
        if not hasattr(value, '__iter__'):
            msg = u'{cls}.{field}: expected list of documents, got {value}'
            raise validators.ValidationError(msg.format(
                cls=type(cls).__name__, field=key, value=repr(value)))
        return

    if datatype and not isinstance(value, datatype):
        msg = u'{cls}.{field}: expected a {datatype} instance, got {value}'
        raise validators.ValidationError(msg.format(
            cls=type(cls).__name__, field=key, datatype=datatype.__name__,
            value=repr(value)))
