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

MASTER_RELEASE = '5.0.0'
version_branch_regex = re.compile(r'^(master)|(R\d+\.\d+(\.\d+)?(\.x)?)$')


class ReleaseType(object):
    CONTINUOUS_INTEGRATION = 'continuous-integration'
    NIGHTLY = 'nightly'


def get_build_number(buildset, version, db_connection_info):
    import MySQLdb
    # db exceptions should fail the build, as we are not able to generate a proper build number
    db = MySQLdb.connect(**db_connection_info)
    cur = db.cursor()
    cur.execute("SELECT * FROM build_metadata_cache where zuul_buildset_id = %s and version = %s", (buildset, version))
    results = list(cur)
    if len(results) == 0:
        cur.execute("SELECT max(build_number) FROM build_metadata_cache GROUP BY version HAVING version = %s", (version,))
        results = list(cur)
        if len(results) == 0:
            # First build for this version
            build_number = 1
        else:
            build_number = results[0][0] + 1
        cur.execute("INSERT INTO build_metadata_cache (build_number, zuul_buildset_id, version) VALUES (%s, %s, %s)", (build_number, buildset, version))
        db.commit()
    else:
        build_number = results[0][0]
    db.close()
    return build_number


def main():
    module = AnsibleModule(
        argument_spec=dict(
            zuul=dict(type='dict', required=True),
            release_type=dict(type='str', required=False, default=ReleaseType.CONTINUOUS_INTEGRATION),
            build_cache_db_connection_info=dict(type='dict', required=False, default={})
        )
    )

    zuul = module.params['zuul']
    release_type = module.params['release_type']
    build_cache_db_connection_info = module.params['build_cache_db_connection_info']

    branch = zuul['branch']
    if not version_branch_regex.match(branch):
        branch = 'master'
    date = datetime.now().strftime("%Y%m%d%H%M%S")

    version = {'epoch': None}
    if branch == 'master':
        version['upstream'] = MASTER_RELEASE
        docker_version = 'master'
    else:
        version['upstream'] = branch[1:]
        docker_version = version['upstream']

    if build_cache_db_connection_info:
        build_number = get_build_number(zuul['buildset'], docker_version, build_cache_db_connection_info)
        module.exit_json(ansible_facts={'build_tag': build_number}, **result)

    if release_type == ReleaseType.CONTINUOUS_INTEGRATION:
        # Versioning in CI consists of change id, pachset and date
        change = zuul['change']
        patchset = zuul['patchset']
        version['distrib'] = "ci{change}.{patchset}".format(
            change=change, patchset=patchset, date=date
        )
        repo_name = "{change}-{patchset}".format(change=change, patchset=patchset)
    elif release_type == ReleaseType.NIGHTLY:
        version['distrib'] = "{}".format(build_number)
        docker_version = '{}-{:04}'.format(docker_version, build_number)
        repo_name = docker_version
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
        'repo_name': repo_name,
        'docker_version': docker_version,
    }

    module.exit_json(ansible_facts={'packaging': packaging}, **result)


if __name__ == "__main__":
    main()
