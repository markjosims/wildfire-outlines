import boto3
import json
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)


def get_secret():
    # logger.info("Loading api key from AWS secrets...")
    print("Loading api key from AWS secrets...")

    secret_name = "openai-api-key"
    region_name = "us-west-2"

    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e

    secret = secret_value_response["SecretString"]

    return secret
