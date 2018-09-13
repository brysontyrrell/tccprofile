# tccprofile
Creates a mobileconfig profile for TCC configuration in a certain version of macOS.

Currently it _only_ generates payloads for _application_ binaries, and will generate the same allow settings (i.e. Allow/Deny the app control) for any apps specified.

The applications also need to be installed on the system you're running `tccprofile.py` on.

## Code Signing Requirements
The output of `codesign -dr - /Application/Application.app` is likely to vary as the developer of the app releases new versions, etc, or needs to re-sign the app for whatever reason. It will be critical to maintain an accurate profile with these correct `codesign` results, as being not specific enough can potentially lead to bad actors maliciously acting on your system.

For example, both the values below for the `CodeRequirement` of payloads for Adobe Photoshop CC 2018 will work.

Example A:
```
identifier "com.adobe.Photoshop" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ and certificate leaf[subject.OU] = JQ525L2MZD
```
Example B:
```
identifier "com.adobe.Photoshop" and anchor apple generic
```

Out of these two examples, `Example B` can be considered the least secure/most generic, while `Example A` is the most secure/least generic. `Example A` will be more cumbersome to maintain, however.

## Requires
1. python 2.7.10 (as tested on)
1. `/usr/bin/codesign`
1. The application the profile is generated for must be installed on the machine `tccprofile.py` is run on.

## Tested on
macOS 10.12.6 (should work on any recent macOS release)

## Usage:
1. `git clone https://github.com/carlashley/tccprofile`
1. `cd tccprofile && chmod +x tccprofile.py`
1. `./tccprofile.py --help`

Example:
```
./tccprofile.py -a /Applications/Automator.app --allow --payload-description="Whitelist Apps" --payload-identifier="com.github.carlashley" --payload-name="TCC Whitelist" --payload-org="My Great Company" --payload-version="1" -o TCC_Accessibility_Profile_20180816_v1.mobileconfig
```

To sign:
```
./tccprofile.py -a /Applications/Automator.app --allow --payload-description="Whitelist Apps" --payload-identifier="com.github.carlashley" --payload-name="TCC Whitelist" --payload-org="My Great Company" --payload-version="1" -o TCC_Accessibility_Profile_20180816_v1.mobileconfig --sign="Certificate Name"
```

To create an AppleEvent Payload, you must provide _both_ apps as comma seperated. The first app is the app _sending_ the event, the second app is the app _receiving_ the event.
```
./tccprofile.py --appleevents /Applications/Adobe\ Photoshop\ CC\ 2018/Adobe\ Photoshop\ CC\ 2018.app,/System/Library/CoreServices/Finder.app --payload-description="TCC Whitelist for Adobe Photoshop" --payload-name="TCC Whitelist" --payload-org="My Great Company"\n --payload-version=1 --payload-identifier="com.carlashley.github" -o Adobe_Photoshop_TCC.mobileconfig --allow --sign="Certificate Name"
```

To create payloads for all four types:
```
./tccprofile.py --appleevents /Applications/Adobe\ Photoshop\ CC\ 2018/Adobe\ Photoshop\ CC\ 2018.app,/System/Library/CoreServices/Finder.app --sysadminfiles /Applications/Utilities/Terminal.app /Applications/Chess.app --allfiles /usr/sbin/installer /Applications/Dictionary.app --accessibility /Applications/Adobe\ Photoshop\ CC\ 2018/Adobe\ Photoshop\ CC\ 2018.app --payload-description="TCC Whitelist for various applications" --payload-name="TCC Whitelist" --payload-org="My Great Company" --payload-version=1 --payload-identifier="com.carlashley.github" -o TCC_Whitelists.mobileconfig --allow --sign="Certificate Name"
```
