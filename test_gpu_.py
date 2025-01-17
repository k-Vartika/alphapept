import alphapept.performance
import os
from time import time
import wget
from alphapept.settings import load_settings
from alphapept.paths import DEFAULT_SETTINGS_PATH
import alphapept.interface
import sys
import shutil
import logging
import importlib
import alphapept.feature_finding


FILE_DICT = {}
FILE_DICT['thermo_IRT.raw'] = 'https://datashare.biochem.mpg.de/s/GpXsATZtMwgQoQt/download'
FILE_DICT['IRT_fasta.fasta'] = 'https://datashare.biochem.mpg.de/s/p8Qu3KolzbSiCHH/download'

tmp_folder = 'E:/test_temp/'


def delete_folder(dir_name):
    if os.path.exists(dir_name):
        shutil.rmtree(dir_name)


def create_folder(dir_name):
    if not os.path.exists(dir_name):
        logging.info(f'Creating dir {dir_name}.')
        os.makedirs(dir_name)


def main():
    mode = sys.argv[1]
    print(f"Testing with mode {mode}")
    global alphapept
    alphapept.performance.set_compilation_mode(mode)
    alphapept.performance.set_worker_count(0)
    importlib.reload(alphapept.feature_finding)

    delete_folder(tmp_folder)
    create_folder(tmp_folder)

    for file in FILE_DICT:
        target = os.path.join(tmp_folder, file)
        if not os.path.isfile(target):
            wget.download(FILE_DICT[file], target)

    settings = load_settings(DEFAULT_SETTINGS_PATH)
    settings['experiment']['file_paths'] =  [os.path.join(tmp_folder, 'thermo_IRT.raw')]
    settings['experiment']['fasta_paths'] = [os.path.join(tmp_folder, 'IRT_fasta.fasta')]

    import alphapept.interface

    settings_ = alphapept.interface.import_raw_data(settings)
    start = time()
    settings_ = alphapept.interface.feature_finding(settings)
    end = time()

    te = end-start

    print(f'Time elapsed {te}')


if __name__ == "__main__":
    main()
