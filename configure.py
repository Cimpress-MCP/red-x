import boto3

path_prefix = '/red-x/'

parameters = [{
    'Name': f'{path_prefix}gitlab/endpoint',
    'Description': 'GitLab API Endpoint',
    'Type': 'String'
},
{
    'Name': f'{path_prefix}gitlab/project',
    'Description': 'GitLab project to track delegation errors',
    'Type': 'String'
},
{
    'Name': f'{path_prefix}gitlab/token',
    'Description': 'GitLab project to track delegation errors',
    'KeyId': 'alias/red-x/settings',
    'Type': 'SecureString'
},
{
    'Name': f'{path_prefix}route53/zoneId',
    'Description': 'The hosted zone id to check for delegation errors',
    'Type': 'String'
},
{
    'Name': f'{path_prefix}sns/topic',
    'Description': 'The SNS topic ARN to notify of delegation errors',
    'Type': 'String'
}]

ssm = boto3.client('ssm')

print("""Red-X Configuration Setup:

Red-X uses the EC2 Parameter Store to load its configuration. Let's make sure you
have all of the correct parameters created in the right paths and the right ones
are encrypted.

Note: This script assumes you have already deployed the function and makes use of
a KMS key it creates. If you don't wish to use the red-x KMS key, please update
the KeyId in `configure.py` before running this.
""")

for param in parameters:
    param_name = param['Name']
    existing_value = ''

    try:
        existing_value = ssm.get_parameter(Name=param_name, WithDecryption=True)['Parameter']['Value']
        param['Overwrite'] = True
    except ssm.exceptions.ParameterNotFound:
        pass

    print(f'''
Name: {param_name}
Description: {param['Description']}''')

    new_value = input(f'Value ({existing_value}): ')
    if not new_value:
        param['Value'] = existing_value
    else:
        param['Value'] = new_value

    if not param['Value']:
        # We don't want a bunch of empty params up there.
        print(f'No value specified, skipping {param_name}...')
    else:
        ssm.put_parameter(**param)
