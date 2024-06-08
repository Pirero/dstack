import os
from typing import Any, Dict, List, Optional

import botocore.client
import botocore.exceptions

import dstack.version as version
from dstack._internal.core.errors import ComputeResourceNotFoundError


def get_image_id(ec2_client: botocore.client.BaseClient, cuda: bool) -> str:
    image_name = (
        f"dstack-{version.base_image}" if not cuda else f"dstack-cuda-{version.base_image}"
    )

    response = ec2_client.describe_images(Filters=[{"Name": "name", "Values": [image_name]}])
    images = sorted(
        (i for i in response["Images"] if i["State"] == "available"),
        key=lambda i: i["CreationDate"],
        reverse=True,
    )
    if not images:
        raise ComputeResourceNotFoundError()
    return images[0]["ImageId"]


def create_security_group(
    ec2_client: botocore.client.BaseClient,
    project_id: str,
    vpc_id: Optional[str],
) -> str:
    security_group_name = "dstack_security_group_" + project_id.replace("-", "_").lower()
    describe_security_groups_filters = [
        {
            "Name": "group-name",
            "Values": [security_group_name],
        },
    ]
    if vpc_id is not None:
        describe_security_groups_filters.append(
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            }
        )
    response = ec2_client.describe_security_groups(Filters=describe_security_groups_filters)
    if response.get("SecurityGroups"):
        security_group = response["SecurityGroups"][0]
    else:
        create_security_group_kwargs = {}
        if vpc_id is not None:
            create_security_group_kwargs["VpcId"] = vpc_id
        security_group = ec2_client.create_security_group(
            Description="Generated by dstack",
            GroupName=security_group_name,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [
                        {"Key": "owner", "Value": "dstack"},
                        {"Key": "dstack_project", "Value": project_id},
                    ],
                },
            ],
            **create_security_group_kwargs,
        )
    security_group_id = security_group["GroupId"]

    _add_ingress_security_group_rule_if_missing(
        ec2_client=ec2_client,
        security_group=security_group,
        security_group_id=security_group_id,
        rule={
            "FromPort": 22,
            "ToPort": 22,
            "IpProtocol": "tcp",
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        },
    )
    _add_ingress_security_group_rule_if_missing(
        ec2_client=ec2_client,
        security_group=security_group,
        security_group_id=security_group_id,
        rule={
            "IpProtocol": "-1",
            "UserIdGroupPairs": [{"GroupId": security_group_id}],
        },
    )
    _add_egress_security_group_rule_if_missing(
        ec2_client=ec2_client,
        security_group=security_group,
        security_group_id=security_group_id,
        rule={"IpProtocol": "-1"},
    )
    return security_group_id


def create_instances_struct(
    disk_size: int,
    image_id: str,
    instance_type: str,
    iam_instance_profile_arn: Optional[str],
    user_data: str,
    tags: List[Dict[str, str]],
    security_group_id: str,
    spot: bool,
    subnet_id: Optional[str] = None,
    allocate_public_ip: bool = True,
) -> Dict[str, Any]:
    struct = dict(
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": disk_size,
                    "VolumeType": "gp2",
                },
            }
        ],
        ImageId=image_id,
        InstanceType=instance_type,
        MinCount=1,
        MaxCount=1,
        UserData=user_data,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": tags,
            },
        ],
    )
    if iam_instance_profile_arn:
        struct["IamInstanceProfile"] = {"Arn": iam_instance_profile_arn}
    if spot:
        struct["InstanceMarketOptions"] = {
            "MarketType": "spot",
            "SpotOptions": {
                "SpotInstanceType": "one-time",
                "InstanceInterruptionBehavior": "terminate",
            },
        }
    # AWS allows specifying either NetworkInterfaces for specific subnet_id
    # or instance-level SecurityGroupIds in case of no specific subnet_id, not both.
    if subnet_id is not None:
        struct["NetworkInterfaces"] = [
            {
                "AssociatePublicIpAddress": allocate_public_ip,
                "DeviceIndex": 0,
                "SubnetId": subnet_id,
                "Groups": [security_group_id],
            },
        ]
    else:
        struct["SecurityGroupIds"] = [security_group_id]
    return struct


def get_gateway_image_id(
    ec2_client: botocore.client.BaseClient, name_filter: str = None, owner_alias_filter: str = None
) -> str:
    if name_filter is None:
        name_filter = os.getenv(
            "AWS_GATEWAY_AMI", "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
        )
    if owner_alias_filter is None:
        owner_alias_filter = os.getenv("AWS_AMI_OWNER", "amazon")
    response = ec2_client.describe_images(
        Filters=[
            {
                "Name": "name",
                "Values": [name_filter],
            },
            {
                "Name": "owner-alias",
                "Values": [owner_alias_filter],
            },
        ],
    )
    image = sorted(response["Images"], key=lambda i: i["CreationDate"], reverse=True)[0]
    return image["ImageId"]


def create_gateway_security_group(
    ec2_client: botocore.client.BaseClient,
    project_id: str,
    vpc_id: Optional[str],
) -> str:
    security_group_name = "dstack_gw_sg_" + project_id.replace("-", "_").lower()
    describe_security_groups_filters = [
        {
            "Name": "group-name",
            "Values": [security_group_name],
        },
    ]
    if vpc_id is not None:
        describe_security_groups_filters.append(
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            }
        )
    response = ec2_client.describe_security_groups(Filters=describe_security_groups_filters)
    if response.get("SecurityGroups"):
        return response["SecurityGroups"][0]["GroupId"]
    create_security_group_kwargs = {}
    if vpc_id is not None:
        create_security_group_kwargs["VpcId"] = vpc_id
    security_group = ec2_client.create_security_group(
        Description="Generated by dstack",
        GroupName=security_group_name,
        TagSpecifications=[
            {
                "ResourceType": "security-group",
                "Tags": [
                    {"Key": "owner", "Value": "dstack"},
                    {"Key": "role", "Value": "gateway"},
                    {"Key": "dstack_project", "Value": project_id},
                ],
            },
        ],
        **create_security_group_kwargs,
    )
    group_id = security_group["GroupId"]

    ec2_client.authorize_security_group_ingress(
        GroupId=group_id,
        IpPermissions=[
            {
                "FromPort": 0,
                "ToPort": 65535,
                "IpProtocol": "tcp",
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }
        ],
    )

    ec2_client.authorize_security_group_egress(
        GroupId=group_id,
        IpPermissions=[{"IpProtocol": "-1"}],
    )
    return group_id


def get_vpc_id_by_name(
    ec2_client: botocore.client.BaseClient,
    vpc_name: str,
) -> Optional[str]:
    response = ec2_client.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": [vpc_name]}])
    if len(response["Vpcs"]) == 0:
        return None
    return response["Vpcs"][0]["VpcId"]


def get_default_vpc_id(ec2_client: botocore.client.BaseClient) -> Optional[str]:
    response = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    if "Vpcs" in response and len(response["Vpcs"]) > 0:
        return response["Vpcs"][0]["VpcId"]
    return None


def get_vpc_by_vpc_id(ec2_client: botocore.client.BaseClient, vpc_id: str) -> Optional[str]:
    response = ec2_client.describe_vpcs(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    if "Vpcs" in response and len(response["Vpcs"]) > 0:
        return response["Vpcs"][0]
    return None


def get_subnets_ids_for_vpc(
    ec2_client: botocore.client.BaseClient,
    vpc_id: str,
    allocate_public_ip: bool,
) -> List[str]:
    """
    If `allocate_public_ip` is True, returns public subnets found in the VPC.
    If `allocate_public_ip` is False, returns subnets with NAT found in the VPC.
    """
    subnets = _get_subnets_by_vpc_id(ec2_client=ec2_client, vpc_id=vpc_id)
    if len(subnets) == 0:
        return []
    subnets_ids = []
    for subnet in subnets:
        subnet_id = subnet["SubnetId"]
        if allocate_public_ip:
            is_public_subnet = _is_public_subnet(
                ec2_client=ec2_client, vpc_id=vpc_id, subnet_id=subnet_id
            )
            if is_public_subnet:
                subnets_ids.append(subnet_id)
        else:
            subnet_behind_nat = _is_subnet_behind_nat(
                ec2_client=ec2_client,
                vpc_id=vpc_id,
                subnet_id=subnet_id,
            )
            if subnet_behind_nat:
                subnets_ids.append(subnet_id)
    return subnets_ids


def _add_ingress_security_group_rule_if_missing(
    ec2_client: botocore.client.BaseClient,
    security_group: Dict,
    security_group_id: str,
    rule: Dict,
) -> bool:
    if _rule_exists(rule, security_group.get("IpPermissions", [])):
        return False
    ec2_client.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=[rule],
    )
    return True


def _add_egress_security_group_rule_if_missing(
    ec2_client: botocore.client.BaseClient,
    security_group: Dict,
    security_group_id: str,
    rule: Dict,
) -> bool:
    if _rule_exists(rule, security_group.get("IpPermissionsEgress", [])):
        return False
    ec2_client.authorize_security_group_egress(
        GroupId=security_group_id,
        IpPermissions=[rule],
    )
    return True


def _rule_exists(rule: Dict, rules: List[Dict]) -> bool:
    """
    Rule exists if there are an existing rule that includes all the keys with the same values.
    Note that the existing rule may have keys missing from the rule.
    """
    return any(_is_subset(rule, other_rule) for other_rule in rules)


def _is_subset(subset, superset) -> bool:
    if isinstance(subset, dict) and isinstance(superset, dict):
        return all(k in superset and _is_subset(v, superset[k]) for k, v in subset.items())
    if isinstance(subset, list) and isinstance(superset, list):
        return len(subset) == len(superset) and all(
            _is_subset(v1, v2) for v1, v2 in zip(subset, superset)
        )
    return subset == superset


def _get_subnets_by_vpc_id(
    ec2_client: botocore.client.BaseClient,
    vpc_id: str,
) -> List[Dict]:
    response = ec2_client.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    return response["Subnets"]


def _is_public_subnet(
    ec2_client: botocore.client.BaseClient,
    vpc_id: str,
    subnet_id: str,
) -> bool:
    # Public subnet – The subnet has a direct route to an internet gateway.
    # Private subnet – The subnet does not have a direct route to an internet gateway.

    # Check explicitly associated route tables
    response = ec2_client.describe_route_tables(
        Filters=[{"Name": "association.subnet-id", "Values": [subnet_id]}]
    )
    for route_table in response["RouteTables"]:
        for route in route_table["Routes"]:
            if "GatewayId" in route and route["GatewayId"].startswith("igw-"):
                return True

    # Main route table controls the routing of all subnetes
    # that are not explicitly associated with any other route table.
    if len(response["RouteTables"]) > 0:
        return False

    # Check implicitly associated main route table
    response = ec2_client.describe_route_tables(
        Filters=[
            {"Name": "association.main", "Values": ["true"]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )
    for route_table in response["RouteTables"]:
        for route in route_table["Routes"]:
            if "GatewayId" in route and route["GatewayId"].startswith("igw-"):
                return True

    return False


def _is_subnet_behind_nat(
    ec2_client: botocore.client.BaseClient,
    vpc_id: str,
    subnet_id: str,
) -> bool:
    # Check explicitly associated route tables
    response = ec2_client.describe_route_tables(
        Filters=[{"Name": "association.subnet-id", "Values": [subnet_id]}]
    )
    for route_table in response["RouteTables"]:
        for route in route_table["Routes"]:
            if "NatGatewayId" in route and route["NatGatewayId"].startswith("nat-"):
                return True

    # Main route table controls the routing of all subnetes
    # that are not explicitly associated with any other route table.
    if len(response["RouteTables"]) > 0:
        return False

    # Check implicitly associated main route table
    response = ec2_client.describe_route_tables(
        Filters=[
            {"Name": "association.main", "Values": ["true"]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )
    for route_table in response["RouteTables"]:
        for route in route_table["Routes"]:
            if "NatGatewayId" in route and route["NatGatewayId"].startswith("nat-"):
                return True

    return False
