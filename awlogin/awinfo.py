""" awinfo """

# Import required modules
import sys
import os
import shutil
import socket
import signal
import json
import time
import datetime
from version import __version__

try:
  from configparser import ConfigParser  # For Python > 3.0
except ImportError:
  from ConfigParser import ConfigParser  # For Python < 3.0

# String colorization functions (defined as early as possible)
def whi (s):
  return '\033[0;37m' + s + '\033[0m'

def red (s):
  return '\033[1;31m' + s + '\033[0m'

# Ensure these additional modules are also installed
try: 
  import boto3
except ImportError: 
  print "Missing", whi('boto3'), "module. Do", whi('sudo pip install boto3'), "to install."
  sys.exit(1)
try: 
  import requests
except ImportError: 
  print "Missing", whi('requests'), "module. Do", whi('sudo pip install requests'), "to install."
  sys.exit(1)

# Global variables
PROG_NAME = 'awinfo'
PROG_CONF_DIR = os.path.join(os.environ['HOME'], '.' + PROG_NAME)
AWS_CONFIG_FILE = os.path.join(os.environ['HOME'], '.aws/config')
AWS_CREDS_FILE = os.path.join(os.environ['HOME'], '.aws/credentials')
AWS_REGION = ''
AWS_ACCOUNT_ID = ''
AWS_ACCOUNT_ALIAS = ''
DNS_DATAFILE = 'dns.json'
ZONE_DATAFILE = 'zone.json'
ELB_DATAFILE = 'elb.json'
INSTANCE_DATAFILE = 'inst.json'
STACK_DATAFILE = 'stack.json'
# Hard-coded S3 bucket value. You need to update this to the bucket name you'll be
# using for this program. You'll also want to setup a scheduled job to update that bucket
# by running this program periodically with the -3 switch (see hidden option below)
S3_BUCKET = 'awinfo'
S3_URL_BASE = 'https://s3.amazonaws.com/awinfo'
API_SECONDS_DELAY = 1


# AWS's 'datetime' variables are not serializable with the json module
# This serializes them by converting them to an ISO format string
json.JSONEncoder.default = lambda self,obj: (obj.isoformat() if isinstance(obj, datetime.datetime) else None)


# Capture CTRL-C interrupt for a more graceful exit without errors
def ctrlc_handler(signal, frame):
    sys.exit(1)


signal.signal(signal.SIGINT, ctrlc_handler)


def PrintUsage ():
  print "AWS CLI Information Utility " + __version__ + "\nUSAGE\n" + \
    whi(PROG_NAME) + " -u            Update local stores with current AWS account records\n" + \
    whi(PROG_NAME) + " -x            Delete local data store files to start afresh\n" + \
    whi(PROG_NAME) + " -z  [STRING]  List zones with optional STRING in name\n" + \
    whi(PROG_NAME) + " -d  [STRING]  List DNS records with optional STRING in name|value|zoneID\n" + \
    whi(PROG_NAME) + " -e  [STRING]  List ELBs with optional STRING in name|DNSName|instanceIds\n" + \
    whi(PROG_NAME) + " -es [STRING]  List ELB SSL certs with optional STRING in DNSName|Cert\n" + \
    whi(PROG_NAME) + " -eh [STRING]  List ELB health-checks with optional STRING in DNSName|Target\n" + \
    whi(PROG_NAME) + " -i  [STRING]  List EC2 instances with optional STRING in name|id|type|state|ip\n" + \
    whi(PROG_NAME) + " -s  [STRING]  List CloudFormation stacks with optional STRING in name|status\n" + \
    whi(PROG_NAME) + " -sv [STRING]  List CloudFormation stacks, and show all parameters\n" + \
    whi(PROG_NAME) + " DNSRECORD     Print IPs/ELB/instances breakdown for given DNSRECORD"
    # Hidden option to be used by a scheduled process
    # whi(PROG_NAME) + " -3           Copy local stores to S3 bucket (view code for more info)\n" + \
  sys.exit(1)


def WriteListToFile (List, StoreFile):
  LocalFile = PROG_CONF_DIR + '/' + StoreFile   # Note PROG_CONF_DIR is global
  with open(LocalFile,'wb') as f:
    try:
      json.dump(List, f)
    except:
      print "Error writing file %s" % (whi(LocalFile))
      sys.exit(1)


def ReadListFromFile (StoreFile):
  # Lets read and get the list from the S3 store if it's newer
  S3FileURL = S3_URL_BASE + '/' + StoreFile
  response  = requests.head(S3FileURL)
  if response.status_code == 200:
    # LOCALFILE: Get last modified time in epoch seconds to ease comparison below
    LocalFile     = PROG_CONF_DIR + '/' + StoreFile
    if os.path.isfile(LocalFile):
      LocalFileDate = os.path.getmtime(LocalFile)                     # Get date in local TZ epoch seconds
    else:
      LocalFileDate = 1                                               # If missing file, set to 1 epoch second
    LocalFileDate = datetime.datetime.utcfromtimestamp(LocalFileDate) # Convert to UTC datetime object
    LocalFileDate = int(LocalFileDate.strftime('%s'))                 # Convert datetime to epoc seconds integer

    # S3FILE: Get last modified time in epoch seconds integer to ease comparison below
    LastModified = response.headers['Last-Modified']
    S3FileDate   = int(datetime.datetime.strptime(LastModified, '%a, %d %b %Y %H:%M:%S %Z').strftime('%s'))

    # Use S3 file if it's newer
    if S3FileDate > LocalFileDate:
      response = requests.get(S3FileURL)
      if response.status_code == 200:
        try:
          List = response.json()
          WriteListToFile(List,StoreFile)  # Also replace local file store with this newer set
          return List                      # Return this newer set
        except:
          print "Error decoding JSON file %s" % (red(S3FileURL))
      else:
        print "Error retrieving %s" % (red(S3FileURL))

  # Else, let's just read and get the list from the local file store
  List = []  # Assume it's empty
  LocalFile = PROG_CONF_DIR + '/' + StoreFile   # Note PROG_CONF_DIR is global
  if os.path.isfile(LocalFile):
    with open(LocalFile,'r') as f:
      try:
        List = json.load(f)
      except:
        pass   # Do nothing if the file is empty, which will simply returns the empty list
  return List


def ListZones (Filter):
  for z in ReadListFromFile(ZONE_DATAFILE):
    if Filter == None or \
       Filter in z['Name'].lower() or \
       Filter in z['Id'].lower():
      zName = z['Name'].strip('.')          # Cleanup useless suffix
      zType = 'public'
      if z['Config']['PrivateZone']:
        zType = 'private'
      print "%-44s  %-8s  %6d  %-30s" % (zName, zType, z['ResourceRecordSetCount'], z['Id'])


def UpdateLocalZoneStoreFromAWS ():
  print "Updating local DNS zone store"
  ZoneList = ReadListFromFile(ZONE_DATAFILE)   # Start with existing local store set

  # Remove all existing zones for this AWS account, since we want to replace them
  ZoneList = [zone for zone in ZoneList if zone['AccountId'] != AWS_ACCOUNT_ID]

  # Now add all zones for this AWS account
  for zone in GetZoneListFromAWS():

    # NOTE we modify the default AWS JSON record by adding these attributes for our purpose
    zone['AccountId']    = AWS_ACCOUNT_ID
    zone['AccountAlias'] = AWS_ACCOUNT_ALIAS

    # Add this record to the list
    ZoneList.append(zone)

  # Replace local file store with this newer set
  WriteListToFile (ZoneList, ZONE_DATAFILE)


def GetZoneListFromAWS ():
  ZoneList   = []
  client     = boto3.client('route53', region_name=AWS_REGION)
  response   = []
  NextMarker = ''
  TheresMore = True

  # Loop requests, in case there are more than MaxItems records or we're being throttled by AWS
  while TheresMore:
    try:
      if 'IsTruncated' in response and response['IsTruncated'] != None:
        # 100 MaxItems is an AWS limit
        response = client.list_hosted_zones(MaxItems='100',Marker=NextMarker)
      else:
        response = client.list_hosted_zones(MaxItems='100')
    except Exception as ErrorString:
      if BeingThrottled(ErrorString):
        time.sleep(1)                 # Being throttled, sleep for 1 second
        continue                      #   then continue the while loop
      print "\n", ErrorString         # Exit if it's a non-throttling error
      sys.exit(1)

    # Add this batch of zone records to our list
    for zone in response['HostedZones']:
      ZoneList.append(zone)

    if response['IsTruncated'] == False:
      TheresMore = False  # Setup to break out of the loop because there's no more data from AWS
    else:
      NextMarker = response['NextMarker']

  return ZoneList


def ListDNSRecs (Filter):
  for dns in ReadListFromFile(DNS_DATAFILE):
    Type       = ''
    Count      = 0
    ValuesList = []
    Values     = ''
    # Check only for CNAME and A records. Skip all others types
    if dns['Type'] == 'CNAME':
      Type  = 'CNAME'            # CNAMEs only have 1 value, index 0
      Count = 1
      ValuesList.append(dns['ResourceRecords'][0]['Value'].strip('.'))  # Trim superfluous suffixes
    elif dns['Type'] == 'A':     # Decipher regular 'A' from AWS 'A Alias' record
      if 'AliasTarget' in dns:   # If there's a pointer, then the value
        Type  = 'ALIAS'          # is an AWS ALIAS record (our own identifying convention)
        Count = 1
        ValuesList.append(dns['AliasTarget']['DNSName'].strip('dualstack').strip('.'))
        # Also trim superfluous pre/suffixes ^^
      else:
        Type  = 'A'                          # It's a regular A record
        Count = len(dns['ResourceRecords'])  # Get the number of values (IPs)
        for i in range(Count):
          ValuesList.append(dns['ResourceRecords'][i]['Value'])
    else:
      continue                       # Skip all other DNS record types
    Ttl = '-'                        # Assume no TTL
    if 'TTL' in dns:                 # If there's a pointer then there's a TTL value
      Ttl = str(dns['TTL'])          # Convert it to string

    for i in range(Count):           # Put all values in one single string
      Values += ValuesList[i] + ' '
    Values.strip()

    if Filter == None or \
       Filter in dns['Name'].lower() or \
       Filter in Values.lower() or \
       Filter in Type.lower() or \
       Filter in Ttl.lower() or \
       Filter in dns['ZoneId'].lower():
      # Notice we don't actually display d.ZoneID but we do filter by it
      print "%-60s  %-8s  %6s  %-2d  %s" % (dns['Name'].strip('.'), Type, Ttl, Count, Values)


def BreakdownDNS (DNSName):
  # Do DNS search thru every CNAME until we find an A record
  addresses = ''
  IsaCName = True
  while IsaCName:
    try:
      addresses = socket.gethostbyname_ex(DNSName)
    except Exception as ErrorString:
      print ErrorString
      sys.exit(1)
    # NOTE that we overwrite/update passed DNSName variable here
    DNSName = addresses[0].split('dualstack.').pop()
    cName = None
    try:
      cName = addresses[1][0]    # Fails if empty, indicating no more CNAME
    except:
      IsaCName = False 

  # Print IP addresses of last A record
  print "    ".join(addresses[2])

  # Check if DNS record for last CNAME exists in local store
  LastCNAMEDNS = None   # Assume it's not
  for d in ReadListFromFile(DNS_DATAFILE):
    if d['Name'].lower().strip('.') == DNSName.lower().strip('.'):
      LastCNAMEDNS = d
      break             # If we find it, break out of the for-loop

  # See if it's an AWS Alias pointing to an ELB
  if LastCNAMEDNS != None and 'AliasTarget' in LastCNAMEDNS:
    BreakdownELB(LastCNAMEDNS['AliasTarget']['DNSName'].strip('dualstack').strip('.'))
  else:
    BreakdownELB(DNSName)


def GetDNSByZoneIdFromAWS (zoneId):
  DNSList    = []
  client     = boto3.client('route53', region_name=AWS_REGION)
  response   = []
  NextRecord = ''
  TheresMore = True

  # Loop requests, in case there are more than MaxItems records or we're being throttled by AWS
  while TheresMore:
    try:
      if 'IsTruncated' in response and response['IsTruncated'] != None:
        # 100 MaxItems is an AWS limit
        response = client.list_resource_record_sets(HostedZoneId=zoneId,MaxItems='100',StartRecordName=NextRecord)
      else:
        response = client.list_resource_record_sets(HostedZoneId=zoneId,MaxItems='100')
    except Exception as ErrorString:
      if BeingThrottled(ErrorString):
        print "\nBeing throttled by AWS. Sleeping for 3 minutes, then trying again."
        time.sleep(180)
        continue
      else:
        print "\nUnknown error while calling client.list_resource_record_sets():\n%s" % (ErrorString)
        print "Let's try again..."
        continue

    # Add this batch of DNS records to our list
    for dns in response['ResourceRecordSets']:
      DNSList.append(dns)

    if response['IsTruncated'] == False:
      TheresMore = False  # Setup to break out of the loop because there's no more data from AWS
    else:
      NextRecord = response['NextRecordName']
      time.sleep(API_SECONDS_DELAY)   # Slow down request time between getting pages, to avoid AWS throttling

  return DNSList


def UpdateLocalDNSStoreFromAWS ():
  print "Updating local DNS records store (can take a few minutes)"
  DNSList = ReadListFromFile(DNS_DATAFILE)   # Start with existing local store set

  # Remove all existing dns records for this AWS account, since we want to replace them
  DNSList = [dns for dns in DNSList if dns['AccountId'] != AWS_ACCOUNT_ID]

  # Now add all zones for this AWS account

  # Let's get every DNS record in every one of our zones
  for zone in ReadListFromFile(ZONE_DATAFILE):
    # We only care to update those records that are in the current AWS account we're logged onto
    if zone['AccountId'] != AWS_ACCOUNT_ID:
      continue
    for dns in GetDNSByZoneIdFromAWS(zone['Id']):

      # NOTE we modify the default AWS JSON record by adding these attributes for our purpose
      dns['AccountId']    = AWS_ACCOUNT_ID
      dns['AccountAlias'] = AWS_ACCOUNT_ALIAS
      dns['ZoneId']       = zone['Id']

      # Add this record to list
      DNSList.append(dns)
    sys.stdout.write('.') ; sys.stdout.flush()  # Dot the progress of processing every zone

    # Slow down these AWS API calls to avoid throttling errors
    time.sleep(API_SECONDS_DELAY)

  print  # Print newline

  # Replace local file store with this newer set
  WriteListToFile (DNSList, DNS_DATAFILE)


def ListELBHealth (Filter):
  # Display all ELB health-checks with applied Filter
  for e in ReadListFromFile(ELB_DATAFILE):
    # DEBUG
    # print json.dumps(e, sort_keys=True, indent=2, separators=(',', ': '))
    # sys.exit(1)
    if 'HealthCheck' in e:
      eName       = e['DNSName']
      eHealthyT   = e['HealthCheck']['HealthyThreshold']
      eUnhealthyT = e['HealthCheck']['UnhealthyThreshold']
      eInterval   = e['HealthCheck']['Interval']
      eTimeout    = e['HealthCheck']['Timeout']
      eTarget     = e['HealthCheck']['Target']
      # Print only if qualified by Filter
      if Filter == None or \
         Filter in eName.lower() or \
         Filter in eTarget.lower():
        print "%-80s  %4s  %4s  %4s  %4s  %s" % (eName, eHealthyT, eUnhealthyT, eInterval, eTimeout, eTarget)


def ListELBCerts (Filter):
  # Display all ELB|SSL cert pairs with applied Filter
  for e in ReadListFromFile(ELB_DATAFILE):
    Cert = '-'
    if len(e['ListenerDescriptions']) > 0:
      for l in e['ListenerDescriptions']:
        if l['Listener']['Protocol'] == 'HTTPS':
          Cert = l['Listener']['SSLCertificateId']

    # Print only if qualified by Filter
    if Filter == None or \
       Filter in e['DNSName'].lower() or \
       Filter in Cert.lower():
      print "%-80s  %s" % (e['DNSName'], Cert)


def ListELBs (Filter):
  # Display all ELB records with applied Filter
  for e in ReadListFromFile(ELB_DATAFILE):
    InstCount = len(e['Instances'])
    InstIdsList = []
    if InstCount > 0:
      for i in e['Instances']:
        InstIdsList.append(i['InstanceId'])
    InstIdsString = " ".join(InstIdsList)

    # Print only if qualified by Filter
    if Filter == None or \
       Filter in e['LoadBalancerName'].lower() or \
       Filter in e['DNSName'].lower() or \
       Filter in InstIdsString.lower():
      print "%-36s  %-80s  %4d  %s" % (e['LoadBalancerName'], e['DNSName'], InstCount, InstIdsString)


def BreakdownELB (ELBDNSName):
  # Display breakdown of ELB -> Instances
  if ELBDNSName == None or ELBDNSName == '':
    return

  # Check if ELB record exists in local store
  ELB = None     # Assume it doesn't
  for e in ReadListFromFile(ELB_DATAFILE):
    if e['DNSName'].lower() == ELBDNSName.lower():
      ELB = e
      break      # If we find it, break out of the for-loop

  if ELB == None:
    return

  # Print ELB DNSName
  print "%s" % (ELB['DNSName'].lower())

  # Print listener ports and target instance ports starting in 2nd column
  if len(ELB['ListenerDescriptions']) > 0:
    for l in ELB['ListenerDescriptions']:
      lPort = l['Listener']['LoadBalancerPort']
      iPort = l['Listener']['InstancePort']
      print "  %-5d -> %5d" % (lPort, iPort)
  else:
    print "  No listeners defined"

  # Print instances starting in 4th column
  InstanceList = ReadListFromFile(INSTANCE_DATAFILE)
  if len(ELB['Instances']) > 0:
    for i in ELB['Instances']:
      Instance = GetInstanceByIdFromList(i['InstanceId'], InstanceList)
      (Name, Id, Type, State, Ip, Account, LaunchTime) = GetInstanceKeyDetails(Instance)
      print  "    %-38s  %-20s  %-12s  %-10s  %-16s  %-16s" % (Name, Id, Type, State, Ip, Account)


def GetELBListFromAWS ():
  ELBList    = []
  client     = boto3.client('elb', region_name=AWS_REGION)
  response   = []
  PageSize   = 400
  TheresMore = True

  # Loop requests, in case there are more than PageSize records or we're being throttled by AWS
  while TheresMore:
    try:
      if 'NextMarker' in response and response['NextMarker'] != None:
        response = client.describe_load_balancers(Marker=response['NextMarker'],PageSize=PageSize)
      else:
        response = client.describe_load_balancers(PageSize=PageSize)
    except Exception as ErrorString:
      if BeingThrottled(ErrorString):
        time.sleep(1)                 # Being throttled, sleep for 1 second
        continue                      #   then continue the while loop
      print "\n", ErrorString         # Exit if it's a non-throttling error
      sys.exit(1)

    # Add this batch of ELBs to our list
    for elb in response['LoadBalancerDescriptions']:
      ELBList.append(elb)

    if 'NextMarker' not in response: # Break out of the loop if there's no more data from AWS
      TheresMore = False

  return ELBList


def UpdateLocalELBStoreFromAWS ():
  print "Updating local ELB store"
  ELBList = ReadListFromFile(ELB_DATAFILE)   # Start with existing local store set

  # Remove all existing elb records for this AWS account, since we want to replace them
  ELBList = [elb for elb in ELBList if elb['AccountId'] != AWS_ACCOUNT_ID]

  # Now add all zones for this AWS account
  for elb in GetELBListFromAWS():

    # NOTE we modify the default AWS JSON record by adding these attributes for our purpose
    elb['AccountId']    = AWS_ACCOUNT_ID
    elb['AccountAlias'] = AWS_ACCOUNT_ALIAS

    # Add this record to the list
    ELBList.append(elb)

  # Replace local file store with this newer set
  WriteListToFile(ELBList, ELB_DATAFILE)


def GetInstanceKeyDetails (i):
  State = 'Unknown'
  if i['State']['Name']:
    State = i['State']['Name']
  Ip    = '-'
  if 'PrivateIpAddress' in i:
    if i['PrivateIpAddress']:
      Ip = i['PrivateIpAddress'] 
  Name  = '-'
  if 'Tags' in i:
    for tag in i['Tags']:
      if tag['Key'] == 'Name':
        Name = tag['Value']
  return (Name, i['InstanceId'], i['InstanceType'], State, Ip, i['AccountAlias'], i['LaunchTime'])


def ListInstances (Filter):
  # Display all EC2 instances with applied Filter
  for i in ReadListFromFile(INSTANCE_DATAFILE):
    #print json.dumps(i, sort_keys=True, indent=2, separators=(',', ': '))
    (Name, Id, Type, State, Ip, Account, LaunchTime) = GetInstanceKeyDetails(i)           
    # Apply string search on Name, Id, Type, State, Status, or IP addresses
    if Filter == None or \
       Filter in Name.lower() or \
       Filter in Id.lower() or \
       Filter in Type.lower() or \
       Filter in State.lower() or \
       Filter in Ip.lower():
       #"LaunchTime": "2015-10-06T15:05:47+00:00"
      LaunchTime = LaunchTime[:10] + ' ' + LaunchTime[11:16]
      print "%-38s  %-20s  %-12s  %-10s  %-16s  %-18s  %-20s" % (Name, Id, Type, State, Ip, Account, LaunchTime)


def GetInstanceByIdFromList (Id, InstanceList):
  Instance = None
  if Id == '' or Id == None:   # Return empty object if no Id given
    return Instance
  for i in InstanceList:
    if i['InstanceId'].lower() == Id.lower():
      return i
  return Instance              # Return empty object if not found


def GetInstanceListFromAWS ():
  # Return all instance objects in current AWS account
  InstanceList = []
  client       = boto3.client('ec2', region_name=AWS_REGION)
  try:
    response = client.describe_instances()
    for res in response['Reservations']:
      for inst in res['Instances']:
        InstanceList.append(inst)
  except Exception as ErrorString:
    print ErrorString
    sys.exit(1)
  return InstanceList


def UpdateLocalInstanceStoreFromAWS ():
  print "Updating local EC2 instance store"
  InstanceList = ReadListFromFile(INSTANCE_DATAFILE)   # Start with existing local store set

  # Remove all existing instances for this AWS account, since we want to replace them
  InstanceList = [inst for inst in InstanceList if inst['AccountId'] != AWS_ACCOUNT_ID]

  # Now add all instances for this AWS account
  for inst in GetInstanceListFromAWS():

    if inst['State']['Name'].lower() == 'terminated':  # Ignore terminated instances
      continue
    
    # NOTE we modify the default AWS JSON record by adding these attributes for our purpose
    inst['AccountId']    = AWS_ACCOUNT_ID
    inst['AccountAlias'] = AWS_ACCOUNT_ALIAS

    # Add this record to the list
    InstanceList.append(inst)

  # Replace local file store with this newer set
  ReadListFromFile(INSTANCE_DATAFILE)
  WriteListToFile (InstanceList, INSTANCE_DATAFILE)


def ListStacks (Filter, Option):
  # Display all CloudFormation stacks with applied Filter
  for stack in ReadListFromFile(STACK_DATAFILE):
    # We only care about active stacks
    if 'delete_complete' in stack['StackStatus'].lower():
      continue
    if Filter == None or \
       Filter in stack['StackName'].lower() or \
       Filter in stack['StackId'].lower() or \
       Filter in stack['StackStatus'].lower() or \
       Filter in stack['AccountAlias'].lower():
      if 'LastUpdatedTime' in stack:
        lastUpdate = stack['LastUpdatedTime'][:10] + ' ' + stack['LastUpdatedTime'][11:19]
      else:
        lastUpdate = 'LastUpdate=null'
      print "%-34s  %-22s  %-22s  %s" % (stack['StackName'], stack['AccountAlias'], stack['StackStatus'], lastUpdate)
      if Option == '-sv':   # List parameters if (s)tack (v)erbosity was requested
        if 'Parameters' in stack:
          for p in stack['Parameters']:
            print "  %-32s  %s" % (p['ParameterKey'], p['ParameterValue'])


def UpdateLocalStackStoreFromAWS ():
  print "Updating local CloudFormation stack store"
  StackList = ReadListFromFile(STACK_DATAFILE)   # Start with existing local store set

  # Remove all existing stacks for this AWS account, since we want to replace them
  StackList = [stack for stack in StackList if stack['AccountId'] != AWS_ACCOUNT_ID]

  # Now add all stacks for this AWS account
  for stack in GetStackListFromAWS():

    # NOTE we modify the default AWS JSON record by adding these attributes for our purpose
    stack['AccountId']    = AWS_ACCOUNT_ID
    stack['AccountAlias'] = AWS_ACCOUNT_ALIAS

    # Add this record to the list
    StackList.append(stack)

  # Replace local file store with this newer set
  WriteListToFile (StackList, STACK_DATAFILE)


def GetStackListFromAWS ():
  # Return all cloudformation stack objects in current AWS account
  StackList  = []
  client     = boto3.client('cloudformation', region_name=AWS_REGION)
  response   = []
  NextMarker = None
  TheresMore = True

  while TheresMore:  # Loop requests, in case they exceed the 1MB max
    try:
      if NextMarker:
        response = client.describe_stacks(NextToken=NextMarker)
      else:
        response = client.describe_stacks()
    except Exception as ErrorString:
      if BeingThrottled(ErrorString):
        time.sleep(1)                 # Being throttled, sleep for 1 second
        continue                      #   then continue the while loop
      print "\n", ErrorString         # Exit if it's a non-throttling error
      sys.exit(1)

    # Add this batch of stack records to our list
    for stack in response['Stacks']:
      StackList.append(stack)

    try:
      NextMarker = response['NextToken']  # This assignment fails if NextToken is null
    except:
      TheresMore = False                  # So setup to break out of the loop if no more records

  return StackList


def CopyLocalStoresToS3Bucket ():
  # Semi-hidden option to be used by a scheduled process
  FileList = [DNS_DATAFILE, ZONE_DATAFILE, ELB_DATAFILE, INSTANCE_DATAFILE, STACK_DATAFILE]
  s3 = boto3.resource('s3')
  for DataFile in FileList:
    DataFileLocal = PROG_CONF_DIR + '/' + DataFile
    try:
      s3.meta.client.upload_file(DataFileLocal, S3_BUCKET, DataFile)
      print "Copied %s -> %s" % (whi(DataFileLocal), whi('s3://'+S3_BUCKET+'/'+DataFile))
    except:
      print "Error copying %s to %s" % (red(DataFileLocal),red('s3://'+S3_BUCKET+'/'+DataFile))


def DeleteLocalStoresFiles ():
  FileList = [DNS_DATAFILE, ZONE_DATAFILE, ELB_DATAFILE, INSTANCE_DATAFILE, STACK_DATAFILE]
  for DataFile in FileList:
    if os.path.isfile(DataFile):
      os.remove(PROG_CONF_DIR + '/' + DataFile)


def SetAWSRegion ():
  # Exit if unable to find a way to set the AWS_REGION global variable
  global AWS_REGION
  AWS_REGION = ''
  # First, check the environment variables (order is important)
  try:
    AWS_REGION = os.environ['AWS_REGION']
  except:
    try:
      AWS_REGION = os.environ['AMAZON_REGION']
    except:
      try:
        AWS_REGION = os.environ['AWS_DEFAULT_REGION']
      except:
        # Secondly, check if it's defined in the aws config file
        if not os.path.isfile(AWS_CONFIG_FILE):  
          print "AWS_REGION variable is not defined, and " + AWS_CONFIG_FILE + " file does not exist."
          sys.exit(1)
        cfg = ConfigParser()
        cfg.read(AWS_CONFIG_FILE)
        AWS_REGION = cfg.get('default', 'region')

  if AWS_REGION == '':
    print "AWS_REGION variable is not defined anywhere."
    sys.exit(1)


def DefineAWSAccountId ():
  global AWS_ACCOUNT_ID
  client = boto3.client('ec2', region_name = AWS_REGION)
  AWS_ACCOUNT_ID = client.describe_security_groups()['SecurityGroups'][0]['OwnerId']


def DefineAWSAccountAlias ():
  global AWS_ACCOUNT_ALIAS
  client = boto3.client('iam', region_name = AWS_REGION)
  AWS_ACCOUNT_ALIAS = client.list_account_aliases()['AccountAliases'][0]


def BeingThrottled (ErrorString):
  if '(Throttling)' in ErrorString or 'exceeded' in ErrorString:
    return True
  return False


def SetupAWSAccess ():
  # Set AWS account ID and Alias, and also implicitly tests whether user is logged in or not
  SetAWSRegion()
  try:
    DefineAWSAccountId()
    DefineAWSAccountAlias()
  except:
    print "AWS login is required."
    sys.exit(1)


def parse_arguments (argv):
  """ Parse command line arguments """

  # Allow only 1 or 2 arguments; an Option with an optional Filter
  args = len(argv) - 1
  Option, Filter = (None, None)
  if args == 1:
    Option = argv[1]
  elif args == 2:
    Option = argv[1]
    Filter = argv[2].lower()  # All filtering comparisons will be done in lowercase
  else:
    PrintUsage()

  # Process given Option with optional Filter
  if Option == '-u':
    SetupAWSAccess()
    UpdateLocalInstanceStoreFromAWS()
    UpdateLocalZoneStoreFromAWS()
    UpdateLocalELBStoreFromAWS()
    UpdateLocalStackStoreFromAWS()
    UpdateLocalDNSStoreFromAWS()
  elif Option == '-3':
    # Semi-hidden option to be used by a scheduled process
    SetupAWSAccess()
    CopyLocalStoresToS3Bucket()
  elif Option == '-x':
    DeleteLocalStoresFiles()
  elif Option == '-z':
    ListZones(Filter)
  elif Option == '-d':
    ListDNSRecs(Filter)
  elif Option == '-e':
    ListELBs(Filter)
  elif Option == '-es':
    ListELBCerts(Filter)
  elif Option == '-eh':
    ListELBHealth(Filter)
  elif Option == '-i':
    ListInstances(Filter)
  elif Option in ['-s', '-sv']:
    ListStacks(Filter, Option)
  elif Filter != None or Option in ['-h', '-?']:
    PrintUsage()
  else:
    BreakdownDNS(Option)   # The Option naturally becomes the DNS name in this case


def house_keeping():
  """ Ensure certain prerequisites are satisfied """

  # Ensure config directory exist
  if not os.path.isdir(PROG_CONF_DIR):
    try:
      os.makedirs(PROG_CONF_DIR)
    except IOError:
      print "Error creating directory %s" % (whi(PROG_CONF_DIR))
      sys.exit(1)


def main(args=None):
  """ Main program """

  house_keeping()
  parse_arguments(sys.argv)
  sys.exit(0)


if __name__ == '__main__':
  main()
