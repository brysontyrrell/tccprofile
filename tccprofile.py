#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import errno
import os
import plistlib
import uuid
import subprocess
import sys

# Imports specifically for FoundationPlist
# PyLint cannot properly find names inside Cocoa libraries, so issues bogus
# No name 'Foo' in module 'Bar' warnings. Disable them.
# pylint: disable=E0611
from Foundation import NSData  # NOQA
from Foundation import NSPropertyListSerialization  # NOQA
from Foundation import NSPropertyListMutableContainers  # NOQA
from Foundation import NSPropertyListXMLFormat_v1_0  # NOQA
# pylint: enable=E0611

# from pprint import pprint  # NOQA


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
    def __init__(self, payload_description, payload_name, payload_identifier, payload_organization, payload_version, profile_filename, sign_cert):
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
        self.sign_cert = sign_cert

        if not os.path.splitext(self.profile_filename)[1] == '.mobileconfig':
            self.profile_filename = self.profile_filename.replace(os.path.splitext(self.profile_filename)[1], '.mobileconfig')

        self.template = {
            'PayloadContent': [
                {
                    'PayloadDescription': self.payload_description,
                    'PayloadDisplayName': self.payload_name,
                    'PayloadIdentifier': '{}.{}'.format(self.payload_identifier, self.payload_uuid),  # This needs to be different to the root 'PayloadIdentifier'
                    'PayloadOrganization': self.payload_organization,
                    'PayloadType': self.payload_type,
                    'PayloadUUID': self.payload_uuid,
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

    def getFileMimeType(self, path):
        '''Returns the mimetype of a given file'''
        if os.path.exists(path.rstrip('/')):
            cmd = ['/usr/bin/file', '--mime-type', path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result, error = process.communicate()

            if process.returncode is 0:
                # Only need the mime type, so return the last bit
                result = result.replace(' ', '').replace('\n', '').split(':')[1].split('/')[1]
                return result

    def getCodeSignRequirements(self, path):
        if os.path.exists(path.rstrip('/')):
            mimetype = self.getFileMimeType(path=path)
            if mimetype == 'x-python':
                return 'identifier "org.python.python" and anchor apple'
            elif mimetype == 'x-shellscript':
                return 'identifier "com.apple.sh" and anchor apple'
            else:
                cmd = ['/usr/bin/codesign', '-dr', '-', path]
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                result, error = process.communicate()

                if process.returncode is 0:
                    # For some reason, part of the output gets dumped to stderr, but the bit we need goes to stdout
                    if result.startswith('designated => '):
                        return result.replace('designated => ', '').strip('\n')
                elif process.returncode is 1 and 'not signed' in error:
                    print 'App at {} is not signed. Exiting.'.format(path)
                    sys.exit(1)
        else:
            raise OSError.FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    def getIdentifierAndType(self, app_path):
        '''Checks file type, and returns appropriate values for `Identifier` and `IdentifierType` keys in the final profile payload.'''
        mimetype = self.getFileMimeType(path=app_path)
        if mimetype in ['x-shellscript', 'x-python']:
            identifier = app_path
            identifier_type = 'path'
        else:
            try:
                identifier = readPlist(os.path.join(app_path.rstrip('/'), 'Contents/Info.plist'))['CFBundleIdentifier']
                identifier_type = 'bundleID'
            except Exception:
                identifier = app_path.rstrip('/')
                identifier_type = 'path'

        return {'identifier': identifier, 'identifier_type': identifier_type}

    def buildPayload(self, app_path, allowed, apple_event, code_requirement, comment):
        '''Builds an Accessibility payload for the profile.'''
        if type(allowed) is bool and type(code_requirement) is str and type(apple_event) is bool:
            # Check if building an Apple Event. The sending app and receiving app must be seperated by comma
            # Example: ['/Applications/Foo.app,/Applications/Bar.app']
            # The receiving app is the second/last app in the "list" (splits on comma)
            if apple_event and ',' in app_path and len(app_path.split(',')) == 2:
                receiving_app = app_path.split(',')[1]
                app_path = app_path.split(',')[0]
                receiving_app_identifiers = self.getIdentifierAndType(app_path=receiving_app)
                receiving_app_identifier = receiving_app_identifiers['identifier']
                receiving_app_identifier_type = receiving_app_identifiers['identifier_type']
            elif apple_event and ',' not in app_path and len(app_path.split(',')) == 2:
                print 'AppleEvents applications must be in the format of /Application/Path/EventSending.app,/Application/Path/EventReceiving.app'
                sys.exit(1)

            app_identifiers = self.getIdentifierAndType(app_path=app_path)
            identifier = app_identifiers['identifier']
            identifier_type = app_identifiers['identifier_type']

            # Only return a basic dict, even though the Services needs a dict supplied, and the 'Accessibility' "payload" is a list of dicts.
            result = {
                'Allowed': allowed,
                'CodeRequirement': code_requirement,
                'Comment': comment,
                'Identifier': identifier,
                'IdentifierType': identifier_type,
            }

            if apple_event:
                result['AEReceiverIdentifier'] = receiving_app_identifier
                result['AEReceiverIdentifierType'] = receiving_app_identifier_type
                result['AEReceiverCodeRequirement'] = self.getCodeSignRequirements(path=receiving_app)

            return result

    def systemPolicyAllFilesPayload(self, app_path, allowed, code_requirement, comment):
        '''Builds a SystemPolicyAllFiles payload for the profile.'''

    def signProfile(self, certificate_name, input_file):
        if self.sign_cert and os.path.exists(input_file) and input_file.endswith('.mobileconfig'):
            cmd = ['/usr/bin/security', 'cms', '-S', '-N', certificate_name, '-i', input_file, '-o', '{}'.format(input_file.replace('.mobileconfig', '_Signed.mobileconfig'))]
            subprocess.call(cmd)


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
        '--accessibility',
        type=str,
        nargs='*',
        dest='accessibility_apps_list',
        metavar='<app paths>',
        help='Generate an Accessibility payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--allfiles',
        type=str,
        nargs='*',
        dest='allfiles_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicyAllFiles payload for the specified applications. This applies to all protected system files.',
        required=False,
    )

    parser.add_argument(
        '--appleevents',
        type=str,
        nargs='*',
        dest='events_apps_list',
        metavar='<app paths>',
        help='Generate an AppleEvents payload for the specified applications. This allows applications to send restricted AppleEvents to another process',
        required=False,
    )

    parser.add_argument(
        '--sysadminfiles',
        type=str,
        nargs='*',
        dest='sysadmin_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicySysAdminFiles payload for the specified applications.This applies to some files used in system administration.',
        required=False,
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
        '-o', '--output',
        type=str,
        dest='payload_filename',
        metavar='payload_filename',
        help='Filename to save the profile as.',
        required=True,
    )

    parser.add_argument(
        '--payload-description',
        type=str,
        dest='payload_description',
        metavar='payload_description',
        help='A short and sweet description of the payload.',
        required=True,
    )

    parser.add_argument(
        '--payload-identifier',
        type=str,
        dest='payload_identifier',
        metavar='payload_identifier',
        help='An identifier to use for the profile. Example: org.foo.bar',
        required=True,
    )

    parser.add_argument(
        '--payload-name',
        type=str,
        dest='payload_name',
        metavar='payload_name',
        help='A short and sweet name for the payload.',
        required=True,
    )

    parser.add_argument(
        '--payload-org',
        type=str,
        dest='payload_org',
        metavar='payload_org',
        help='Organization to use for the profile.',
        required=True,
    )

    parser.add_argument(
        '--payload-version',
        type=int,
        dest='payload_ver',
        metavar='payload_version',
        help='Version to use for the profile.',
        required=True,
    )

    parser.add_argument(
        '-s', '--sign',
        type=str,
        nargs=1,
        dest='sign_profile',
        metavar='certificate_name',
        help='Signs a profile using the specified Certificate Name. To list code signing certificate names: /usr/bin/security find-identity -p codesigning -v',
        required=False,
    )

    # Parse the args
    args = parser.parse_args()

    # Build up args to pass to the class init
    if args.accessibility_apps_list:
        accessibility_apps = args.accessibility_apps_list
    else:
        accessibility_apps = False

    if args.allfiles_apps_list:
        allfiles_apps = args.allfiles_apps_list
    else:
        allfiles_apps = False

    if args.events_apps_list:
        events_apps = args.events_apps_list
    else:
        events_apps = False

    if args.sysadmin_apps_list:
        sysadmin_apps = args.sysadmin_apps_list
    else:
        sysadmin_apps = False

    allow = args.allow_app
    description = args.payload_description
    payload_id = args.payload_identifier
    name = args.payload_name
    organization = args.payload_org
    version = args.payload_ver
    filename = args.payload_filename

    if args.sign_profile and len(args.sign_profile):
        sign_cert = args.sign_profile[0]
    else:
        sign_cert = False

    # Init the class
    tccprofiles = PrivacyProfiles(payload_description=description, payload_name=name, payload_identifier=payload_id, payload_organization=organization, payload_version=version, profile_filename=filename, sign_cert=sign_cert)

    # Build services dict to insert
    services_dict = {}

    if accessibility_apps:
        services_dict['Accessibility'] = []

    if allfiles_apps:
        services_dict['SystemPolicyAllFiles'] = []

    if events_apps:
        services_dict['AppleEvents'] = []

    if sysadmin_apps:
        services_dict['SystemPolicySysAdminFiles'] = []

    # Insert the service dict into the template
    tccprofiles.template['PayloadContent'][0]['Services'] = services_dict

    # Iterate over the apps to build payloads for
    if accessibility_apps:
        for app in accessibility_apps:
            app_name = os.path.basename(os.path.splitext(app)[0])
            codesign_result = tccprofiles.getCodeSignRequirements(path=app)
            accessibility_dict = tccprofiles.buildPayload(app_path=app, allowed=allow, apple_event=False, code_requirement=codesign_result, comment='Allow Accessibility control for {}'.format(app_name))
            if accessibility_dict not in tccprofiles.template['PayloadContent'][0]['Services']['Accessibility']:
                tccprofiles.template['PayloadContent'][0]['Services']['Accessibility'].append(accessibility_dict)

    if allfiles_apps:
        for app in allfiles_apps:
            app_name = os.path.basename(os.path.splitext(app)[0])
            codesign_result = tccprofiles.getCodeSignRequirements(path=app)
            allfiles_dict = tccprofiles.buildPayload(app_path=app, allowed=allow, apple_event=False, code_requirement=codesign_result, comment='Allow SystemPolicyAllFiles control for {}'.format(app_name))
            if allfiles_dict not in tccprofiles.template['PayloadContent'][0]['Services']['SystemPolicyAllFiles']:
                tccprofiles.template['PayloadContent'][0]['Services']['SystemPolicyAllFiles'].append(allfiles_dict)

    if events_apps:
        for app in events_apps:
            if not len(app.split(',')) == 2:
                print 'AppleEvents applications must be in the format of /Application/Path/EventSending.app,/Application/Path/EventReceiving.app'
                sys.exit(1)
            else:
                sending_app = app.split(',')[0]
                receiving_app = app.split(',')[1]
                sending_app_name = os.path.basename(os.path.splitext(sending_app)[0])
                receiving_app_name = os.path.basename(os.path.splitext(receiving_app)[0])
                codesign_result = tccprofiles.getCodeSignRequirements(path=app.split(',')[0])
                events_dict = tccprofiles.buildPayload(app_path=app, allowed=allow, apple_event=True, code_requirement=codesign_result, comment='Allow {} to send AppleEvents control to {}'.format(sending_app_name, receiving_app_name))
                if events_dict not in tccprofiles.template['PayloadContent'][0]['Services']['AppleEvents']:
                    tccprofiles.template['PayloadContent'][0]['Services']['AppleEvents'].append(events_dict)

    if sysadmin_apps:
        for app in sysadmin_apps:
            app_name = os.path.basename(os.path.splitext(app)[0])
            codesign_result = tccprofiles.getCodeSignRequirements(path=app)
            sysadminpolicy_dict = tccprofiles.buildPayload(app_path=app, allowed=allow, apple_event=False, code_requirement=codesign_result, comment='Allow SystemPolicySysAdminFiles control for {}'.format(app_name))
            if sysadminpolicy_dict not in tccprofiles.template['PayloadContent'][0]['Services']['SystemPolicySysAdminFiles']:
                tccprofiles.template['PayloadContent'][0]['Services']['SystemPolicySysAdminFiles'].append(sysadminpolicy_dict)

    # Write the plist out
    plistlib.writePlist(tccprofiles.template, tccprofiles.profile_filename)

    if tccprofiles.sign_cert:
        tccprofiles.signProfile(certificate_name=tccprofiles.sign_cert, input_file=tccprofiles.profile_filename)


if __name__ == '__main__':
    main()
