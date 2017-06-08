## awlogin
This utility simplifies AWS MFA logons from the command line.

This is the Python version. For the GoLang version go to https://github.com/lencap/awlogin-go. Writing it in two different languages was done to get more familiar with each language, but also with the respective AWS SDK.

This utilility allows CLI MFA authentication to any AWS account profile defined in `~/.aws/credentials`, but it expects that file to be formatted using 3 additional variables (read more below). Below is a example of how the `~/.aws/credentials` file should be formatted:

<pre><code>
[default]
profile_name = stag
aws_access_key_id = AKERNEIDUFENICUQ3NDO
aws_secret_access_key = ilsjkasdUEwlwDUgvD1b7234Fn/lepi0ACmk8upFy

[prod]
profile_name = prod
account_number = 544492114123
user_role = PowerUser

[accountN]
profile_name = accountN
account_number = 012345114123
user_role = Administrator
</code></pre>

Note that you can also read above and below information by running `awlogin -h`.

In short, the formatting means that:
  1. The **default** profile is for your main AWS account, where your users are stored
  2. All other profiles are treated as **federated** AWS accounts that you may have access to
  3. You **must** defined a valid key pair for your **default** profile
  4. Each profile must have a unique **profile_name** so this utility can identify it
  5. Each federated profile must have a valid **account_number** and **user_role**
  6. The `-c` switch can create a fresh skeleton `~/.aws/credentials` file

**NOTE:** This utility introduces and uses three new special variables (profile_name, account_number, and user_role) without breaking any of the original AWS `~/.aws/credentials` file functionality. If you find that it does, please let me know.

## Installation
  1. `pip install .`
  2. To reinstall after a recent code update do: `pip install --upgrade --no-deps --force-reinstall .`

## Usage
To logon to one of your accounts run `awlogin stag TOKEN` where **stag** is one of the **profile_name** defined in your `~/.aws/credentials` file, and **TOKEN** is a 6-digit number from your MFA device. If the logon is successful, it will drop you into a **subshell** from where you can run **awscli** commands. To further verify you've logged on, you can run `env | grep AWS` to view the **AWS_SESSION_TOKEN** environment variable that were generated for this specific session.

Once you're done with your work, you can exit this subshell to return to your original shell. **Note that you can run this utility in different shell windows, thus allowing you the capability to logon to multiple accounts at the same time.**
  
### Usage shell output
<pre><code>
$ awlogin
AWS CLI MFA Logon Utility v1.4.2
awlogin PROFILE TOKEN   Logon to account PROFILE using 6-digit TOKEN
awlogin -l              List all account profiles in ~/.aws/credentials
awlogin -c              Create skeleton ~/.aws/credentials file
awlogin -h              Show additional help information
</code></pre>

## Development notes
To test run the program as soon as you clone the code, or as you make changes, you can use `python -m awlogin` from the root of the working directory.

This utility uses the Python **boto3** SDK for AWS (see http://boto3.readthedocs.io/en/latest/guide/configuration.html)
