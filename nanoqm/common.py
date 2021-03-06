"""Module containing physical constants and `NamedTuple`s to store molecular orbitals, shell, etc.

Index
-----
.. currentmodule:: nanoqm.common
.. autosummary::
    DictConfig
    change_mol_units
    getmass
    number_spherical_functions_per_atom
    retrieve_hdf5_data
    is_data_in_hdf5
    store_arrays_in_hdf5

API
---
.. autoclass:: DictConfig
.. autofunction:: is_data_in_hdf5
.. autofunction:: retrieve_hdf5_data
.. autofunction:: number_spherical_functions_per_atom
.. autofunction:: store_arrays_in_hdf5

"""

__all__ = ['DictConfig', 'Matrix', 'Tensor3D', 'Vector',
           'change_mol_units', 'getmass', 'h2ev', 'hardness',
           'number_spherical_functions_per_atom', 'retrieve_hdf5_data',
           'is_data_in_hdf5', 'store_arrays_in_hdf5']


import os
from itertools import chain, repeat
from pathlib import Path
from typing import (Any, Dict, Iterable, List, Mapping, NamedTuple, Tuple,
                    Union, overload)

import h5py
import mendeleev
import numpy as np
from qmflows.common import AtomXYZ
from qmflows.type_hints import PathLike
from scipy.constants import physical_constants
from scm.plams import Atom, Molecule


class DictConfig(dict):
    """Class to extend the Dict class with `.` dot notation."""

    def __getattr__(self, attr):
        """Extract key using dot notation."""
        return self.get(attr)

    def __setattr__(self, key, value):
        """Set value using dot notation."""
        self.__setitem__(key, value)

    def __deepcopy__(self, _):
        """Deepcopy of the Settings object."""
        return DictConfig(self.copy())


class BasisFormats(NamedTuple):
    """NamedTuple that contains the name/value for the basis formats."""

    name: str
    value: List[str]


def concat(xss: Iterable) -> List[Any]:
    """Concatenate of all the elements of a list."""
    return list(chain(*xss))


# ================> Constants <================
#: Angstrom to a.u
angs2au = 1e-10 / physical_constants['atomic unit of length'][0]
#: from femtoseconds to au
femtosec2au = 1e-15 / physical_constants['atomic unit of time'][0]
#: hartrees to electronvolts
h2ev = physical_constants['Hartree energy in eV'][0]
#: conversion from rydberg to meV
r2meV = 1e3 * physical_constants['Rydberg constant times hc in eV'][0]
#: conversion from fs to cm-1
fs_to_cm = 1e13 * physical_constants['hertz-inverse meter relationship'][0]
#: conversion from fs to nm
fs_to_nm = 299.79246
#: planck constant in eV * fs
hbar = 1e15 * physical_constants['Planck constant over 2 pi in eV s'][0]

# type hints
MolXYZ = List[AtomXYZ]
Vector = np.ndarray
Matrix = np.ndarray
Tensor3D = np.ndarray


def path_to_posix(path: PathLike) -> PathLike:
    """Convert a Path to posix string."""
    if isinstance(path, Path):
        return path.absolute().absolute()
    else:
        return path


def getmass(s: str) -> int:
    """Get the atomic mass for a given element s."""
    element = mendeleev.element(s.capitalize())
    return element.mass_number


def hardness(s: str) -> float:
    """Get the element hardness."""
    d = {
        'h': 6.4299, 'he': 12.5449, 'li': 2.3746, 'be': 3.4968, 'b': 4.619, 'c': 5.7410,
        'n': 6.8624, 'o': 7.9854, 'f': 9.1065, 'ne': 10.2303, 'na': 2.4441, 'mg': 3.0146,
        'al': 3.5849, 'si': 4.1551, 'p': 4.7258, 's': 5.2960, 'cl': 5.8662, 'ar': 6.4366,
        'k': 2.3273, 'ca': 2.7587, 'sc': 2.8582, 'ti': 2.9578, 'v': 3.0573, 'cr': 3.1567,
        'mn': 3.2564, 'fe': 3.3559, 'co': 3.4556, 'ni': 3.555, 'cu': 3.6544, 'zn': 3.7542,
        'ga': 4.1855, 'ge': 4.6166, 'as': 5.0662, 'se': 5.4795, 'br': 5.9111, 'kr': 6.3418,
        'rb': 2.1204, 'sr': 2.5374, 'y': 2.6335, 'zr': 2.7297, 'nb': 2.8260, 'mo': 2.9221,
        'tc': 3.0184, 'ru': 3.1146, 'rh': 3.2107, 'pd': 3.3069, 'ag': 3.4032, 'cd': 3.4994,
        'in': 3.9164, 'sn': 4.3332, 'sb': 4.7501, 'te': 5.167, 'i': 5.5839, 'xe': 6.0009,
        'cs': 0.6829, 'ba': 0.9201, 'la': 1.1571, 'ce': 1.3943, 'pr': 1.6315, 'nd': 1.8686,
        'pm': 2.1056, 'sm': 2.3427, 'eu': 2.5798, 'gd': 2.8170, 'tb': 3.0540, 'dy': 3.2912,
        'ho': 3.5283, 'er': 3.7655, 'tm': 4.0026, 'yb': 4.2395, 'lu': 4.4766, 'hf': 4.7065,
        'ta': 4.9508, 'w': 5.1879, 're': 5.4256, 'os': 5.6619, 'ir': 5.900, 'pt': 6.1367,
        'au': 6.3741, 'hg': 6.6103, 'tl': 1.7043, 'pb': 1.9435, 'bi': 2.1785, 'po': 2.4158,
        'at': 2.6528, 'rn': 2.8899, 'fr': 0.9882, 'ra': 1.2819, 'ac': 1.3497, 'th': 1.4175,
        'pa': 1.9368, 'u': 2.2305, 'np': 2.5241, 'pu': 3.0436, 'am': 3.4169, 'cm': 3.4050,
        'bk': 3.9244, 'cf': 4.2181, 'es': 4.5116, 'fm': 4.8051, 'md': 5.0100, 'no': 5.3926,
        'lr': 5.4607}
    return d[s] / 27.211


def xc(s: str) -> Dict[str, Any]:
    """Return the exchange functional composition."""
    d = {
        'pbe': {
            'type': 'pure', 'alpha1': 1.42, 'alpha2': 0.48, 'ax': 0, 'beta1': 0.2, 'beta2': 1.83},
        'blyp': {
            'type': 'pure', 'alpha1': 1.42, 'alpha2': 0.48, 'ax': 0, 'beta1': 0.2, 'beta2': 1.83},
        'bp': {
            'type': 'pure', 'alpha1': 1.42, 'alpha2': 0.48, 'ax': 0, 'beta1': 0.2, 'beta2': 1.83},
        'pbe0': {
            'type': 'hybrid', 'alpha1': 1.42, 'alpha2': 0.48, 'ax': 0.25, 'beta1': 0.2, 'beta2': 1.83},
        'b3lyp': {
            'type': 'hybrid', 'alpha1': 1.42, 'alpha2': 0.48, 'ax': 0.20, 'beta1': 0.2, 'beta2': 1.83},
        'bhlyp': {
            'type': 'hybrid', 'alpha1': 1.42, 'alpha2': 0.48, 'ax': 0.50, 'beta1': 0.2, 'beta2': 1.83},
        'cam-b3lyp': {
            'type': 'rhs', 'alpha1': 1.86, 'alpha2': 0.00, 'ax': 0.38, 'beta1': 0.90, 'beta2': 0},
        'lc-blyp': {
            'type': 'rhs', 'alpha1': 8.0, 'alpha2': 0.00, 'ax': 0.53, 'beta1': 4.50, 'beta2': 0},
        'wb97': {
            'type': 'rhs', 'alpha1': 8.0, 'alpha2': 0.00, 'ax': 0.61, 'beta1': 4.41, 'beta2': 0.0}}
    return d[s]


@overload
def retrieve_hdf5_data(path_hdf5: PathLike, paths_to_prop: str) -> np.ndarray:
    ...


@overload
def retrieve_hdf5_data(path_hdf5: PathLike, paths_to_prop: List[str]) -> List[np.ndarray]:
    ...


def retrieve_hdf5_data(path_hdf5, paths_to_prop):
    """Read Numerical properties from ``paths_hdf5``.

    Parameters
    ----------
    path_hdf5
        path to the HDF5
    path_to_prop
        str or list of str to data

    Returns
    -------
    np.ndarray
        array or list of array

    Raises
    ------
    RuntimeError
        The property has not been found

    """
    path_hdf5 = path_to_posix(path_hdf5)
    try:
        with h5py.File(path_hdf5, 'r') as f5:
            if isinstance(paths_to_prop, list):
                return [f5[path][()] for path in paths_to_prop]
            else:
                return f5[paths_to_prop][()]
    except KeyError:
        msg = f"There is not {paths_to_prop} stored in the HDF5\n"
        raise KeyError(msg)
    except FileNotFoundError:
        msg = "there is not HDF5 file containing the numerical results"
        raise RuntimeError(msg)


def is_data_in_hdf5(path_hdf5: PathLike, xs: Union[str, List[str]]) -> bool:
    """Search if the node exists in the HDF5 file.

    Parameters
    ----------
    path_hdf5
        path to the HDF5
    xs
        either Node path or a list of paths to the stored data

    Returns
    -------
    bool
        Whether the data is stored

    """
    path_hdf5 = path_to_posix(path_hdf5)
    if os.path.exists(path_hdf5):
        with h5py.File(path_hdf5, 'r+') as f5:
            if isinstance(xs, list):
                return all(path in f5 for path in xs)
            else:
                return xs in f5
    else:
        return False


@overload
def store_arrays_in_hdf5(
        path_hdf5: PathLike, paths: str, tensor: np.ndarray,
        dtype: float = np.float32, attribute: Union[BasisFormats, None] = None) -> None:
    ...


@overload
def store_arrays_in_hdf5(
    path_hdf5: PathLike, paths: List[str], tensor: np.ndarray,
        dtype: float = np.float32, attribute: Union[BasisFormats, None] = None) -> None:
    ...


def store_arrays_in_hdf5(
        path_hdf5, paths, tensor, dtype=np.float32, attribute=None):
    """Store a tensor in the HDF5.

    Parameters
    ----------
    path_hdf5
        path to the HDF5
    paths
        str or list of nodes where the data is going to be stored
    tensor
        Numpy array or list of array to store
    dtype
        Data type use to store the numerical array
    attribute
        Attribute associated with the tensor

    """
    path_hdf5 = path_to_posix(path_hdf5)

    def add_attribute(data_set, k: int = 0):
        if attribute is not None:
            dset.attrs[attribute.name] = attribute.value[k]

    with h5py.File(path_hdf5, 'r+') as f5:
        if isinstance(paths, list):
            for k, path in enumerate(paths):
                data = tensor[k]
                dset = f5.require_dataset(path, shape=np.shape(data),
                                          data=data, dtype=dtype)
                add_attribute(dset, k)
        else:
            dset = f5.require_dataset(paths, shape=np.shape(
                tensor), data=tensor, dtype=dtype)
            add_attribute(dset)


def change_mol_units(mol: List[AtomXYZ], factor: float = angs2au) -> List[AtomXYZ]:
    """Change the units of the molecular coordinates."""
    new_molecule = []
    for atom in mol:
        coord = tuple(map(lambda x: x * factor, atom.xyz))
        new_molecule.append(AtomXYZ(atom.symbol, coord))
    return new_molecule


def tuplesXYZ_to_plams(xs: List[AtomXYZ]) -> Molecule:
    """Transform a list of namedTuples to a Plams molecule."""
    plams_mol = Molecule()
    for at in xs:
        symb = at.symbol
        cs = at.xyz
        plams_mol.add_atom(Atom(symbol=symb, coords=tuple(cs)))

    return plams_mol


def number_spherical_functions_per_atom(
        mol: List[AtomXYZ], package_name: str, basis_name: str, path_hdf5: PathLike) -> np.ndarray:
    """Compute the number of spherical shells per atom."""
    with h5py.File(path_hdf5, 'r') as f5:
        xs = [f5[f'{package_name}/basis/{atom[0]}/{basis_name}/coefficients']
              for atom in mol]
        ys = [calc_orbital_Slabels(
            read_basis_format(path.attrs['basisFormat'])) for path in xs]

        return np.stack([sum(len(x) for x in ys[i]) for i in range(len(mol))])


@overload
def calc_orbital_Slabels(fss: List[int]) -> List[Tuple[str, ...]]:
    ...


@overload
def calc_orbital_Slabels(fss: List[List[int]]) -> List[Tuple[str, ...]]:
    ...


def calc_orbital_Slabels(fss):
    """Compute the spherical CGFs for a given basis set.

    Most quantum packages use standard basis set which contraction is
    presented usually by a format like:
    c def2-SV(P)
    # c     (7s4p1d) / [3s2p1d]     {511/31/1}
    this mean that this basis set for the Carbon atom uses 7 ``s`` CGF,
    4 ``p`` CGF and 1 ``d`` CGFs that are contracted in 3 groups of 5-1-1
    ``s`` functions, 3-1 ``p`` functions and 1 ``d`` function. Therefore
    the basis set format can be represented by [[5,1,1], [3,1], [1]].

    On the other hand Cp2k uses a special basis set ``MOLOPT`` which
    format explanation can be found at: `C2pk
    <https://github.com/cp2k/cp2k/blob/e392d1509d7623f3ebb6b451dab00d1dceb9a248/cp2k/data/BASIS_MOLOPT>`_.

    Parameters
    ----------
    name
        Quantum package name
    fss
        Format basis set

    Returns
    -------
    list
        containing tuples with the spherical CGFs

    """
    angular_momentum = ['s', 'p', 'd', 'f', 'g']
    return concat([funSlabels(dict_cp2k_order_sphericals, label, fs)
                   for label, fs in zip(angular_momentum, fss)])


@overload
def funSlabels(d: Mapping[str, Tuple[str, ...]], label: str, fs: int) -> List[Tuple[str, ...]]:
    ...


@overload
def funSlabels(d: Mapping[str, Tuple[str, ...]], label: str, fs: List[int]) -> List[Tuple[str, ...]]:
    ...


def funSlabels(data, label, fs):
    """Search for the spherical functions for each orbital type `label`."""
    if isinstance(fs, list):
        fs = sum(fs)
    labels = repeat(data[label], fs)
    return labels


def read_basis_format(basis_format: str) -> List[int]:
    """Read the basis set using the specified format."""
    s = basis_format.replace('[', '').split(']')[0]
    fss = list(map(int, s.split(',')))
    fss = fss[4:]  # cp2k coefficient formats start in column 5
    return fss


#: Ordering of the Spherical shells
dict_cp2k_order_sphericals: Mapping[str, Tuple[str, ...]] = {
    's': ('s',),
    'p': ('py', 'pz', 'px'),
    'd': ('d-2', 'd-1', 'd0', 'd+1', 'd+2'),
    'f': ('f-3', 'f-2', 'f-1', 'f0', 'f+1', 'f+2', 'f+3')
}


def read_cell_parameters_as_array(file_cell_parameters: PathLike) -> Tuple[str, np.ndarray]:
    """Read the cell parameters as a numpy array."""
    arr = np.loadtxt(file_cell_parameters, skiprows=1)

    with open(file_cell_parameters, 'r') as f:
        header = f.readline()

    return header, arr
