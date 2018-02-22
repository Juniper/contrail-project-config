import os
import re

from ansible.module_utils.basic import AnsibleModule
from datetime import datetime

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

result = dict(
    changed=False,
    original_message='',
    message='',
)

MASTER_RELEASE = '5.0'
version_branch_regex = re.compile(r'^(master)|(R\d+\.\d+(\.\d+)?(\.x)?)$')

def get_build_number(zuul):
    # if zuul buildset id in database, return previously saved build number
    # else get highest build number from the same version, increment and store with current zuul buildset id
    zuul_buildset_id = zuul['buildset']
    """SELECT build_number FROM build_metadata_cache WHERE zuul_buildset_id = %s"""
    """SELECT max(build_number)+1 FROM build_metadata_cache GROUP BY version HAVING version = %s"""
    """INSERT INTO build_metadata_cache (version, build_number, zuul_buildset_id) VALUES (%s, %s, %s)"""
    return 42

class ReleaseType(object):
    CONTINUOUS_INTEGRATION = 'continuous-integration'
    NIGHTLY = 'nightly'

def main():
    module = AnsibleModule(
        argument_spec=dict(
            zuul=dict(type='dict', required=True),
            release_type=dict(type='str', required=False, default=ReleaseType.CONTINUOUS_INTEGRATION)
        )
    )

    zuul = module.params['zuul']
    release_type = module.params['release_type']

    branch = zuul['branch']
    if not version_branch_regex.match(branch):
        branch = 'master'
    date = datetime.now().strftime("%Y%m%d%H%M%S")

    version = {'epoch': None}
    if branch == 'master':
        version['upstream'] = MASTER_RELEASE
        version['public'] = 'master'
    else:
        version['upstream'] = branch[1:]
        version['public'] = version['upstream']

    if release_type == ReleaseType.CONTINUOUS_INTEGRATION:
        # Versioning in CI consists of change id, pachset and date
        change = zuul['change']
        patchset = zuul['patchset']
        version['distrib'] = "ci{change}.{patchset}".format(
            change=change, patchset=patchset, date=date
        )
        build_tag = "{change}-{patchset}".format(change=change, patchset=patchset)
    elif release_type == ReleaseType.NIGHTLY:
        build_number = get_build_number()
        version['distrib'] = "{version}b{build_number}".format(version=version['public'], build_number=build_number)
        build_tag = "{version}-{build_number}".format(version=version['public'], build_number=build_number])
    else:
        module.fail_json(
            msg="Unknown release_type: %s" % (release_type,), **result
        )

    debian_dir = None
    for project in zuul['projects']:
        if project['short_name'] == 'contrail-packages':
            debian_dir = project['src_dir']

    if not debian_dir:
        module.fail_json(
            msg="Could not find contrail-packages repository" % (release_type,), **result
        )

    debian_dir = os.path.join(debian_dir, "debian/contrail/debian")
    target_dir = "contrail-%s" % (version['upstream'],)

    full_version = "{upstream}~{distrib}".format(**version)

    packaging = {
        'name': 'contrail',
        'debian_dir': debian_dir,
        'full_version': full_version,
        'version': version,
        'target_dir': target_dir,
        'build_tag': build_tag
    }

    module.exit_json(ansible_facts={'packaging': packaging}, **result)

if __name__ == "__main__":
    main()
