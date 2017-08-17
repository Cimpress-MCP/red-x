red-x
=====

![](http://i.dailymail.co.uk/i/pix/2013/09/02/article-2408624-1B8BA853000005DC-231_964x603.jpg)

>The Red X is a warning placard affixed to a vacant building structure
alerting first responders to the existence of structural or interior hazards
in the building that warrant extreme caution when conducting interior
firefighting or rescue operations with entry occurring only for known life
hazards.

In this case, red-x alerts us of abandoned domain delegations.

## What it does

* Fetches configuration from EC2 Parameter Store
* Gets a list of all records in the configured Route53 Hosted Zone
* Pulls out all delegations (NS records)
* Iterates over the delegations
    * Checks each of the nameservers in the delegation.
    * Ensures each nameserver returns the expected result for NS records.
    * No response implies the delegation is abandoned.
    * Mismatched results implies misconfiguration or zone hijacking.

Then, it can notify you in two ways:
1. GitLab issues.
    * Open an issue in the configured project for each delegation error.
    * Close any open issues no longer associated with delegation errors.
2. SNS notifications.
    * Send a summary of delegation errors to the configured SNS topic.

## Configuration

Configuration for this function is controlled by the EC2 Parameter Store.
Setting up your configuration (and updating it later) is simplified using
the [`configure.py`](./configure.py) script at the root of this repo.

Running `python configure.py` with credentials for your account will let you
create or update your Red-X configuration.

**NOTE**: If you intend to use the GitLab integration, you should only do
this _after_ you have deployed the function, as it will attempt to use the KMS
key created by CloudFormation to encrypt your API token.

## Setup/CloudFormation

Deploying this function will create the following resources (in addition to
the 'usual' Serverless resources):

* A KMS key to encrypt secret configuration info (i.e. GitLab API Token)
    * Aliased as 'alias/red-x/settings'
* An SNS topic `Red-X-Reports` for publishing delegation error summaries

## Deployment

This is a Python3.6 Lambda function, since the DNS library for node isn't great.
So you're kind of straddling two worlds, here.

```
$ npm install
$ virtualenv env
$ source ./env/bin/activate
$ ./node_modules/.bin/sls deploy
```

Then, optionally, you can run `python configure.py` to set up the parameters in
the EC2 Parameter Store.

You can also invoke the function locally with `./node_modules/.bin/sls invoke local -f check_delegations`.
