import json

import pulumi
import pulumi_aws_native as awsn
from pulumi import ResourceOptions, Output
from pulumi_aws_native.ec2 import LaunchTemplate, LaunchTemplateArgs, LaunchTemplateDataArgs, \
    LaunchTemplateBlockDeviceMappingArgs, LaunchTemplateEbsArgs
from pulumi_aws_native.eks import Cluster, ClusterArgs, ClusterResourcesVpcConfigArgs, \
    Addon, AddonArgs, Nodegroup, NodegroupArgs, NodegroupLaunchTemplateSpecificationArgs, NodegroupScalingConfigArgs
import pulumi_awsx as awsx
from pulumi_aws_native.iam import Role, RoleArgs, OidcProvider, OidcProviderArgs

from utils import generate_userdata

awsn = awsn.Provider("awsn", region="us-east-1")

vpc = awsx.ec2.Vpc("vpc-repro-1747", opts=ResourceOptions(provider=awsn))

cluster_role = Role(resource_name=f"eks-role-1747",
                    args=RoleArgs(role_name="eks-role-1747",
                                  assume_role_policy_document=json.dumps({
                                      "Version": "2012-10-17",
                                      "Statement": [
                                          {
                                              "Effect": "Allow",
                                              "Principal": {
                                                  "Service": "eks.amazonaws.com"
                                              },
                                              "Action": "sts:AssumeRole"
                                          }
                                      ]
                                  }),
                                  managed_policy_arns=["arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
                                                       "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"]),
                    opts=ResourceOptions(provider=awsn))

cluster = Cluster(resource_name="eks-1747",
                  args=ClusterArgs(role_arn=cluster_role.arn, version="1.29",
                                   resources_vpc_config=ClusterResourcesVpcConfigArgs(
                                       subnet_ids=Output.all(vpc.private_subnet_ids, vpc.public_subnet_ids)
                                       .apply(lambda ids: ids[0] + ids[1]),
                                       endpoint_public_access=True,
                                       endpoint_private_access=True),
                                   ),
                  opts=ResourceOptions(provider=awsn))

oidc_provider = OidcProvider(resource_name="oidc-provider-1747",
                             args=OidcProviderArgs(url=cluster.open_id_connect_issuer_url,
                                                   client_id_list=["sts.amazonaws.com"]),
                             opts=ResourceOptions(provider=awsn))

vpc_cni_role = Role(resource_name=f"vpc-cni-role",
                    args=RoleArgs(assume_role_policy_document=oidc_provider.arn.apply(
                        lambda oidc_arn:
                        json.dumps({
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": {
                                        "Federated": oidc_arn
                                    },
                                    "Action": "sts:AssumeRoleWithWebIdentity",
                                    "Condition": {
                                        "StringEquals": {
                                            "/".join(oidc_arn.split("/")[1:])
                                            + ":sub": f"system:serviceaccount:kube-system:aws-node",
                                            "/".join(oidc_arn.split("/")[1:]) + ":aud": "sts.amazonaws.com"
                                        }
                                    }
                                }
                            ]
                        })),
                        managed_policy_arns=["arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"]),
                    opts=ResourceOptions(provider=awsn))

Addon(resource_name=f"vpc-cni-addon",
      args=AddonArgs(cluster_name=cluster.name, addon_name="vpc-cni",
                     service_account_role_arn=vpc_cni_role.arn),
      opts=ResourceOptions(provider=awsn))

node_role = Role(resource_name="nodes-role",
                 args=RoleArgs(assume_role_policy_document=json.dumps({
                     "Version": "2012-10-17",
                     "Statement": [
                         {
                             "Effect": "Allow",
                             "Principal": {
                                 "Service": "ec2.amazonaws.com"
                             },
                             "Action": "sts:AssumeRole"
                         }
                     ]
                 }),
                     managed_policy_arns=[
                         "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
                         "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
                         "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"]),
                 opts=ResourceOptions(provider=awsn))

eks_nodes_launch_template = LaunchTemplate(resource_name="cluster-launch-template",
                                           args=LaunchTemplateArgs(
                                               launch_template_data=LaunchTemplateDataArgs(
                                                   instance_type="m5.large",
                                                   image_id="ami-02561a005c32adc67",  # amazon-eks-node-1.29-v20240928
                                                   # image_id="ami-0cc12556e85f93d9a", # amazon-eks-node-1.29-v20240924
                                                   user_data=generate_userdata(cluster_name=cluster.name),
                                                   security_group_ids=[cluster.cluster_security_group_id],
                                                   block_device_mappings=[
                                                       LaunchTemplateBlockDeviceMappingArgs(
                                                           device_name="/dev/xvda",
                                                           ebs=LaunchTemplateEbsArgs(
                                                               volume_type="gp3",
                                                               volume_size=80,
                                                               iops=3000,
                                                               throughput=125))])),
                                           opts=ResourceOptions(provider=awsn))

Nodegroup(resource_name=f"managed-nodes",
          args=NodegroupArgs(cluster_name=cluster.name,
                             capacity_type="ON_DEMAND",
                             node_role=node_role.arn,
                             launch_template=NodegroupLaunchTemplateSpecificationArgs(
                                 name=eks_nodes_launch_template.launch_template_name,
                                 version=eks_nodes_launch_template.latest_version_number
                             ),
                             subnets=vpc.private_subnet_ids,
                             scaling_config=NodegroupScalingConfigArgs(desired_size=2,
                                                                       min_size=2,
                                                                       max_size=3)),
            opts=ResourceOptions(provider=awsn))
          # FIXME: Use this workaround to be able to Upgrade the NodeGroup with a new AMI
          # opts=ResourceOptions(replace_on_changes=["launchTemplate.version"],
          #                      delete_before_replace=False,
          #                      provider=awsn))


pulumi.export("cluster_name", cluster.name)