## awlogin
Command line utility to facilitate AWS Secure CLI MFA Logons.

After installing run `awlogin -h` to understand how this works.

## Installation
  1. `git clone git@github.com:lencap/awlogin`
  2. `cd awlogin`
  3. `pip install .` Note the period (`.`) at the end.
  4. To reinstall after a recent code update do: `pip install --upgrade --no-deps --force-reinstall .`

## Usage

### Usage shell output
<pre><code>
$ awlogin
AWS Secure CLI MFA Logon Utility v1.4.2
awlogin PROFILE TOKEN   Logon to account PROFILE using 6-digit TOKEN
awlogin -l              List all account profiles in ~/.aws/credentials
awlogin -c              Create skeleton ~/.aws/credentials file
awlogin -h              Show additional help information
</code></pre>

## Development notes
To test run the program as soon as you clone the code or as you make changes you can use `python -m awlogin` from the root of the working directory.
