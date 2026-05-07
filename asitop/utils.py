import os
import glob
import tempfile
import subprocess
from subprocess import PIPE, DEVNULL
import psutil
from .parsers import *
import plistlib


def get_powermetrics_dir(base_dir=None):
    root = base_dir or tempfile.gettempdir()
    path = os.path.join(root, f"asitop-{os.getuid()}")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def get_powermetrics_path(timecode, base_dir=None):
    return os.path.join(get_powermetrics_dir(base_dir), f"powermetrics-{timecode}.plist")


def cleanup_powermetrics_files(base_dir=None):
    for tmpf in glob.glob(os.path.join(get_powermetrics_dir(base_dir), "powermetrics-*.plist")):
        try:
            os.remove(tmpf)
        except FileNotFoundError:
            continue


def parse_powermetrics(path=None, timecode="0"):
    path = path or get_powermetrics_path(timecode)
    data = None
    try:
        with open(path, 'rb') as fp:
            data = fp.read()
        data = data.split(b'\x00')
        powermetrics_parse = plistlib.loads(data[-1])
        thermal_pressure = parse_thermal_pressure(powermetrics_parse)
        cpu_metrics_dict = parse_cpu_metrics(powermetrics_parse)
        gpu_metrics_dict = parse_gpu_metrics(powermetrics_parse)
        #bandwidth_metrics = parse_bandwidth_metrics(powermetrics_parse)
        bandwidth_metrics = None
        timestamp = powermetrics_parse["timestamp"]
        return cpu_metrics_dict, gpu_metrics_dict, thermal_pressure, bandwidth_metrics, timestamp
    except Exception as e:
        if data:
            if len(data) > 1:
                powermetrics_parse = plistlib.loads(data[-2])
                thermal_pressure = parse_thermal_pressure(powermetrics_parse)
                cpu_metrics_dict = parse_cpu_metrics(powermetrics_parse)
                gpu_metrics_dict = parse_gpu_metrics(powermetrics_parse)
                #bandwidth_metrics = parse_bandwidth_metrics(powermetrics_parse)
                bandwidth_metrics = None
                timestamp = powermetrics_parse["timestamp"]
                return cpu_metrics_dict, gpu_metrics_dict, thermal_pressure, bandwidth_metrics, timestamp
        return False


def clear_console():
    command = 'clear'
    os.system(command)


def convert_to_GB(value):
    return round(value/1024/1024/1024, 1)


def run_powermetrics_process(timecode, nice=10, interval=1000):
    output_path = get_powermetrics_path(timecode)
    cleanup_powermetrics_files()
    output_file_flag = "-o"
    command = " ".join([
        "sudo nice -n",
        str(nice),
        "powermetrics",
        "--samplers cpu_power,gpu_power,thermal",
        output_file_flag,
        output_path,
        "-f plist",
        "-i",
        str(interval)
    ])
    process = subprocess.Popen(
        command.split(" "),
        stdin=DEVNULL,
        stdout=DEVNULL,
    )
    return process


def get_ram_metrics_dict():
    ram_metrics = psutil.virtual_memory()
    swap_metrics = psutil.swap_memory()
    total_GB = convert_to_GB(ram_metrics.total)
    free_GB = convert_to_GB(ram_metrics.available)
    used_GB = convert_to_GB(ram_metrics.total-ram_metrics.available)
    swap_total_GB = convert_to_GB(swap_metrics.total)
    swap_used_GB = convert_to_GB(swap_metrics.used)
    swap_free_GB = convert_to_GB(swap_metrics.total-swap_metrics.used)
    if swap_total_GB > 0:
        swap_free_percent = int(100-(swap_free_GB/swap_total_GB*100))
    else:
        swap_free_percent = None
    ram_metrics_dict = {
        "total_GB": round(total_GB, 1),
        "free_GB": round(free_GB, 1),
        "used_GB": round(used_GB, 1),
        "free_percent": int(100-(ram_metrics.available/ram_metrics.total*100)),
        "swap_total_GB": swap_total_GB,
        "swap_used_GB": swap_used_GB,
        "swap_free_GB": swap_free_GB,
        "swap_free_percent": swap_free_percent,
    }
    return ram_metrics_dict


def get_cpu_info():
    cpu_info = os.popen('sysctl -a | grep machdep.cpu').read()
    cpu_info_lines = cpu_info.split("\n")
    data_fields = ["machdep.cpu.brand_string", "machdep.cpu.core_count"]
    cpu_info_dict = {}
    for l in cpu_info_lines:
        for h in data_fields:
            if h in l:
                value = l.split(":")[1].strip()
                cpu_info_dict[h] = value
    return cpu_info_dict


def get_core_counts():
    cores_info = os.popen('sysctl -a | grep hw.perflevel').read()
    cores_info_lines = cores_info.split("\n")
    data_fields = ["hw.perflevel0.logicalcpu", "hw.perflevel1.logicalcpu"]
    cores_info_dict = {}
    for l in cores_info_lines:
        for h in data_fields:
            if h in l:
                value = int(l.split(":")[1].strip())
                cores_info_dict[h] = value
    return cores_info_dict


def get_gpu_cores():
    try:
        cores = os.popen(
            "system_profiler -detailLevel basic SPDisplaysDataType | grep 'Total Number of Cores'").read()
        cores = int(cores.split(": ")[-1])
    except:
        cores = "?"
    return cores


def get_soc_info():
    cpu_info_dict = get_cpu_info()
    core_counts_dict = get_core_counts()
    try:
        e_core_count = core_counts_dict["hw.perflevel1.logicalcpu"]
        p_core_count = core_counts_dict["hw.perflevel0.logicalcpu"]
    except:
        e_core_count = "?"
        p_core_count = "?"
    soc_info = {
        "name": cpu_info_dict["machdep.cpu.brand_string"],
        "core_count": int(cpu_info_dict["machdep.cpu.core_count"]),
        "cpu_max_power": None,
        "gpu_max_power": None,
        "cpu_max_bw": None,
        "gpu_max_bw": None,
        "e_core_count": e_core_count,
        "p_core_count": p_core_count,
        "gpu_core_count": get_gpu_cores()
    }

    # NOTE:
    # - bandwidth values below are based on Apple's published unified memory bandwidth
    # - power values below are estimates / heuristics, not Apple-published TDPs

    soc_specs = {
        # M1 series
        "Apple M1":       {"cpu_power": 20, "gpu_power": 20,  "cpu_bw": 70,  "gpu_bw": 70},
        "Apple M1 Pro":   {"cpu_power": 30, "gpu_power": 30,  "cpu_bw": 200, "gpu_bw": 200},
        "Apple M1 Max":   {"cpu_power": 30, "gpu_power": 60,  "cpu_bw": 250, "gpu_bw": 400},
        "Apple M1 Ultra": {"cpu_power": 60, "gpu_power": 120, "cpu_bw": 500, "gpu_bw": 800},

        # M2 series
        "Apple M2":       {"cpu_power": 25, "gpu_power": 15,  "cpu_bw": 100, "gpu_bw": 100},
        "Apple M2 Pro":   {"cpu_power": 30, "gpu_power": 30,  "cpu_bw": 200, "gpu_bw": 200},
        "Apple M2 Max":   {"cpu_power": 35, "gpu_power": 60,  "cpu_bw": 400, "gpu_bw": 400},
        "Apple M2 Ultra": {"cpu_power": 70, "gpu_power": 120, "cpu_bw": 800, "gpu_bw": 800},

        # M3 series
        "Apple M3":       {"cpu_power": 25, "gpu_power": 20,  "cpu_bw": 100, "gpu_bw": 100},
        "Apple M3 Pro":   {"cpu_power": 30, "gpu_power": 35,  "cpu_bw": 150, "gpu_bw": 150},
        "Apple M3 Max":   {"cpu_power": 35, "gpu_power": 60,  "cpu_bw": 400, "gpu_bw": 400},
        "Apple M3 Ultra": {"cpu_power": 70, "gpu_power": 120, "cpu_bw": 819, "gpu_bw": 819},

        # M4 series
        "Apple M4":       {"cpu_power": 25, "gpu_power": 20,  "cpu_bw": 120, "gpu_bw": 120},
        "Apple M4 Pro":   {"cpu_power": 35, "gpu_power": 40,  "cpu_bw": 273, "gpu_bw": 273},
        "Apple M4 Max":   {"cpu_power": 40, "gpu_power": 70,  "cpu_bw": 546, "gpu_bw": 546},

        # M5 series
        "Apple M5":       {"cpu_power": 30, "gpu_power": 25,  "cpu_bw": 153, "gpu_bw": 153},
        "Apple M5 Pro":   {"cpu_power": 40, "gpu_power": 45,  "cpu_bw": 307, "gpu_bw": 307},
        "Apple M5 Max":   {"cpu_power": 45, "gpu_power": 80,  "cpu_bw": 614, "gpu_bw": 614},
    }

    spec = soc_specs.get(
        soc_info["name"],
        {"cpu_power": 20, "gpu_power": 20, "cpu_bw": 70, "gpu_bw": 70},
    )

    soc_info["cpu_max_power"] = spec["cpu_power"]
    soc_info["gpu_max_power"] = spec["gpu_power"]
    soc_info["cpu_max_bw"] = spec["cpu_bw"]
    soc_info["gpu_max_bw"] = spec["gpu_bw"]

    return soc_info
