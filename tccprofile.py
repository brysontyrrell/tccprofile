#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import errno
import os
import plistlib
import uuid
import re
import subprocess
import sys
import Tkinter as tk
import ttk
import tkFileDialog

# Imports specifically for FoundationPlist
# PyLint cannot properly find names inside Cocoa libraries, so issues bogus
# No name 'Foo' in module 'Bar' warnings. Disable them.
# pylint: disable=E0611
import AppKit
from Foundation import NSData  # NOQA
from Foundation import NSPropertyListSerialization  # NOQA
from Foundation import NSPropertyListMutableContainers  # NOQA
from Foundation import NSPropertyListXMLFormat_v1_0  # NOQA
# pylint: enable=E0611

__author__ = ['Carl Windus', 'Bryson Tyrrell']
__license__ = 'Apache License 2.0'
__version__ = '1.0.1'

VERSION_STRING = 'Version: {} ({}), Authors: {}'.format(__version__, __license__, ', '.join(__author__))


# Special thanks to the munki crew for the plist work.
# FoundationPlist from munki
class FoundationPlistException(Exception):
    """Basic exception for plist errors"""
    pass


class NSPropertyListSerializationException(FoundationPlistException):
    """Read/parse error for plists"""
    pass


class TCCProfileException(Exception):
    """Base exception for script errors"""
    pass


class App(tk.Frame):
    def __init__(self, master):
        tk.Frame.__init__(self, master)
        self.pack()
        self.master.title("TCC Profile Generator")
        self.master.resizable(False, False)
        self.master.tk_setPalette(background='#ececec')

        self.master.protocol('WM_DELETE_WINDOW', self.click_quit)
        self.master.bind('<Return>', self.click_save)
        self.master.bind('<Escape>', self.click_quit)

        x = (self.master.winfo_screenwidth() - self.master.winfo_reqwidth()) / 2
        y = (self.master.winfo_screenheight() - self.master.winfo_reqheight()) / 4
        self.master.geometry("+{}+{}".format(x, y))

        self.master.config(menu=tk.Menu(self.master))

        # Payload Details UI

        payload_frame = tk.Frame(self)
        payload_frame.pack(padx=15, pady=15, fill=tk.BOTH)

        tk.Label(
            payload_frame,
            text='Payload Details',
            font=('System', 18)
        ).grid(row=0, column=0, columnspan=5, sticky='w')

        tk.Label(payload_frame, text="Name").grid(
            row=1, column=0, sticky='w'
        )
        self._payload_name = tk.Entry(payload_frame, bg='white', width=30)
        self._payload_name.insert(0, 'TCC Whitelist')
        self._payload_name.grid(row=2, column=0, columnspan=2, sticky='we')

        # This is an empty spacer for the grid layout of the frame
        tk.Label(
            payload_frame,
            text='',
            width=6
        ).grid(row=1, column=2)

        tk.Label(payload_frame, text="Organization").grid(
            row=1, column=3, sticky='w'
        )
        self._payload_org = tk.Entry(payload_frame, bg='white', width=30)
        self._payload_org.insert(0, 'My Org Name')
        self._payload_org.grid(row=2, column=3, columnspan=2, sticky='we')

        tk.Label(payload_frame, text="Identifier").grid(
            row=3, column=0, sticky='w'
        )
        self._payload_id = tk.Entry(payload_frame, bg='white')
        self._payload_id.insert(0, 'com.my.tccprofile')
        self._payload_id.grid(row=4, column=0, columnspan=2, sticky='we')

        tk.Label(payload_frame, text="Version").grid(
            row=3, column=3, sticky='w'
        )
        self._payload_version = tk.Entry(payload_frame, bg='white')
        self._payload_version.insert(0, '1')
        self._payload_version.grid(row=4, column=3, columnspan=2, sticky='we')

        tk.Label(payload_frame, text="Description").grid(
            row=5, column=0, sticky='w'
        )
        self._payload_desc = tk.Entry(payload_frame, bg='white')
        self._payload_desc.insert(0, 'TCC Whitelist for various applications')
        self._payload_desc.grid(row=6, column=0, columnspan=5, sticky='we')

        self._payload_sign = tk.StringVar()
        self._payload_sign.set('No')

        tk.Label(payload_frame, text="Sign Profile?").grid(
            row=7, column=0, sticky='e'
        )
        tk.OptionMenu(
            payload_frame,
            self._payload_sign,
            *self._list_signing_certs()
        ).grid(row=7, column=1, columnspan=4, sticky='we')

        # UI Feedback Section

        feedback_frame = tk.Frame(self)
        feedback_frame.pack(padx=15, fill=tk.BOTH)

        self._feedback_label = tk.Label(
            feedback_frame,
            font=("System", 12, "italic"),
            fg='red'
        )
        self._feedback_label.grid(row=0, column=0, sticky='we')

        # Services UI

        services_frame = tk.Frame(self)
        services_frame.pack(padx=15, pady=15, fill=tk.BOTH)

        self._services_target_var = tk.StringVar()
        self._services_target_var_display = tk.StringVar()

        tk.Label(
            services_frame,
            text='Setup Service Permissions',
            font=('System', 18)
        ).grid(row=0, column=0, columnspan=5, sticky='w')

        tk.Label(services_frame, text="Target App...").grid(
            row=1, column=0, sticky='w'
        )
        self.app_env_source_btn = tk.Button(
            services_frame,
            text='Choose...',
            command=lambda: self._app_picker('_services_target_var')
        )
        self.app_env_source_btn.grid(row=2, column=0, sticky='w')

        tk.Label(
            services_frame,
            textvariable=self._services_target_var_display,
            width=16
        ).grid(row=2, column=1, sticky='w')

        self._available_services = {
            'AddressBook': True,
            'Calendar': True,
            'Reminders': True,
            'Photos': True,
            'Camera': False,
            'Microphone': False,
            'Accessibility': True,
            'PostEvent': True,
            'SystemPolicyAllFiles': True,
            'SystemPolicySysAdminFiles': True
        }

        self._selected_service = tk.StringVar()
        self._selected_service.set('AddressBook')

        tk.Label(services_frame, text="Service...").grid(
            row=1, column=2, sticky='w'
        )
        tk.OptionMenu(
            services_frame,
            self._selected_service,
            *sorted([i for i in self._available_services.keys()])
        ).grid(row=2, column=2, sticky='w')

        # This is an empty spacer for the grid layout of the frame
        tk.Label(
            services_frame,
            text='',
            width=6
        ).grid(row=2, column=3)

        tk.Button(
            services_frame,
            text='Add +',
            command=self._add_service
        ).grid(row=2, column=4, sticky='e')

        self.services_table = ttk.Treeview(
            services_frame,
            columns=('target', 'service', 'allow_deny'),
            height=5
        )
        self.services_table['show'] = 'headings'
        self.services_table.heading('target', text='Target')
        self.services_table.heading('service', text='Service')
        self.services_table.heading('allow_deny', text='Allow/Deny')
        self.services_table.grid(row=3, column=0, columnspan=5, sticky='we')

        # Apple Events UI

        apple_events_frame = tk.Frame(self)
        apple_events_frame.pack(padx=15, pady=15, fill=tk.BOTH)

        self._app_env_source_var = tk.StringVar()
        self._app_env_target_var = tk.StringVar()
        self._app_env_source_var_display = tk.StringVar()
        self._app_env_target_var_display = tk.StringVar()

        tk.Label(
            apple_events_frame,
            text='Setup Apple Events',
            font=('System', 18)
        ).grid(row=0, column=0, columnspan=5, sticky='w')

        tk.Label(apple_events_frame, text="Source App...").grid(
            row=1, column=0, sticky='w'
        )

        self.app_env_source_btn = tk.Button(
            apple_events_frame,
            text='Choose...',
            command=lambda: self._app_picker('_app_env_source_var')
        )
        self.app_env_source_btn.grid(row=2, column=0, sticky='w')

        tk.Label(
            apple_events_frame,
            textvariable=self._app_env_source_var_display,
            width=20
        ).grid(row=2, column=1, sticky='w')

        tk.Label(apple_events_frame, text="Target App...").grid(
            row=1, column=2, sticky='w'
        )

        self.app_env_target_btn = tk.Button(
            apple_events_frame,
            text='Choose...',
            command=lambda: self._app_picker('_app_env_target_var')
        )
        self.app_env_target_btn.grid(row=2, column=2, sticky='w')

        tk.Label(
            apple_events_frame,
            textvariable=self._app_env_target_var_display,
            width=20
        ).grid(row=2, column=3, sticky='w')

        tk.Button(
            apple_events_frame,
            text='Add +',
            command=self._add_apple_event
        ).grid(row=2, column=4, sticky='e')

        self.app_env_table = ttk.Treeview(
            apple_events_frame, columns=('source', 'target'), height=5
        )
        self.app_env_table['show'] = 'headings'
        self.app_env_table.heading('source', text='Source')
        self.app_env_table.heading('target', text='Target')
        self.app_env_table.grid(row=3, column=0, columnspan=5, sticky='we')

        # Bottom frame for "Save' and 'Quit' buttons
        button_frame = tk.Frame(self)
        button_frame.pack(padx=15, pady=(0, 15), anchor='e')

        tk.Button(button_frame, text='Save', command=self.click_save).pack(
            side='right'
        )
        tk.Button(button_frame, text='Quit', command=self.click_quit).pack(
            side='right'
        )

    def click_save(self, event=None):
        print("The user clicked 'Save'")

        payload = dict()
        payload['Description'] = self._payload_desc.get()
        payload['Name'] = self._payload_name.get()
        payload['Identifier'] = self._payload_id.get()
        payload['Organization'] = self._payload_org.get()

        for k, v in payload.items():
            if not v:
                self._feedback_label['text'] = \
                    "Missing input for '{}'".format(k)
                return

        # The 'PayloadVersion' key MUST be an Integer value
        _version = self._payload_version.get()
        try:
            if float(_version).is_integer():
                version = int(_version)
            else:
                raise ValueError
        except ValueError:
            print('Invalid payload version')
            self._feedback_label['text'] = "The 'Version' must be an integer!"
            return

        app_lists = dict()

        for child in self.services_table.get_children():
            values = self.services_table.item(child)["values"]
            if not app_lists.get(values[1]):
                app_lists[values[1]] = list()

            app_lists[values[1]].append(values[0])

        for child in self.app_env_table.get_children():
            if not app_lists.get('AppleEvents'):
                app_lists['AppleEvents'] = list()

            app_lists['AppleEvents'].append(
                ','.join(self.app_env_table.item(child)["values"])
            )

        if not any(app_lists.keys()):
            self._feedback_label['text'] = 'You must provide at least one ' \
                                           'payload type to create a profile!'
            return

        sign = self._payload_sign.get()

        desktop_path = os.path.expanduser('~/Desktop')
        filename = tkFileDialog.asksaveasfilename(
            parent=self,
            defaultextension='.mobileconfig',
            initialdir=desktop_path,
            initialfile='tccprofile.mobileconfig',
            title='Save TCC Profile...'
        )

        tcc_profile = PrivacyProfiles(
            payload_description=payload['Description'],
            payload_name=payload['Name'],
            payload_identifier=payload['Identifier'],
            payload_organization=payload['Organization'],
            payload_version=version,
            sign_cert=None if sign == 'No' else sign,
            filename=filename
        )

        tcc_profile.set_services_dict(app_lists)
        tcc_profile.build_profile(allow=True)
        tcc_profile.write()

        self._feedback_label['text'] = ''

    def click_quit(self, event=None):
        print("The user clicked 'Quit'")
        self.master.destroy()

    @staticmethod
    def _list_signing_certs():
        output = subprocess.check_output(
            ['/usr/bin/security', 'find-identity', '-p', 'codesigning', '-v']
        ).split('\n')

        cert_list = ['No']
        for i in output:
            r = re.findall(r'"(.*?)"', i)
            if r:
                cert_list.extend(r)

        return cert_list

    def _app_picker(self, var_name):
        app_name = tkFileDialog.askopenfilename(
            parent=self,
            # filetypes=[('App', '.app')],
            initialdir='/Applications',
            title='Select App'
        )
        getattr(self, var_name).set(app_name)
        getattr(self, var_name + '_display').set(os.path.basename(app_name))

    def _add_apple_event(self):
        source_app = self._app_env_source_var.get()
        target_app = self._app_env_target_var.get()

        if not all([source_app, target_app]):
            print('Source and Target not both provided')
            return

        self.app_env_table.insert('', 'end', values=(source_app, target_app))
        self._app_env_target_var.set('')
        self._app_env_source_var.set('')
        self._app_env_source_var_display.set('')
        self._app_env_target_var_display.set('')

    def _add_service(self):
        target_app = self._services_target_var.get()
        selected_service = self._selected_service.get()
        allow_deny = 'Allow' if \
            self._available_services.get(selected_service) else 'Deny'

        if not target_app:
            print('Target app not provided')
            return

        self.services_table.insert(
            '', 'end',
            values=(target_app, selected_service, allow_deny)
        )
        self._services_target_var.set('')
        self._services_target_var_display.set('')


def read_plist(filepath):
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


def read_plist_from_string(data):
    """Read a plist data from a string. Return the root object."""
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


class PrivacyProfiles(object):
    # List of Payload types to iterate on because lazy code is good code
    PAYLOADS = [
        'AddressBook',
        'Calendar',
        'Reminders',
        'Photos',
        'Camera',
        'Microphone',
        'Accessibility',
        'PostEvent',
        'SystemPolicyAllFiles',
        'SystemPolicySysAdminFiles',
        'AppleEvents'
    ]

    def __init__(self, payload_description, payload_name, payload_identifier,
                 payload_organization, payload_version, sign_cert, filename):
        """Creates a Privacy Preferences Policy Control Profile for macOS
        Mojave.
        """
        # Init the things to put in the template, and elsewhere
        self.payload_description = payload_description
        self.payload_name = payload_name
        self.payload_identifier = payload_identifier
        self.payload_organization = payload_organization
        self.payload_type = 'com.apple.TCC.configuration-profile-policy'
        self.payload_uuid = str(uuid.uuid1()).upper()  # This is used in the 'PayloadContent' part of the profile
        self.profile_uuid = str(uuid.uuid1()).upper()  # This is used in the root of the profile
        self.payload_version = payload_version

        # Basic requirements for this profile to work
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
                    'Services': dict()  # This will be an empty list to house the dicts.
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

        self._app_lists = dict()
        self._sign_cert = self._set_sign_profile(sign_cert)
        self._filename = self._set_filename(filename)

        # Note, there's different values for the python codesigns depending on which python is called.
        # /usr/bin/python is com.apple.python
        # /System/Library/Frameworks/Python.framework/Resources/Python.app is org.python.python
        # These different codesign values cause issues with LaunchAgents/LaunchDaemons that don't explicitly call
        # the interpreter in the ProgramArguments array.
        # For the time being, strongly recommend any LaunchDaemons/LaunchAgents that launch python scripts to
        # add in <string>/usr/bin/python</string> to the ProgramArguments array _before_ the <string>/path/to/pythonscript.py</string> line.

    def set_services_dict(self, args):
        if not isinstance(args, dict):
            arguments = vars(args)
            app_lists = dict()

            # Build up args to pass to the class init
            app_lists['AddressBook'] = arguments.get(
                'address_book_apps_list', False)
            app_lists['Calendar'] = arguments.get('calendar_apps_list', False)
            app_lists['Reminders'] = arguments.get('reminders_apps_list', False)
            app_lists['Photos'] = arguments.get('photos_apps_list', False)
            app_lists['Camera'] = arguments.get('camera_apps_list', False)
            app_lists['Microphone'] = arguments.get(
                'microphone_apps_list', False)
            app_lists['Accessibility'] = arguments.get(
                'accessibility_apps_list', False)
            app_lists['PostEvent'] = arguments.get(
                'post_event_apps_list', False)
            app_lists['SystemPolicyAllFiles'] = arguments.get(
                'allfiles_apps_list', False)
            app_lists['SystemPolicySysAdminFiles'] = arguments.get(
                'sysadmin_apps_list', False)
            app_lists['AppleEvents'] = arguments.get('events_apps_list', False)
        else:
            app_lists = args

        # Handle if no payload arguments are supplied,
        # Can't create an empty profile.
        if not any(app_lists.keys()):
            print 'You must provide at least one payload type to create a profile.'
            raise TCCProfileException

        self._app_lists = app_lists

        # Create payload lists in the services_dict
        for payload in self.PAYLOADS:
            if app_lists.get(payload):
                self.template['PayloadContent'][0]['Services'][payload] = []

    def build_profile(self, allow):
        for payload in self.PAYLOADS:
            if self._app_lists.get(payload):
                for app in self._app_lists[payload]:
                    if payload in ['Camera', 'Microphone'] or not allow:  # Camera and Microphone payloads can only DENY an app access to that hardware.
                        _allow = False
                        allow_statement = 'Deny'
                    else:
                        _allow = allow
                        allow_statement = 'Allow'

                    if payload == 'AppleEvents':  # AppleEvent payload has additional requirements
                        if not len(app.split(',')) == 2:
                            print 'AppleEvents applications must be in the format of /Application/Path/EventSending.app,/Application/Path/EventReceiving.app'
                            sys.exit(1)
                        else:
                            sending_app = app.split(',')[0]
                            receiving_app = app.split(',')[1]
                            sending_app_name = os.path.basename(
                                os.path.splitext(sending_app)[0])
                            receiving_app_name = os.path.basename(
                                os.path.splitext(receiving_app)[0])
                            codesign_result = self._get_code_sign_requirements(
                                path=app.split(',')[0])
                            payload_dict = self._build_payload(
                                app_path=app, allowed=allow, apple_event=True,
                                code_requirement=codesign_result,
                                comment='{} {} to send {} control to {}'.format(
                                    allow_statement, sending_app_name, payload,
                                    receiving_app_name))

                    else:
                        app_name = os.path.basename(os.path.splitext(app)[0])
                        codesign_result = self._get_code_sign_requirements(
                            path=app)
                        payload_dict = self._build_payload(
                            app_path=app,
                            allowed=_allow,
                            apple_event=False,
                            code_requirement=codesign_result,
                            comment='{} {} control for {}'.format(
                                allow_statement,
                                payload,
                                app_name
                            )
                        )

                    if payload_dict not in self.template['PayloadContent'][0]['Services'][payload]:
                        self.template['PayloadContent'][0]['Services'][payload].append(payload_dict)

    def write(self):
        if self._filename:
            # Write the plist out to file
            plistlib.writePlist(self.template, self._filename)

            # Sign it if required
            if self._sign_cert:
                self._sign_profile(
                    certificate_name=self._sign_cert,
                    input_file=self._filename
                )
        else:
            # Print as formatted plist out to stdout
            print plistlib.writePlistToString(self.template).rstrip('\n')

    @staticmethod
    def _set_sign_profile(sign_cert):
        if sign_cert and len(sign_cert):
            return sign_cert[0]
        else:
            return False

    @staticmethod
    def _set_filename(filename):
        if filename:
            _filename = os.path.expandvars(os.path.expanduser(filename))
            if not os.path.splitext(filename)[1] == '.mobileconfig':
                _filename = filename.replace(os.path.splitext(filename)[1], '.mobileconfig')

            return _filename
        else:
            return None

    @staticmethod
    def _get_file_mime_type(path):
        """Returns the mimetype of a given file."""
        if os.path.exists(path.rstrip('/')):
            cmd = ['/usr/bin/file', '--mime-type', path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result, error = process.communicate()

            if process.returncode is 0:
                # Only need the mime type, so return the last bit
                result = result.replace(' ', '').replace('\n', '').split(':')[1].split('/')[1]
                return result

    @staticmethod
    def _read_shebang(app_path):
        """Returns the contents of the shebang in a script file, as long as env
        is not in the shebang
        """
        with open(app_path, 'r') as textfile:
            line = textfile.readline().rstrip('\n')
            if line.startswith('#!') and 'env ' not in line:
                return line.replace('#!', '')
            elif line.startswith('#!') and 'env ' in line:
                raise Exception('Cannot check codesign for shebangs that refer to \'env\'.')

    def _get_code_sign_requirements(self, path):
        """Returns the values for the CodeRequirement key."""
        def _is_code_signed(path):
            """Returns True/False if specified path is code signed or not."""
            cmd = ['/usr/bin/codesign', '-dr', '-', path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result, error = process.communicate()

            if process.returncode is 0:
                return True
            elif process.returncode is 1 and 'not signed' in error:
                return False

        if os.path.exists(path.rstrip('/')):
            # Handle situations where path is a script, and shebang is
            # ['/bin/sh', '/bin/bash', '/usr/bin/python']
            mimetype = self._get_file_mime_type(path=path)
            if mimetype in ['x-python', 'x-shellscript']:
                if not _is_code_signed(path):  # Only use shebang path if a script is not code signed
                    path = self._read_shebang(app_path=path)

            cmd = ['/usr/bin/codesign', '-dr', '-', path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result, error = process.communicate()

            if process.returncode is 0:
                # For some reason, part of the output gets dumped to stderr, but the bit we need goes to stdout
                # Also, there can be multiple lines in the result, so handle this properly
                # There are circumstances where the codesign 'designated => ' is not the start of the line, so handle these.
                result = result.rstrip('\n').splitlines()
                result = [line for line in result if 'designated => ' in line][0]
                result = result.partition('designated => ')
                result = result[result.index('designated => ') + 1:][0]
                # result = [x.rstrip('\n') for x in result.splitlines() if x.startswith('designated => ')][0]
                return result
            elif process.returncode is 1 and 'not signed' in error:
                print 'App at {} is not signed. Exiting.'.format(path)
                sys.exit(1)
        else:
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    def _get_identifier_and_type(self, app_path):
        """Checks file type, and returns appropriate values for `Identifier`and
        `IdentifierType` keys in the final profile payload.
        """
        mimetype = self._get_file_mime_type(path=app_path)
        if mimetype in ['x-shellscript', 'x-python']:
            identifier = app_path
            identifier_type = 'path'
        else:
            try:
                identifier = read_plist(os.path.join(app_path.rstrip('/'), 'Contents/Info.plist'))['CFBundleIdentifier']
                identifier_type = 'bundleID'
            except Exception:
                identifier = app_path.rstrip('/')
                identifier_type = 'path'

        return {'identifier': identifier, 'identifier_type': identifier_type}

    def _build_payload(self, app_path, allowed, apple_event, code_requirement, comment):
        """Builds an Accessibility payload for the profile."""
        if type(allowed) is bool and type(code_requirement) is str and type(apple_event) is bool:
            # Check if building an Apple Event. The sending app and receiving app must be seperated by comma
            # Example: ['/Applications/Foo.app,/Applications/Bar.app']
            # The receiving app is the second/last app in the "list" (splits on comma)
            if apple_event and ',' in app_path and len(app_path.split(',')) == 2:
                receiving_app = app_path.split(',')[1]
                app_path = app_path.split(',')[0]
                receiving_app_identifiers = self._get_identifier_and_type(app_path=receiving_app)
                receiving_app_identifier = receiving_app_identifiers['identifier']
                receiving_app_identifier_type = receiving_app_identifiers['identifier_type']
            elif apple_event and ',' not in app_path and len(app_path.split(',')) == 2:
                print 'AppleEvents applications must be in the format of /Application/Path/EventSending.app,/Application/Path/EventReceiving.app'
                sys.exit(1)

            app_identifiers = self._get_identifier_and_type(app_path=app_path)
            identifier = app_identifiers['identifier']
            identifier_type = app_identifiers['identifier_type']

            # Only return a basic dict, even though the Services needs a dict
            # supplied, and the 'Accessibility' "payload" is a list of dicts.
            result = {
                'Allowed': allowed,
                'CodeRequirement': code_requirement,
                'Comment': comment,
                'Identifier': identifier,
                'IdentifierType': identifier_type,
            }

            # If the payload is an AppleEvent type, there are additional
            # requirements relating to the receiving app.
            if apple_event:
                result['AEReceiverIdentifier'] = receiving_app_identifier
                result['AEReceiverIdentifierType'] = receiving_app_identifier_type
                result['AEReceiverCodeRequirement'] = self._get_code_sign_requirements(path=receiving_app)

            return result

    def _sign_profile(self, certificate_name, input_file):
        """Signs the profile."""
        if self._sign_cert and os.path.exists(input_file) and input_file.endswith('.mobileconfig'):
            cmd = ['/usr/bin/security', 'cms', '-S', '-N', certificate_name, '-i', input_file, '-o', '{}'.format(input_file.replace('.mobileconfig', '_Signed.mobileconfig'))]
            subprocess.call(cmd)


class SaneUsageFormat(argparse.HelpFormatter):
    """Makes the help output somewhat more sane. Code used was from Matt Wilkie.

    http://stackoverflow.com/questions/9642692/argparse-help-without-duplicate-allcaps/9643162#9643162
    """

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


def parse_args():
    parser = argparse.ArgumentParser(formatter_class=SaneUsageFormat)

    parser.add_argument(
        '--ab', '--address-book',
        type=str,
        nargs='*',
        dest='address_book_apps_list',
        metavar='<app paths>',
        help='Generate an AddressBook payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--cal', '--calendar',
        type=str,
        nargs='*',
        dest='calendar_apps_list',
        metavar='<app paths>',
        help='Generate a Calendar payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--rem', '--reminders',
        type=str,
        nargs='*',
        dest='reminders_apps_list',
        metavar='<app paths>',
        help='Generate a Reminders payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--pho', '--photos',
        type=str,
        nargs='*',
        dest='photos_apps_list',
        metavar='<app paths>',
        help='Generate a Photos payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--cam', '--camera',
        type=str,
        nargs='*',
        dest='camera_apps_list',
        metavar='<app paths>',
        help='Generate a Camera payload for the specified applications. '
             'This will be a DENY payload.',
        required=False,
    )

    parser.add_argument(
        '--mic', '--microphone',
        type=str,
        nargs='*',
        dest='microphone_apps_list',
        metavar='<app paths>',
        help='Generate a Microphone payload for the specified applications. '
             'This will be a DENY payload.',
        required=False,
    )

    parser.add_argument(
        '--acc', '--accessibility',
        type=str,
        nargs='*',
        dest='accessibility_apps_list',
        metavar='<app paths>',
        help='Generate an Accessibility payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--pe', '--post-event',
        type=str,
        nargs='*',
        dest='post_event_apps_list',
        metavar='<app paths>',
        help='Generate a PostEvent payload for the specified applications to '
             'allow CoreGraphics APIs to send CGEvents.',
        required=False,
    )

    parser.add_argument(
        '--af', '--allfiles',
        type=str,
        nargs='*',
        dest='allfiles_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicyAllFiles payload for the specified '
             'applications. This applies to all protected system files.',
        required=False,
    )

    parser.add_argument(
        '--ae', '--appleevents',
        type=str,
        nargs='*',
        dest='events_apps_list',
        metavar='<app paths>',
        help='Generate an AppleEvents payload for the specified applications. '
             'This allows applications to send restricted AppleEvents to '
             'another process',
        required=False,
    )

    parser.add_argument(
        '--sf', '--sysadminfiles',
        type=str,
        nargs='*',
        dest='sysadmin_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicySysAdminFiles payload for the specified '
             'applications.This applies to some files used in system '
             'administration.',
        required=False,
    )

    parser.add_argument(
        '--allow',
        action='store_true',
        dest='allow_app',
        default=False,
        help='Configure the profile to allow control for all apps provided '
             'with the --apps command.',
        required=False
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        dest='payload_filename',
        metavar='payload_filename',
        help='Filename to save the profile as.',
        required=False,
    )

    parser.add_argument(
        '--pd', '--payload-description',
        type=str,
        dest='payload_description',
        metavar='payload_description',
        help='A short and sweet description of the payload.',
        required=True,
    )

    parser.add_argument(
        '--pi', '--payload-identifier',
        type=str,
        dest='payload_identifier',
        metavar='payload_identifier',
        help='An identifier to use for the profile. Example: org.foo.bar',
        required=True,
    )

    parser.add_argument(
        '--pn', '--payload-name',
        type=str,
        dest='payload_name',
        metavar='payload_name',
        help='A short and sweet name for the payload.',
        required=True,
    )

    parser.add_argument(
        '--po', '--payload-org',
        type=str,
        dest='payload_org',
        metavar='payload_org',
        help='Organization to use for the profile.',
        required=True,
    )

    parser.add_argument(
        '--pv', '--payload-version',
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
        help='Signs a profile using the specified Certificate Name. To list '
             'code signing certificate names: /usr/bin/security find-identity '
             '-p codesigning -v',
        required=False,
    )

    parser.add_argument(
        '-v', '--version',
        action='version',
        version=VERSION_STRING
    )

    # parser.add_argument(
    #     '--lg', '--launch-gui',
    #     action='store_true',
    #     default=False,
    #     dest='launch_gui',
    #     help='Launch the GUI and populate the provided values passed via the '
    #          'arguments.',
    #     required=False
    # )

    return parser.parse_args()


def launch_gui(args=None):
    info = AppKit.NSBundle.mainBundle().infoDictionary()
    info['LSUIElement'] = True

    print(args)

    root = tk.Tk()
    app = App(root)
    AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    app.mainloop()


def main():
    if len(sys.argv) == 1:
        launch_gui()
        sys.exit(0)
    else:
        args = parse_args()
        # if args.launch_gui:
        #     launch_gui(args)

    tcc_profile = PrivacyProfiles(
        payload_description=args.payload_description,
        payload_name=args.payload_name,
        payload_identifier=args.payload_identifier,
        payload_organization=args.payload_org,
        payload_version=args.payload_ver,
        sign_cert=args.sign_profile,
        filename=args.payload_filename
    )

    # Insert the service dict into the template
    tcc_profile.set_services_dict(args)

    # Iterate over the payloads dict to build payloads
    tcc_profile.build_profile(allow=args.allow_app)

    tcc_profile.write()


if __name__ == '__main__':
    main()
