import time
import os
import serial
import numpy as np
from scipy.spatial.distance import euclidean
from sensor_read import Sensor

from solano_telnet import Solano, COMMANDS_INFO

SENSOR_CONFIG = [(0, 0x2A)]
SERIAL_PORT = "COM3"

def optimize_path(locations):
    """
    Reorder the locations to minimize the path length using a Nearest Neighbor heuristic.
    Only x, y, z coordinates are considered.
    """
    if not locations:
        return []

    optimized_path = [locations.pop(0)]  # Start with the first location

    while locations:
        last = optimized_path[-1]
        next_location = min(locations, key=lambda loc: euclidean(last[:3], loc[:3]))
        optimized_path.append(next_location)
        locations.remove(next_location)

    return optimized_path

def sensor_columns(sensor_config):
    return [
        f"S{sensor_idx}_L{channel_idx}"
        for sensor_idx in range(len(sensor_config))
        for channel_idx in range(4)
    ]

def read_sensor_values(sensor):
    _, sensors = sensor.process_single_measurement_all()
    return [value for sensor_data in sensors for value in sensor_data["inductance"]]

def write_calibration_row(filename, location, sensor_values):
    x, y, z, roll, pitch, yaw = location
    values = [time.time(), x, y, z, roll, pitch, yaw, *sensor_values]
    with open(filename, 'a') as f:
        f.write(",".join(str(value) for value in values) + "\n")

if __name__ == "__main__":
    sensor_id = "s5"
    type = "calibration" # or "validation" # or 
    filename = "./v2_sensor/" + type + "_"+sensor_id+"_"+time.strftime("%Y%m%d-%H%M%S")+".csv"
    
    
    if os.path.exists(filename):
        # ask user if they want to overwrite
        overwrite = input(f"{filename} already exists. Overwrite? (y/n): ").strip().lower()
        if overwrite != 'y':
            print("Exiting without overwriting.")
            exit()

    solano = Solano(host="192.168.16.220", port=23, timeout=1)
    print("Connecting to Solano hexapod...")
    solano.connect()
    if not solano.connection:
        print("Failed to connect to Solano hexapod.")
        exit()
    time.sleep(0.5)  # Wait for connection to stabilize
    print("Connected to Solano hexapod.")

    
    solano.authenticate()
    solano.init()

    xlim = 5.0 # mm +-
    ylim = 5.0 # mm +-
    zlim = 5.0 # mm +-
    pitch_value = 0 # degrees static
    roll_value = 0 # degrees static
    yaw_value = 0 # degrees static

    n_tests = 1000  # total number of test positions

    # New configuration for layered spiral
    n_points_per_layer = 200    # number of samples (points) per spiral layer
    turns = 15                   # spiral turns per layer
    z_resolution = 1.0      # step in z between layers in mm

    # random=True

    # if random:# Define a random list of 6-DOF locations (x, y, z, roll, pitch, yaw)
    #     locations = [
    #         (np.random.uniform(0, xlim) * np.cos(np.random.uniform(0, 2 * np.pi)),  # x calculated from radius and theta
    #         np.random.uniform(0, ylim) * np.sin(np.random.uniform(0, 2 * np.pi)),  # y calculated from radius and theta
    #         np.random.uniform(-zlim, zlim), 
    #         np.random.uniform(-roll_value, roll_value),
    #         np.random.uniform(-pitch_value, pitch_value),
    #         np.random.uniform(-yaw_value, yaw_value)) for _ in range(n_tests)
    #     ]

    #     # Optimize the locations list
    #     locations = optimize_path(locations)

    # else: # Define a grid of 6-DOF locations (x, y, z, roll, pitch, yaw)
    #     x_values = np.linspace(-xlim, xlim, num=5)
    #     y_values = np.linspace(-ylim, ylim, num=5)
    #     z_values = np.linspace(-zlim, zlim, num=5)
    #     roll_values = np.linspace(-roll_value, roll_value, num=1)
    #     pitch_values = np.linspace(-pitch_value, pitch_value, num=1)
    #     yaw_values = np.linspace(-yaw_value, yaw_value, num=1)
    #     locations = []

    #     for z in z_values:
    #         for y_idx, y in enumerate(y_values):
    #         # Alternate x traversal direction for zig-zag pattern
    #             x_traversal = x_values if y_idx % 2 == 0 else x_values[::-1]
    #             for x in x_traversal:
    #                 for roll in roll_values:
    #                     for pitch in pitch_values:
    #                         for yaw in yaw_values:
    #                             locations.append((x, y, z, roll, pitch, yaw))

    #     #locations = optimize_path(locations)

    # Calculate number of layers (ensure at least 1)
    if z_resolution <= 0:
        raise ValueError('z_resolution must be > 0')
    n_layers = max(1, int(np.ceil((2 * zlim) / z_resolution)))

    # Precompute concentric circles for a single layer
    max_radius = min(xlim, ylim)
    rad_resolution = 0.5  # Define the radial resolution (number of circles)
    radii = np.arange(rad_resolution, max_radius + rad_resolution, rad_resolution)

    # Calculate total circumference of all circles in the layer
    total_circumference = sum(2 * np.pi * r for r in radii)

    # Divide total circumference by n_points_per_layer to get arc length
    arc_length = total_circumference / n_points_per_layer

    # Generate points for each circle
    theta = []
    r = []
    for radius in radii:
        # Estimate the number of points for this circle
        n_points_circle = max(1, int(np.ceil((2 * np.pi * radius) / arc_length)))

        # Round the number of points to the nearest multiple of 4
        n_points_circle = int(np.ceil(n_points_circle / 4) * 4)

        # Generate points for this circle
        theta_circle = np.linspace(0, 2 * np.pi, n_points_circle, endpoint=False)
        r_circle = [radius] * n_points_circle

        # Append to the overall list
        theta.extend(theta_circle)
        r.extend(r_circle)

    x_vals_out = np.array(r) * np.cos(theta)
    y_vals_out = np.array(r) * np.sin(theta)

    locations = []

    # # Set locations so they are a line in z (x and y =0) from -5 to 5 and back in steps of 50um
    # z_values = np.arange(-zlim, zlim + 0.0001, 0.05)  # 0.05 mm steps
    # for z in z_values:
    #     locations.append((0.0, 0.0, float(z), roll_value, pitch_value, yaw_value))
    # for z in z_values[::-1]:
    #     locations.append((0.0, 0.0, float(z), roll_value, pitch_value, yaw_value))

    # # Build layered spiral: alternate outward and inward on successive Z planes
    # for layer_idx in range(n_layers):
    #     # Determine z for this layer (centered around 0)
    #     z_layer = -zlim + layer_idx * z_resolution

    #     # Select direction: even layers -> outward, odd layers -> inward
    #     if (layer_idx % 2) == 0:
    #         # outward
    #         xs = x_vals_out
    #         ys = y_vals_out
    #     else:
    #         # inward: traverse the spiral in reverse order
    #         xs = x_vals_out[::-1]
    #         ys = y_vals_out[::-1]

    #     # Append layer points
    #     for xi, yi in zip(xs, ys):
    #         locations.append((float(xi), float(yi), float(z_layer), roll_value, pitch_value, yaw_value))

    # Build square zig zag pattern layered in Z
        # Define 2 layers - one swept in x, the next swept in y. this needs to be a grid of points with "z_resolution sparation
        # 
    layer_a_points = []
    layer_b_points = []
    x_coords = np.arange(-xlim, xlim + 0.0001, z_resolution)  # 0.5 mm steps
    y_coords = np.arange(-ylim, ylim + 0.0001, z_resolution)  # 0.5 mm steps"

    for xi, x in enumerate(x_coords):
        # Alternate y traversal direction for zig-zag pattern
        y_traversal = y_coords if xi % 2 == 0 else y_coords[::-1]
        for y in y_traversal:
            layer_a_points.append((float(x), float(y), 0.0, roll_value, pitch_value, yaw_value))
    for yi, y in enumerate(y_coords):
        # Alternate x traversal direction for zig-zag pattern
        x_traversal = x_coords if yi % 2 == 0 else x_coords[::-1]
        for x in x_traversal:
            layer_b_points.append((float(x), float(y), 0.0, roll_value, pitch_value, yaw_value))
    # Build layered pattern
    for layer_idx in range(n_layers):
        # Determine z for this layer (centered around 0)
        z_layer = -zlim + layer_idx * z_resolution

        # Select layer points: even layers -> layer_a, odd layers -> layer_b
        if (layer_idx % 2) == 0:
            # layer_a
            for point in layer_a_points:
                x, y, _, roll, pitch, yaw = point
                locations.append((float(x), float(y), float(z_layer), roll, pitch, yaw))
        else:
            # layer_b
            for point in layer_b_points:
                x, y, _, roll, pitch, yaw = point
                locations.append((float(x), float(y), float(z_layer), roll, pitch, yaw))


    # # Trim the trajectory so it fits within a cone either side of the xy plane with the base on the xy plane
    # filtered_locations = []
    # for loc in locations:
    #     x, y, z, roll, pitch, yaw = loc
    #     max_radius_at_z = (1 - abs(z) / zlim) * min(xlim, ylim)
    #     radius = np.sqrt(x**2 + y**2)
    #     if radius <= max_radius_at_z:
    #         filtered_locations.append(loc)
    # locations = filtered_locations

     


    solano.execute_command("ControlOn")
    print("Control is ON. Ready to move the hexapod.")
    solano.move_P2P(0, 0, 0, 0,0,0)
    print("Hexapod is at the initial position. Ready to start calibration.")
     
    input("Press Enter to start moving...")

        
    # List available serial ports
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if not ports:
        print("No serial ports found.")
    else:
        serial_port = SERIAL_PORT if SERIAL_PORT in ports else ports[0]
        sensor = Sensor(port=serial_port, sensor_config=SENSOR_CONFIG)
        sensor.connect()

        i=0


        with open(filename, 'w') as f:
            f.write("Time,Tx,Ty,Tz,Roll,Pitch,Yaw," + ",".join(sensor_columns(SENSOR_CONFIG)) + "\n")

        try:
            tic = time.time()
            # Iterate through the locations and send move commands
            for i, location in enumerate(locations):
                # Clear terminal
                
                elapsed_time = time.time() - tic
                estimated_total_time = (elapsed_time / (i + 1)) * len(locations)
                remaining_time = estimated_total_time - elapsed_time
               
                x, y, z, roll, pitch, yaw = location
                
                solano.move_P2P(x, y, z, roll, pitch, yaw)
                print("\x1b[H\x1b[2J\x1b[3J")  # ANSI escape code to clear terminal
                # elapsed time as HH mm ss
                print(f"Elapsed time: {int(elapsed_time//3600):02d}:{int((elapsed_time%3600)//60):02d}:{int(elapsed_time%60):02d}")
                print(f"Estimated total time: {int(estimated_total_time//3600):02d}:{int((estimated_total_time%3600)//60):02d}:{int(estimated_total_time%60):02d}")
                print(f"Estimated remaining time: {int(remaining_time//3600):02d}:{int((remaining_time%3600)//60):02d}:{int(remaining_time%60):02d}")
                print(f"Moving to location: {i} out of {len(locations)} ")

                sensor_values = read_sensor_values(sensor)
                print("Calibrated values: " + ", ".join(
                    f"{name}={value}" for name, value in zip(sensor_columns(SENSOR_CONFIG), sensor_values)
                ))

                # Read exact position after moving
                position_response = solano.execute_command("MtpPosition")
                print(f"Current position: {position_response}")

                write_calibration_row(filename, location, sensor_values)
                print(f"Saved: {time.time()}")
                
                # 5 repeats at each position
                for repeat in range(5):
                    sensor_values = read_sensor_values(sensor)
                   

                    # Read exact position after moving
                    position_response 

                    write_calibration_row(filename, location, sensor_values)

                # i += 1

            solano.execute_command("ControlOff")


        except KeyboardInterrupt:
            print("Stopping sensor reading...")
        finally:
            sensor.disconnect()

