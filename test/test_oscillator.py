from nac.workflows.initialization import initialize
from nac.workflows.workflow_AbsortionSpectrum import workflow_oscillator_strength
from os.path import join
from qmflows.utils import dict2Setting
from .utilsTest import copy_basis_and_orbitals

import pytest
import os
import shutil


cp2k_main = dict2Setting({
    'cell_parameters': 28.0, 'potential': 'GTH-PBE',
    'basis': 'DZVP-MOLOPT-SR-GTH', 'specific':
    {'cp2k': {'force_eval':
              {'subsys': {'cell': {'periodic': 'None'}}, 'dft':
               {'print': {'mo': {'mo_index_range': '248 327'}},
                'scf': {'eps_scf': 0.0005, 'max_scf': 200,
                        'added_mos': 30}}}}},
    'cell_angles': [90.0, 90.0, 90.0]})

cp2k_guess = dict2Setting({
    'cell_parameters': 28.0, 'potential': 'GTH-PBE',
    'basis': 'DZVP-MOLOPT-SR-GTH', 'specific':
    {'cp2k': {'force_eval':
              {'subsys': {'cell': {'periodic': 'None'}},
               'dft': {'scf': {'eps_scf': 1e-06, 'ot':
                               {'minimizer': 'DIIS',
                                'n_diis': 7, 'preconditioner':
                                'FULL_SINGLE_INVERSE'},
                               'scf_guess': 'restart',
                               'added_mos': 0}}}}},
    'cell_angles': [90.0, 90.0, 90.0]})

# Environment data
basisname = 'DZVP-MOLOPT-SR-GTH'
path_traj_xyz = 'test/test_files/Cd.xyz'
scratch_path = 'scratch'
path_original_hdf5 = 'test/test_files/Cd.hdf5'
path_test_hdf5 = join(scratch_path, 'test.hdf5')
project_name = 'Cd'


@pytest.mark.slow
def test_couplings_and_oscillators():
    """
    Test couplings and oscillator strength for Cd33Se33
    """
    if not os.path.exists(scratch_path):
        os.makedirs(scratch_path)
    try:
        shutil.copy('test/test_files/BASIS_MOLOPT', scratch_path)
        shutil.copy('test/test_files/GTH_POTENTIALS', scratch_path)

        # Run the actual test
        copy_basis_and_orbitals(path_original_hdf5, path_test_hdf5,
                                project_name)
        data = calculate_oscillators()
        print(data)

    finally:
        # remove tmp data and clean global config
        shutil.rmtree(scratch_path)


def calculate_oscillators():
    """
    Compute a couple of couplings with the Levine algorithm
    using precalculated MOs.
    """
    initial_config = initialize(
        project_name, path_traj_xyz,
        basisname=basisname, path_basis=None,
        path_potential=None, enumerate_from=0,
        calculate_guesses='first', path_hdf5=path_test_hdf5,
        scratch_path=scratch_path)

    data = workflow_oscillator_strength(
        'cp2k', project_name, cp2k_main, guess_args=cp2k_guess,
        nHOMO=6, initial_states=list(range(1, 7)),
        energy_range=(0, 5),  # eV
        final_states=[range(7, 26)], **initial_config)

    return data


if __name__ == "__main__":
    test_couplings_and_oscillators()
