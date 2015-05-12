from boto import ec2

from .base import BaseCloudProvider, PROVISION


class AWS(BaseCloudProvider):

    def __init__(self, config, credentials):
        self.credentials = credentials

    def create_machine(self, name, region='us-west-2',
                       image=None, inst_type=None,
                       min_count=1, max_count=1,
                       server='master.cloudrunner.io',
                       security_groups=None,
                       key_name=None, **kwargs):
        try:
            self.conn = ec2.connect_to_region(
                region,
                aws_access_key_id=self.credentials.user,
                aws_secret_access_key=self.credentials.password)

            res = self.conn.run_instances(
                image,
                min_count=min_count, max_count=max_count,
                user_data=PROVISION % dict(server=server,
                                           name=name,
                                           api_key=self.credentials.api_key),
                instance_type=inst_type,
                key_name=key_name,
                security_groups=security_groups)

            instance_ids = [inst.id for inst in res.instances]
            self.conn.create_tags(instance_ids, {"Name": name})
        except:
            return self.FAIL
        return self.OK

    def delete_machine(self, name, *args, **kwargs):
        pass
