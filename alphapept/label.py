# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/15_label.ipynb (unless otherwise specified).

__all__ = ['label_search', 'search_label_on_ms_file', 'find_labels']

# Cell
from numba import njit
from .search import compare_frags
import numpy as np

@njit
def label_search(query_frag: np.ndarray, query_int: np.ndarray, label: np.ndarray, reporter_frag_tol:float, ppm:bool)-> (np.ndarray, np.ndarray):
    """Function to search for a label for a given spectrum.

    Args:
        query_frag (np.ndarray): Array with query fragments.
        query_int (np.ndarray): Array with query intensities.
        label (np.ndarray): Array with label masses.
        reporter_frag_tol (float): Fragment tolerance for search.
        ppm (bool): Flag to use ppm instead of Dalton.

    Returns:
        np.ndarray: Array with intensities for the respective label channel.
        np.ndarray: Array with offset masses.

    """

    report = np.zeros(len(label))
    off_mass = np.zeros_like(label)

    hits = compare_frags(query_frag, label, reporter_frag_tol, ppm)
    for idx, _ in enumerate(hits):
        if _ > 0:
            report[idx] = query_int[_-1]
            off_mass[idx] = query_frag[_-1] - label[idx]

            if ppm:
                off_mass[idx] = off_mass[idx] / (query_frag[_-1] + label[idx]) *2 * 1e6

    return report, off_mass

# Cell
from typing import NamedTuple
import alphapept.io

def search_label_on_ms_file(file_name:str, label:NamedTuple, reporter_frag_tol:float, ppm:bool):
    """Wrapper function to search labels on an ms_file and write results to the peptide_fdr of the file.

    Args:
        file_name (str): Path to ms_file:
        label (NamedTuple): Label with channels, mod_name and masses.
        reporter_frag_tol (float): Fragment tolerance for search.
        ppm (bool): Flag to use ppm instead of Dalton.

    """

    ms_file = alphapept.io.MS_Data_File(file_name, is_read_only = False)

    df = ms_file.read(dataset_name='peptide_fdr')
    label_intensities = np.zeros((len(df), len(label.channels)))
    off_masses = np.zeros((len(df), len(label.channels)))
    labeled = df['sequence'].str.startswith(label.mod_name).values
    query_data = ms_file.read_DDA_query_data()

    query_indices = query_data["indices_ms2"]
    query_frags = query_data['mass_list_ms2']
    query_ints = query_data['int_list_ms2']

    for idx, query_idx in enumerate(df['raw_idx']):

        query_idx_start = query_indices[query_idx]
        query_idx_end = query_indices[query_idx + 1]
        query_frag = query_frags[query_idx_start:query_idx_end]
        query_int = query_ints[query_idx_start:query_idx_end]

        query_frag_idx = query_frag < label.masses[-1]+1
        query_frag = query_frag[query_frag_idx]
        query_int = query_int[query_frag_idx]

        if labeled[idx]:
            label_int, off_mass = label_search(query_frag, query_int, label.masses, reporter_frag_tol, ppm)
            label_intensities[idx, :] = label_int
            off_masses[idx, :] = off_mass

    df[label.channels] = label_intensities
    df[[_+'_off_ppm' for _ in label.channels]] = off_masses

    ms_file.write(df, dataset_name="peptide_fdr", overwrite=True) #Overwrite dataframe with label information


# Cell
import logging
import os

from .constants import label_dict

def find_labels(
    to_process: dict,
    callback: callable = None,
    parallel:bool = False
) -> bool:
    """Wrapper function to search for labels.

    Args:
        to_process (dict): A dictionary with settings indicating which files are to be processed and how.
        callback (callable): A function that accepts a float between 0 and 1 as progress. Defaults to None.
        parallel (bool): If True, process multiple files in parallel.
            This is not implemented yet!
            Defaults to False.

    Returns:
        bool: True if and only if the label finding was succesful.

    """
    index, settings = to_process
    raw_file = settings['experiment']['file_paths'][index]
    try:
        base, ext = os.path.splitext(raw_file)
        file_name = base+'.ms_data.hdf'
        label = label_dict[settings['isobaric_label']['label']]

        reporter_frag_tol = settings['isobaric_label']['reporter_frag_tolerance']
        ppm = settings['isobaric_label']['reporter_frag_tolerance_ppm']

        search_label_on_ms_file(file_name, label, reporter_frag_tol, ppm)

        logging.info(f'Tag finding of file {file_name} complete.')
        return True
    except Exception as e:
        logging.error(f'Tag finding of file {file_name} failed. Exception {e}')
        return f"{e}" #Can't return exception object, cast as string
    return True