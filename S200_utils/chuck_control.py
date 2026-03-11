import time
import pyvisa

def move_relative(prober=None, x_microns=0, y_microns=0):
    if prober is None:
        # print("Prober resource not provided. Cannot move chuck.")
        # return 1
        raise ValueError("Prober resource not provided. Cannot move chuck.")
    """
    Relative move of the chuck by specified microns in X and Y directions.
    """
    response = prober.query('ReadChuckPosition')
    print(f"Start Position: {response}")
    
    # print(f"Moving chuck to separation height...")
    # prober.write('MoveChuckSeparation 100.')
    # time.sleep(5)

    # time.sleep(1)
    print(f"Commanding move: X={x_microns}, Y={y_microns}...")        
    prober.write(f'MoveChuck {-1*x_microns} {-1*y_microns} R Y 100.')
    time.sleep(10)

    # print(f"Moving chuck to contact height...")
    # prober.write('MoveChuckContact 100.')
    # time.sleep(5)

    response = prober.query('ReadChuckPosition')
    print(f"Current Position: {response}")

    # return 0

def move_separation_height(prober=None):
    if prober is None:
        # print("Prober resource not provided. Cannot move chuck.")
        # return 1
        raise ValueError("Prober resource not provided. Cannot move chuck.")
    """
    Move the chuck to separation height.
    """
    print(f"Moving chuck to separation height...")
    prober.write('MoveChuckSeparation 100.')
    time.sleep(5)
    return 0

def move_contact_height(prober=None):
    if prober is None:
        # print("Prober resource not provided. Cannot move chuck.")
        # return 1
        raise ValueError("Prober resource not provided. Cannot move chuck.")
    """
    Move the chuck to contact height.
    """
    print(f"Moving chuck to contact height...")
    prober.write('MoveChuckContact 100.')
    time.sleep(5)
    # return 0