# -*- encoding: utf-8 -*-

import psycopg2
import re

from django.db import models
from django.utils.text import capfirst
from django.utils.translation import ugettext_lazy as _

from datetime import timedelta
from dateutil.relativedelta import relativedelta

from interval.forms import IntervalFormField

day_seconds = 24 * 60 * 60
microseconds = 1000000

from lib.time_24_hour import time24hour

from south.modelsinspector import add_introspection_rules

months_re = re.compile('(\d+) months?')
days_re = re.compile('(\d+) days?')
hms_re = re.compile('(\d\d:\d\d:\d\d)')


def cast_interval(value, cur):
    """
    Convert PostgreSQL string <value> to Python relativedelta.
    """
    ret = relativedelta()

    if not value:
        return ret

    for month in months_re.findall(value):
        ret.months += int(month)

    for day in days_re.findall(value):
        ret.days += int(day)

    for hms in hms_re.findall(value):
        h, m, s = hms.split(':')
        ret.hours += int(h)
        ret.minutes += int(m)
        ret.seconds += int(s)

    return ret

interval_oid = 1186  # interval column OID
interval_type = psycopg2.extensions.new_type(
    (interval_oid,), 'interval', cast_interval)
psycopg2.extensions.register_type(interval_type)



def formatError(value):
    raise ValueError(
        "please use [[DD]D days,]HH:MM:SS[.ms] instead of %r" % value)


def relativedelta_topgsqlstring(value):
    buf = []
    for attr in ['months', 'days', 'seconds', 'microseconds']:
        v = getattr(value, attr)
        if v:
            buf.append('%i %s' % (v, attr.upper()))
    if not buf:
        return '0'
    return " ".join(buf)


def relativedelta_tobigint(value):
    return (
        value.days * day_seconds * microseconds
        + value.seconds * microseconds
        + value.microseconds
        )


def range_check(value, name, min=None, max=None):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError("%s is not an integer" % value)

    if min is not None:
        if value < min:
            raise ValueError("%s is less than %s" % (value, min))

    if max is not None:
        if value > max:
            raise ValueError("%s is more than %s" % (value, max))

    return value


class IntervalField(models.Field):
    """This is a field, which maps to Python's dateutil.relativedelta

    For PostgreSQL, its type is INTERVAL - a native interval type.
    - http://www.postgresql.org/docs/8.4/static/datatype-datetime.html

    For other databases, its type is BIGINT and relativedelta value is stored
    as number of seconds * 1000000 .
    """

    __metaclass__ = models.SubfieldBase

    description = _("interval")

    def __init__(
        self, verbose_name=None, min_value=None, max_value=None, format=None,
        *args, **kw):

        models.Field.__init__(
            self, verbose_name=verbose_name, *args, **kw)

        self.min_value = min_value
        self.max_value = max_value
        self.format = format

        if self.min_value is not None and self.max_value is not None:
            if self.min_value >= self.max_value:
                raise ValueError('min_value >= max_value')

    def db_type(self, connection):
        if connection.settings_dict['ENGINE'].find('postgresql') >= 0 or \
                connection.settings_dict['ENGINE'].find('postgis') >= 0:
            return 'INTERVAL'
        return 'BIGINT'

    def to_python(self, value):
        if isinstance(value, relativedelta):
            # psycopg2 will return a relativedelta() for INTERVAL type column
            # in database
            return value
        if isinstance(value, timedelta):
            return relativedelta(seconds=value.total_seconds())

        if value is None or value is '' or value is u'':
            return None

        # string forms: in form like "X days, HH:MM:SS.ms" (can be used in
        # fixture files)
        if isinstance(value, basestring) and value.find(":") >= 0:
            days = 0

            if value.find("days,") >= 0 or value.find("day,") >= 0:
                if value.find("days,") >= 0:
                    days, value = value.split("days,")
                else:
                    days, value = value.split("day,")
                value = value.strip()
                try:
                    days = int(days.strip())
                except ValueError:
                    formatError(value)

                days = range_check(days, "days", 0)

            try:
                h, m, s = value.split(":")
            except ValueError:
                formatError(value)

            h = range_check(h, "hours", 0)
            m = range_check(m, "minutes", 0, 59)

            if s.find(".") >= 0:
                s, ms = s.split(".")
            else:
                ms = "0"

            s = range_check(s, "seconds", 0, 59)

            l = len(ms)
            ms = range_check(ms, "microseconds", 0, microseconds)
            ms = ms * (microseconds / (10 ** l))

            return relativedelta(
                days=days, hours=h, minutes=m,
                seconds=s, microseconds=ms)

        # other database backends:
        return relativedelta(seconds=float(value) / microseconds)

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None or value is '':
            return None

        if connection.settings_dict['ENGINE'].find('postgresql') >= 0 or \
                connection.settings_dict['ENGINE'].find('postgis') >= 0:
            if isinstance(value, basestring):
                # Can happen, when using south migrations
                return value
            return relativedelta_topgsqlstring(value)

        return relativedelta_tobigint(value)

    def formfield(self, form_class=IntervalFormField, **kwargs):
        defaults = {'min_value': self.min_value,
                    'max_value': self.max_value,
                    'format': self.format or 'DHMS',
                    'required': not self.blank,
                    'label': capfirst(self.verbose_name),
                    'help_text': self.help_text}

        if self.has_default():
            defaults['initial'] = self.default

        defaults.update(kwargs)
        return form_class(**defaults)


try:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules([], ["^interval\.fields\.IntervalField"])
except ImportError:
    pass
