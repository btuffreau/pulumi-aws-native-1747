# Reproduce pulumi-aws-native/issues/1747
ref. https://github.com/pulumi/pulumi-aws-native/issues/1747

TL;DR it's expected that changing the AMI ID via a launch template would trigger a node rotation.

## Assumes 2 launch templates, ideally referring to 2 different IDs
```bash
aws eks update-nodegroup-version  --cluster-name=$cluster_name --nodegroup-name=$nodegroup_name --launch-template name=$nodegroup_Name,version=2
aws eks update-nodegroup-version  --cluster-name=$cluster_name --nodegroup-name=$nodegroup_name --launch-template name=$nodegroup_Name,version=1
```

## Steps to reproduce
1. `pulumi up`
2. edit `ami_id` in eks_nodes_launch_template
3. `pulumi up`

```
  aws-native:eks:Nodegroup (managed-nodes):
    error: operation UPDATE failed with "InvalidRequest": You cannot specify the field releaseVersion when using custom AMIs. (Service: Eks, Status Code: 400, Request ID: dd4a5f62-dd56-4c7e-841e-466756c840ab)
```

### Utils
- Inspect NodeGroup outputs
pulumi stack export | jq '.deployment.resources[] | select(.type == "aws-native:eks:Nodegroup") | .outputs'

- Get kubeconfig:

`aws eks update-kubeconfig --alias repro --name $(pulumi stack output -j | jq .cluster_name) --region us-east-1`