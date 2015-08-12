"""
Generates a simple Java class that can map an Android device model String to a
user friendly String.
"""

__version__ = '0.0.1'

from string import Template
from datetime import datetime
import time
import os
import re

try:
    import requests
except ImportError:
    requests = None  # Downloading disabled.

VALID_MODEL_REGEX = re.compile("^\S+$")
VALID_NAME_REGEX = re.compile("^[a-zA-Z0-9-+\.\s]+$")

JAVA_ELSE_IF = 'else if ("%s".equals(%s)) { return "%s"; }\n'
JAVA_ELSE = 'else { return %s; }'
JAVA_PARAM_MODEL = "model"
JAVA_PARAM_FALLBACK = "fallback"
JAVA_TEMPLATE = "java.template"
JAVA_CLASS_NAME = "DeviceNames.java"


def generate_java_class(sources, collision_handler=None):
    """
    Generates the Java class.

    :param sources: a list of Source objects.
    :param collision_handler: (optional) a function for resolving duplicate
    entries, e.g.:
    lambda model, old_name, new_name: raise Exception("collision")
    """
    merged = merge_source_dicts(sources, collision_handler)
    if not merged:
        raise Exception("sources contain no model-name pairs")
    content = []
    for model, name in merged.iteritems():
        java_statement = JAVA_ELSE_IF % (model, JAVA_PARAM_MODEL, name)
        content.append(java_statement)
    content.append(JAVA_ELSE % JAVA_PARAM_FALLBACK)
    with open(JAVA_TEMPLATE, 'rb') as template:
        class_template = template.read()
    content = Template(class_template).substitute(
        datetime=datetime.now().strftime('%d %b %Y %H:%M:%S'),
        version=__version__,
        devices=''.join(content))
    with open(JAVA_CLASS_NAME, 'wb') as java_class:
        java_class.write(content)


def merge_source_dicts(sources, collision_handler=None):
    """
    Merges multiple source dicts into a single dict and returns it.

    :param sources: a list of Source objects.
    :param collision_handler: (optional) a function for resolving duplicate
    entries, e.g.:
    lambda model, old_name, new_name: raise Exception("collision")
    """
    merged = {}
    for source in sources:
        source_dict = source.get_dict(collision_handler)
        for model, name in source_dict.iteritems():
            if collision_handler is not None and model in merged:
                name = collision_handler(model, merged[model], name)
            merged[model] = name
    return merged


class Source(object):
    def get_dict(self, collision_handler=None):
        """
        Returns a dictionary where keys are device models and values are
        user-friendly name, e.g.: "GT-I9500" : "Samsung Galaxy S4"
        """
        raise NotImplementedError("implementation missing")


# Utils

def download_device_list(url, target, chunk=2048):
    """
    Downloads a file containing device information.

    :param url: the device list location
    :param target: the file path where device list will be saved
    """
    if requests is None:
        raise Exception("'requests' lib missing")
    if not url:
        raise Exception("url not specified")
    with open(target, 'wb') as t:
        response = requests.get(url, stream=True)
        if not response.ok:
            raise Exception("download failed")
        for block in response.iter_content(chunk):
            t.write(block)


ONE_WEEK = 604800  # in seconds.


def is_stale(target, freshness_interval):
    """
    Determines if a device list is stale.

    :param target: the file path to be checked
    :param freshness_interval: elapsed seconds the target is considered fresh
    :return: True if device list should be refreshed, False otherwise
    """
    if os.path.exists(target):
        last_modified = os.path.getmtime(target)
        return time.time() - last_modified > freshness_interval
    return True


def create_content_dict(target, device_handler, collision_handler):
    """
    Reads the target file and creates a "device": "name" dict.

    :param target: the file path source
    :param device_handler: a function transforming a line to (device,
    name) tuple, e.g.:
        lambda line: line.split("=")
    :param collision_handler: (optional) a function for resolving duplicate
    entries, e.g.:
        lambda model, old_name, new_name: raise Exception("collision")
    """
    with open(target, 'rb') as device_list:
        devices = device_list.readlines()
    content_dict = {}
    for device in devices:
        model, name = device_handler(device)
        if model in content_dict:
            name = collision_handler(model, content_dict[model], name)
        content_dict[model] = name
    return content_dict


def exception_collision_handler(model, old, new):
    raise Exception("multiple names for '%s': '%s', '%s'" % (model, old, new))


# Sources

class MeetupSource(Source):
    """ Meetup Github source. """

    source_file = "meetup.devices"
    source_url = "https://raw.githubusercontent.com/meetup/android-device" \
                 "-names/master/android_models.properties"

    def get_dict(self, collision_handler=exception_collision_handler):
        if is_stale(self.source_file, ONE_WEEK):
            download_device_list(self.source_url, self.source_file)
        return create_content_dict(self.source_file, self.device_handler,
                                   collision_handler)

    @staticmethod
    def device_handler(device_line):
        model, name = (d.strip() for d in device_line.split('='))
        if not name:
            name = model.replace("_", " ")
        return model, name


class CachedSource(Source):
    """ Local source, see cached.devices file. """

    def get_dict(self, collision_handler=None):
        return create_content_dict('cached.devices', self.device_handler,
                                   collision_handler)

    @staticmethod
    def device_handler(device_line):
        model, name = (d.strip() for d in device_line.split('='))
        if not name:
            name = model.replace("_", " ")
        if not re.match(VALID_MODEL_REGEX, model):
            raise Exception("invalid model: %s" % model)
        if not re.match(VALID_NAME_REGEX, name):
            raise Exception("invalid name: %s" % name)
        return model, name

# Main

if __name__ == "__main__":
    source_list = [CachedSource(), ]
    generate_java_class(source_list,
                        collision_handler=exception_collision_handler)