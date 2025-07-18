import json, boto3, botocore, os, logging, sys

log = logging.getLogger(__name__)

logging.basicConfig(
    encoding = "utf-8",
    # format = "%(asctime)s : %(levelname)s : %(message)s",
    format = "{\"timestamp\": \"%(asctime)s\", \"level\": \"%(levelname)s\", \"message\": \"%(message)s\"}\n",
    datefmt = "%Y-%m-%dT%H-%M-%SZ%z",
    level = logging.INFO
)

# Helper functions
def assume_role(role_arn):
    client = boto3.client('sts')

    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sts/client/assume_role.html
    response = client.assume_role(
        RoleArn = role_arn,
        RoleSessionName = "secrets-vault"
    )

    # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#passing-credentials-as-parameters
    session = boto3.Session(
        aws_access_key_id = response["Credentials"]["AccessKeyId"],
        aws_secret_access_key = response["Credentials"]["SecretAccessKey"],
        aws_session_token = response["Credentials"]["SessionToken"]
    )

    log.debug(f"assume {role_arn} with session name \"vault\"")

    return session

def get_parameter(parameter_name):
    client = boto3.client('ssm')

    try:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/client/get_parameter.html
        response = client.get_parameter(
            Name = parameter_name,
            WithDecryption = True
        )

        log.debug("retrieved parameter value")
    
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'ParameterNotFound':
            log.warning(f"Parameter's likely been deleted, skipping event")
            sys.exit(0)
        
        else:
            log.error(error)
            raise

    else:   
        return response["Parameter"]["Value"]

def describe_parameter(parameter_name):
    client = boto3.client('ssm')

    parameter_user = None
    parameter_timestamp = None
    parameter_type = None
    parameter_description = None
    parameter_version = None

    try:

        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/client/describe_parameters.html
        response = client.describe_parameters(
            ParameterFilters=[
                {
                    'Key': 'Name',
                    'Option': 'Equals',
                    'Values': [
                        parameter_name,
                    ]
                },
            ]
        )
    
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'ParameterNotFound':
            return parameter_user, parameter_timestamp, parameter_type, parameter_description, parameter_version
        
        else:
            log.error(error)
            raise
    
    else:

        if (response["Parameters"] != []):
            parameter_user = response["Parameters"][0]["LastModifiedUser"]
            log.info(f"parameter last modified user: {parameter_user}")

            parameter_timestamp = response["Parameters"][0]["LastModifiedDate"].strftime("%Y-%m-%dT%H-%M-%SZ%z")
            log.info(f"parameter last modified timestamp: {parameter_timestamp}")

            parameter_type = response["Parameters"][0]["Type"]
            log.info(f"parameter type: {parameter_type}")

            parameter_version = response["Parameters"][0]["Version"]
            log.info(f"parameter version: {parameter_version}")

            try:
                parameter_description = response["Parameters"][0]["Description"]
                log.info(f"parameter description: {parameter_description}")
            
            except KeyError:
                log.debug("parameter has no description")
                parameter_description = "Shared secret"

        return parameter_user, parameter_timestamp, parameter_type, parameter_description, parameter_version

def get_tags(parameter_name):
    client = boto3.client('ssm')

    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/client/list_tags_for_resource.html
    response = client.list_tags_for_resource(
        ResourceType = "Parameter",
        ResourceId = parameter_name
    )

    parameter_tags = {}
    for tag_pair in response["TagList"]:
        parameter_tags[tag_pair["Key"]] = tag_pair["Value"]

    log.info(f"parameter tags: {parameter_tags}")

    return parameter_tags

def process_tags(parameter_arn, parameter_tags):
    # 112233445566 | r-... | ou-...

    targets = []
    current_account = parameter_arn.split(":")[4]

    for tag_key in parameter_tags.keys():

        tag_value = parameter_tags[tag_key].lower()

        if (tag_value == "true"):
            
            # Cast to int
            try:
                tag_key = int(tag_key)
            
            # Not valid int
            except ValueError:
                tag_key = str(tag_key).lower()    # Leave as string


            # AWS Account ID
            if ( (isinstance(tag_key, int)) and ( len(f"{tag_key}") == 12 ) ):
                
                return [f"{tag_key}"]
            
            # Org root (all accounts)
            elif ( tag_key[:2] == "r-"):
                session = assume_role(os.environ["AWS_MANG_ACC_ROLE"])

                client = session.client('organizations')

                paginator = client.get_paginator('list_accounts')

                response_iterator = paginator.paginate()

                for page in response_iterator:
                    for line in page["Accounts"]:

                        targets.append( line["Id"] )
            
            # Org unit
            elif ( tag_key[:3] == "ou-"):
                session = assume_role(os.environ["AWS_MANG_ACC_ROLE"])

                client = session.client('organizations')

                paginator = client.get_paginator('list_accounts_for_parent')

                response_iterator = paginator.paginate(
                    ParentId = tag_key
                )

                try:

                    for page in response_iterator:
                        for line in page["Accounts"]:
                            targets.append( line["Id"] )
                
                except botocore.exceptions.ClientError as error:
                    if error.response['Error']['Code'] == 'InvalidInputException':
                        log.error(f"invalid Organisation Unit Tag: {tag_key}")
                        raise
                    
                    else:
                        log.warning(f"unexpected error: {error}")
                        raise
            
            else:
                log.warning(f"invalid tag key: {tag_key}")
        
        else:
            log.warning(f"invalid tag value: {tag_value}")
    

    targets = list( set(targets) )

    try:
        targets.remove(current_account)  # Don't share to vault account
    
    # `current_account` not in list
    except ValueError:
        pass

    return targets

# Operation functions
def handle_create_parameter(parameter_name, parameter_tags, parameter_description, parameter_type, parameter_arn, parameter_user, parameter_timestamp):
    parameter_value = get_parameter(parameter_name)

    targets = process_tags(parameter_arn, parameter_tags)
    log.debug(f"sharing targets: {targets}")

    for target in targets:
        role_arn = f"arn:aws:iam::{target}:role/{os.environ["AWS_MEMBER_ACC_ROLE_NAME"]}"

        session = assume_role(role_arn)

        client = session.client('ssm')

        try:

            response = client.put_parameter(
                Name = parameter_name,
                Description = parameter_description,
                Value = parameter_value,
                Type = parameter_type,
                Overwrite = True,
                Tier = 'Standard'
            )

            # Can't include tags with `Overwrite = True` in put_parameter
            response = client.add_tags_to_resource(
                ResourceType = 'Parameter',
                ResourceId = parameter_name,
                Tags=[
                    {
                        'Key': 'shared-from',
                        'Value': parameter_arn
                    },
                    {
                        'Key': 'last-modified-by',
                        'Value': parameter_user
                    },
                    {
                        'Key': 'last-modified-at',
                        'Value': parameter_timestamp
                    }
                ]
            )
        
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'ParameterAlreadyExists':
                log.error(f"failed to share with \"{target}\": {error}")
            
            else:
                log.error(f"unexpected error: {error}")
                raise

        else:
            log.info(f"shared with {target}")

def handle_delete_parameter(parameter_name, parameter_arn, parameter_tags):

    targets = process_tags(parameter_arn, parameter_tags)
    log.debug(f"sharing targets: {targets}")

    for target in targets:
        role_arn = f"arn:aws:iam::{target}:role/{os.environ["AWS_MEMBER_ACC_ROLE_NAME"]}"

        session = assume_role(role_arn)

        client = session.client('ssm')

        try:

            response = client.delete_parameter(
                Name = parameter_name,
            )
        
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'ParameterNotFound':
                continue
            
            else:
                log.error(f"unexpected error: {error}")
                raise

        else:
            log.info(f"deleted from {target}")

def handle_tag_update(parameter_name, parameter_tags, parameter_arn, parameter_user, parameter_timestamp, parameter_description, parameter_type):
    
    targets = process_tags(parameter_arn, parameter_tags)
    log.info(f"sharing targets: {targets}")

    for target in targets:
        role_arn = f"arn:aws:iam::{target}:role/{os.environ["AWS_MEMBER_ACC_ROLE_NAME"]}"

        session = assume_role(role_arn)

        client = session.client('ssm')

        try:
            response = client.add_tags_to_resource(
                ResourceType = 'Parameter',
                ResourceId = parameter_name,
                Tags=[
                    {
                        'Key': 'shared-from',
                        'Value': parameter_arn
                    },
                    {
                        'Key': 'last-modified-by',
                        'Value': parameter_user
                    },
                    {
                        'Key': 'last-modified-at',
                        'Value': parameter_timestamp
                    }
                ]
            )
            
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'ParameterAlreadyExists':
                log.error(f"failed to share with \"{target}\": {error}")
            
            # Sharing with new account
            elif error.response['Error']['Code'] == 'InvalidResourceId':

                handle_create_parameter(
                    parameter_name, 
                    parameter_tags, 
                    parameter_description, 
                    parameter_type, 
                    parameter_arn, 
                    parameter_user, 
                    parameter_timestamp
                )
            
            else:
                log.error(f"unexpected error: {error}")
                raise

        else:
            log.info(f"updated tags in {target}")

def lambda_handler(event, context):
    log.info(f"Event: {event}")

    event_type = event["detail-type"]
    
    # Parameter Created = v1
    # Parameter Deleted = detail.tags = {}
    # Parameter's Tags updated = len(detail.tags.keys()) > len(detail.changed-tag-keys.keys())
    if (event_type == "Tag Change on Resource"):
        parameter_arn = event["resources"][0]
        parameter_name = parameter_arn.split(":parameter")[-1]

        log.info(f"Parameter name: {parameter_name}")
        
        parameter_user, parameter_timestamp, parameter_type, parameter_description, parameter_version = describe_parameter(parameter_name)

        # Parameter Created
        if (parameter_version == 1):
            handle_create_parameter(
                parameter_name, 
                event["detail"]["tags"], 
                parameter_description, 
                parameter_type, 
                parameter_arn, 
                parameter_user, 
                parameter_timestamp
            )
        
        # Parameter deleted
        elif (event["detail"]["tags"] == {}):
            old_parameter_tags = {}
            for tag_key in event["detail"]["changed-tag-keys"]:
                old_parameter_tags[tag_key] = "true"

            handle_delete_parameter(
                parameter_name,
                parameter_arn,
                old_parameter_tags
            )
        
        # Parameter's tags modified
        elif ( event["detail"]["tags"].keys() != event["detail"]["changed-tag-keys"] ):

            # Get only changed tags
            # Reduces API calls for updating parameters
            new_parameter_tags = {}
            old_parameter_tags = {}
            for tag_key in event["detail"]["changed-tag-keys"]:

                try:
                    new_parameter_tags[tag_key] = event["detail"]["tags"][tag_key]
                
                except KeyError:
                    old_parameter_tags[tag_key] = "true"

            if (new_parameter_tags != {}):
                handle_tag_update(
                    parameter_name,
                    new_parameter_tags,
                    parameter_arn,
                    parameter_user,
                    parameter_timestamp,
                    parameter_description, 
                    parameter_type
                )
            
            if (old_parameter_tags != {}):
                handle_delete_parameter(parameter_name, parameter_arn, old_parameter_tags)
    
    # Parameter's value changed
    elif (event_type == "Parameter Store Change"):
        parameter_arn = event["resources"][0]
        parameter_name = parameter_arn.split(":parameter")[-1]

        log.debug(f"Parameter name: {parameter_name}")
        
        parameter_user, parameter_timestamp, parameter_type, parameter_description, version = describe_parameter(parameter_name)

        parameter_tags = get_tags(parameter_name)

        # Utilise `overwrite` to update in-place
        handle_create_parameter(
            parameter_name, 
            parameter_tags, 
            parameter_description, 
            parameter_type, 
            parameter_arn, 
            parameter_user, 
            parameter_timestamp
        )
    
    else:
        raise Exception(f"Invalid event type: {event_type}")
