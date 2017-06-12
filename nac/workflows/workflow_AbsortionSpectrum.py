
__all__ = ['workflow_oscillator_strength']

from collections import namedtuple
from itertools import chain
from noodles import (gather, schedule)
from nac.common import (
    Matrix, Vector, change_mol_units, getmass, h2ev,
    retrieve_hdf5_data, triang2mtx)
from nac.integrals.multipoleIntegrals import calcMtxMultipoleP
from nac.schedule.components import calculate_mos
from qmworks import run
from qmworks.parsers import parse_string_xyz
from scipy import sparse
from scipy.constants import physical_constants

import logging
import numpy as np

# Type hints
from typing import (Dict, List, Tuple)

# Get logger
logger = logging.getLogger(__name__)

# Named tuple
Oscillator = namedtuple("Oscillator",
                        ('initialS', 'finalS', 'deltaE', 'fij', 'components'))

au_energy_to_ev = physical_constants['atomic unit of energy'][0] / physical_constants['electron volt'][0]


def workflow_oscillator_strength(
        package_name: str, project_name: str, package_args: Dict,
        guess_args: Dict=None, geometries: List=None,
        dictCGFs: Dict=None, enumerate_from: int=0,
        calc_new_wf_guess_on_points: str=None,
        path_hdf5: str=None, package_config: Dict=None,
        work_dir: str=None,
        initial_states: List=None, final_states: List=None,
        traj_folders: List=None, hdf5_trans_mtx: str=None,
        nHOMO: int=None, couplings_range: Tuple=None,
        calculate_oscillator_every: int=50,
        convolution: str='gaussian', broadening: float=0.1,  # eV
        energy_range: Tuple=None,  # eV
        geometry_units='angstrom', **kwargs):
    """
    Compute the oscillator strength

    :param package_name: Name of the package to run the QM simulations.
    :param project_name: Folder name where the computations
    are going to be stored.
    :param geometry:string containing the molecular geometry.
    :param package_args: Specific settings for the package
    :param guess_args: Specific settings for guess calculate with `package`.
    :type package_args: dict
    :param initial_states: List of the initial Electronic states.
    :type initial_states: [Int]
    :param final_states: List containing the sets of possible electronic
    states.
    :type final_states: [[Int]]
    :param calc_new_wf_guess_on_points: Points where the guess wave functions
    are calculated.
    :param package_config: Parameters required by the Package.
    :param  convolution: gaussian | lorentzian
    :param calculate_oscillator_every: step to compute the oscillator strengths
    :returns: None
    """
    # Start logging event
    file_log = '{}.log'.format(project_name)
    logging.basicConfig(filename=file_log, level=logging.DEBUG,
                        format='%(levelname)s:%(message)s  %(asctime)s\n',
                        datefmt='%m/%d/%Y %I:%M:%S %p')

    # Point calculations Using CP2K
    mo_paths_hdf5 = calculate_mos(
        package_name, geometries, project_name, path_hdf5, traj_folders,
        package_args, guess_args, calc_new_wf_guess_on_points,
        enumerate_from, package_config=package_config)

    # geometries in atomic units
    molecules_au = [change_mol_units(parse_string_xyz(gs))
                    for gs in geometries]

    # Schedule the function the compute the Oscillator Strenghts
    scheduleOscillator = schedule(calcOscillatorStrenghts)

    oscillators = gather(
        *[scheduleOscillator(
            i, project_name, mo_paths_hdf5, dictCGFs, mol,
            path_hdf5, hdf5_trans_mtx=hdf5_trans_mtx,
            initial_states=initial_states, final_states=final_states)
          for i, mol in enumerate(molecules_au)
          if i % calculate_oscillator_every == 0])

    energies, promised_cross_section = create_promised_cross_section(
        path_hdf5, mo_paths_hdf5, oscillators, broadening, energy_range,
        convolution, calculate_oscillator_every)

    cross_section, data = run(
        gather(promised_cross_section, oscillators), folder=work_dir)

    # Transform the energy to eV
    energies *= au_energy_to_ev

    # Save cross section
    np.savetxt('cross_section_cm.txt',
               np.stack((energies, cross_section), axis=1),
               header='Energy [eV] photoabsorption_cross_section [cm^2]')

    # molar extinction coefficients (e in M-1 cm-1)
    nA = physical_constants['Avogadro constant'][0]
    cte = np.log(10) * 1e3 / nA
    extinction_coefficients = cross_section / cte
    np.savetxt('molar_extinction_coefficients.txt',
               np.stack((energies, extinction_coefficients), axis=1),
               header='Energy [eV] Extinction_coefficients [M^-1 cm^-1]')

    print("Calculation Done")

    # Write data in human readable format
    write_information(data)

    return data


def create_promised_cross_section(
        path_hdf5: str, mo_paths_hdf5: List, oscillators: List,
        broadening: float, energy_range: Tuple, convolution: str,
        calculate_oscillator_every: int):
    """
    Create the function call that schedule the computation of the
    photoabsorption cross section
    """
    # broadening in atomic units
    broad_au = broadening / h2ev

    # Energy grid in  hartrees
    initial_energy = energy_range[0] / h2ev
    final_energy = energy_range[1] / h2ev
    npoints = int((final_energy - initial_energy) / broad_au)
    energies = np.linspace(initial_energy, final_energy, npoints)

    # Compute the cross section
    schedule_cross_section = schedule(compute_cross_section_grid)

    return energies, schedule_cross_section(
        oscillators, path_hdf5, mo_paths_hdf5, convolution, energies,
        broadening, calculate_oscillator_every)


def compute_cross_section_grid(
        oscillators: List, path_hdf5: str, mo_paths_hdf5: List,
        convolution: str, energies: Vector, broadening: float,
        calculate_oscillator_every: int) -> float:
    """
    Compute the photoabsorption cross section as a function of the energy.
    See: The UV absorption of nucleobases: semi-classical ab initio spectra
    simulations. Phys. Chem. Chem. Phys., 2010, 12, 4959–4967
    """
    print(oscillators)
    # speed of light in a.u.
    c = 137.036
    # Constant
    cte = 2 * (np.pi ** 2) / c

    # convulation functions for the intensity
    convolution_functions = {'gaussian': gaussian_distribution,
                             'lorentzian': lorentzian_distribution}
    fun_convolution = convolution_functions[convolution]

    def compute_cross_section(energy: float) -> Vector:
        """
        compute a single value of the photoabsorption cross section by
        rearranging oscillator strengths by initial states and perform
        the summation.
        """
        # Photo absorption in length a.u.^2
        grid_au = cte * sum(
            sum(
                sum(osc.fij * fun_convolution(energy, osc.deltaE, broadening)
                    for osc in ws) / len(ws)
                for ws in zip(*arr)) for arr in zip(*oscillators))

        # convert the cross section to cm^2
        au_length = physical_constants['atomic unit of length'][0]

        return grid_au * (au_length * 100) ** 2

    vectorized_cross_section = np.vectorize(compute_cross_section)

    return vectorized_cross_section(energies)


def gaussian_distribution(x: float, center: float, delta: float) -> Vector:
    """
    Return gaussian as described at:
    Phys. Chem. Chem. Phys., 2010, 12, 4959–4967
    """
    pre_expo = np.sqrt(2 / np.pi) / delta
    expo = np.exp(-2 * ((x - center) / delta) ** 2)

    return pre_expo * expo


def lorentzian_distribution(
        x: float, center: float, delta: float) -> Vector:
    """
    Return a Lorentzian as described at:
    Phys. Chem. Chem. Phys., 2010, 12, 4959–4967
    """
    cte = delta / (2 * np.pi)
    denominator = (x - center) ** 2  + (delta / 2) ** 2

    return cte * (1 / denominator)


def calcOscillatorStrenghts(
        i: int, project_name: str,
        mo_paths_hdf5: str, dictCGFs: Dict,
        atoms: List, path_hdf5: str, hdf5_trans_mtx: str=None,
        initial_states: List=None, final_states: List=None):

    """
    Use the Molecular orbital Energies and Coefficients to compute the
    oscillator_strength.

    :param i: time frame
    :param project_name: Folder name where the computations
    are going to be stored.
    :param mo_paths_hdf5: Path to the MO coefficients and energies in the
    HDF5 file.
    :paramter dictCGFS: Dictionary from Atomic Label to basis set.
    :type     dictCGFS: Dict String [CGF],
              CGF = ([Primitives], AngularMomentum),
              Primitive = (Coefficient, Exponent)
    :param atoms: Molecular geometry.
    :type atoms: [namedtuple("AtomXYZ", ("symbol", "xyz"))]
    :param path_hdf5: Path to the HDF5 file that contains the
    numerical results.
    :param hdf5_trans_mtx: path to the transformation matrix in the HDF5 file.
    :param initial_states: List of the initial Electronic states.
    :type initial_states: [Int]
    :param final_states: List containing the sets of possible electronic
    states.
    :type final_states: [[Int]]
    """
    # Energy and coefficients at time t
    es, coeffs = retrieve_hdf5_data(path_hdf5, mo_paths_hdf5[i])

    # If the MO orbitals are given in Spherical Coordinates transform then to
    # Cartesian Coordinates.
    if hdf5_trans_mtx is not None:
        trans_mtx = retrieve_hdf5_data(path_hdf5, hdf5_trans_mtx)

    logger.info("Computing the oscillator strength at time: {}".format(i))
    # Overlap matrix

    # Origin of the dipole
    rc = compute_center_of_mass(atoms)

    # Dipole matrix element in spherical coordinates
    mtx_integrals_spher = calcDipoleCGFS(atoms, dictCGFs, rc, trans_mtx)

    oscillators = [
        compute_oscillator_strength(
            rc, atoms, dictCGFs, es, coeffs, mtx_integrals_spher, initialS, fs)
        for initialS, fs in zip(initial_states, final_states)]

    return oscillators


def compute_oscillator_strength(
        rc: Tuple, atoms: List, dictCGFs: Dict, es: Vector, coeffs: Matrix,
        mtx_integrals_spher: Matrix, initialS: int, fs: List):
    """
    Compute the oscillator strenght using the matrix elements of the position
    operator:

    .. math:
    f_i->j = 2/3 * E_i->j * ∑^3_u=1 [ <ψi | r_u | ψj> ]^2

    where Ei→j is the single particle energy difference of the transition
    from the Kohn-Sham state ψi to state ψj and rμ = x,y,z is the position
    operator.
    """
    # Retrieve the molecular orbital coefficients and energies
    css_i = coeffs[:, initialS]
    energy_i = es[initialS]

    # Compute the oscillator strength
    xs = []
    for finalS in fs:
        # Get the molecular orbitals coefficients and energies
        css_j = coeffs[:, finalS]
        energy_j = es[finalS]
        deltaE = energy_j - energy_i

        # compute the oscillator strength and the transition dipole components
        fij, components = oscillator_strength(
            css_i, css_j, deltaE, mtx_integrals_spher)

        st = 'transition {:d} -> {:d} Fij = {:f}\n'.format(
            initialS, finalS, fij)
        logger.info(st)
        osc = Oscillator(initialS, finalS, deltaE, fij, components)
        xs.append(osc)

    return xs


def write_information(data: Tuple) -> None:
    """
    Write to a file the oscillator strenght information
    """
    header = "Transition Energy[eV] Energy[nm^-1] Oscillator Transition_dipole_components [a.u.]\n"
    filename = 'oscillators.txt'
    for xs in list(chain(*data)):
        with open(filename, 'w') as f:
            f.write(header)
        for args in xs:
            write_oscillator(filename, *args)


def write_oscillator(
        filename: str, initialS: int, finalS: int, deltaE: float, fij: float,
        components: Tuple) -> None:
    """
    Write oscillator strenght information in one file
    """
    energy = deltaE * h2ev
    energy_nm = deltaE * 2.19475e5 * 1e7  # a.u. to cm^-1 to nm^-1
    fmt = '{}->{} {:12.5f} {:12.5e} {:12.5f} {:11.5f} {:11.5f} {:11.5f}\n'.format(
        initialS, finalS, energy, energy_nm, fij, *components)

    with open(filename, 'a') as f:
        f.write(fmt)


def transform2Spherical(trans_mtx: Matrix, matrix: Matrix) -> Matrix:
    """
    Transform from spherical to cartesians using the sparse representation
    """
    trans_mtx = sparse.csr_matrix(trans_mtx)
    transpose = trans_mtx.transpose()

    return trans_mtx.dot(sparse.csr_matrix.dot(matrix, transpose))


def calcDipoleCGFS(
        atoms: List, dictCGFs: List, rc: Tuple, trans_mtx: Matrix) -> Matrix:
    """
    Compute the Multipole matrix in cartesian coordinates and
    expand it to a matrix and finally convert it to spherical coordinates.

    :param atoms: Atomic label and cartesian coordinates in au.
    type atoms: List of namedTuples
    :param cgfsN: Contracted gauss functions normalized, represented as
    a list of tuples of coefficients and Exponents.
    type cgfsN: [(Coeff, Expo)]
    :param trans_mtx: Transformation matrix to translate from Cartesian
    to Sphericals.
    :type trans_mtx: Numpy Matrix
    :returns: tuple(<ψi | x | ψj>, <ψi | y | ψj>, <ψi | z | ψj> )
    """
    # x,y,z exponents value for the dipole
    exponents = [{'e': 1, 'f': 0, 'g': 0}, {'e': 0, 'f': 1, 'g': 0},
                 {'e': 0, 'f': 0, 'g': 1}]

    dimCart = trans_mtx.shape[1]
    mtx_integrals_triang = tuple(calcMtxMultipoleP(atoms, dictCGFs, rc, **kw)
                                 for kw in exponents)
    mtx_integrals_cart = tuple(triang2mtx(xs, dimCart)
                               for xs in mtx_integrals_triang)
    return tuple(transform2Spherical(trans_mtx, x) for x
                 in mtx_integrals_cart)


def oscillator_strength(css_i: Matrix, css_j: Matrix, energy: float,
                        mtx_integrals_spher: Matrix) -> Tuple:
    """
    Calculate the oscillator strength between two state i and j using a
    molecular geometry in atomic units, a set of contracted gauss functions
    normalized, the coefficients for both states, the nergy difference between
    the states and a matrix to transform from cartesian to spherical
    coordinates in case the coefficients are given in cartesian coordinates.

    :param css_i: MO coefficients of initial state
    :param css_j: MO coefficients of final state
    :param energy: energy difference i -> j.
    :returns: Oscillator strength
    """
    components = tuple(
        map(lambda mtx: np.dot(css_i, np.dot(mtx, css_j)),
            mtx_integrals_spher))

    sum_integrals = sum(x ** 2 for x in components)

    fij = (2 / 3) * energy * sum_integrals

    return fij, components


def compute_center_of_mass(atoms: List) -> Tuple:
    """
    Compute the center of mass of a molecule
    """
    # Get the masses of the atoms
    symbols = map(lambda at: at.symbol, atoms)
    masses = np.array([getmass(s) for s in symbols])
    total_mass = np.sum(masses)

    # Multiple the mass by the coordinates
    mrs = [getmass(at.symbol) * np.array(at.xyz) for at in atoms]
    xs = np.sum(mrs, axis=0)

    # Center of mass
    cm = xs / total_mass

    return tuple(cm)
