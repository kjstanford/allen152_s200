import numpy as np
from scipy.interpolate import interp1d

""" split double sweep into fwd and bkd sweeps """
def get_sweeps(X):
    N1 = len(X)
    X_ = {}
    X_['f'] = X[:int(N1/2)]
    X_['b'] = X[int(N1/2):]
    return X_

def Vt_at_constant_Id(Vg_data, Id_data, Id_target=1e-9):
    """
    Extracts Vt at a constant drain current using Log-Linear interpolation.
    """
    # 1. Take absolute value (handles p-type or negative probe setups)
    Id_abs = np.abs(Id_data)
    
    # 2. Filter for positive currents only (to avoid log(0) or log(negative) errors)
    valid_mask = Id_abs > 0
    Vg_clean = Vg_data[valid_mask]
    Id_clean = Id_abs[valid_mask]

    # 3. Sort data by Current (Id)
    # interp1d requires the 'x' argument (Id in this inverse lookup) to be monotonic.
    # We sort by Id just to be safe against noisy data or hysteresis loops.
    sorted_indices = np.argsort(Id_clean)
    Id_sorted = Id_clean[sorted_indices]
    Vg_sorted = Vg_clean[sorted_indices]

    # 4. Interpolate using Log(Id)
    # We map log10(Id) -> Vg. 
    # This respects the exponential physics of the subthreshold region.
    interp_func = interp1d(np.log10(Id_sorted), Vg_sorted, 
                           kind='linear', 
                           fill_value="extrapolate")

    # 5. Calculate Vt
    Vt = interp_func(np.log10(Id_target))
    
    return float(Vt)