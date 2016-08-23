"""
Generates a Java class that can map an Android device model String to a
user friendly String.
"""

__author__ = 'tslamic'
__license__ = 'Apache 2.0'
__version__ = '0.0.1'

from datetime import datetime
import string
import time
import os
import re

try:
    import requests
except ImportError:
    requests = None  # Downloading disabled.

VALID_MODEL_REGEX = re.compile(r'^[a-zA-Z0-9-_+\.\s]+$')
VALID_NAME_REGEX = re.compile(r'^[a-zA-Z0-9-_+/\.\s\(\)]+$')

JAVA_PARAM_MODEL = 'model'
JAVA_TEMPLATE = 'templates/java.template'
JAVA_LETTER_TEMPLATE = 'templates/java_letter.template'
JAVA_CLASS_NAME = 'DeviceNames.java'

JAVA_TEST_TEMPLATE = 'templates/test.template'
JAVA_TEST_CASE_TEMPLATE = 'templates/test_case.template'
JAVA_TEST_CLASS_NAME = 'DeviceNamesTest.java'

JAVA_IF = 'if ("%s".equals(%s)) { return "%s"; }\n'
JAVA_ELSE_IF = '        else ' + JAVA_IF

JAVA_CASE = "            case '%s':\n"
JAVA_FUNCTION = "                deviceName = %sMethod(model);\n"
JAVA_BREAK = '                break;\n'
JAVA_RETURN = '        return "";\n'
JAVA_DEFAULT_CASE = '                default:\n'


def generate_java_class(sources, collision_handler=None):
    """
    Generates a mapping Java class.

    :param sources: a list of Source objects.
    :param collision_handler: (optional) a function for resolving duplicate
    entries, e.g.:
    lambda model, old_name, new_name: raise Exception("collision")
    """
    merged = merge_source_dicts(sources, collision_handler)

    if not merged:
        raise Exception('sources contain no model-name pairs')

    switch_statement = generate_switch_statement()
    assert switch_statement

    letter_functions = generate_letter_functions(merged)
    assert letter_functions

    with open(JAVA_TEMPLATE, 'rb') as template:
        class_template = template.read()

    content = string.Template(class_template).substitute(
        datetime=datetime.now().strftime('%d %b %Y %H:%M:%S'),
        version=__version__,
        count=len(merged),
        devices=switch_statement,
        device_methods=letter_functions)

    with open(JAVA_CLASS_NAME, 'wb') as java_class:
        java_class.write(content)

    generate_java_test_class(merged)


def generate_java_test_class(merged_dict):
    """
    Generates a mapping Java test class.

    :param merged_dict: a model:name dict with unique entries
    """
    with open(JAVA_TEST_CASE_TEMPLATE, 'rb') as template:
        test_case_template = template.read()
    test_cases = []
    test_case_id = 0
    for model, name in merged_dict.iteritems():
        test_case_id += 1  # Used for the test case method name
        test = string.Template(test_case_template).substitute(
            method=test_case_id,
            model=model,
            name=name
        )
        test_cases.append(test)
    assert test_cases

    with open(JAVA_TEST_TEMPLATE, 'rb') as template:
        class_template = template.read()

    tests = string.Template(class_template).substitute(
        tests=''.join(test_cases)
    )

    with open(JAVA_TEST_CLASS_NAME, 'wb') as java_test_class:
        java_test_class.write(tests)


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


def generate_letter_functions(merged_dict):
    """
    Generates a java method for each letter to make sure each method
    is below the 64K java limit.  e.g.

        private static String $letterMethod(String model) {
            // models starting with letter $letter
            $letter_devices
        }

    :param merged_dict: a model:name dict with unique entries
    """
    with open(JAVA_LETTER_TEMPLATE, 'rb') as letter_template:
        class_letter_template = letter_template.read()

    alphabet_dict = {letter: [] for letter in string.ascii_uppercase}
    others = []  # For models not starting with an alphabet letter.
    for model, name in merged_dict.iteritems():
        letter = model[0].upper()  # Use the first letter for branching.
        alphabet_dict.get(letter, others).append((model, name))

    statement = []
    for letter, pairs in alphabet_dict.iteritems():
        template_copy = class_letter_template
        content = string.Template(template_copy).substitute({
                    "letter_method": "%sMethod" % letter.lower(),
                    "letter_devices": generate_ifs(pairs)})
        statement.append(content)

    template_copy = class_letter_template
    content = string.Template(template_copy).substitute({
                "letter_method": "otherMethod",
                "letter_devices": generate_ifs(others)})
    statement.append(content)

    return ''.join(statement)


def generate_switch_statement():
    """
    Generates a java switch statement where cases are based on the first
    model letter, e.g.:
        case 'A':
            aMethod(model);
            break;
        case 'B':
            bMethod(model);
            break;
        case 'C':
            // etc.

    """
    statement = []
    alphabet_list = list(string.ascii_uppercase)
    for letter in alphabet_list:
        statement.append(JAVA_CASE % letter)
        statement.append(JAVA_FUNCTION % letter.lower())
        statement.append(JAVA_BREAK)
    statement.append(JAVA_DEFAULT_CASE)
    statement.append(JAVA_FUNCTION % "other")
    return ''.join(statement)


def generate_ifs(pairs):
    """
    Generates the if - elseif block from given pairs, e.g.:
        if ("model_name".equals(model)) { return "model_name"; }
        else if ("model_name".equals(model)) { return "model_name"; }

    :param pairs: a list of (model, name) tuples
    :return: the generated if else block
    """
    block = []
    if pairs:
        # Generates the first if
        model, name = pairs[0]
        java_if = JAVA_IF % (model, JAVA_PARAM_MODEL, name)
        block.append("%s" % java_if)
        del pairs[0]
        # Generates a bunch of else-ifs
        for pair in pairs:
            model, name = pair
            java_else_if = JAVA_ELSE_IF % (model, JAVA_PARAM_MODEL, name)
            block.append("%s" % java_else_if)
    block.append(JAVA_RETURN)
    return ''.join(block)


class Source(object):
    def get_dict(self, collision_handler=None):
        """
        Returns a dictionary where keys are device models and values are
        user-friendly name, e.g.: "GT-I9500" : "Samsung Galaxy S4"
        """
        raise NotImplementedError('implementation missing')


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
        raise Exception('url not specified')
    with open(target, 'wb') as t:
        response = requests.get(url, stream=True)
        if not response.ok:
            raise Exception('download failed')
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
        try:
            model, name = device_handler(device)
        except Exception as e:
            print e
            continue
        if model in content_dict:
            name = collision_handler(model, content_dict[model], name)
        content_dict[model] = name
    return content_dict


def exception_collision_handler(model, old, new):
    raise Exception("multiple names for '%s': '%s', '%s'" % (model, old, new))


# Sources

class MeetupSource(Source):
    """ Meetup Github source. """

    source_file = 'meetup.devices'
    source_url = 'https://raw.githubusercontent.com/meetup/android-device' \
                 '-names/master/android_models.properties'

    def get_dict(self, collision_handler=exception_collision_handler):
        if is_stale(self.source_file, ONE_WEEK):
            download_device_list(self.source_url, self.source_file)
        return create_content_dict(self.source_file, self.device_handler,
                                   collision_handler)

    @staticmethod
    def device_handler(device_line):
        model, name = (d.strip() for d in device_line.split('='))
        if not name:
            name = model.replace('_', ' ')
        return model, name


class CachedSource(Source):
    """ Local source, see cached.devices file. """

    def get_dict(self, collision_handler=None):
        return create_content_dict('devices/cached.devices',
                                   self.device_handler, collision_handler)

    @staticmethod
    def device_handler(device_line):
        model, name = (d.strip() for d in device_line.split('='))
        if not name:
            name = model.replace('_', ' ')
        if not re.match(VALID_MODEL_REGEX, model):
            raise Exception("invalid model: '%s'" % model)
        if not re.match(VALID_NAME_REGEX, name):
            raise Exception("invalid name: '%s'" % name)
        return model, name

# Main

if __name__ == '__main__':
    generate_java_class((CachedSource(),),
                        collision_handler=exception_collision_handler)
