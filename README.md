## awlogin

_This is a fork of https://github.com/lencap/awlogin._

This utility simplifies AWS MFA logons from the command line.

This utilility allows CLI MFA authentication to any AWS account profile defined in `~/.aws/credentials`.
It expects that you have already define a profile that should be used for MFA authentication.
<pre><code>
[<PROFILE>]
aws_access_key_id = AKERNEIDUFENICUQ3NDO
aws_secret_access_key = ilsjkasdUEwlwDUgvD1b7234Fn/lepi0ACmk8upFy

</code></pre>

Note that you can also read above and below information by running `awlogin -h`.

**NOTE:** This utility modifies youe `~/.aws/credentials` file, so be sure to back it up before using this tool!

## Installation
  1. `pip install .`
  2. To reinstall after a recent code update do: `pip install --upgrade --no-deps --force-reinstall .`

## Usage
### Usage shell output
<pre><code>
$ awlogin
AWS CLI MFA Logon Utility v1.0.0
Usage: awlogin PROFILE TOKEN   Logon to account PROFILE using 6-digit TOKEN

awlogin -l              List all account profiles in ~/.aws/credentials
awlogin -c              Create skeleton ~/.aws/credentials file
awlogin -h              Show additional help information
</code></pre>

## Development notes
This utility uses the Python **boto3** SDK for AWS (see http://boto3.readthedocs.io/en/latest/guide/configuration.html)
