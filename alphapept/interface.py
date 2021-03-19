# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/11_interface.ipynb (unless otherwise specified).

__all__ = ['parallel_execute', 'tqdm_wrapper', 'check_version_and_hardware', 'create_database', 'import_raw_data',
           'feature_finding', 'wrapped_partial', 'search_data', 'recalibrate_data', 'score', 'align', 'match',
           'quantification', 'export', 'get_summary', 'run_complete_workflow', 'FileWatcher', 'run_cli', 'cli_overview',
           'cli_database', 'cli_import', 'cli_feature_finding', 'cli_search', 'cli_recalibrate', 'cli_score',
           'cli_align', 'cli_match', 'cli_quantify', 'cli_export', 'cli_workflow', 'cli_gui', 'cli_watcher',
           'CONTEXT_SETTINGS', 'CLICK_SETTINGS_OPTION']

# Cell
import alphapept.utils
from .utils import set_logger
from multiprocessing import Pool

import logging
import sys
import numpy as np
import psutil

def parallel_execute(settings, step, callback=None):

    """
    Generic function to parallel execute worklow steps on a file basis

    """
    n_processes = settings['general']['n_processes']
    files = settings['experiment']['file_paths']
    n_files = len(files)
    logging.info(f'Processing {len(files)} files for step {step.__name__}')

    if 'failed' not in settings:
        settings['failed'] = {}

    failed = []

    to_process = [(i, settings) for i in range(n_files)]

    if n_files == 1:
        if not step(to_process[0], callback=callback, parallel=True):
            failed.append(files[0])

    else:
        #Limit number of processes for Bruker FF
        if step.__name__ == 'find_features':
            base, ext = os.path.splitext(files[0])
            if ext.lower() == '.d':
                memory_available = psutil.virtual_memory().available/1024**3
                n_processes = np.max([int(np.floor(memory_available/25)),1])
                logging.info(f'Using Bruker Feature Finder. Setting Process limit to {n_processes}.')
            elif ext.lower() == '.raw':
                memory_available = psutil.virtual_memory().available/1024**3
                n_processes = np.max([int(np.floor(memory_available/8)),1]) #8 Gb per File
                logging.info(f'Setting Process limit to {n_processes}')
            else:
                raise NotImplementedError('File extension {} not understood.'.format(ext))

        if step.__name__ == 'search_db':
            memory_available = psutil.virtual_memory().available/1024**3
            n_processes = np.max([int(np.floor(memory_available/6)),1]) # 8 gb per file: Todo: make this better
            logging.info(f'Searching. Setting Process limit to {n_processes}.')

        with Pool(n_processes) as p:
            for i, success in enumerate(p.imap(step, to_process)):
                if success is not True:
                    failed.append(files[i])
                    logging.error(f'Processing of {files[i]} for step {step.__name__} failed. Exception {success}')

                if callback:
                    callback((i+1)/n_files)

    if step.__name__ in settings['failed']:
        settings['failed'][step.__name__] = failed
    else:
        settings['failed'][step.__name__+'_2'] = failed

    return settings


# Cell

import tqdm

def tqdm_wrapper(pbar, update):
    current_value = pbar.n
    delta = update - current_value
    pbar.update(delta)

# Cell

def check_version_and_hardware(settings):
    import alphapept.utils
    #alphapept.utils.check_hardware()
    #alphapept.utils.check_python_env()
    alphapept.utils.show_platform_info()
    alphapept.utils.show_python_info()


    settings = alphapept.utils.check_settings(settings)
    return settings

# Cell

import os
import functools
import copy

def create_database(
    settings,
    logger_set=False,
    settings_parsed=False,
    callback=None
):
    import alphapept.fasta
    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)
    if 'database_path' not in settings['fasta']:
        database_path = ''
    else:
        database_path = settings['fasta']['database_path']

    if not settings['fasta']['save_db']:
        logging.info('Creating small database w/o modifications for first search.')
        temp_settings = copy.deepcopy(settings)
        temp_settings['fasta']['mods_fixed'] = []
        temp_settings['fasta']['mods_fixed_terminal'] = []
        temp_settings['fasta']['mods_fixed_terminal_prot'] = []
        temp_settings['fasta']['mods_variable'] = []
        temp_settings['fasta']['mods_variable_terminal'] = []
        temp_settings['fasta']['mods_variable_terminal_prot'] = []
    else:
        temp_settings = settings

    if os.path.isfile(database_path):
        logging.info(
            'Database path set and exists. Using {} as database.'.format(
                database_path
            )
        )
    else:
        logging.info(
            'Database path {} is not a file.'.format(database_path)
        )

        if len(settings['fasta']['fasta_paths']) == 0:
            raise FileNotFoundError("No FASTA files set.")

        total_fasta_size = 0

        for fasta_file in settings['fasta']['fasta_paths']:
            if os.path.isfile(fasta_file):

                fasta_size = os.stat(fasta_file).st_size/(1024**2)

                total_fasta_size += fasta_size

                logging.info(
                    'Found FASTA file {} with size {:.2f} Mb.'.format(
                        fasta_file,
                        fasta_size
                    )
                )
            else:
                raise FileNotFoundError(
                    'File {} not found'.format(fasta_file)
                )

        max_fasta_size = settings['fasta']['max_fasta_size']

        if total_fasta_size >= max_fasta_size:
            logging.info(f'Total FASTA size {total_fasta_size:.2f} is larger than the set maximum size of {max_fasta_size:.2f} Mb')

            settings['fasta']['database_path'] = None

            return settings

        logging.info('Creating a new database from FASTA.')

        if not callback:
            cb = functools.partial(tqdm_wrapper, tqdm.tqdm(total=1))
        else:
            cb = callback

        (
            spectra,
            pept_dict,
            fasta_dict
        ) = alphapept.fasta.generate_database_parallel(
            temp_settings,
            callback=cb
        )
        logging.info(
            'Digested {:,} proteins and generated {:,} spectra'.format(
                len(fasta_dict),
                len(spectra)
            )
        )

        alphapept.fasta.save_database(
            spectra,
            pept_dict,
            fasta_dict,
            **settings['fasta']
        )
        logging.info(
            'Database saved to {}. Filesize of database is {:.2f} GB'.format(
                database_path,
                os.stat(database_path).st_size/(1024**3)
            )
        )

        settings['fasta']['database_path'] = database_path

    return settings

# Cell

def import_raw_data(
    settings,
    logger_set=False,
    settings_parsed=False,
    callback=None
):
    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    if not callback:
        cb = functools.partial(tqdm_wrapper, tqdm.tqdm(total=1))
    else:
        cb = callback

    import alphapept.io

    settings = parallel_execute(settings, alphapept.io.raw_conversion, callback = cb)

    return settings

# Cell

def feature_finding(
    settings,
    logger_set=False,
    settings_parsed=False,
    callback=None
):

    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    import alphapept.feature_finding

    if not callback:
        cb = functools.partial(tqdm_wrapper, tqdm.tqdm(total=1))
    else:
        cb = callback

    settings = parallel_execute(settings, alphapept.feature_finding.find_features, callback = cb)

    return settings

# Cell

def wrapped_partial(func, *args, **kwargs):
    partial_func = functools.partial(func, *args, **kwargs)
    functools.update_wrapper(partial_func, func)
    return partial_func

def search_data(
    settings,
    first_search=True,
    logger_set=False,
    settings_parsed=False,
    callback=None
):
    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    import alphapept.search
    import alphapept.io

    if not callback:
        cb = functools.partial(tqdm_wrapper, tqdm.tqdm(total=1))
    else:
        cb = callback

    if first_search:
        logging.info('Starting first search.')
        if settings['fasta']['database_path'] is not None:
            settings = parallel_execute(settings, wrapped_partial(alphapept.search.search_db, first_search = first_search), callback = cb)

            db_data = alphapept.fasta.read_database(settings['fasta']['database_path'])

            fasta_dict = db_data['fasta_dict'].item()
            pept_dict = db_data['pept_dict'].item()


        else:
            ms_files = []
            for _ in settings['experiment']['file_paths']:
                base, ext = os.path.splitext(_)
                ms_files.append(base + '.ms_data.hdf')

            fasta_dict = alphapept.search.search_parallel(
                settings,
                callback=cb
            )
            pept_dict = None

        logging.info('First search complete.')
    else:
        logging.info('Starting second search with DB.')

        if settings['fasta']['save_db']:
            settings = parallel_execute(settings, wrapped_partial(alphapept.search.search_db, first_search = first_search), callback = cb)

            db_data = alphapept.fasta.read_database(settings['fasta']['database_path'])

            fasta_dict = db_data['fasta_dict'].item()
            pept_dict = db_data['pept_dict'].item()


        else:

            ms_files = []
            for _ in settings['experiment']['file_paths']:
                base, ext = os.path.splitext(_)
                ms_files.append(base + '.ms_data.hdf')

            try:
                offsets = [
                    alphapept.io.MS_Data_File(
                        ms_file_name
                    ).read(
                        dataset_name="corrected_mass",
                        group_name="features",
                        attr_name="estimated_max_precursor_ppm"
                    ) * settings['search']['calibration_std'] for ms_file_name in ms_files
                ]
            except KeyError:
                logging.info('No calibration found.')
                offsets = None

            logging.info('Starting second search.')

            fasta_dict = alphapept.search.search_parallel(
                settings,
                calibration=offsets,
                callback=cb
            )
            pept_dict = None

        logging.info('Second search complete.')
    return settings, pept_dict, fasta_dict

# Cell

def recalibrate_data(
    settings,
    logger_set=False,
    settings_parsed=False,
    callback=None
):
    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    import alphapept.recalibration

    if settings['search']['calibrate']:
        if not callback:
            cb = functools.partial(tqdm_wrapper, tqdm.tqdm(total=1))
        else:
            cb = callback

        settings = parallel_execute(settings, alphapept.recalibration.calibrate_hdf, callback = cb)

    return settings

# Cell

def score(
    settings,
    pept_dict=None,
    fasta_dict=None,
    logger_set=False,
    settings_parsed=False,
    callback=None
):
    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    import alphapept.score
    import alphapept.fasta

    if not callback:
        cb = functools.partial(tqdm_wrapper, tqdm.tqdm(total=1))
    else:
        cb = callback



    if fasta_dict is None:

        db_data = alphapept.fasta.read_database(
            settings['fasta']['database_path']
        )
        fasta_dict = db_data['fasta_dict'].item()
        pept_dict = db_data['pept_dict'].item()

    settings = parallel_execute(settings, alphapept.score.score_hdf, callback = cb)

    if pept_dict is None: #Pept dict extractions needs scored
        pept_dict = alphapept.fasta.pept_dict_from_search(settings)


    logging.info(f'Fasta dict with length {len(fasta_dict):,}, Pept dict with length {len(pept_dict):,}')

    # Protein groups
    logging.info('Extracting protein groups.')

    if not callback:
        cb = functools.partial(tqdm_wrapper, tqdm.tqdm(total=1))
    else:
        cb = callback

    # This is on each file individually -> when having repeats maybe
    # use differently (if this matter at all )
    alphapept.score.protein_groups_hdf_parallel(
        settings,
        pept_dict,
        fasta_dict,
        callback=cb
    )
    logging.info('Protein groups complete.')

    return settings

# Cell

import pandas as pd


def align(
    settings,
    logger_set=False,
    settings_parsed=False,
    callback=None
):

    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    import alphapept.matching

    alphapept.matching.align_datasets(settings, callback = callback)

    return settings

def match(
    settings,
    logger_set=False,
    settings_parsed=False,
    callback=None
):
    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    import alphapept.matching

    if settings['matching']['match_between_runs']:
        alphapept.matching.match_datasets(settings)

    return settings

# Cell

import pandas as pd


def quantification(
    settings,
    logger_set=False,
    settings_parsed=False,
    callback=None
):
    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    import alphapept.quantification

    field = settings['quantification']['mode']

    logging.info('Assembling dataframe.')
    df = alphapept.utils.assemble_df(settings)
    logging.info('Assembly complete.')

    if settings["general"]["lfq_quantification"]:

        if field in df.keys():  # Check if the quantification information exists.
            # We could include another protein fdr in here..
            if 'fraction' in df.keys():
                logging.info('Delayed Normalization.')
                df, normalization = alphapept.quantification.delayed_normalization(
                    df,
                    field
                )
                pd.DataFrame(normalization).to_hdf(
                    settings['experiment']['results_path'],
                    'fraction_normalization'
                )
                df_grouped = df.groupby(
                    ['shortname', 'precursor', 'protein', 'filename']
                )[['{}_dn'.format(field)]].sum().reset_index()
            else:
                df_grouped = df.groupby(
                    ['shortname', 'precursor', 'protein', 'filename']
                )[field].sum().reset_index()

            df.to_hdf(
                settings['experiment']['results_path'],
                'combined_protein_fdr_dn'
            )

            logging.info('Complete. ')
            logging.info('Starting profile extraction.')

            if not callback:
                cb = functools.partial(tqdm_wrapper, tqdm.tqdm(total=1))
            else:
                cb = callback

            protein_table = alphapept.quantification.protein_profile_parallel(
                settings,
                df_grouped,
                callback=cb
            )
            protein_table.to_hdf(
                settings['experiment']['results_path'],
                'protein_table'
            )
            results_path = settings['experiment']['results_path']
            base, ext = os.path.splitext(results_path)
            protein_table.to_csv(base+'_proteins.csv')

            logging.info('LFQ complete.')

    if len(df) > 0:
        logging.info('Exporting as csv.')
        results_path = settings['experiment']['results_path']
        base, ext = os.path.splitext(results_path)
        df.to_csv(base+'.csv')
        logging.info(f'Saved df of length {len(df):,} saved to {base}')
    else:
        logging.info(f"No Proteins found.")

    return settings

# Cell

import yaml


def export(
    settings,
    logger_set=False,
    settings_parsed=False,
    callback=None
):
    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)
    base, ext = os.path.splitext(settings['experiment']['results_path'])
    out_path_settings = base+'.yaml'

    with open(out_path_settings, 'w') as file:
        yaml.dump(settings, file)

    logging.info('Settings saved to {}'.format(out_path_settings))
    logging.info('Analysis complete.')
    return settings

# Cell

from time import time, sleep
from .__version__ import VERSION_NO

def get_summary(settings, summary):

    summary['file_sizes'] = {}

    file_sizes = {}
    for _ in settings['experiment']['file_paths']:

        base, ext = os.path.splitext(_)
        filename = os.path.split(base)[1]
        file_sizes[base+"_ms_data"] = os.path.getsize(os.path.splitext(_)[0] + ".ms_data.hdf")/1024**2
        # file_sizes[base+"_result"] = os.path.getsize(os.path.splitext(_)[0] + ".hdf")/1024**2

        ms_data = alphapept.io.MS_Data_File(os.path.splitext(_)[0] + ".ms_data.hdf")
        n_ms2 = ms_data.read(group_name='Raw/MS2_scans', dataset_name='prec_mass_list2', return_dataset_shape=True)[0]
        for key in ms_data.read():
            if "is_pd_dataframe" in ms_data.read(
                attr_name="",
                group_name=key
            ):
                f_summary = {}
                for key in ms_data.read():
                    if "is_pd_dataframe" in ms_data.read(
                        attr_name="",
                        group_name=key
                    ):
                        df = ms_data.read(dataset_name=key)

                        f_name = filename+'_'+key.lstrip('/')

                        f_summary[key] = len(df)
                        if key in 'protein_fdr':
                            if 'type' in df.columns:
                                f_summary['id_rate'] = df[df['type'] == 'msms']['raw_idx'].nunique() / n_ms2
                            else:
                                f_summary['id_rate'] = df['raw_idx'].nunique() / n_ms2

                            for field in ['protein','protein_group','precursor','naked_sequence','sequence']:
                                f_summary['n_'+field] = df[field].nunique()

                    summary[filename] = f_summary

    summary['file_sizes']['files'] = file_sizes
    if os.path.isfile(settings['experiment']['results_path']):
        summary['file_sizes']['results'] = os.path.getsize(settings['experiment']['results_path'])/1024**2

    return summary


def run_complete_workflow(
    settings,
    progress = False,
    logger_set=False,
    settings_parsed=False,
    callback=None,
    callback_overall = None,
    callback_task = None
):

    if not logger_set:
        set_logger()
    if not settings_parsed:
        settings = check_version_and_hardware(settings)

    steps = []

    general = settings['general']

    if general["create_database"]:
        steps.append(create_database)
    if general["import_raw_data"]:
        steps.append(import_raw_data)
    if general["find_features"]:
        steps.append(feature_finding)
    if general["search_data"]:
        steps.append(search_data)
    if general["recalibrate_data"]:
        steps.append(recalibrate_data)
        steps.append(search_data)
    steps.append(score)
    if general["align"]:
        steps.append(align)
    if general["match"]:
        if align not in steps:
            steps.append(align)
        steps.append(match)

    steps.append(quantification)
    steps.append(export)

    n_steps = len(steps)
    logging.info(f"Workflow has {n_steps} steps")


    if progress:
        logging.info('Setting callback to logger.')
        #log progress to be used
        def cb_logger_o(x):
            logging.info(f"__progress_overall {x:.3f}")
        def cb_logger_c(x):
            logging.info(f"__progress_current {x:.3f}")
        def cb_logger_t(x):
            logging.info(f"__current_task {x}")

        callback = cb_logger_c
        callback_overall = cb_logger_o
        callback_task = cb_logger_t


    def progress_wrapper(step, n_steps, current):
        if callback:
            callback(current)
        if callback_overall:
            callback_overall((step/n_steps)+(current/n_steps))

    pept_dict = None
    fasta_dict = None

    first_search = True

    time_dict = {}

    run_start = time()

    summary = {}

    for idx, step in enumerate(steps):
        if callback_task:
            callback_task(step.__name__)

        start = time()

        if callback_overall:
            progress_wrapper(idx, n_steps, 0)
            cb = functools.partial(progress_wrapper, idx, n_steps)
        elif callback:
            cb = callback
        else:
            cb = None

        if step is search_data:
            settings, pept_dict, fasta_dict = step(settings, first_search=first_search, logger_set = True, settings_parsed = True, callback = cb)

        elif step is score:

            settings = step(settings, pept_dict=pept_dict, fasta_dict=fasta_dict, logger_set = True,  settings_parsed = True, callback = cb)

        else:
            if step is export:
                # Get summary information
                summary = get_summary(settings, summary)
                settings['summary'] = summary

            settings = step(settings, logger_set = True,  settings_parsed = True, callback = cb)

        if step is recalibrate_data:
            first_search = False

        if callback_overall:
            progress_wrapper(idx, n_steps, 1)

        end = time()

        if step.__name__ in time_dict:
            time_dict[step.__name__+'_2'] = (end-start)/60 #minutes
        else:
            time_dict[step.__name__] = (end-start)/60 #minutes

        time_dict['total'] = (end-run_start)/60

        summary['timing'] = time_dict
        summary['version'] = VERSION_NO

    return settings

# Cell
class FileWatcher():
    """
    Class to watch files and process
    """
    def __init__(self, config_path):
        db_set = True
        try:
            from pymongo import MongoClient
        except:
            print('DB upload requires pymongo - DB upload deactivated')
            db_set = False

        try:
            import dns
        except:
            print('DB upload requires dnspython - DB upload deactivated')
            db_set = False

        if os.path.isfile(config_path):
            watcher_config = alphapept.settings.load_settings(config_path)
        else:
            raise FileNotFoundError(config_path)

        if os.path.isdir(watcher_config['path']):
            self.path = watcher_config['path']
        else:
            raise FileNotFoundError(path)


        db_config = {}
        for db_field in ['db_user', 'db_password', 'db_url', 'db_database', 'db_collection']:
            if watcher_config[db_field] == '':
                print(f"{db_field} not set.")
                db_set = False
            else:
                db_config[db_field] = watcher_config[db_field]

        if db_set:
            self.set_db(**db_config)
        else:
            self.db_set = False

        if os.path.isfile(watcher_config['settings']):
            self.settings = alphapept.settings.load_settings(watcher_config['settings'])
            print(f"Loaded settings from {watcher_config['settings']}")
        else:
            raise FileNotFoundError(watcher_config['settings'])

        self.update_rate = watcher_config['update_rate']
        self.n_processed = 0
        self.n_failed = 0
        self.minimum_file_size = watcher_config['minimum_file_size']
        self.tag = watcher_config['tag']

    def check_new_files(self):
        """
        Check for new files in folder
        """
        new_files = []

        for dirpath, dirnames, filenames in os.walk(self.path):

            for dirname in [d for d in dirnames if d.endswith(('.d','.d/'))]: #Bruker
                new_file = os.path.join(dirpath, dirname)
                base, ext = os.path.splitext(dirname)
                hdf_path = os.path.join(dirpath, base+'.ms_data.hdf')

                if not os.path.exists(hdf_path):
                    new_files.append(new_file)

            for filename in [f for f in filenames if f.lower().endswith(('.raw','.raw/'))]: #Thermo
                new_file = os.path.join(dirpath, filename)
                base, ext = os.path.splitext(filename)
                hdf_path = os.path.join(dirpath, base+'.ms_data.hdf')

                if not os.path.exists(hdf_path):
                    new_files.append(new_file)
        return new_files

    def set_db(self, db_user = '', db_password = '', db_url = '', db_database= '', db_collection= ''):

        self.db_user = db_user
        self.db_password = db_password
        self.db_url = db_url
        self.db_database = db_database
        self.db_collection = db_collection

        self.db_set = True


    def check_file_completion(self, list_of_files, sleep_time = 10):
        to_analyze = []
        file_dict = {}

        for file in list_of_files:
            if file.endswith('.d'):
                to_check = os.path.join(file, 'analysis.tdf_bin')
            else:
                to_check = file

            file_dict[file] = os.path.getsize(to_check)

        sleep(sleep_time)

        for file in list_of_files:
            if file.endswith('.d'):
                to_check = os.path.join(file, 'analysis.tdf_bin')
            else:
                to_check = file

            filesize = os.path.getsize(to_check)
            if (filesize == file_dict[file]) & (filesize/1024/1024 > self.minimum_file_size):
                to_analyze.append(file)

        return to_analyze

    def run(self):
        print(f'Starting FileWatcher on {self.path}')

        while True:
            unprocessed = self.check_file_completion(self.check_new_files())

            if self.tag != '':
                unprocessed = [_ for _ in unprocessed if self.tag.lower() in _.lower()]

            if len(unprocessed) > 0:
                try:
                    settings = self.settings.copy()
                    settings['experiment']['file_paths'] =  [unprocessed[0]]
                    settings_ = alphapept.interface.run_complete_workflow(settings)

                    if self.db_set:
                        self.upload_to_db(settings_)
                    self.n_processed +=1
                    print(f'--- File Watcher Status: Files processed {self.n_processed:,} - failed {self.n_failed:,} ---')
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logging.info(e)
                    self.n_failed +=1
            else:
                sleep(self.update_rate)


    def upload_to_db(self, settings):
        from pymongo import MongoClient
        logging.info('Uploading to DB')
        string = f"mongodb+srv://{self.db_user}:{self.db_password}@{self.db_url}"
        client = MongoClient(string)

        post_id = client[self.db_database][self.db_collection].insert_one(settings).inserted_id

        logging.info(f"Uploaded {post_id}.")

        return post_id

# Cell

import click
import os
import alphapept.settings
from .__version__ import VERSION_NO
from .__version__ import COPYRIGHT
from .__version__ import URL

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
CLICK_SETTINGS_OPTION = click.argument(
    "settings_file",
#     help="A .yaml file with settings.",
    type=click.Path(exists=True, dir_okay=False),
#     default=f"{os.path.dirname(__file__)}/settings_template.yaml"
)


def run_cli():
    print(
        "\n".join(
            [
                "\n",
                r"     ___    __      __          ____             __ ",
                r"    /   |  / /___  / /_  ____  / __ \___  ____  / /_",
                r"   / /| | / / __ \/ __ \/ __ \/ /_/ / _ \/ __ \/ __/",
                r"  / ___ |/ / /_/ / / / / /_/ / ____/ ___/ /_/ / /_  ",
                r" /_/  |_/_/ .___/_/ /_/\__,_/_/    \___/ .___/\__/  ",
                r"         /_/                          /_/           ",
                '.'*52,
                '.{}.'.format(URL.center(50)),
                '.{}.'.format(COPYRIGHT.center(50)),
                '.{}.'.format(VERSION_NO.center(50)),
                '.'*52,
                "\n"
            ]
        )
    )
    cli_overview.add_command(cli_database)
    cli_overview.add_command(cli_import)
    cli_overview.add_command(cli_feature_finding)
    cli_overview.add_command(cli_search)
    cli_overview.add_command(cli_recalibrate)
    cli_overview.add_command(cli_score)
    cli_overview.add_command(cli_quantify)
    cli_overview.add_command(cli_export)
    cli_overview.add_command(cli_workflow)
    cli_overview.add_command(cli_gui)
    cli_overview.add_command(cli_watcher)
    cli_overview()


@click.group(
    context_settings=CONTEXT_SETTINGS,
#     help="AlphaPept"
)
def cli_overview():
    pass


@click.command(
    "database",
    help="Create a database from a fasta file.",
    short_help="Create a database from a fasta file."
)
@CLICK_SETTINGS_OPTION
def cli_database(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    create_database(settings)


@click.command(
    "import",
    help="Import and convert raw data from vendor to `.ms_data.hdf` file.",
    short_help="Import and convert raw data from vendor to `.ms_data.hdf` file."
)
@CLICK_SETTINGS_OPTION
def cli_import(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    import_raw_data(settings)


@click.command(
    "features",
    help="Find features in a `.ms_data.hdf` file.",
    short_help="Find features in a `.ms_data.hdf` file."
)
@CLICK_SETTINGS_OPTION
def cli_feature_finding(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    feature_finding(settings)


@click.command(
    "search",
    help="Search and identify feature in a `.ms_data.hdf` file.",
    short_help="Search and identify feature in a `.ms_data.hdf` file."
)
@CLICK_SETTINGS_OPTION
@click.option(
    '--recalibrated_features',
    '-r',
    'recalibrated',
    help="Use recalibrated features if present",
    is_flag=True,
    default=False,
    show_default=True,
)
def cli_search(settings_file, recalibrated):
    settings = alphapept.settings.load_settings(settings_file)
    search_data(settings, recalibrated)


@click.command(
    "recalibrate",
    help="Recalibrate a `.ms_data.hdf` file.",
    short_help="Recalibrate a `.ms_data.hdf` file."
)
@CLICK_SETTINGS_OPTION
def cli_recalibrate(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    recalibrate_data(settings)


@click.command(
    "score",
    help="Score PSM from a `.ms_data.hdf` file.",
    short_help="Score PSM from a `.ms_data.hdf` file."
)
@CLICK_SETTINGS_OPTION
def cli_score(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    score(settings)

@click.command(
    "align",
    help="Align multiple `.ms_data.hdf` files.",
    short_help="Align multiple `.ms_data.hdf` files."
)
@CLICK_SETTINGS_OPTION
def cli_align(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    align(settings)

@click.command(
    "match",
    help="Perform match between run type analysis on multiple `.ms_data.hdf` files.",
    short_help="Perform match between run type analysis on multiple `.ms_data.hdf` files."
)
@CLICK_SETTINGS_OPTION
def cli_match(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    align(settings)
    match(settings)

@click.command(
    "quantify",
    help="Quantify and compare multiple `.ms_data.hdf` files.",
    short_help="Quantify and compare multiple `.ms_data.hdf` files."
)
@CLICK_SETTINGS_OPTION
def cli_quantify(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    quantification(settings)


@click.command(
    "export",
    help="Export protein table from `.ms_data.hdf` files as `.csv`",
    short_help="Export protein table from `.ms_data.hdf` files as `.csv`."
)
@CLICK_SETTINGS_OPTION
def cli_export(settings_file):
    settings = alphapept.settings.load_settings(settings_file)
    export(settings)


@click.command(
    "workflow",
    help="Run the complete AlphaPept workflow.",
    short_help="Run the complete AlphaPept workflow."
)
@click.option(
    "--progress",
    "-p",
    help="Log progress output.",
    is_flag=True,
)
@CLICK_SETTINGS_OPTION
def cli_workflow(settings_file, progress):
    settings = alphapept.settings.load_settings(settings_file)
    run_complete_workflow(settings, progress = progress)


@click.command(
    "gui",
    help="Start graphical user interface for AlphaPept.",
)
@click.option(
    "--test",
    "test",
    help="Test",
    is_flag=True,
    default=False,
    show_default=True,
)
def cli_gui(test):
    print('Launching GUI')
    import alphapept.ui
    if test:
        alphapept.ui.main(close=True)
    else:
        alphapept.ui.main()

@click.command(
    "watcher",
    help="Watch folder for new files and automatically process them. Upload to MongoDB possible.",
    short_help="File watching and procesing."
)
@CLICK_SETTINGS_OPTION
def cli_watcher(settings_file):
    x = FileWatcher(settings_file)
    x.run()