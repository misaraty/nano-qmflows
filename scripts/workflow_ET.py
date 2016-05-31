__author__ = "Felipe Zapata"

# ================> Python Standard  and third-party <==========
from collections import namedtuple
from os.path import join

import fnmatch
import h5py
import numpy as np
import os
import plams

# ==================> Internal modules <==========
from nac.common import retrieve_hdf5_data
from nac.schedule.scheduleCoupling import schedule_transf_matrix
from nac.integrals.electronTransfer import photoExcitationRate
from noodles import (gather, schedule)

from qmworks import run, Settings
from qmworks.common import AtomXYZ
from qmworks.parsers import parse_string_xyz
from qmworks.utils import chunksOf, flatten

from workflow_coupling import (calculate_mos, create_dict_CGFs,
                               create_point_folder)
# ==============================<>=========================
# Tuple contanining file paths
JobFiles = namedtuple("JobFiles", ("get_xyz", "get_inp", "get_out", "get_MO"))

# ==============================> Main <==================================


def generate_hdf5_file(project_name, scratch_folder):
    """
    Generates a unique path to store temporal data as HDF5
    """
    scratch = join(scratch_folder, project_name)
    if not os.path.exists(scratch):
        os.makedirs(scratch)

    return join(scratch, 'quantum.hdf5')


def search_data_in_hdf5(path_hdf5, path_to_prop):
    """
    Search if the node exists in the HDF5 file.
    """
    with h5py.File(path_hdf5, 'r') as f5:
        if isinstance(paths_to_prop, list):
            pred = all(path in f5 for path in paths_to_prop)
        else:
            pred = paths_to_prop in f5

    return pred


def calculate_ETR(package_name, project_name, all_geometries, cp2k_args,
                  pathTimeCoeffs=None, initial_conditions=[0],
                  path_hdf5=None, enumerate_from=0):
    """
    Use a md trajectory to calculate the Electron transfer rate
    nmad.

    :param package_name: Name of the package to run the QM simulations.
    :type  package_name: String
    :param project_name: Folder name where the computations
    are going to be stored.
    :type project_name: String
    :param all_geometries: List of string cotaining the molecular geometries
    numerical results.
    :type path_traj_xyz: [String]
    :param package_args: Specific settings for the package
    :type package_args: dict
    :param use_wf_guess_each: number of Computations that used a previous
    calculation as guess for the wave function.
    :type use_wf_guess_each: Int
    :param enumerate_from: Number from where to start enumerating the folders
    create for each point in the MD
    :type enumerate_from: Int
    :returns: None
    """
    #  Environmental Variables
    cwd = os.path.realpath(".")
    
    basisName = cp2k_args.basis
    work_dir = os.path.join(cwd, project_name)
    if path_hdf5 is None:
        path_hdf5 = os.path.join(work_dir, "quantum.hdf5")

    # Create Work_dir if it does not exist
    if not os.path.exists(work_dir):
        os.makedirs(work_dir)

    # Generate a list of tuples containing the atomic label
    # and the coordinates to generate
    # the primitive CGFs
    atoms = parse_string_xyz(all_geometries[0])
    dictCGFs = create_dict_CGFs(path_hdf5, basisName, atoms)

    # Calculcate the matrix to transform from cartesian to spherical
    # representation of the overlap matrix
    hdf5_trans_mtx = schedule_transf_matrix(path_hdf5, atoms,
                                            basisName, work_dir,
                                            packageName=package_name)

    # Create a folder for each point the the dynamics
    traj_folders = create_point_folder(work_dir, len(all_geometries),
                                       enumerate_from)

    # Time-dependent coefficients
    time_depend_coeffs = retrieve_hdf5_data(path_hdf5, pathTimeCoeffs)
    
    # prepare Cp2k Jobs
    # Point calculations Using CP2K
    use_wf_guess_each = 1  # Use previous restart
    enumerate_from = 0  # starts naming from 0
    mo_paths_hdf5 = calculate_mos(package_name, all_geometries, work_dir,
                                  path_hdf5, traj_folders, cp2k_args,
                                  use_wf_guess_each, enumerate_from)

    # Number of ETR points calculated with the MD trajectory
    nPoints = len(all_geometries) - 2

    # List of tuples containing the electron transfer rates
    if hdf5_trans_mtx is not None:
            trans_mtx = retrieve_hdf5_data(path_hdf5, hdf5_trans_mtx)

    etrs = [schedule_photoexcitation(i, path_hdf5, dictCGFs, all_geometries,
                                     time_depend_coeffs, mo_paths_hdf5,
                                     trans_mtx=trans_mtx)
            for i in range(nPoints)]

    electronTransferRates = run(gather(*etrs))

    result = flatten(map(lambda ts: '{:10.6f} {:10.6f}\n'.format(*ts),
                         electronTransferRates))

    with open("ElectronTranferRates", "w") as f:
        f.write(result)

# ==============================> Tasks <=======================================


def schedule_photoexcitation(i, path_hdf5, dictCGFs, all_geometries,
                             time_depend_paths, mo_paths, trans_mtx=None,
                             enumerate_from=0):
    """
    :param i: nth coupling calculation.
    :type i: Int
    :param path_hdf5: Path to the HDF5 file that contains the
    numerical results.
    :type path_hdf5: String
    :paramter dictCGFS: Dictionary from Atomic Label to basis set
    :type     dictCGFS: Dict String [CGF],
              CGF = ([Primitives], AngularMomentum),
              Primitive = (Coefficient, Exponent)
    :param all_geometries: list of molecular geometries
    :type all_geometries: String list
    :param time_depend_paths: Path to the time-dependent coefficients
    calculated with PYXAID and stored in HDF5 format.
    :type time_depend_paths: [String]
    :param mo_paths: Paths to the MO coefficients and energies in the
    HDF5 file.
    :type mo_paths: [String]
    :param trans_mtx: transformation matrix from cartesian to spherical
    orbitals.
    :type trans_mtx: Numpy Array
    :param enumerate_from: Number from where to start enumerating the folders
    create for each point in the MD
    :type enumerate_from: Int
    :returns: promise to path to the Coupling inside the HDF5

    """
    j, k = i + 1, i + 2
    geometries = all_geometries[i], all_geometries[j], all_geometries[k]
    mos = tuple(map(lambda j:
                    retrieve_hdf5_data(path_hdf5,
                                       mo_paths[i + j][1]), range(3)))
    time_coeffs = tuple(map(lambda j:
                            retrieve_hdf5_data(path_hdf5,
                                               time_depend_paths[i + j]),
                            range(3)))
    
    return photoExcitationRate(geometries, dictCGFs, time_coeffs, mos,
                               trans_mtx=trans_mtx)


def split_file_geometries(pathXYZ):
    """
    Reads a set of molecular geometries in xyz format and returns
    a list of string, where is element a molecular geometry
    
    :returns: String list containing the molecular geometries.
    """
    # Read Cartesian Coordinates
    with open(pathXYZ) as f:
        xss = f.readlines()

    numat = int(xss[0].split()[0])
    return list(map(flatten, chunksOf(xss, numat + 2)))


def create_file_names(work_dir, i):
    """
    Creates a namedTuple with the name of the 4 files used
    for each point in the trajectory
    
    :returns: Namedtuple containing the IO files
    """
    file_xyz = join(work_dir, 'coordinates_{}.xyz'.format(i))
    file_inp = join(work_dir, 'point_{}.inp'.format(i))
    file_out = join(work_dir, 'point_{}.out'.format(i))
    file_MO = join(work_dir, 'mo_coeff_{}.out'.format(i))

    return JobFiles(file_xyz, file_inp, file_out, file_MO)


def parse_population(filePath):
    """
    returns a matrix contaning the pop for each time in each row.
    """
    with open(filePath, 'r') as f:
        xss = f.readlines()
    rss = [[float(x) for i, x in enumerate(l.split())
            if i % 2 == 1 and i > 2] for l in xss]
        
    return np.array(rss)


def read_time_dependent_coeffs(path_hdf5, pathProperty, path_pyxaid_out):
    """
    
    :param path_hdf5: Path to the HDF5 file that contains the
    numerical results.
    :type path_hdf5: String
    :param pathProperty: path to the node that contains the time
    coeffficients.
    :type pathProperty: String
    :param path_pyxaid_out: Path to the out of the NA-MD carried out by
    PYXAID.
    :type path_pyxaid_out: String
    :returns: None
    """
    # Read output files
    files_out = os.listdir(path_pyxaid_out)
    names_out_es, names_out_pop  = [fnmatch.filter(files_out, x) for x
                                    in ["*energies*", "out*"]]
    paths_out_es, paths_out_pop = [[join(path_pyxaid_out, x) for x in xs]
                                   for xs in [names_out_es, names_out_pop]]

    # ess = map(parse_energies, paths_out_es)
    pss = map(parse_population, paths_out_pop)

    # Make a 3D stack of arrays the calculate the mean value
    # for the same time
    # average_es = np.mean(np.stack(ess), axis=0)
    # average_pop = np.mean(np.stack(pss), axis=0)
    data = np.stack(pss)

    with open(path_hdf5) as f5:
        f5.require_dataset(pathProperty, shape=np.shape(data),
                           data=data, dtype=np.float32)
    
# ==============================> Main <==================================


def main():
    plams.init()
    project_name = 'NAC'

    # Path to the MD geometries
    path_traj_xyz = "./data/traj_3_points.xyz"

    # CP2k Configuration

    # create Settings for the Cp2K Jobs
    cp2k_args = Settings()
    cp2k_args.basis = "DZVP-MOLOPT-SR-GTH"
    cp2k_args.potential = "GTH-PBE"
    cp2k_args.cell_parameters = [28.0] * 3
    cp2k_args.specific.cp2k.force_eval.dft.scf.eps_scf = 3e-5
    cp2k_args.specific.cp2k.force_eval.dft.scf.added_mos = 100

    # Work_dir
    scratch = "/scratch-shared"
    scratch_path = join(scratch, project_name)
    if not os.path.exists(scratch_path):
        os.makedirs(scratch)

    # HDF5 path
    path_hdf5 = join(scratch_path, 'quantum.hdf5')

    # PYXAID Results
    pyxaid_out_dir = "./step3/out"

    # Process PYXAID results
    pathProperty = join(project_name, "pyxaid/timeCoeffs")
    read_time_dependent_coeffs(path_hdf5, pathProperty, pyxaid_out_dir)

    # Named the points of the MD starting from this number
    enumerate_from = 0

    # all_geometries type :: [String]
    geometries = split_file_geometries(path_traj_xyz)

    # Electron Transfer rate calculation
    pyxaid_initial_cond = [0, 24, 49]
    
    # Electron transfer rate computation computation
    calculate_ETR('cp2k', project_name, geometries, cp2k_args,
                  pathTimeCoeffs=pathProperty,
                  initial_conditions=pyxaid_initial_cond,
                  path_hdf5=path_hdf5, enumerate_from=enumerate_from)

    print("PATH TO HDF5:{}\n".format(path_hdf5))
    plams.finish()

# ==============<>=============
    
if __name__ == "__main__":
    main()
