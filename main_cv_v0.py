# Check communication with E4980A
from e4980A_utils.comm_test import *
from e4980A_utils.qcodes_cv import *
from S200_utils.initialize_s200 import *
from S200_utils.chuck_control import *
import os

current_dir = os.getcwd()
save_data = True  # Set to False to skip saving data
save_plot = True  # Set to False to skip saving plots
save_settings = True  # Set to False to skip saving settings

def main(dr, dc, lcr_meter):
    cv_settings = settings.copy()
    cv_settings['sample_name'] = "JK_MISM_baseline_000"
    cv_settings['device_group'] = "MISM_200_150"
    cv_settings['start_volt'] = -4.0
    cv_settings['stop_volt'] = 1.0
    cv_settings['num_points'] = 51

    dev_row_idx = dr  # Index of the device row in the CSV file (0-based)
    dev_col_idx = dc  # Index of the device column in the CSV file (0-based)

    save_dir = os.path.join("saved_data", cv_settings['sample_name'], cv_settings['device_group'])
    os.makedirs(save_dir, exist_ok=True)
    cv_measurement = CVMeasurement(cv_settings, lcr_meter=lcr_meter)
    move_contact_height(prober=prober)
    df = cv_measurement.perform_cv_sweep()
    move_separation_height(prober=prober)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    save_csv_path = os.path.join(save_dir, f"row_{dev_row_idx}_col_{dev_col_idx}_{timestamp}_cv_data.csv")
    save_settings_path = os.path.join(save_dir, f"row_{dev_row_idx}_col_{dev_col_idx}_{timestamp}_cv_settings.yaml")
    save_plot_path = os.path.join(save_dir, f"row_{dev_row_idx}_col_{dev_col_idx}_{timestamp}_cv_plot.png")

    if save_data:
        df.to_csv(save_csv_path, index=False)
        print(f"Data saved to {save_csv_path}")

    if save_settings:
        cv_settings.update({'timestamp': timestamp})
        with open(save_settings_path, 'w') as f:
            yaml.dump(cv_settings, f)
        print(f"Settings saved to {save_settings_path}")

    # Plotting
    fig = plt.figure()
    voltage_col = next((c for c in df.columns if 'voltage' in c.lower() or 'bias' in c.lower()), None)
    x_data = df[voltage_col] if voltage_col else np.linspace(cv_settings['start_volt'], cv_settings['stop_volt'], cv_settings['num_points'])
    xlabel = voltage_col if voltage_col else 'Voltage (V)'

    if 'direction' in df.columns:
        fwd_mask = df['direction'] == 'fwd'
        bwd_mask = df['direction'] == 'bwd'
        plt.plot(df[fwd_mask][voltage_col], df[fwd_mask]['capacitance'], 'b.-', label='Forward')
        plt.plot(df[bwd_mask][voltage_col], df[bwd_mask]['capacitance'], 'r.-', label='Backward')
        plt.legend()
    else:
        plt.plot(x_data, df['capacitance'], 'o-')

    plt.xlabel(xlabel)
    plt.ylabel('Capacitance (F)')
    plt.title(f'C-V Sweep: {cv_settings["device_group"]}')
    plt.grid(True)
    plt.tight_layout()
    plt.show(block=False)
    plt.pause(5)

    if save_plot:
        plt.savefig(save_plot_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {save_plot_path}")

    plt.close(fig)

def main_cvf(dr, dc, lcr_meter):
    cvf_settings = settings.copy()
    cvf_settings['sample_name'] = "JK_MISM_baseline_000"
    cvf_settings['device_group'] = "MISM_200_200"
    cvf_settings['start_volt'] = 1.0
    cvf_settings['stop_volt'] = -4.0
    cvf_settings['step_volt'] = -0.05
    cvf_settings['start_freq'] = 1e3
    cvf_settings['stop_freq'] = 1e6
    cvf_settings['num_freq_decade'] = 5

    dev_row_idx = dr  # Index of the device row in the CSV file (0-based)
    dev_col_idx = dc  # Index of the device column in the CSV file (0-based)

    save_dir = os.path.join("saved_data", cvf_settings['sample_name'], cvf_settings['device_group'])
    os.makedirs(save_dir, exist_ok=True)
    cvf_measurement = CVMeasurement(cvf_settings, lcr_meter=lcr_meter)
    move_contact_height(prober=prober)
    df = cvf_measurement.perform_cvf_sweep()
    move_separation_height(prober=prober)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    save_csv_path = os.path.join(save_dir, f"row_{dev_row_idx}_col_{dev_col_idx}_{timestamp}_cvf_data.csv")
    save_settings_path = os.path.join(save_dir, f"row_{dev_row_idx}_col_{dev_col_idx}_{timestamp}_cvf_settings.yaml")
    save_plot_path = os.path.join(save_dir, f"row_{dev_row_idx}_col_{dev_col_idx}_{timestamp}_cvf_plot.png")

    if save_data:
        df.to_csv(save_csv_path, index=False)
        print(f"Data saved to {save_csv_path}")

    if save_settings:
        cvf_settings.update({'timestamp': timestamp})
        with open(save_settings_path, 'w') as f:
            yaml.dump(cvf_settings, f)
        print(f"Settings saved to {save_settings_path}")

    # Plotting
    fig = plt.figure()
    volt_col = 'voltage'
    freq_col = 'frequency'
    freq_unique = df[freq_col].unique()
    dir_unique = df['direction'].unique() if 'direction' in df.columns else ['fwd']
    for direction in dir_unique:
        for freq in freq_unique:
            mask = (df[volt_col].notna()) & (df[freq_col] == freq) & ((df['direction'] == direction) if 'direction' in df.columns else True)
            marker = 'o' if direction == 'fwd' else 's'
            color = plt.cm.viridis((np.log10(freq) - np.log10(cvf_settings['start_freq'])) / (np.log10(cvf_settings['stop_freq']) - np.log10(cvf_settings['start_freq'])))
            plt.plot(df[mask][volt_col], df[mask]['capacitance'], marker=marker, color=color, label=f'{direction} - {freq/1e3:.1f} kHz')
    # plt.legend()
    plt.xlabel('Voltage (V)')
    plt.ylabel('Capacitance (F)')
    plt.title(f'C-V-F Sweep: {cvf_settings["device_group"]}')
    plt.grid(True)
    plt.tight_layout()
    plt.show(block=False)
    plt.pause(5)

    if save_plot:
        plt.savefig(save_plot_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {save_plot_path}")

    plt.close(fig)


if __name__ == "__main__":
    r_pitch = 350  # Row pitch in microns
    c_pitch = 500  # Column pitch in microns
    r_num = 1  # Number of rows
    c_num = 4  # Number of columns
    start_dr = 0  # Starting row index (0-based)
    start_dc = 0  # Starting column index (0-based)
    curr_x_disp = 0
    curr_y_disp = 0

    lcr_meter = KeysightE4980A('lcr_meter', settings['lcr_meter_address'])
    # skip_list = [(0, 0), (1, 0), (0, 1), (0, 2), (0, 3), (0, 4)]
    # skip_list = [(0, 0), (0, 1)]
    skip_list = []

    for dr in range(r_num):
        for dc in range(c_num):
            if (dr, dc) in skip_list:
                print(f"Skipping device at row {dr}, column {dc}")
                continue
            print(f"Moving to device at row {dr}, column {dc}")
            reqd_x_disp = (dc - start_dc) * c_pitch
            reqd_y_disp = (dr - start_dr) * r_pitch
            move_relative(prober=prober, x_microns=reqd_x_disp-curr_x_disp, y_microns=reqd_y_disp-curr_y_disp)
            curr_x_disp = reqd_x_disp
            curr_y_disp = reqd_y_disp
            main_cvf(dr=dr, dc=dc, lcr_meter=lcr_meter)
    prober.close()
    rm.close()