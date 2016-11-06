
from nac import initialize
from nac.common import change_mol_units
from nac.schedule.scheduleCoupling import lazy_schedule_couplings
from nac.workflows.workflow_coupling import generate_pyxaid_hamiltonians
from nose.plugins.attrib import attr
from os.path import join
from pymonad import curry
from qmworks import (run, Settings)
from qmworks.parsers import parse_string_xyz
from utilsTest import try_to_remove

import h5py
import numpy as np
import os
import shutil

# ===============================<>============================================
path_hdf5 = 'test/test_files/ethylene.hdf5'
path_hdf5_test = 'test/test_files/test.hdf5'
path_xyz = 'test/test_files/threePoints.xyz'
project_name = 'ethylene'


def is_antisymmetric(arr):
    """
    Check if a matrix is antisymmetric. Notice that the coupling matrix has
    all the diagonal elements equal to zero.
    """
    return np.sum(arr + np.transpose(arr)) < 1.0e-8


@attr('slow')
def test_workflow_coupling():
    """
    run a single point calculation using CP2K and store the MOs.
    """
    home = os.path.expanduser('~')  # HOME Path
    scratch_path = join(home, '.test_qmworks')
    if not os.path.exists(scratch_path):
        os.makedirs(scratch_path)
    try:
        shutil.copy('test/test_files/BASIS_MOLOPT', scratch_path)
        shutil.copy('test/test_files/GTH_POTENTIALS', scratch_path)
        basiscp2k = join(scratch_path, 'BASIS_MOLOPT')
        potcp2k = join(scratch_path, 'GTH_POTENTIALS')

        initial_config = initialize(project_name, path_xyz,
                                    "DZVP-MOLOPT-SR-GTH",
                                    path_basis=basiscp2k,
                                    path_potential=potcp2k,
                                    calculate_guesses=None,
                                    path_hdf5=path_hdf5_test,
                                    scratch=scratch_path)
        fun_workflow_coupling(initial_config)
        # fun_lazy_coupling(initial_config)
    finally:
        # remove tmp data and clean global config
        shutil.rmtree(scratch_path)


@try_to_remove([path_hdf5_test])
def fun_workflow_coupling(initial_config):
    """
    Call cp2k and calculated the coupling for an small molecule.
    """
    basis_pot = initial_config['package_config']
    # create Settings for the Cp2K Jobs
    cp2k_args = Settings()
    cp2k_args.basis = "DZVP-MOLOPT-SR-GTH"
    cp2k_args.potential = "GTH-PBE"
    cp2k_args.cell_parameters = [12.74] * 3
    dft = cp2k_args.specific.cp2k.force_eval.dft
    dft.scf.added_mos = 20
    dft.scf.diagonalization.jacobi_threshold = 1e-6

    force = cp2k_args.specific.cp2k.force_eval
    force.dft.basis_set_file_name = basis_pot['basis']
    force.dft.potential_file_name = basis_pot['potential']

    generate_pyxaid_hamiltonians('cp2k', project_name,
                                 cp2k_args, nCouplings=40,
                                 **initial_config)

    with h5py.File(path_hdf5) as f5, h5py.File(path_hdf5_test) as f6:
        path_es = 'ethylene/point_1/cp2k/mo/eigenvalues'
        es_expected = f5[path_es].value
        es_test = f6[path_es].value

        path_coupling = 'ethylene/coupling_0'
        coupling_expected = f5[path_coupling].value
        coupling_test = f6[path_coupling].value

        tolerance = 1e-8
        assert ((np.sum(es_expected - es_test) < tolerance) and
                (np.sum(coupling_expected - coupling_test) < tolerance))


@try_to_remove([path_hdf5_test])
def fun_lazy_coupling(initial_config):
    """
    The matrix containing the derivative coupling must be antisymmetric and
    it should be equal to the already known value stored in the HDF5 file:
    `test/test_files/ethylene.hdf5`
    """
    parser = curry(parse_string_xyz)

    # function composition
    new_fun = change_mol_units * parser
    geometries = tuple(map(new_fun, initial_config['geometries']))

    # The MOs were already computed an stored in ethylene.hdf5
    root_css = 'ethylene/point_{}/cp2k/mo/coefficients'.format
    root_es = 'ethylene/point_{}/cp2k/mo/exponents'.format
    mo_paths = [[root_es(i), root_css(i)] for i in range(3)]

    with h5py.File(path_hdf5) as f5, h5py.File(path_hdf5_test, 'w') as f6:
        # Copy the MOs and trans_mtx to the temporal hdf5
        f6.create_group('ethylene')
        f5.copy('ethylene/trans_mtx', f6['ethylene'])
        for k in range(3):
            p = 'ethylene/point_{}'.format(k)
            f5.copy(p, f6['ethylene'])

    output_folder = 'ethylene'
    rs = lazy_schedule_couplings(0, path_hdf5_test, initial_config['dictCGFs'],
                                 geometries, mo_paths, dt=1,
                                 hdf5_trans_mtx='ethylene/trans_mtx',
                                 output_folder=output_folder,
                                 nCouplings=40)
    path_coupling = run(rs)

    with h5py.File(path_hdf5, 'r') as f5, h5py.File(path_hdf5_test, 'r') as f6:
        expected = f5[path_coupling].value
        arr = f6[path_coupling].value

    # remove the hdf5 file used for testing

    assert is_antisymmetric(arr) and (np.sum(arr - expected) < 1.0e-8)
