# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/07_recalibration.ipynb (unless otherwise specified).

__all__ = ['transform', 'get_calibration', 'calibrate_hdf', 'get_db_targets', 'align_run_to_db', 'calibrate_fragments']

# Cell
import pandas as pd
import numpy as np
import os
from .score import score_x_tandem
import alphapept.io
from multiprocessing import Pool
from sklearn.neighbors import KNeighborsRegressor
import logging

def transform(x, _, scaling_dict):

    if _ not in scaling_dict:
        raise NotImplementError(f"Column {_} not in scaling_dict")
    else:
        type_, scale_ = scaling_dict[_]

        if type_ == 'relative':
            return np.log(x, out=np.zeros_like(x), where=(x>0))/scale_
        elif type_ == 'absolute':
            return x/scale_
        else:
            raise NotImplementedError(f"Type {type_} not known.")


def get_calibration(df, features, outlier_std = 3, calib_n_neighbors = 100, calib_mz_range = 20, calib_rt_range = 0.5, calib_mob_range = 0.3, callback = None, **kwargs):
    """
    Calibration

    """

    if len(df) > calib_n_neighbors:
        target = 'o_mass_ppm'
        cols = ['mz','rt']

        if 'mobility' in df.columns:
            cols += ['mobility']

        scaling_dict = {}
        scaling_dict['mz'] = ('relative', calib_mz_range/1e6)
        scaling_dict['rt'] = ('absolute', calib_rt_range)
        scaling_dict['mobility'] = ('relative', calib_mob_range)

        # Remove outliers for calibration
        o_mass_std = np.abs(df['o_mass_ppm'].std())
        o_mass_median = df['o_mass_ppm'].median()

        df_sub = df.query('o_mass_ppm < @o_mass_median+@outlier_std*@o_mass_std and o_mass_ppm > @o_mass_median-@outlier_std*@o_mass_std').copy()

        tree_points = df_sub[cols].values

        for idx, _ in enumerate(df_sub[cols].columns):
            tree_points[:, idx] = transform(tree_points[:, idx], _, scaling_dict)

        target_points = features[[_+'_matched' for _ in cols]].values

        for idx, _ in enumerate(df_sub[cols].columns):
            target_points[:, idx] = transform(target_points[:, idx], _, scaling_dict)

        neigh = KNeighborsRegressor(n_neighbors=calib_n_neighbors, weights = 'distance')
        neigh.fit(tree_points, df_sub[target].values)

        y_hat = neigh.predict(target_points)

        corrected_mass = (1-y_hat/1e6) * features['mass_matched']

        return corrected_mass, y_hat.std()

    else:
        logging.info('Not enough data points present. Skipping recalibration.')
        return features['mass_matched'], np.abs(df['o_mass_ppm'].std())



def calibrate_hdf(to_process, callback = None, parallel=False):

    # TODO Only features are calibrated, not raw MS1 signals.
    # What if features are not present?

    try:
        index, settings = to_process
        file_name = settings['experiment']['file_paths'][index]
        base_file_name, ext = os.path.splitext(file_name)
        ms_file = base_file_name+".ms_data.hdf"
        ms_file_ = alphapept.io.MS_Data_File(ms_file, is_overwritable=True)

        features = ms_file_.read(dataset_name='features')

        try:
            psms =  ms_file_.read(dataset_name='first_search')
        except KeyError: #no elements in search
            psms = pd.DataFrame()

        if len(psms) > 0 :
            df = score_x_tandem(
                psms,
                fdr_level=settings["search"]["peptide_fdr"],
                plot=False,
                verbose=False,
                **settings["search"]
            )
            corrected_mass, o_mass_ppm_std = get_calibration(
                df,
                features,
                **settings["calibration"]
            )
            ms_file_.write(
                corrected_mass,
                dataset_name="corrected_mass",
                group_name="features"
            )
        else:

            ms_file_.write(
                features['mass_matched'],
                dataset_name="corrected_mass",
                group_name="features"
            )

            o_mass_ppm_std = 0

        ms_file_.write(
            o_mass_ppm_std,
            dataset_name="corrected_mass",
            group_name="features",
            attr_name="estimated_max_precursor_ppm"
        )
        logging.info(f'Calibration of file {ms_file} complete.')


        # Calibration of fragments

        skip = False

        try:
            logging.info(f'Calibrating fragments')
            ions = ms_file_.read(dataset_name='ions')
        except KeyError:
            logging.info('No ions to calibrate fragment masses found')

            skip = True

        if not skip:
            delta_ppm = ((ions['db_mass'] - ions['ion_mass'])/((ions['db_mass'] + ions['ion_mass'])/2)*1e6).values
            median_offset = -np.median(delta_ppm)
            std_offset = np.std(delta_ppm)
            mass_list_ms2 = ms_file_.read(dataset_name = 'mass_list_ms2', group_name = "Raw/MS2_scans")

            try:
                offset = ms_file_.read(dataset_name = 'corrected_fragment_mzs')
            except KeyError:
                offset = np.zeros(len(mass_list_ms2))

            offset += median_offset

            logging.info(f'Median fragment offset {median_offset:.2f} - std {std_offset:.2f} ppm')

            ms_file_.write(
                offset,
                dataset_name="corrected_fragment_mzs",
            )

        return True
    except Exception as e:
        logging.error(f'Calibration of file {ms_file} failed. Exception {e}.')
        return f"{e}" #Can't return exception object, cast as string

# Cell

import alphapept.io
import pandas as pd
import numpy as np
import scipy.stats
from matplotlib import pyplot as plt
import numba
import scipy.signal
import scipy.interpolate
import alphapept.fasta

def get_db_targets(
    db_file_name,
    max_ppm=100,
    min_distance=0.5,
    ms_level=2,
):
    if ms_level == 1:
        db_mzs_ = alphapept.fasta.read_database(db_file_name, 'precursors')
    elif ms_level == 2:
        db_mzs_ = alphapept.fasta.read_database(db_file_name, 'fragmasses')
    else:
        raise ValueError(f"{ms_level} is not a valid ms level")
    tmp_result = np.bincount(
        (
            np.log10(
                db_mzs_[
                    np.isfinite(db_mzs_) & (db_mzs_ > 0)
                ].flatten()
            ) * 10**6
        ).astype(np.int64)
    )
    db_mz_distribution = np.zeros_like(tmp_result)
    for i in range(1, max_ppm):
        db_mz_distribution[i:] += tmp_result[:-i]
        db_mz_distribution[:-i] += tmp_result[i:]
    peaks = scipy.signal.find_peaks(db_mz_distribution, distance=max_ppm)[0]
    db_targets = 10 ** (peaks / 10**6)
#     db_vals = db_mz_distribution[peaks]
#     plt.vlines(db_targets, 0, db_vals)
    db_array = np.zeros(int(db_targets[-1]) + 1, dtype=np.float64)
    last_int_mz = -1
    last_mz = -1
    for mz in db_targets:
        mz_int = int(mz)
        if (mz_int != last_int_mz) & (mz > (last_mz + min_distance)):
            db_array[mz_int] = mz
        else:
            db_array[mz_int] = 0
        last_int_mz = mz_int
        last_mz = mz
    return db_array

# Cell

def align_run_to_db(
    ms_data_file_name,
    db_array,
    max_ppm_distance=1000000,
    rt_step_size=0.1,
    plot_ppms=False,
    ms_level=2,
):
    ms_data = alphapept.io.MS_Data_File(ms_data_file_name)
    if ms_level == 1:
        mzs = ms_data.read(dataset_name="mass_matched", group_name="features")
        rts = ms_data.read(dataset_name="rt_matched", group_name="features")
    elif ms_level == 2:
        mzs = ms_data.read(dataset_name="Raw/MS2_scans/mass_list_ms2")
        inds = ms_data.read(dataset_name="Raw/MS2_scans/indices_ms2")
        precursor_rts = ms_data.read(dataset_name="Raw/MS2_scans/rt_list_ms2")
        rts = np.repeat(precursor_rts, np.diff(inds))
    else:
        raise ValueError(f"{ms_level} is not a valid ms level")

    selected = mzs.astype(np.int64)
    ds = np.zeros((3, len(selected)))
    if len(db_array) < len(selected) + 1:
        tmp = np.zeros(len(selected) + 1)
        tmp[:len(db_array)] = db_array
        db_array = tmp
    ds[0] = mzs - db_array[selected - 1]
    ds[1] = mzs - db_array[selected]
    ds[2] = mzs - db_array[selected + 1]
    min_ds = np.take_along_axis(
        ds,
        np.expand_dims(np.argmin(np.abs(ds), axis=0), axis=0),
        axis=0
    ).squeeze(axis=0)
    ppm_ds = min_ds / mzs * 10**6

    selected = np.abs(ppm_ds) < max_ppm_distance
    selected &= np.isfinite(rts)
    rt_order = np.argsort(rts)
    rt_order = rt_order[selected[rt_order]]


    ordered_rt = rts[rt_order]
    ordered_ppm = ppm_ds[rt_order]

    rt_idx_break = np.searchsorted(
        ordered_rt,
        np.arange(ordered_rt[0], ordered_rt[-1], rt_step_size),
        "left"
    )
    median_ppms = np.empty(len(rt_idx_break) - 1)
    for i in range(len(median_ppms)):
        median_ppms[i] = np.median(
            ordered_ppm[rt_idx_break[i]: rt_idx_break[i + 1]]
        )

    if plot_ppms:
        import matplotlib.pyplot as plt
        plt.plot(
            rt_step_size + np.arange(
                ordered_rt[0],
                ordered_rt[-1],
                rt_step_size
            )[:-1],
            median_ppms
        )
        plt.show()

    estimated_errors = scipy.interpolate.griddata(
        rt_step_size / 2 + np.arange(
            ordered_rt[0],
            ordered_rt[-1] - 2 * rt_step_size,
            rt_step_size
        ),
        median_ppms,
        rts,
        fill_value=0,
        method="linear",
        rescale=True
    )

    estimated_errors[~np.isfinite(estimated_errors)] = 0

    return estimated_errors

# Cell

def calibrate_fragments(
    db_file_name,
    ms_data_file_name,
    ms_level=2
):
    db_array = get_db_targets(
        db_file_name,
        max_ppm=100,
        min_distance=0.5,
        ms_level=ms_level,
    )
    estimated_errors = align_run_to_db(
        ms_data_file_name,
        db_array=db_array,
        ms_level=ms_level,
        plot_ppms=False,
    )

    ms_file = alphapept.io.MS_Data_File(ms_data_file_name, is_overwritable=True)
    ms_file.write(
        estimated_errors,
        dataset_name="corrected_fragment_mzs",
    )