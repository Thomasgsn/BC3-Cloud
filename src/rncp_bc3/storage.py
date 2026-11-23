"""S3 privé : objets chiffrés côté client, empreinte vérifiée après lecture."""

import hashlib
import json

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import SECRET_DIR, secrets, setting
from .security import decrypt, encrypt

BUCKET = setting("S3_BUCKET", "bc3-private")


def client(service="s3"):
    mode = setting("BC3_STORAGE_MODE", "local")
    if mode not in ["local", "aws"]:
        raise ValueError("Profil de stockage invalide")
    options = {
        "region_name": setting("AWS_REGION", "us-east-1"),
        "config": Config(
            signature_version="s3v4" if service == "s3" else "v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 2},
            connect_timeout=4,
            read_timeout=15,
        ),
    }
    if mode == "local":
        conf = secrets()
        options.update(
            endpoint_url=setting("S3_ENDPOINT", "https://s3:8343")
            if service == "s3"
            else setting("QUEUE_ENDPOINT", "https://queue:9325"),
            aws_access_key_id=conf["s3_access"],
            aws_secret_access_key=conf["s3_secret"],
            verify=str(SECRET_DIR / "ca.crt"),
        )
    # AWS : chaîne IAM/Pod Identity native du SDK, CA publiques, aucun credential statique injecté.
    return boto3.client(service, **options)


def initialize():
    c = client()
    if setting("BC3_STORAGE_MODE", "local") == "aws":
        c.head_bucket(Bucket=BUCKET)
        return
    try:
        c.head_bucket(Bucket=BUCKET)
    except ClientError as e:
        if e.response["ResponseMetadata"]["HTTPStatusCode"] not in [404]:
            raise
        c.create_bucket(Bucket=BUCKET)
    q = client("sqs")
    dlq = q.create_queue(QueueName="jobs-deadletter")["QueueUrl"]
    arn = q.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    url = q.create_queue(QueueName="jobs")["QueueUrl"]
    q.set_queue_attributes(
        QueueUrl=url,
        Attributes={
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": arn, "maxReceiveCount": "3"})
        },
    )


def put(key, data):
    sha = hashlib.sha256(data).hexdigest()
    body = encrypt(data, key)
    client().put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="application/octet-stream",
        Metadata={"sha256": sha, "encryption": "client-aes256-gcm-v1"},
    )
    return sha


def get(key, sha):
    response = client().get_object(Bucket=BUCKET, Key=key)
    raw = response["Body"].read()
    plain = decrypt(raw, key)
    if hashlib.sha256(plain).hexdigest() != sha:
        raise ValueError("Empreinte objet incohérente")
    return plain


def queue_url():
    return setting("QUEUE_URL", "") or client("sqs").get_queue_url(QueueName="jobs")["QueueUrl"]


def enqueue(job_id):
    client("sqs").send_message(QueueUrl=queue_url(), MessageBody=str(job_id))


def deadletter(body):
    q = client("sqs")
    url = setting("DLQ_URL", "") or q.get_queue_url(QueueName="jobs-deadletter")["QueueUrl"]
    q.send_message(QueueUrl=url, MessageBody=body)
