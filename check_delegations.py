import json
import boto3
import dns.resolver
import gitlab
from datetime import datetime

# Load configuration from the EC2 Parameter Store
# Transforms: /red-x/gitlab/token
# Into: {'red-x': {'gitlab': {'token': 'value'}}}
def load_config(ssmPath):
    ssm = boto3.client('ssm')
    resp = ssm.get_parameters_by_path(
        Path = ssmPath,
        Recursive=True,
        WithDecryption=True
    )
    config = {}

    for param in resp['Parameters']:
        path = param['Name'].split('/')
        current_level = config
        for level in path:
            if(level == '' or level == 'red-x'):
                continue
            if(level not in current_level):
                current_level[level] = {}
            if(level == path[-1]):
                current_level[level] = param['Value']
            else:
                current_level = current_level[level]
    return config

# Open or close GitLab issues based on delegation errors discovered by red-x.
# Opens an issue in the configured project for delegation errors and closes
# any open issues when it no longer identifies that error.
def notify_gitlab_issues(config, errors):
    # Load up all open issues in the configured project with label 'red-x'.
    gl = gitlab.Gitlab(config['gitlab']['endpoint'], config['gitlab']['token'], api_version=4)
    project = gl.projects.get(config['gitlab']['project'])
    issues = project.issues.list(labels=['red-x', 'delegation'], state='opened')
    zones_with_issues = [i.title for i in issues]

    for error in errors:
        # This error already has an issue
        if f"{error} delegation error" in zones_with_issues:
            print(f"ALREADY FILED! {error}! Skipping")
            zones_with_issues.remove(f"{error} delegation error")
        # This error needs a new issue created
        else:
            error_json = json.dumps(errors[error], indent=1)
            print(f"FILING: {error}!")
            issue = project.issues.create({'title': f"{error} delegation error",
                               'description': f"""```
{error_json}
```""",
                               'labels': ['red-x', 'delegation']})

    # These issues no longer have a delegation error associated with them
    # and can be closed.
    for leftover in zones_with_issues:
        print(f"CLOSING ISSUE: {leftover}")
        issue = [x for x in issues if x.title == leftover][0]
        issue.notes.create({"body": "Subsequent runs of red-x no longer see this delegation as an issue. Automatically closing ticket."})
        issue.state_event = "close"
        issue.save()

# Send a summary of results to a configured SNS topic
def notify_sns_topic(config, errors):
    if len(errors) == 0:
        print("No delegation errors, not sending SNS notification...")
        return

    notification_time = str(datetime.now())
    sns = boto3.client('sns')
    error_text = json.dumps(errors, indent=2)
    sns.publish(
        TargetArn=config['sns']['topic'],
        Subject=f"Red-X Delegation Errors @ {notification_time}",
        Message=json.dumps({'default': f"""
Red-X has run and found the following abandoned or misconfigured delegations. You should take action to prevent zone hijacking!

""" + error_text}),
        MessageStructure='json'
    )

def handler(event, context):
    config = load_config('/red-x/')
    r53 = boto3.client('route53')
    zone_id = config['route53']['zoneId']

    records = []
    nextName = None
    nextType = None

    # Fetch all records in the requested hosted zone
    while True:
        if nextName and nextType:
            response = r53.list_resource_record_sets(
                HostedZoneId = zone_id,
                StartRecordName = nextName,
                StartRecordType = nextType
            )
        else:
            response = r53.list_resource_record_sets(
                HostedZoneId = zone_id
            )

        records = records + response['ResourceRecordSets']

        if 'NextRecordName' in response and 'NextRecordType' in response:
            nextName = response['NextRecordName']
            nextType = response['NextRecordType']
        else:
            break

    # Discard everything except NS records
    delegations = [x for x in records if x['Type'] == 'NS']
    delegation_errors = {}

    resolver = dns.resolver.Resolver(configure=False)
    resolver.timeout = 5

    # For each delegated zone
    for delegation in delegations:
        zone = delegation['Name']
        nameservers = [d['Value'] for d in delegation["ResourceRecords"]]

        # For each nameserver in the delegation
        for ns in nameservers:
            resolver.nameservers = [ns]
            try:
                # Query the nameserver for our zone
                answer = dns.resolver.query(zone, 'NS')
                found = []
                for s in answer:
                    found = found + [s.to_text()]

                # If the nameserver we queried didn't return the expected results,
                # the domain may have been hijacked (or just misconfigured).
                if set(nameservers) != set(found):
                    if zone not in delegation_errors:
                        delegation_errors[zone] = []
                    delegation_errors[zone].append({
                        "error": "NS Mismatch",
                        "source": ns,
                        "found": found,
                        "expected": nameservers
                    })
            # If the nameserver doesn't know about this zone, the delegation
            # may be abandoned.
            except dns.resolver.NoNameservers:
                    if zone not in delegation_errors:
                        delegation_errors[zone] = []
                    delegation_errors[zone].append({
                        "zone": zone,
                        "source": ns,
                        "error": "Unreachable nameservers or no delegation"
                    })

    # Open or close GitLab issues for these delegation errors.
    if('gitlab' in config):
        notify_gitlab_issues(config, delegation_errors)

    # Notify an SNS topic of all delegation errors.
    if('sns' in config):
        notify_sns_topic(config, delegation_errors)

    return {
        "message": "Completed checking for abandoned delegations.",
        "errors": delegation_errors
    }