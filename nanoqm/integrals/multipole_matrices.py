"""Compute multipole integrals using `Libint2 <https://github.com/evaleev/libint/wiki>`.

The interface to the C++ Libint2 library is located at the parent folder,
in the `libint` folder.

Index
-----
.. currentmodule:: nanoqm.integrals.multipole_matrices
.. autosummary::
    get_multipole_matrix
    compute_matrix_multipole

API
---
.. autofunction:: get_multipole_matrix
.. autofunction:: compute_matrix_multipole
"""
import logging
import os
import uuid
from os.path import join
from typing import List, Optional
import numpy as np

from compute_integrals import compute_integrals_multipole
from qmflows.common import AtomXYZ
from qmflows.type_hints import PathLike

from ..common import (DictConfig, Matrix, is_data_in_hdf5, retrieve_hdf5_data,
                      store_arrays_in_hdf5, tuplesXYZ_to_plams)

logger = logging.getLogger(__name__)


def get_multipole_matrix(config: DictConfig, inp: DictConfig, multipole: str) -> Matrix:
    """Retrieve the `multipole` number `i` from the trajectory. Otherwise compute it.

    Parameters
    ----------
    config
        Global configuration to run a workflow
    inp
        Information about the current point, e.g. molecular geometry.
    multipole
        Either overlap, dipole or quadrupole.

    Returns
    -------
    np.ndarray
        Tensor containing the multipole.

    """
    root = join(config.project_name, 'multipole',
                f'point_{inp.i + config.enumerate_from}')
    path_hdf5 = config.path_hdf5
    path_multipole_hdf5 = join(root, multipole)
    matrix_multipole = search_multipole_in_hdf5(
        path_hdf5, path_multipole_hdf5, multipole)

    if matrix_multipole is None:
        matrix_multipole = compute_matrix_multipole(inp.mol, config, multipole)
        store_arrays_in_hdf5(path_hdf5, path_multipole_hdf5, matrix_multipole)

    return matrix_multipole


def search_multipole_in_hdf5(
        path_hdf5: PathLike, path_multipole_hdf5: str, multipole: str) -> Optional[np.ndarray]:
    """Search if the multipole is already store in the HDF5."""
    if is_data_in_hdf5(path_hdf5, path_multipole_hdf5):
        logger.info(f"retrieving multipole: {multipole} from the hdf5")
        return retrieve_hdf5_data(path_hdf5, path_multipole_hdf5)
    else:
        logger.info(f"computing multipole: {multipole}")
        return None


def compute_matrix_multipole(
        mol: List[AtomXYZ], config: DictConfig, multipole: str) -> Matrix:
    """Compute a `multipole` matrix: overlap, dipole, etc. for a given geometry `mol`.

    The multipole is Computed in spherical coordinates.

    Note: for the dipole and quadrupole the super_matrix contains all the matrices stack all the
    0-axis.

    Parameters
    ----------
    mol
        Molecule to compute the dipole
    config
        Dictionary with the current configuration
    multipole
        kind of multipole to compute

    Returns
    -------
    np.ndarray
        Matrix with entries <ψi | x^i y^j z^k | ψj>

    """
    path_hdf5 = config.path_hdf5

    # Write molecule in temporal file
    path = join(config.scratch_path, f"molecule_{uuid.uuid4()}.xyz")
    mol_plams = tuplesXYZ_to_plams(mol)
    mol_plams.write(path)

    # name of the basis set
    basis_name = config["cp2k_general_settings"]["basis"]

    if multipole == 'overlap':
        matrix_multipole = compute_integrals_multipole(
            path, path_hdf5, basis_name, multipole)
    elif multipole == 'dipole':
        # The tensor contains the overlap + {x, y, z} dipole matrices
        super_matrix = compute_integrals_multipole(
            path, path_hdf5, basis_name, multipole)
        dim = super_matrix.shape[1]

        # Reshape the super_matrix as a tensor containing overlap + {x, y, z} dipole matrices
        matrix_multipole = super_matrix.reshape(4, dim, dim)

    elif multipole == 'quadrupole':
        # The tensor contains the overlap + {xx, xy, xz, yy, yz, zz} quadrupole matrices
        print("super_matrix: ", path, path_hdf5, basis_name, multipole)
        super_matrix = compute_integrals_multipole(
            path, path_hdf5, basis_name, multipole)
        dim = super_matrix.shape[1]

        # Reshape to 3d tensor containing overlap + {x, y, z} + {xx, xy, xz, yy, yz, zz} quadrupole matrices
        matrix_multipole = super_matrix.reshape(10, dim, dim)

    # Delete the tmp molecule file
    os.remove(path)

    return matrix_multipole
