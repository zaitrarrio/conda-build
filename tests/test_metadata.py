import os
import subprocess
import sys

import pytest

from conda_build.metadata import select_lines, MetaData
from conda_build import api, conda_interface, render
from .utils import thisdir, metadata_dir


def test_uses_vcs_in_metadata(testing_workdir, testing_metadata):
    testing_metadata.meta_path = os.path.join(testing_workdir, 'meta.yaml')
    with open(testing_metadata.meta_path, 'w') as f:
        f.write('http://hg.something.com')
    assert not testing_metadata.uses_vcs_in_meta
    assert not testing_metadata.uses_vcs_in_build
    with open(testing_metadata.meta_path, 'w') as f:
        f.write('hg something something')
    assert not testing_metadata.uses_vcs_in_meta
    assert testing_metadata.uses_vcs_in_build
    with open(testing_metadata.meta_path, 'w') as f:
        f.write('hg.exe something something')
    assert not testing_metadata.uses_vcs_in_meta
    assert testing_metadata.uses_vcs_in_build
    with open(testing_metadata.meta_path, 'w') as f:
        f.write('HG_WEEEEE')
    assert testing_metadata.uses_vcs_in_meta
    assert not testing_metadata.uses_vcs_in_build


def test_select_lines():
    lines = """
test
test [abc] no
test [abc] # no

test [abc]
 'quoted # [abc] '
 "quoted # [abc] yes "
test # stuff [abc] yes
test {{ JINJA_VAR[:2] }}
test {{ JINJA_VAR[:2] }} # stuff [abc] yes
test {{ JINJA_VAR[:2] }} # stuff yes [abc]
test {{ JINJA_VAR[:2] }} # [abc] stuff yes
{{ environ["test"] }}  # [abc]
"""

    assert select_lines(lines, {'abc': True}) == """
test
test [abc] no
test [abc] # no

test
 'quoted'
 "quoted"
test
test {{ JINJA_VAR[:2] }}
test {{ JINJA_VAR[:2] }}
test {{ JINJA_VAR[:2] }}
test {{ JINJA_VAR[:2] }}
{{ environ["test"] }}
"""
    assert select_lines(lines, {'abc': False}) == """
test
test [abc] no
test [abc] # no

test {{ JINJA_VAR[:2] }}
"""


def test_disallow_leading_period_in_version(testing_metadata):
    testing_metadata.meta['package']['version'] = '.ste.ve'
    testing_metadata.final = True
    with pytest.raises(ValueError):
        testing_metadata.version()


def test_disallow_dash_in_features(testing_metadata):
    testing_metadata.meta['build']['features'] = ['abc']
    testing_metadata.parse_again()
    with pytest.raises(ValueError):
        testing_metadata.meta['build']['features'] = ['ab-c']
        testing_metadata.parse_again()


def test_append_section_data(testing_metadata):
    testing_metadata.final = False
    testing_metadata.parse_again()
    requirements_len = len(testing_metadata.meta['requirements']['build'])
    testing_metadata.config.append_sections_file = os.path.join(thisdir, 'test-append.yaml')
    testing_metadata.final = False
    testing_metadata.parse_again()
    assert len(testing_metadata.meta['requirements']['build']) == requirements_len + 1
    assert 'frank' in testing_metadata.meta['requirements']['build']


def test_clobber_section_data(testing_metadata):
    testing_metadata.config.clobber_sections_file = os.path.join(thisdir, 'test-clobber.yaml')
    testing_metadata.final = False
    testing_metadata.parse_again()
    # a field that should be clobbered
    testing_metadata.meta['about']['summary'] = 'yep'
    # a field that should stay the same
    testing_metadata.meta['about']['home'] = 'sweet home'


def test_build_bootstrap_env_by_name(testing_metadata):
    assert not any("git" in pkg for pkg in testing_metadata.meta["requirements"]["build"]), \
        testing_metadata.meta["requirements"]["build"]
    try:
        cmd = "conda create -y -n conda_build_bootstrap_test git"
        subprocess.check_call(cmd.split())
        testing_metadata.config.bootstrap = "conda_build_bootstrap_test"
        testing_metadata.final = False
        testing_metadata.parse_again()
        assert any("git" in pkg for pkg in testing_metadata.meta["requirements"]["build"]), \
            testing_metadata.meta["requirements"]["build"]
    finally:
        cmd = "conda remove -y -n conda_build_bootstrap_test --all"
        subprocess.check_call(cmd.split())


def test_build_bootstrap_env_by_path(testing_metadata):
    assert not any("git" in pkg for pkg in testing_metadata.meta["requirements"]["build"]), \
        testing_metadata.meta["requirements"]["build"]
    path = os.path.join(thisdir, "conda_build_bootstrap_test")
    try:
        cmd = "conda create -y -p {} git".format(path)
        subprocess.check_call(cmd.split())
        testing_metadata.config.bootstrap = path
        testing_metadata.final = False
        testing_metadata.parse_again()
        assert any("git" in pkg for pkg in testing_metadata.meta["requirements"]["build"]), \
            testing_metadata.meta["requirements"]["build"]
    finally:
        cmd = "conda remove -y -p {} --all".format(path)
        subprocess.check_call(cmd.split())


@pytest.mark.parametrize('py_ver', [('2.7', 'vs2008_win-x86_64'),
                                    ('3.4', 'vs2010_win-x86_64'),
                                    ('3.5', 'vs2015_win-x86_64'), ])
def test_native_compiler_metadata_win(testing_config, py_ver, mocker):
    testing_config.platform = 'win'
    metadata = api.render(os.path.join(metadata_dir, '_compiler_jinja2'), config=testing_config,
                          variants={'python': py_ver[0], 'target_platform': 'win-x86_64'},
                          permit_unsatisfiable_variants=True,
                          finalize=False)[0][0]
    assert any(dep.startswith(py_ver[1]) for dep in metadata.meta['requirements']['build'])


def test_native_compiler_metadata_linux(testing_config, mocker):
    testing_config.platform = 'linux'
    metadata = api.render(os.path.join(metadata_dir, '_compiler_jinja2'),
                          config=testing_config, permit_unsatisfiable_variants=True,
                          finalize=False)[0][0]
    _64 = '64' if conda_interface.bits == 64 else '32'
    assert any(dep.startswith('gcc_linux-' + _64) for dep in metadata.meta['requirements']['build'])
    assert any(dep.startswith('gxx_linux-' + _64) for dep in metadata.meta['requirements']['build'])
    assert any(dep.startswith('gfortran_linux-' + _64) for dep in metadata.meta['requirements']['build'])


def test_native_compiler_metadata_osx(testing_config, mocker):
    testing_config.platform = 'osx'
    metadata = api.render(os.path.join(metadata_dir, '_compiler_jinja2'),
                          config=testing_config, permit_unsatisfiable_variants=True,
                          finalize=False)[0][0]
    _64 = '64' if conda_interface.bits == 64 else '32'
    assert any(dep.startswith('clang_osx-' + _64) for dep in metadata.meta['requirements']['build'])
    assert any(dep.startswith('clangxx_osx-' + _64) for dep in metadata.meta['requirements']['build'])
    assert any(dep.startswith('gfortran_osx-' + _64) for dep in metadata.meta['requirements']['build'])


def test_compiler_metadata_cross_compiler():
    variant = {'c_compiler': 'c-compiler-linux',
               'cxx_compiler': 'cxx-compiler-linux',
               'fortran_compiler': 'fortran-compiler-linux',
               'target_platform': 'osx-109-x86_64'}
    metadata = MetaData(os.path.join(metadata_dir, '_compiler_jinja2'), variant=variant)
    assert 'c-compiler-linux_osx-109-x86_64' in metadata.meta['requirements']['build']
    assert 'cxx-compiler-linux_osx-109-x86_64' in metadata.meta['requirements']['build']
    assert 'fortran-compiler-linux_osx-109-x86_64' in metadata.meta['requirements']['build']


req = 'zlib 1.2.8 '
if sys.platform == 'win32':
    vc_ver = '9' if sys.version_info[0] == 2 else '14'
    req += 'vc{}_'.format(vc_ver)
req += '3'
test_reqs = [req]
if sys.platform == 'win32':
    test_reqs.append('vc {}'.format(vc_ver))


def test_hash_build_id(testing_metadata):
    testing_metadata.meta['requirements']['build'] = test_reqs
    testing_metadata = render.finalize_metadata(testing_metadata)
    if sys.platform == 'win32':
        if sys.version_info[0] == 2:
            assert testing_metadata._hash_dependencies() == 'h5e09b76'
            assert testing_metadata.build_id() == 'h5e09b76_1'
        else:
            assert testing_metadata._hash_dependencies() == 'h9802f05'
            assert testing_metadata.build_id() == 'h9802f05_1'
    else:
        assert testing_metadata._hash_dependencies() == 'hbcfeb9f'
        assert testing_metadata.build_id() == 'hbcfeb9f_1'


def test_hash_build_id_key_order(testing_metadata):
    deps = testing_metadata.meta['requirements']['build'][:]

    # first, prepend
    newdeps = deps[:]
    newdeps.insert(0, 'steve')
    testing_metadata.meta['requirements']['build'] = newdeps
    hash_pre = testing_metadata._hash_dependencies()

    # next, append
    newdeps = deps[:]
    newdeps.append('steve')
    testing_metadata.meta['requirements']['build'] = newdeps
    hash_post = testing_metadata._hash_dependencies()

    # make sure they match
    assert hash_pre == hash_post


def test_hash_applies_to_custom_build_string(testing_metadata):
    testing_metadata.meta['build']['string'] = 'steve'
    testing_metadata.meta['requirements']['build'] = test_reqs
    testing_metadata = render.finalize_metadata(testing_metadata)
    if sys.platform == 'win32':
        if sys.version_info[0] == 2:
            assert testing_metadata.build_id() == 'steveh5e09b76'
        else:
            assert testing_metadata.build_id() == 'steveh9802f05'
    else:
        assert testing_metadata.build_id() == 'stevehbcfeb9f'


def test_config_member_decoupling(testing_metadata):
    testing_metadata.config.some_member = 'abc'
    b = testing_metadata.copy()
    b.config.some_member = '123'
    assert b.config.some_member != testing_metadata.config.some_member
