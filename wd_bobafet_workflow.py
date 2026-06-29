"""
Usage:
    python wd_bobafet_workflow.py --config <path_to_config.json>

Example:
    python wd_bobafet_workflow.py --config wd_bobafet_utils/run_config.json
"""

# "dev_y_idx_list": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40],

import argparse
import json
import os

def _parse_args():
    p = argparse.ArgumentParser(description='3-terminal FET measurement script (v1)')
    p.add_argument('--config', required=True, help='Path to JSON config file')
    return p.parse_args()

_args = _parse_args()
with open(_args.config) as _f:
    _cfg = json.load(_f)

_misc = _cfg.get('miscellaneous', {})
_meas = _cfg.get('measurement', {})
_sample = _cfg.get('sample', {})
_dev_grp = _cfg.get('dev-group', {})

if _misc.get('mode', 'debug') != 'debug':
    from b1500A_utils.initialize_smus import *
    from S200_utils.initialize_s200 import *
    from e4980A_utils.comm_test import *
    from e4980A_utils.qcodes_cv import *

from wd_bobafet_utils.main_wd_bobafet import *

current_dir = os.getcwd()

mylcr_meter = KeysightE4980A('lcr_meter', settings['lcr_meter_address'])
myb1500 = b1500
myprober = prober
smu_gate = b1500.smu4
smu_drain = b1500.smu2
smu_source = b1500.smu3

if __name__ == '__main__':
    measure_dev_grp(_misc=_misc, _meas=_meas, _sample=_sample, _dev_grp=_dev_grp, myb1500=myb1500, smu_gate=smu_gate, smu_drain=smu_drain, smu_source=smu_source, prober=myprober)
    myprober.close()
    rm.close()