# tccprofile
Creates a mobileconfig profile for TCC configuration in a certain version of macOS.

## !Warning!
Presently this has _not_ been tested to ensure the generated profiles will deploy correctly. This was whipped up fairly quickly. I'm quite happy to accept pull requests to fix issues, typos, all that jazz.

Currently it _only_ generates `Accessibility` payloads, and will generate the same allow settings (i.e. Allow/Deny the app control) for any apps specified.

## Requires
1. python 2.7.10 (as tested on)
1. `/usr/bin/codesign`
1. The application the profile is generated for to be installed on the machine this is run on.

## Tested on
macOS 10.12.6 (should work on any recent macOS release)

## Usage:
1. `git clone https://github.com/carlashley/tccprofile`
1. `cd tccprofile && chmod +x tccprofile.py`
1. `./tccprofile --help`

Example:
```
./tccprofile.py -a /Applications/Automator.app --allow --payload-description="Whitelist Apps" --payload-identifier="com.github.carlashley" --payload-name="TCC Whitelist" --payload-org="My Great Company" --payload-version="1" -o TCC_Accessibility_Profile_20180816_v1.mobileconfig
```

To sign:
```
./tccprofile.py -a /Applications/Automator.app --allow --payload-description="Whitelist Apps" --payload-identifier="com.github.carlashley" --payload-name="TCC Whitelist" --payload-org="My Great Company" --payload-version="1" -o TCC_Accessibility_Profile_20180816_v1.mobileconfig --sign="Certificate Name"
```
