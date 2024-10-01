import base64

from pulumi import Input


def generate_userdata(cluster_name: Input[str]):
    return cluster_name.apply(lambda name:
                              base64.b64encode("""MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="==MYBOUNDARY=="

--==MYBOUNDARY==
Content-Type: text/x-shellscript; charset="us-ascii"
#!/bin/bash
set -ex
/etc/eks/bootstrap.sh {cluster_name}

--==MYBOUNDARY==--
""".format(cluster_name=name).encode('UTF-8')).decode('UTF-8'))
