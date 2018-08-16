#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import errno
import os
import plistlib
import uuid
import subprocess

# Imports specifically for FoundationPlist
# PyLint cannot properly find names inside Cocoa libraries, so issues bogus
# No name 'Foo' in module 'Bar' warnings. Disable them.
# pylint: disable=E0611
from Foundation import NSData  # NOQA
from Foundation import NSPropertyListSerialization  # NOQA
from Foundation import NSPropertyListMutableContainers  # NOQA
from Foundation import NSPropertyListXMLFormat_v1_0  # NOQA
# pylint: enable=E0611


# Special thanks to the munki crew for the plist work.
# FoundationPlist from munki
class FoundationPlistException(Exception):
    """Basic exception for plist errors"""
    pass


class NSPropertyListSerializationException(FoundationPlistException):
    """Read/parse error for plists"""
    pass


def readPlist(filepath):
    """
    Read a .plist file from filepath.  Return the unpacked root object
    (which is usually a dictionary).
    """
    plistData = NSData.dataWithContentsOfFile_(filepath)
    dataObject, dummy_plistFormat, error = (
        NSPropertyListSerialization.
        propertyListFromData_mutabilityOption_format_errorDescription_(
            plistData, NSPropertyListMutableContainers, None, None))
    if dataObject is None:
        if error:
            error = error.encode('ascii', 'ignore')
        else:
            error = "Unknown error"
        errmsg = "%s in file %s" % (error, filepath)
        raise NSPropertyListSerializationException(errmsg)
    else:
        return dataObject


def readPlistFromString(data):
    '''Read a plist data from a string. Return the root object.'''
    try:
        plistData = buffer(data)
    except TypeError, err:
        raise NSPropertyListSerializationException(err)
    dataObject, dummy_plistFormat, error = (
        NSPropertyListSerialization.
        propertyListFromData_mutabilityOption_format_errorDescription_(
            plistData, NSPropertyListMutableContainers, None, None))
    if dataObject is None:
        if error:
            error = error.encode('ascii', 'ignore')
        else:
            error = "Unknown error"
        raise NSPropertyListSerializationException(error)
    else:
        return dataObject


class PrivacyProfiles():
    def __init__(self, payload_description, payload_name, payload_identifier, payload_organization, payload_version, profile_filename):
        # Init the things to put in the template, and elsewhere
        self.payload_description = payload_description
        self.payload_name = payload_name
        self.payload_identifier = payload_identifier
        self.payload_organization = payload_organization
        self.payload_type = 'com.apple.TCC.configuration-profile-policy'
        self.payload_uuid = str(uuid.uuid1()).upper()  # This is used in the 'PayloadContent' part of the profile
        self.profile_uuid = str(uuid.uuid1()).upper()  # This is used in the root of the profile
        self.payload_version = payload_version
        self.profile_filename = os.path.expandvars(os.path.expanduser(profile_filename))

        if not os.path.splitext(self.profile_filename)[1] == '.mobileconfig':
            self.profile_filename = self.profile_filename.replace(os.path.splitext(self.profile_filename)[1], '.mobileconfig')

        self.template = {
            'PayloadContent': [
                {
                    'PayloadDescription': self.payload_description,
                    'PayloadDisplayName': self.payload_name,
                    'PayloadIdentifier': '{}.{}'.format(self.payload_identifier, self.payload_uuid),  # This needs to be different to the root 'PayloadIdentifier'
                    'PayloadVersion': self.payload_version,
                    'Services': []  # This will be an empty list to house the dicts.
                }
            ],
            'PayloadDescription': self.payload_description,
            'PayloadDisplayName': self.payload_name,
            'PayloadIdentifier': self.payload_identifier,
            'PayloadOrganization': self.payload_organization,
            'PayloadScope': 'system',  # What's the point in making this a user profile?
            'PayloadType': 'Configuration',
            'PayloadUUID': self.profile_uuid,
            'PayloadVersion': self.payload_version,
        }

    def getCodeSignRequirements(self, path):
        if os.path.exists(path.rstrip('/')):
            cmd = ['/usr/bin/codesign', '-dr', '-', path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result, error = process.communicate()

            if process.returncode is 0:
                # For some reason, part of the output gets dumped to stderr, but the bit we need goes to stdout
                if result.startswith('designated => '):
                    return result.replace('designated => ', '').replace('"', '&quot;').strip('\n')
        else:
            raise OSError.FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    def accessibilityPayload(self, app_path, allowed, code_requirement, comment):
        if type(allowed) is bool and type(code_requirement) is str:
            try:
                identifier = readPlist(os.path.join(app_path.rstrip('/'), 'Contents/Info.plist'))['CFBundleIdentifier']
                identifier_type = 'bundleID'
            except:
                identifier = app_path.rstrip('/')
                identifier_type = 'path'

            # Only return a basic dict, even though the Services needs a dict supplied, and the 'Accessibility' "payload" is a list of dicts.
            return {
                'Allowed': allowed,
                'CodeRequirement': code_requirement,
                'Comment': comment,
                'Identifier': identifier,
                'IdentifierType': identifier_type,
            }


def main():
    class SaneUsageFormat(argparse.HelpFormatter):
        '''Makes the help output somewhat more sane. Code used was from Matt Wilkie.'''
        '''http://stackoverflow.com/questions/9642692/argparse-help-without-duplicate-allcaps/9643162#9643162'''

        def _format_action_invocation(self, action):
            if not action.option_strings:
                default = self._get_default_metavar_for_positional(action)
                metavar, = self._metavar_formatter(action, default)(1)
                return metavar
            else:
                parts = []
                # if the Optional doesn't take a value, format is:
                #    -s, --long
                if action.nargs == 0:
                    parts.extend(action.option_strings)
                # if the Optional takes a value, format is:
                #    -s ARGS, --long ARGS
                else:
                    default = self._get_default_metavar_for_optional(action)
                    args_string = self._format_args(action, default)
                    for option_string in action.option_strings:
                        parts.append(option_string)
                    return '{} {}'.format(', '.join(parts), args_string)
                return ', '.join(parts)

        def _get_default_metavar_for_optional(self, action):
            return action.dest.upper()

    # Now build the arguments
    parser = argparse.ArgumentParser(formatter_class=SaneUsageFormat)

    parser.add_argument(
        '-a', '--apps',
        type=str,
        nargs='*',
        dest='apps_list',
        metavar='<app paths>',
        help='Generate an Accessibility profile for the specified applications.',
        required=True,
    )

    parser.add_argument(
        '--allow',
        action='store_true',
        dest='allow_app',
        default=False,
        help='Configure the profile to allow control for all apps provided with the --apps command.',
        required=False
    )

    parser.add_argument(
        '--payload-description',
        type=str,
        dest='payload_description',
        metavar='payload description',
        help='A short and sweet description of the payload.',
        required=True,
    )

    parser.add_argument(
        '--payload-identifier',
        type=str,
        dest='payload_identifier',
        metavar='payload identifier',
        help='An identifier to use for the profile. Example: org.foo.bar',
        required=True,
    )

    parser.add_argument(
        '--payload-name',
        type=str,
        dest='payload_name',
        metavar='payload name',
        help='A short and sweet name for the payload.',
        required=True,
    )

    parser.add_argument(
        '--payload-org',
        type=str,
        dest='payload_org',
        metavar='payload org',
        help='Organization to use for the profile.',
        required=True,
    )

    parser.add_argument(
        '--payload-version',
        type=int,
        dest='payload_ver',
        metavar='payload version',
        help='Version to use for the profile.',
        required=True,
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        dest='payload_filename',
        metavar='payload filename',
        help='Filename to save the profile as.',
        required=True,
    )

    # Parse the args
    args = parser.parse_args()

    # Build up args to pass to the class init
    apps = args.apps_list
    allow = args.allow_app
    description = args.payload_description
    payload_id = args.payload_identifier
    name = args.payload_name
    organization = args.payload_org
    version = args.payload_ver
    filename = args.payload_filename

    # Init the class
    tccprofiles = PrivacyProfiles(payload_description=description, payload_name=name, payload_identifier=payload_id, payload_organization=organization, payload_version=version, profile_filename=filename)

    # Create the empty accessibility dictionary
    tccprofiles.template['PayloadContent'][0]['Services'] = {'Accessibility': []}

    # Iterate over the apps to build payloads for
    for app in apps:
        app_path = os.path.join('/Applications', app)
        app_name = os.path.splitext(app)[0]
        codesign_result = tccprofiles.getCodeSignRequirements(path=app_path)
        accessibility_dict = tccprofiles.accessibilityPayload(app_path=app_path, allowed=allow, code_requirement=codesign_result, comment='Allow accessibility control for {}'.format(app_name))
        if accessibility_dict not in tccprofiles.template['PayloadContent'][0]['Services']['Accessibility']:
            tccprofiles.template['PayloadContent'][0]['Services']['Accessibility'].append(accessibility_dict)

    plistlib.writePlist(tccprofiles.template, tccprofiles.profile_filename)


if __name__ == '__main__':
    main()
