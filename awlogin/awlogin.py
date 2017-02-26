""" awlogin """

# Import required modules
from __future__ import print_function
import os
import sys
import subprocess
from version import __version__

try:
    from configparser import ConfigParser  # For Python > 3.0
except ImportError:
    from ConfigParser import ConfigParser  # For Python < 3.0

# String colorization functions (defined as early as possible)
def whi2(string):
    return '\033[1;37m' + string + '\033[0m'

def whi1(string):
    return '\033[0;37m' + string + '\033[0m'

def red2(string):
    return '\033[1;31m' + string + '\033[0m'


# Ensure these additional modules are also installed
try: 
    import boto3
except ImportError: 
    print("Missing", whi1('boto3'), "module. Do", whi1('sudo pip install boto3'), "to install.")
    sys.exit(1)

# Global variables
PROG_NAME = 'awlogin'
AWS_CONFIG_FILE = os.path.join(os.environ['HOME'], '.aws/config')
AWS_CREDS_FILE  = os.path.join(os.environ['HOME'], '.aws/credentials')
AWS_CREDS_FILEC = whi1('~/.aws/credentials')
SKELETON_CONF = "[default]\n"+ \
                "profile_name = stag\n"+ \
                "aws_access_key_id = AKERNEIDUFENICUQ3NDO\n"+ \
                "aws_secret_access_key = ilsjkasdUEwlwDUgvD1b7234Fn/lepi0ACmk8upFy\n\n"+ \
                "[prod]\n"+ \
                "profile_name = prod\n"+ \
                "account_number = 544492114123\n"+ \
                "user_role = PowerUser\n"


def print_usage():
    """ Display program usage """
    print("AWS Secure CLI MFA Logon Utility v" + __version__ + "\n" + \
        whi1(PROG_NAME) + " PROFILE TOKEN   Logon to account PROFILE using 6-digit TOKEN\n" + \
        whi1(PROG_NAME) + " -l              List all account profiles in " + AWS_CREDS_FILEC + "\n" + \
        whi1(PROG_NAME) + " -c              Create skeleton " + AWS_CREDS_FILEC + " file\n" + \
        whi1(PROG_NAME) + " -h              Show additional help information")
    sys.exit(1)


def print_help():
    """ Display additional information """
    print("This utility facilitates secured CLI MFA authentication to any AWS account\n" + \
        "profile defined in " + AWS_CREDS_FILEC + ". It expects that file to be formatted\n" + \
        "in the following sample manner:\n\n" + \
        SKELETON_CONF + \
        "\nSo ..." + \
        "\n1. The", whi1('default'), "profile is for your main AWS account, where your users are stored" + \
        "\n2. All other profiles are treated as", whi1('federated'), "AWS accounts you may have access to" + \
        "\n3. You", whi1('must'), "defined a valid key pair for your", whi1('default'), "profile" + \
        "\n4. Each profile must have a unique", whi1('profile_name'), "so this utility can identify it" + \
        "\n5. Each federated profile must have a valid", whi1('account_number'), "and", whi1('user_role') + \
        "\n6. The -c switch can create a fresh skeleton", AWS_CREDS_FILEC, "file")
    sys.exit(1)


def create_skeleton_config():
    """ Create basic configuration file """
    if os.path.isfile(AWS_CREDS_FILE):
        print("File", red2(AWS_CREDS_FILE), "already exists.")
    else:
        with open(AWS_CREDS_FILE, 'w') as f:
            f.write(SKELETON_CONF)
    sys.exit(0)


def list_accounts():
    """ Dispaly list of account profiles in configuration file """
    cfg = ConfigParser()
    cfg.read(AWS_CREDS_FILE)
    for sect in cfg.sections():
        print("[%s]" % (whi2(sect)))
        for key,val in cfg.items(sect):
            print("%-21s = %s" % (key, val))  # Justified print for easier reading
        print('')
    sys.exit(0)


def validate_config(profile):
    """ Check configuration file for anomalies """
    cfg = ConfigParser()
    cfg.read(AWS_CREDS_FILE)

    # Ensure there is only one default profile section
    count = 0
    for s in cfg.sections():
        if s == 'default':
            count += 1
    if count > 1:
        print("Too many", red2('default'), "profiles in", AWS_CREDS_FILEC)
        sys.exit(1)

    # Ensure default profile section has mandatory entries
    if 'aws_access_key_id' not in cfg.options('default') or \
       'aws_secret_access_key' not in cfg.options('default'):
        print("Profile", red2('default'), "is missing one or both credentials key entry")
        sys.exit(1)

    # Locate profile section by matching user-specified profile with profile_name entry
    count = 0
    selected_profile = ''
    for sect in cfg.sections():
        if 'profile_name' in cfg.options(sect):
            if profile.lower() == cfg.get(sect, 'profile_name').lower():
                selected_profile = sect
                count += 1
    if count > 1:
        print("Profile name", red2(profile), "is defined multiple times.")
        sys.exit(1)     
    if count == 0:
        print("Profile name", red2(profile), "is not defined in", AWS_CREDS_FILEC)
        sys.exit(1)

    return selected_profile


def logon_to_aws(profile, token):
    """ Logon to AWS account designated by given profile, with given token """
    # In order to make any initial AWS API call we have to use the default profile credentials
    cfg = ConfigParser()
    cfg.read(AWS_CREDS_FILE)
    os.environ['AWS_REGION']            = get_aws_region()
    os.environ['AWS_ACCESS_KEY_ID']     = cfg.get('default', 'aws_access_key_id')
    os.environ['AWS_SECRET_ACCESS_KEY'] = cfg.get('default', 'aws_secret_access_key')

    # Get main account username. Also an implicit validation of the keys in default profile
    resource = boto3.resource('iam')
    try:
        username = resource.CurrentUser().user_name
    except Exception:
        print("Error with AWS keys in", red2('default'), "profile.")
        sys.exit(1)

    # Get main account ID
    # This is one of multiple ways to get the user's AWS account ID
    client = boto3.client('iam')
    main_account_id = client.get_user()['User']['Arn'].split(':')[4]

    # Derived MFA Device ARN
    mfa_device_arn = 'arn:aws:iam::' + main_account_id + ':mfa/' + username

    # Do either main or federated account login, based on profile
    response = None
    client = boto3.client('sts')
    if profile == 'default':
        try:
            response = client.get_session_token(
                DurationSeconds=86400,SerialNumber=mfa_device_arn,TokenCode=token
            )
        except Exception as e:
            print(e)
            sys.exit(1)
    else:
        target_account_id = cfg.get(profile, 'account_number')
        user_role = cfg.get(profile, 'user_role')
        role_arn = 'arn:aws:iam::' + target_account_id + ':role/' + user_role
        try:
            response = client.assume_role(
                RoleArn=role_arn,RoleSessionName=username,DurationSeconds=3600,
                SerialNumber=mfa_device_arn,TokenCode=token
            )
        except Exception as e:
            print(e)
            sys.exit(1)

    # Actual logon = update environment variables with newly acquired credentials
    if response:
        os.environ['AWS_ACCESS_KEY_ID']     = response['Credentials']['AccessKeyId']
        os.environ['AWS_SECRET_ACCESS_KEY'] = response['Credentials']['SecretAccessKey']
        os.environ['AWS_SESSION_TOKEN']     = response['Credentials']['SessionToken']
        subprocess.call('bash')  # Exit to a new shell
        sys.exit(0)


def get_aws_region():
    """ Get the AWS region based on existing values """
    AWS_REGION = ''
    # Start by checking the environment variables (order is important)
    if os.environ.get('AWS_REGION'):
        AWS_REGION = os.environ.get('AWS_REGION')
    elif os.environ.get('AMAZON_REGION'):
        AWS_REGION = os.environ.get('AMAZON_REGION')
    elif os.environ.get('AWS_DEFAULT_REGION'):
        AWS_REGION = os.environ.get('AWS_DEFAULT_REGION')
    else:
        # End by checking the AWS config file
        if not os.path.isfile(AWS_CONFIG_FILE):  
            print("AWS_REGION variable is not defined, and", AWS_CONFIG_FILE, "file does not exist.")
            sys.exit(1)
        cfg = ConfigParser()
        cfg.read(AWS_CONFIG_FILE)
        AWS_REGION = cfg.get('default', 'region')

    if AWS_REGION == '':
        print("AWS_REGION variable is not defined anywhere.")
        sys.exit(1)
    return AWS_REGION


def parse_arguments(argv):
    """ Parse arguments """    
    args = len(argv) - 1
    if args == 1:
        if argv[1] == '-c': # Create skeleton config file
            create_skeleton_config()
        elif argv[1] == '-l': # List defined account profiles
            list_accounts()
        elif argv[1] == '-h': # Print additional info
            print_help()
        else:
            print_usage()
    elif args != 2: # Print usage if not exactly 2 arguments (Account and Token)
        print_usage()

    profile = argv[1] # Account profile in config that user wants to logon into
    token = argv[2] # 6-digit token from the user's MFA device

    if len(token) != 6 and not token.isdigit():
        print("Token", red2(token), "is invalid.")
        sys.exit(1)

    # Validate credentials file settings, locate selected profile, then logon
    selected_profile = validate_config(profile)
    logon_to_aws(selected_profile, token)


def main(args=None):
    """ Main program """
    parse_arguments(sys.argv)
    sys.exit(0)


if __name__ == '__main__':
    main()
