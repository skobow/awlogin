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
def whi2 (s):
  return '\033[1;37m' + s + '\033[0m'

def whi1 (s):
  return '\033[0;37m' + s + '\033[0m'

def red2 (s):
  return '\033[1;31m' + s + '\033[0m'


# Ensure these additional modules are also installed
try: 
  import boto3
except ImportError: 
  print("Missing", whi1('boto3'), "module. Do", whi1('sudo pip install boto3'), "to install.")
  sys.exit(1)

# Global variables
ProgName      = 'awlogin'
AWSConfigFile = os.environ['HOME'] + '/.aws/config'
AWSCredsFile  = os.environ['HOME'] + '/.aws/credentials'
AWSCredsFileC = whi1('~/.aws/credentials')
SkeletonConf  = "[default]\n"+ \
                "profile_name = stag\n"+ \
                "aws_access_key_id = AKERNEIDUFENICUQ3NDO\n"+ \
                "aws_secret_access_key = ilsjkasdUEwlwDUgvD1b7234Fn/lepi0ACmk8upFy\n\n"+ \
                "[prod]\n"+ \
                "profile_name = prod\n"+ \
                "account_number = 544492114123\n"+ \
                "user_role = PowerUser\n"


def print_usage ():
  print("AWS Secure CLI MFA Logon Utility v" + __version__ + "\n" + \
        whi1(ProgName) + " PROFILE TOKEN   Logon to account PROFILE using 6-digit TOKEN\n" + \
        whi1(ProgName) + " -l              List all account profiles in " + AWSCredsFileC + "\n" + \
        whi1(ProgName) + " -c              Create skeleton " + AWSCredsFileC + " file\n" + \
        whi1(ProgName) + " -h              Show additional help information")
  sys.exit(1)


def print_help ():
  print("This utility facilitates secured CLI MFA authentication to any AWS account\n" + \
        "profile defined in " + AWSCredsFileC + ". It expects that file to be formatted\n" + \
        "in the following sample manner:\n\n" + \
        SkeletonConf + \
        "\nSo ..." + \
        "\n1. The", whi1('default'), "profile is for your main AWS account, where your users are stored" + \
        "\n2. All other profiles are treated as", whi1('federated'), "AWS accounts you may have access to" + \
        "\n3. You", whi1('must'), "defined a valid key pair for your", whi1('default'), "profile" + \
        "\n4. Each profile must have a unique", whi1('profile_name'), "so this utility can identify it" + \
        "\n5. Each federated profile must have a valid", whi1('account_number'), "and", whi1('user_role') + \
        "\n6. The -c switch can create a fresh skeleton", AWSCredsFileC, "file")
  sys.exit(1)


def create_skeleton_config ():
  if os.path.isfile(AWSCredsFile):
    print("File", red2(AWSCredsFile), "already exists.")
  else:
    with open(AWSCredsFile, 'w') as f:
      f.write(SkeletonConf)
  sys.exit(0)


def list_accounts ():
  cfg = ConfigParser()
  cfg.read(AWSCredsFile)
  for sect in cfg.sections():
    print("[%s]" % (whi2(sect)))
    for key,val in cfg.items(sect):
      print("%-21s = %s" % (key, val))  # Justified print for easier reading
    print('')
  sys.exit(0)


def validate_config (Profile):
  cfg = ConfigParser()
  cfg.read(AWSCredsFile)

  # Ensure there is only one default profile section
  Count = 0
  for s in cfg.sections():
    if s == 'default':
      Count += 1
  if Count > 1:
    print("Too many", red2('default'), "profiles in", AWSCredsFileC)
    sys.exit(1)

  # Ensure default profile section has mandatory entries
  if 'aws_access_key_id' not in cfg.options('default') or \
     'aws_secret_access_key' not in cfg.options('default'):
    print("Profile", red2('default'), "is missing one or both credentials key entry")
    sys.exit(1)

  # Locate profile section by matching user-specified profile with profile_name entry
  Count = 0
  SelectedProfile = ''
  for sect in cfg.sections():
    if 'profile_name' in cfg.options(sect):
      if Profile.lower() == cfg.get(sect, 'profile_name').lower():
        SelectedProfile = sect
        Count += 1
  if Count > 1:
    print("Profile name", red2(Profile), "is defined multiple times.")
    sys.exit(1)     
  if Count == 0:
    print("Profile name", red2(Profile), "is not defined in", AWSCredsFileC)
    sys.exit(1)

  return SelectedProfile


def logon_to_aws (Profile, Token):
  # In order to make any initial AWS API call we have to use the default profile credentials
  cfg = ConfigParser()
  cfg.read(AWSCredsFile)
  os.environ['AWS_REGION']            = get_aws_region()
  os.environ['AWS_ACCESS_KEY_ID']     = cfg.get('default', 'aws_access_key_id')
  os.environ['AWS_SECRET_ACCESS_KEY'] = cfg.get('default', 'aws_secret_access_key')

  # Get main account UserName. Also an implicit validation of the keys in default profile
  resource = boto3.resource('iam')
  try:
    UserName = resource.CurrentUser().user_name
  except Exception:
    print("Error with AWS keys in", red2('default'), "profile.")
    sys.exit(1)

  # Get main account ID
  # This is one of multiple ways to get the user's AWS account ID
  client = boto3.client('iam')
  MainAccountId = client.get_user()['User']['Arn'].split(':')[4]

  # Derived MFA Device ARN
  MFADeviceARN = 'arn:aws:iam::' + MainAccountId + ':mfa/' + UserName

  # Do either main or federated account login, based on Profile
  response = None
  client   = boto3.client('sts')
  if Profile == 'default':
    try:
      response = client.get_session_token(
        DurationSeconds=86400,SerialNumber=MFADeviceARN,TokenCode=Token
      )
    except Exception as e:
      print(e)
      sys.exit(1)
  else:
    TargetAccountId = cfg.get(Profile, 'account_number')
    UserRole        = cfg.get(Profile, 'user_role')
    RoleARN         = 'arn:aws:iam::' + TargetAccountId + ':role/' + UserRole
    try:
      response = client.assume_role(
        RoleArn=RoleARN,RoleSessionName=UserName,DurationSeconds=3600,
        SerialNumber=MFADeviceARN,TokenCode=Token
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


def get_aws_region ():
  AWSRegion = ''
  # Start by checking the environment variables (order is important)
  if os.environ.get('AWS_REGION') == None:
    if os.environ.get('AMAZON_REGION') == None:
      if os.environ.get('AWS_DEFAULT_REGION') == None:
        # End with checking the AWS config file
        if not os.path.isfile(AWSConfigFile):  
          print("AWS_REGION variable is not defined, and", AWSConfigFile, "file does not exist.")
          sys.exit(1)
        cfg = ConfigParser()
        cfg.read(AWSConfigFile)
        AWSRegion = cfg.get('default', 'region')

  if AWSRegion == '':
    print("AWS_REGION variable is not defined anywhere.")
    sys.exit(1)       # Exit if it's not defined anywhere
  return AWSRegion


def parse_arguments (argv):
  args = len(argv) - 1
  if args == 1:
    if argv[1] == '-c':     # Create skeleton config file
      create_skeleton_config()
    elif argv[1] == '-l':   # List defined account profiles
      list_accounts()
    elif argv[1] == '-h':   # Print additional info
      print_help()
    else:
      print_usage()
  elif args != 2:               # Print usage if not exactly 2 arguments (Account and Token)
    print_usage()

  profile = argv[1]  # Account profile in config that user wants to logon into
  token   = argv[2]  # 6-digit token from the user's MFA device

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
