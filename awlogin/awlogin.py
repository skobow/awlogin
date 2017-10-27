""" awlogin """

# Import required modules
from __future__ import print_function
import os
import sys
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

SKELETON_CONF = "[<PROFILE>]\n"+ \
                "aws_access_key_id = AKERNEIDUFENICUQ3NDO\n"+ \
                "aws_secret_access_key = ilsjkasdUEwlwDUgvD1b7234Fn/lepi0ACmk8upFy\n"

def print_usage():
    """ Display program usage """
    print("AWS Secure CLI MFA Logon Utility v" + __version__ + "\n" + \
        "Usage: " + whi1(PROG_NAME) + " PROFILE TOKEN\n\n" + \
        whi1(PROG_NAME) + " -l              List all account profiles in " + AWS_CREDS_FILEC + "\n" + \
        whi1(PROG_NAME) + " -h              Show additional help information")
    sys.exit(1)


def print_help():
    """ Display additional information """
    print("This utility facilitates secured CLI MFA authentication to any AWS account\n" + \
        "profile defined in " + AWS_CREDS_FILEC + ". It expects that file to be formatted\n" + \
        "in the following sample manner:\n\n" + \
        SKELETON_CONF + \
        "\n1. " + whi1('<PROFILE>') + "hold credentials for your AWS account" + \
        "\n2. A valid key value pair" + whi1('has to be') + "defined for", whi1('<PROFILE>') + \
        "\n3. The -c switch can create a fresh skeleton " + AWS_CREDS_FILEC + "file\n" + \
        "\nYou can also provide the Amazon Rescource Name (ARN) by exporting AWS_MFA_DEVICE_ARN")

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

    # Ensure that specified section exists
    if not cfg.has_section(profile):
        print("Profile", red2(profile), "does not exist in", AWS_CREDS_FILEC)
        sys.exit(1)

    # Ensure specified profile section has mandatory entries
    if 'aws_access_key_id' not in cfg.options(profile) or \
       'aws_secret_access_key' not in cfg.options(profile):
        print("Profile", red2(profile), "is missing one or both credentials key entry")
        sys.exit(1)

    return profile


def logon_to_aws(profile, token):
    """ Logon to AWS account designated by given profile, with given token """
    # In order to make any initial AWS API call we have to use the default profile credentials
    cfg = ConfigParser()
    cfg.read(AWS_CREDS_FILE)
    os.environ['AWS_REGION']            = get_aws_region()
    os.environ['AWS_ACCESS_KEY_ID']     = cfg.get(profile, 'aws_access_key_id')
    os.environ['AWS_SECRET_ACCESS_KEY'] = cfg.get(profile, 'aws_secret_access_key')

    if os.environ.has_key('AWS_MFA_DEVICE_ARN'):
        mfa_device_arn = os.environ['AWS_MFA_DEVICE_ARN']
    else:
        try:
            mfa_device_arn = raw_input("MFA device arn:")
        except KeyboardInterrupt:
            sys.exit(1)

    # Do either main or federated account login, based on profile
    response = None
    client = boto3.client('sts')
    try:
        response = client.get_session_token(
            DurationSeconds=86400,SerialNumber=mfa_device_arn,TokenCode=token
        )
    except Exception as e:
        print(e)
        sys.exit(1)

    # Actual logon = update environment variables with newly acquired credentials
    if response:
        write_default_profile(profile + '_mfa', cfg, response['Credentials'])
        sys.exit(0)


def write_default_profile(mfa_profile, cfg, credentials):
    if not cfg.has_section(mfa_profile):
        cfg.add_section(mfa_profile)

    cfg.set(mfa_profile, 'aws_access_key_id', credentials['AccessKeyId'])
    cfg.set(mfa_profile, 'aws_secret_access_key', credentials['SecretAccessKey'])
    cfg.set(mfa_profile, 'aws_session_token', credentials['SessionToken'])

    with open(AWS_CREDS_FILE, 'wb') as credentials_file:
        cfg.write(credentials_file)


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
    logon_to_aws(profile, token)


def main(args=None):
    """ Main program """
    parse_arguments(sys.argv)
    sys.exit(0)


if __name__ == '__main__':
    main()
