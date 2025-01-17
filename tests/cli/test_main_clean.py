# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import annotations

import json
from datetime import datetime
from os import PathLike, walk
from os.path import basename, exists, isdir, join
from shutil import copy

import pytest

from conda.base.constants import (
    CONDA_LOGS_DIR,
    CONDA_PACKAGE_EXTENSIONS,
    CONDA_TEMP_EXTENSIONS,
)
from conda.cli.main_clean import _get_size
from conda.core.subdir_data import create_cache_dir
from conda.gateways.disk.create import mkdir_p
from conda.gateways.logging import set_verbosity
from conda.testing import CondaCLIFixture, TmpEnvFixture
from conda.testing.integration import make_temp_package_cache


def _get_pkgs(pkgs_dir):
    _, dirs, _ = next(walk(pkgs_dir))
    return [join(pkgs_dir, pkg) for pkg in dirs]


def _get_tars(pkgs_dir):
    _, _, files = next(walk(pkgs_dir))
    return [
        join(pkgs_dir, file)
        for file in files
        if file.endswith(CONDA_PACKAGE_EXTENSIONS)
    ]


def _get_index_cache():
    cache_dir = create_cache_dir()
    _, _, files = next(walk(cache_dir))
    return [join(cache_dir, file) for file in files if file.endswith(".json")]


def _get_tempfiles(pkgs_dir):
    _, _, files = next(walk(pkgs_dir))
    return [
        join(pkgs_dir, file) for file in files if file.endswith(CONDA_TEMP_EXTENSIONS)
    ]


def _get_logfiles(pkgs_dir):
    root, _, files = next(walk(join(pkgs_dir, CONDA_LOGS_DIR)), [None, None, []])
    return [join(root, file) for file in files]


def _get_all(pkgs_dir):
    return _get_pkgs(pkgs_dir), _get_tars(pkgs_dir), _get_index_cache()


def assert_any_pkg(name, contents):
    assert any(basename(content).startswith(f"{name}-") for content in contents)


def assert_not_pkg(name, contents):
    assert not any(basename(content).startswith(f"{name}-") for content in contents)


# conda clean --force-pkgs-dirs
def test_clean_force_pkgs_dirs(
    clear_cache,
    conda_cli: CondaCLIFixture,
    tmp_env: TmpEnvFixture,
):
    pkg = "bzip2"

    with make_temp_package_cache() as pkgs_dir:
        # pkgs_dir is a directory
        assert isdir(pkgs_dir)

        with tmp_env(pkg):
            stdout, _, _ = conda_cli("clean", "--force-pkgs-dirs", "--yes", "--json")
            json.loads(stdout)  # assert valid json

            # pkgs_dir is removed
            assert not exists(pkgs_dir)

        # pkgs_dir is still removed
        assert not exists(pkgs_dir)


# conda clean --packages
def test_clean_and_packages(
    clear_cache,
    conda_cli: CondaCLIFixture,
    tmp_env: TmpEnvFixture,
):
    pkg = "bzip2"

    with make_temp_package_cache() as pkgs_dir:
        # pkg doesn't exist ahead of time
        assert_not_pkg(pkg, _get_pkgs(pkgs_dir))

        with tmp_env(pkg) as prefix:
            # pkg exists
            assert_any_pkg(pkg, _get_pkgs(pkgs_dir))

            # --json flag is regression test for #5451
            stdout, _, _ = conda_cli("clean", "--packages", "--yes", "--json")
            json.loads(stdout)  # assert valid json

            # pkg still exists since its in use by temp env
            assert_any_pkg(pkg, _get_pkgs(pkgs_dir))

            conda_cli("remove", "--prefix", prefix, pkg, "--yes", "--json")
            stdout, _, _ = conda_cli("clean", "--packages", "--yes", "--json")
            json.loads(stdout)  # assert valid json

            # pkg is removed
            assert_not_pkg(pkg, _get_pkgs(pkgs_dir))

        # pkg is still removed
        assert_not_pkg(pkg, _get_pkgs(pkgs_dir))


# conda clean --tarballs
def test_clean_tarballs(
    clear_cache,
    conda_cli: CondaCLIFixture,
    tmp_env: TmpEnvFixture,
):
    pkg = "bzip2"

    with make_temp_package_cache() as pkgs_dir:
        # tarball doesn't exist ahead of time
        assert_not_pkg(pkg, _get_tars(pkgs_dir))

        with tmp_env(pkg):
            # tarball exists
            assert_any_pkg(pkg, _get_tars(pkgs_dir))

            # --json flag is regression test for #5451
            stdout, _, _ = conda_cli("clean", "--tarballs", "--yes", "--json")
            json.loads(stdout)  # assert valid json

            # tarball is removed
            assert_not_pkg(pkg, _get_tars(pkgs_dir))

        # tarball is still removed
        assert_not_pkg(pkg, _get_tars(pkgs_dir))


# conda clean --index-cache
def test_clean_index_cache(
    clear_cache,
    conda_cli: CondaCLIFixture,
    tmp_env: TmpEnvFixture,
):
    pkg = "bzip2"

    with make_temp_package_cache():
        # index cache doesn't exist ahead of time
        assert not _get_index_cache()

        with tmp_env(pkg):
            # index cache exists
            assert _get_index_cache()

            stdout, _, _ = conda_cli("clean", "--index-cache", "--yes", "--json")
            json.loads(stdout)  # assert valid json

            # index cache is cleared
            assert not _get_index_cache()

        # index cache is still cleared
        assert not _get_index_cache()


# conda clean --tempfiles
def test_clean_tempfiles(
    clear_cache,
    conda_cli: CondaCLIFixture,
    tmp_env: TmpEnvFixture,
):
    """Tempfiles are either suffixed with .c~ or .trash.

    .c~ is used to indicate that conda is actively using that file. If the conda process is
    terminated unexpectedly these .c~ files may remain and hence can be cleaned up after the fact.

    .trash appears to be a legacy suffix that is no longer used by conda.

    Since the presence of .c~ and .trash files are dependent upon irregular termination we create
    our own temporary files to confirm they get cleaned up.
    """
    pkg = "bzip2"

    with make_temp_package_cache() as pkgs_dir:
        # tempfiles don't exist ahead of time
        assert not _get_tempfiles(pkgs_dir)

        with tmp_env(pkg):
            # mimic tempfiles being created
            path = _get_tars(pkgs_dir)[0]  # grab any tarball
            for ext in CONDA_TEMP_EXTENSIONS:
                copy(path, f"{path}{ext}")

            # tempfiles exist
            assert len(_get_tempfiles(pkgs_dir)) == len(CONDA_TEMP_EXTENSIONS)

            # --json flag is regression test for #5451
            stdout, _, _ = conda_cli(
                "clean", "--tempfiles", pkgs_dir, "--yes", "--json"
            )
            json.loads(stdout)  # assert valid json

            # tempfiles removed
            assert not _get_tempfiles(pkgs_dir)

        # tempfiles still removed
        assert not _get_tempfiles(pkgs_dir)


# conda clean --logfiles
def test_clean_logfiles(
    clear_cache,
    conda_cli: CondaCLIFixture,
    tmp_env: TmpEnvFixture,
):
    """Logfiles are found in pkgs_dir/.logs.

    Since these log files were uniquely created during the experimental
    phase of the conda-libmamba-solver.
    """
    pkg = "bzip2"

    with make_temp_package_cache() as pkgs_dir:
        # logfiles don't exist ahead of time
        assert not _get_logfiles(pkgs_dir)

        with tmp_env(pkg):
            # mimic logfiles being created
            logs = join(pkgs_dir, CONDA_LOGS_DIR)
            mkdir_p(logs)
            path = join(logs, f"{datetime.utcnow():%Y%m%d-%H%M%S-%f}.log")
            with open(path, "w"):
                pass

            # logfiles exist
            assert path in _get_logfiles(pkgs_dir)

            # --json flag is regression test for #5451
            stdout, _, _ = conda_cli("clean", "--logfiles", "--yes", "--json")
            json.loads(stdout)  # assert valid json

            # logfiles removed
            assert not _get_logfiles(pkgs_dir)

        # logfiles still removed
        assert not _get_logfiles(pkgs_dir)


# conda clean --all [--verbose]
@pytest.mark.parametrize("verbose", [True, False])
def test_clean_all(
    clear_cache,
    verbose: bool,
    conda_cli: CondaCLIFixture,
    tmp_env: TmpEnvFixture,
):
    pkg = "bzip2"
    args = ("--yes", "--json")
    if verbose:
        args = (*args, "--verbose")

    with make_temp_package_cache() as pkgs_dir:
        # pkg, tarball, & index cache doesn't exist ahead of time
        pkgs, tars, cache = _get_all(pkgs_dir)
        assert_not_pkg(pkg, pkgs)
        assert_not_pkg(pkg, tars)
        assert not cache

        with tmp_env(pkg) as prefix:
            # pkg, tarball, & index cache exists
            pkgs, tars, cache = _get_all(pkgs_dir)
            assert_any_pkg(pkg, pkgs)
            assert_any_pkg(pkg, tars)
            assert cache

            stdout, _, _ = conda_cli("clean", "--all", *args)
            json.loads(stdout)  # assert valid json

            # pkg still exists since its in use by temp env
            # tarball is removed
            # index cache is cleared
            pkgs, tars, cache = _get_all(pkgs_dir)
            assert_any_pkg(pkg, pkgs)
            assert_not_pkg(pkg, tars)
            assert not cache

            conda_cli("remove", "--prefix", prefix, pkg, *args)
            stdout, _, _ = conda_cli("clean", "--packages", *args)
            json.loads(stdout)  # assert valid json

            # pkg is removed
            # tarball is still removed
            # index cache is still cleared
            pkgs, tars, index_cache = _get_all(pkgs_dir)
            assert_not_pkg(pkg, pkgs)
            assert_not_pkg(pkg, tars)
            assert not cache

        # pkg is still removed
        # tarball is still removed
        # index cache is still cleared
        pkgs, tars, index_cache = _get_all(pkgs_dir)
        assert_not_pkg(pkg, pkgs)
        assert_not_pkg(pkg, tars)
        assert not cache

    set_verbosity(0)  # reset verbosity


# conda clean --all --verbose
@pytest.mark.parametrize("as_json", [True, False])
def test_clean_all_mock_lstat(
    clear_cache,
    mocker: MockerFixture,
    as_json: bool,
    conda_cli: CondaCLIFixture,
    tmp_env: TmpEnvFixture,
):
    pkg = "bzip2"
    args = ("--yes", "--verbose")
    if as_json:
        args = (*args, "--json")

    with make_temp_package_cache() as pkgs_dir, tmp_env(pkg) as prefix:
        # pkg, tarball, & index cache exists
        pkgs, tars, cache = _get_all(pkgs_dir)
        assert_any_pkg(pkg, pkgs)
        assert_any_pkg(pkg, tars)
        assert cache

        mocker.patch("os.lstat", side_effect=OSError)

        conda_cli("remove", "--prefix", prefix, pkg, *args)
        stdout, _, _ = conda_cli("clean", "--packages", *args)
        assert "WARNING:" in stdout
        if as_json:
            json.loads(stdout)  # assert valid json

        # pkg, tarball, & index cache still exists
        pkgs, tars, index_cache = _get_all(pkgs_dir)
        assert_any_pkg(pkg, pkgs)
        assert_any_pkg(pkg, tars)
        assert cache

    set_verbosity(0)  # reset verbosity


# _get_size unittest, valid file
def test_get_size(tmp_path: Path):
    warnings = []
    path = tmp_path / "file"
    path.write_text("hello")
    assert _get_size(path, warnings=warnings)
    assert not warnings


# _get_size unittest, invalid file
def test_get_size_None():
    with pytest.raises(OSError):
        _get_size("not-a-file", warnings=None)


# _get_size unittest, invalid file and collect warnings
def test_get_size_list():
    warnings = []
    with pytest.raises(NotImplementedError):
        _get_size("not-a-file", warnings=warnings)
    assert warnings
