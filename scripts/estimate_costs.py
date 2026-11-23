"""Budget de scénario Paris depuis tarifs publics AWS datés, sans crédit ni facture inventée."""

import json
from decimal import Decimal
from pathlib import Path

R = Path(__file__).resolve().parents[1]
d = R / "docs/evidence/finops"


def price(file, sku):
    j = json.loads((d / file).read_text())
    if "rates" in j:
        rates = [r for r in j["rates"] if r["sku"] == sku]
        r = next(r for r in rates if r["range"][0] == "0")
        return Decimal(r["price"])
    product = next(p for p in j["products"] if p["sku"] == sku)
    return Decimal(
        next(v for t in product["terms"].values() for v in t["priceDimensions"].values())[
            "pricePerUnit"
        ]["USD"]
    )


rows = []


def add(name, q, rate, unit, source, sku=None):
    rows.append(
        {
            "item": name,
            "quantity": q,
            "unit": unit,
            "usd_unit_price": str(rate),
            "estimated_usd": str(Decimal(str(q)) * rate),
            "source": source,
            "sku": sku,
        }
    )


add(
    "EKS standard control plane",
    730,
    Decimal(".10"),
    "cluster-hour",
    "https://aws.amazon.com/eks/pricing/",
)
for name, q, file, sku, unit in [
    (
        "EC2 Linux t3.medium, two nodes",
        1460,
        "ec2-prices.json",
        "89YAB55PARJAUR5B",
        "instance-hour",
    ),
    ("EBS gp3, two 20 GB nodes", 40, "ec2-prices.json", "XCKADFE99D2BK5V6", "GB-month"),
    ("NAT gateway, one AZ", 730, "ec2-prices.json", "XZT57E2HU6XVM9V7", "gateway-hour"),
    ("NAT processed traffic assumption", 5, "ec2-prices.json", "QBM2FSFWP6GWWHMU", "GB"),
    (
        "RDS PostgreSQL db.t4g.micro Multi-AZ",
        730,
        "rds-prices.json",
        "89KRWUARVTRG7P62",
        "instance-hour",
    ),
    ("RDS Multi-AZ gp3 storage", 20, "rds-storage-prices.json", "CJG2KQWW9D9H7DNZ", "GB-month"),
    ("S3 Standard stored assumption", 5, "pricing-AmazonS3.json", "4PMVMK58J94ER67S", "GB-month"),
    ("S3 PUT/LIST assumption", 10000, "pricing-AmazonS3.json", "JSTCNSNFYXFKBECA", "request"),
    (
        "SQS Standard request assumption",
        100000,
        "pricing-AWSQueueService.json",
        "HSP76GSZN55FQXBC",
        "request",
    ),
    ("One KMS key version", 1, "pricing-awskms.json", "G6KAA982ZNRYXTGR", "key-month"),
    ("KMS calls assumption", 100000, "pricing-awskms.json", "QCRBRVP4WHFE4RN9", "request"),
    ("ECR stored images assumption", 2, "pricing-AmazonECR.json", "TUZFZPEXJNDK38FJ", "GB-month"),
    ("CloudWatch ingest assumption", 1, "pricing-AmazonCloudWatch.json", "BN4XSGJA9MMZKCP7", "GB"),
    (
        "CloudWatch stored logs assumption",
        1,
        "pricing-AmazonCloudWatch.json",
        "ZCM3MJRQPU2BK43T",
        "GB-month",
    ),
    (
        "Three public IPv4, NAT and optional NLB",
        2190,
        "pricing-AmazonVPC.json",
        "T7GTF6TYY473HUA4",
        "address-hour",
    ),
    (
        "Optional public Network Load Balancer",
        730,
        "pricing-AWSELB.json",
        "N6NTFGZN2VWD4QEY",
        "LB-hour",
    ),
    (
        "Optional NLB capacity assumption",
        730,
        "pricing-AWSELB.json",
        "QMZXT6E5MCH634JS",
        "NLCU-hour",
    ),
]:
    add(name, q, price(file, sku), unit, str(json.loads((d / file).read_text())["source"]), sku)
subtotal = sum(Decimal(r["estimated_usd"]) for r in rows)
result = {
    "region": "eu-west-3",
    "scenario_hours": 730,
    "currency": "USD",
    "rate_sources": "AWS public offer files, publication timestamps retained in adjacent evidence",
    "rows": rows,
    "scenario_subtotal_usd": str(subtotal),
    "planning_margin_fraction": ".30",
    "scenario_with_margin_usd": str(subtotal * Decimal("1.30")),
    "actual_spend": None,
    "budget_approved": False,
    "exclusions": [
        "Taxes, currency conversion, credit agreements",
        "CPU surplus credits, extended EKS support, inter-AZ and internet egress",
        "Excess metrics/logs/requests, backup versions and retrieval beyond stated small assumptions",
        "RDS Secrets Manager service/rotation charges and optional domains/ACM services",
        "Node autoscaling beyond two nodes, controller/observability extra volume use",
    ],
    "limits": [
        "No cloud apply executed",
        "One NAT is an availability limit and cross-AZ traffic cost source",
        "Optional NLB is a scenario extension, not a Terraform resource already applied",
        "Margin is a proposal, not a guaranteed upper bound",
    ],
}
(d / "cost-scenario.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "scenario_subtotal_usd": str(subtotal),
            "with_30_percent_planning_margin_usd": str(subtotal * Decimal("1.30")),
            "actual_spend": None,
        }
    )
)
