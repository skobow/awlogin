// main.go
package main

import (
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
    "io/ioutil"
    "strings"
    "strconv"
    "github.com/vaughan0/go-ini"
    "github.com/fatih/color"
    "github.com/aws/aws-sdk-go/aws"
    "github.com/aws/aws-sdk-go/aws/session"
    "github.com/aws/aws-sdk-go/service/iam"
    "github.com/aws/aws-sdk-go/service/sts"
)

// Global constants
const (
    ProgName = "awlogin"
    ProgVer  = "1.5.0"
)

// Global variables
var (
	gra = color.New(color.FgWhite).SprintFunc()
	whi = color.New(color.FgWhite, color.Bold).SprintFunc()
	red = color.New(color.FgRed, color.Bold).SprintFunc()
	skeletonConf = "[default]\n" +
	               "profile_name          = stag\n" +
	               "aws_access_key_id     = AKERNEIDUFENICUQ3NDO\n" +
	               "aws_secret_access_key = ilsjkasdUEwlwDUgvD1b7234Fn/lepi0ACmk8upFy\n\n" +
	               "[prod]\n" +
	               "profile_name   = prod\n" +
	               "account_number = 544492114123\n" +
	               "user_role      = PowerUser\n"    
    progConfDir  = filepath.Join(os.Getenv("HOME"), "." + ProgName)
	awsConfFile  = filepath.Join(os.Getenv("HOME"), ".aws/config")
	awsCredsFile = filepath.Join(os.Getenv("HOME"), ".aws/credentials")
)


func main() {
    // Allow only 1 or 2 arguments
    args := os.Args[1:]
    if len(args) == 1 {
    	if args[0] == "-c" {
    		createSkeletonConfig()
    	} else if args[0] == "-l" {
    		listAccounts()
    	} else if args[0] == "-h" {
    		printHelp()
    	} else {
    		printUsage()
    	}
    } else if len(args) != 2 {
    	printUsage()
    }

    profile := args[0]  // Target account profile in config
    token := args[1]    // 6-digit token from user's MFA device

  	_, err := strconv.Atoi(token)
  	if err != nil || len(token) != 6 {
        Die(1, "Token " + red(token) + " is invalid")
    }

    // Validate credentials file settings, ensuring target profile is valid
    cfg := validateConfig(profile)
    logonToAWS(cfg, profile, token)
}


func printUsage() {
    fmt.Println("AWS CLI MFA Logon Utility", ProgVer)
    fmt.Println(ProgName, "PROFILE TOKEN   Logon to account PROFILE using 6-digit TOKEN")
    fmt.Println("        -l              List all account profiles in", gra(awsCredsFile))
    fmt.Println("        -c              Create skeleton", gra(awsCredsFile), "file")
    fmt.Println("        -h              Show additional help information")
    Die(0,"")
}


func printHelp() {
    fmt.Println("This utility simplifies secured AWS CLI MFA authentication to any account profile")
    fmt.Println("defined in your", gra(awsCredsFile), "file. It expects that file to be")
    fmt.Println("formatted in the following sample manner:\n")
    fmt.Println(skeletonConf)
    fmt.Println("So ...")
    fmt.Println("1. The", gra("default"), "profile is for your primary AWS account, where your username is defined")
    fmt.Println("2. All other profiles are treated as", gra("federated"), "AWS accounts you may have access to")
    fmt.Println("3. You", gra("must"), "defined a valid key pair for your", gra("default"), "profile")
    fmt.Println("4. Each profile must have a unique", gra("profile_name"), "so this utility can identify it")
    fmt.Println("5. Each federated profile must have a valid", gra("account_number"), "and", gra("user_role"))
    fmt.Println("6. The -c switch can create a fresh skeleton", gra(awsCredsFile), "file")
    Die(0,"")
}


// Exit program with a final message
func Die(code int, message string) {
    if message != "" { fmt.Println(message) }
    os.Exit(code)
}


// Create default skeleton credentials file
func createSkeletonConfig() {
    if _, err := os.Stat(awsCredsFile); os.IsNotExist(err) {
        err = ioutil.WriteFile(awsCredsFile, []byte(skeletonConf), 0600)
        if err != nil {
            Die(1, err.Error())
        }        
    } else {
        fmt.Printf("There's already a %s file.\n", gra(awsCredsFile))
    }
	Die(0,"")
}


// List all accounts in current credentials file
func listAccounts() {
    cfg, err := ini.LoadFile(awsCredsFile)
    if err != nil {
        Die(1, err.Error())
    }    
    for section, _ := range cfg {
        fmt.Printf("[%s]\n", whi(section))
        for k, v := range cfg[section] {
            fmt.Printf("%-21s = %s\n", k, v)
        }
        fmt.Println("")
    }
	Die(0,"")
}


// Check configuration file for anomalies and return the full config object
func validateConfig(profile string) (cfg ini.File) {
	// Read the credentials INI file
    cfg, err := ini.LoadFile(awsCredsFile)
    if err != nil {
        Die(1, err.Error())
    }    

    // Ensure there is at least one default section, with the required 2 entries
    deflt, prof := 0, 0
    for section, entries := range cfg {
    	if section == "default" {
    		if entries["aws_access_key_id"] != "" &&
    		   entries["aws_secret_access_key"] != "" {
            	deflt++
        	}
        }
        if section == profile	{
        	prof++
        }
    }
    if deflt == 0 {
    	Die(1, "File " + gra(awsCredsFile) + " is missing " + red("default") + 
    		   " profile or both credential entries.")
    }
    // Ensure user-specified profile is in the config file and is valid
    if prof == 0 {
    	Die(1, "Profile name " + red(profile) + " is not defined in " + gra(awsCredsFile))
    }
    if cfg[profile]["profile_name"] == "" ||
       cfg[profile]["account_number"] == "" ||
       cfg[profile]["user_role"] == "" {
       	Die(1, "Profile name " + red(profile) + " is missing needed entries")
    }
    return cfg
}


// Logon to AWS account designated by given profile, with given token
func logonToAWS(cfg ini.File, profile, token string) {
    // In order to make any initial AWS API call we have validate the default profile credentials
    os.Setenv("AWS_REGION", GetAWSRegion())
    os.Setenv("AWS_ACCESS_KEY_ID", cfg["default"]["aws_access_key_id"])
    os.Setenv("AWS_SECRET_ACCESS_KEY", cfg["default"]["aws_secret_access_key"])

    // Get main account username. Also an implicit validation of the keys in default profile
    sess := session.Must(session.NewSession())
    svc := iam.New(sess, aws.NewConfig())
    resp, err := svc.GetUser(nil)
    if err != nil {
    	Die(1, err.Error())
    }
    usrarn := *resp.User.Arn
    username := *resp.User.UserName
    if usrarn == "" || username == "" {
    	Die(1, "Error with returned AWS user object.")
    } 

    // Derive main account ID and MFA device ARN
    s := strings.Split(usrarn, ":")
    mainAccountId := s[4]
    mfaDeviceArn := "arn:aws:iam::" + mainAccountId + ":mfa/" + username

    // Do either main or federated account login, based on profile
    accessKey, secretKey, sessToken := "", "", ""
  	svc2 := sts.New(sess)
    if profile == cfg["default"]["profile_name"] {
		params := &sts.GetSessionTokenInput{
		    DurationSeconds: aws.Int64(86400),            // One day for default account
		    SerialNumber:    aws.String(mfaDeviceArn),
		    TokenCode:       aws.String(token),
		}
		resp, err := svc2.GetSessionToken(params)
		if err != nil {
	    	Die(1, err.Error())
		}
	    accessKey = *resp.Credentials.AccessKeyId
	    secretKey = *resp.Credentials.SecretAccessKey
	    sessToken = *resp.Credentials.SessionToken
    } else {
    	// Derive the Role ARN
        targetAccountId := cfg[profile]["account_number"]
        userRole := cfg[profile]["user_role"]
        roleArn := "arn:aws:iam::" + targetAccountId + ":role/" + userRole
		params := &sts.AssumeRoleInput{
		    DurationSeconds: aws.Int64(3600),             // One hour for target account
		    SerialNumber:    aws.String(mfaDeviceArn),
		    TokenCode:       aws.String(token),
		    RoleSessionName: aws.String(username),
		    RoleArn:         aws.String(roleArn),
		}
		resp, err := svc2.AssumeRole(params)
		if err != nil {
	    	Die(1, err.Error())
		}
	    accessKey = *resp.Credentials.AccessKeyId
	    secretKey = *resp.Credentials.SecretAccessKey
	    sessToken = *resp.Credentials.SessionToken
    }

    // Actual logon is to simply update these 3 environment variables with newly
    // acquired credentials then jumping into a subshell
    if resp != nil {
	    os.Setenv("AWS_ACCESS_KEY_ID", accessKey)
	    os.Setenv("AWS_SECRET_ACCESS_KEY", secretKey)
	    os.Setenv("AWS_SESSION_TOKEN", sessToken)
	    fmt.Println(ProgName, ": Logged in to AWS within a new subshell. Type exit when done.")
	    execCommand(os.Getenv("SHELL"))
	    Die(0, ProgName + ": Back to your original shell session.")
	}
}


// Run any OS command
func execCommand(program string, args ...string) {
    cmd := exec.Command(program, args...)
    cmd.Stdin = os.Stdin
    cmd.Stdout = os.Stdout
    cmd.Stderr = os.Stderr
    err := cmd.Run() 
    if err != nil {
        Die(1, err.Error())
    }
}


func GetAWSRegion() (awsRegion string) {
    // Start by checking the environment variables (order is important)
    if os.Getenv("AWS_REGION") != "" {
        awsRegion = os.Getenv("AWS_REGION")
    } else if os.Getenv("AMAZON_REGION") != "" {
        awsRegion = os.Getenv("AMAZON_REGION")
    } else if os.Getenv("AWS_DEFAULT_REGION") != "" {
        awsRegion = os.Getenv("AWS_DEFAULT_REGION")
    } else {
        // End by checking the AWS config file
        if _, err := os.Stat(awsConfFile); os.IsNotExist(err) {    
            Die(1, "AWS region variable is not defined, and " + awsConfFile + " file does not exist.")
        }
        cfgfile, err := ini.LoadFile(awsConfFile)
        if err != nil {
            Die(1, err.Error())
        }
        awsRegion, _ = cfgfile.Get("default", "region")
    }
    if awsRegion == "" {
        Die(1, "Error. AWS region variable is not defined anywhere.")
    }
    return awsRegion
}
