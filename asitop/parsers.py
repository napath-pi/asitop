def parse_thermal_pressure(powermetrics_parse):
    return powermetrics_parse["thermal_pressure"]


def parse_bandwidth_metrics(powermetrics_parse):
    bandwidth_metrics = powermetrics_parse["bandwidth_counters"]
    bandwidth_metrics_dict = {}
    data_fields = ["PCPU0 DCS RD", "PCPU0 DCS WR",
                   "PCPU1 DCS RD", "PCPU1 DCS WR",
                   "PCPU2 DCS RD", "PCPU2 DCS WR",
                   "PCPU3 DCS RD", "PCPU3 DCS WR",
                   "PCPU DCS RD", "PCPU DCS WR",
                   "ECPU0 DCS RD", "ECPU0 DCS WR",
                   "ECPU1 DCS RD", "ECPU1 DCS WR",
                   "ECPU DCS RD", "ECPU DCS WR",
                   "GFX DCS RD", "GFX DCS WR",
                   "ISP DCS RD", "ISP DCS WR",
                   "STRM CODEC DCS RD", "STRM CODEC DCS WR",
                   "PRORES DCS RD", "PRORES DCS WR",
                   "VDEC DCS RD", "VDEC DCS WR",
                   "VENC0 DCS RD", "VENC0 DCS WR",
                   "VENC1 DCS RD", "VENC1 DCS WR",
                   "VENC2 DCS RD", "VENC2 DCS WR",
                   "VENC3 DCS RD", "VENC3 DCS WR",
                   "VENC DCS RD", "VENC DCS WR",
                   "JPG0 DCS RD", "JPG0 DCS WR",
                   "JPG1 DCS RD", "JPG1 DCS WR",
                   "JPG2 DCS RD", "JPG2 DCS WR",
                   "JPG3 DCS RD", "JPG3 DCS WR",
                   "JPG DCS RD", "JPG DCS WR",
                   "DCS RD", "DCS WR"]
    for h in data_fields:
        bandwidth_metrics_dict[h] = 0
    for l in bandwidth_metrics:
        if l["name"] in data_fields:
            bandwidth_metrics_dict[l["name"]] = l["value"]/(1e9)
    bandwidth_metrics_dict["PCPU DCS RD"] = bandwidth_metrics_dict["PCPU DCS RD"] + \
        bandwidth_metrics_dict["PCPU0 DCS RD"] + \
        bandwidth_metrics_dict["PCPU1 DCS RD"] + \
        bandwidth_metrics_dict["PCPU2 DCS RD"] + \
        bandwidth_metrics_dict["PCPU3 DCS RD"]
    bandwidth_metrics_dict["PCPU DCS WR"] = bandwidth_metrics_dict["PCPU DCS WR"] + \
        bandwidth_metrics_dict["PCPU0 DCS WR"] + \
        bandwidth_metrics_dict["PCPU1 DCS WR"] + \
        bandwidth_metrics_dict["PCPU2 DCS WR"] + \
        bandwidth_metrics_dict["PCPU3 DCS WR"]
    bandwidth_metrics_dict["JPG DCS RD"] = bandwidth_metrics_dict["JPG DCS RD"] + \
        bandwidth_metrics_dict["JPG0 DCS RD"] + \
        bandwidth_metrics_dict["JPG1 DCS RD"] + \
        bandwidth_metrics_dict["JPG2 DCS RD"] + \
        bandwidth_metrics_dict["JPG3 DCS RD"]
    bandwidth_metrics_dict["JPG DCS WR"] = bandwidth_metrics_dict["JPG DCS WR"] + \
        bandwidth_metrics_dict["JPG0 DCS WR"] + \
        bandwidth_metrics_dict["JPG1 DCS WR"] + \
        bandwidth_metrics_dict["JPG2 DCS WR"] + \
        bandwidth_metrics_dict["JPG3 DCS WR"]
    bandwidth_metrics_dict["VENC DCS RD"] = bandwidth_metrics_dict["VENC DCS RD"] + \
        bandwidth_metrics_dict["VENC0 DCS RD"] + \
        bandwidth_metrics_dict["VENC1 DCS RD"] + \
        bandwidth_metrics_dict["VENC2 DCS RD"] + \
        bandwidth_metrics_dict["VENC3 DCS RD"]
    bandwidth_metrics_dict["VENC DCS WR"] = bandwidth_metrics_dict["VENC DCS WR"] + \
        bandwidth_metrics_dict["VENC0 DCS WR"] + \
        bandwidth_metrics_dict["VENC1 DCS WR"] + \
        bandwidth_metrics_dict["VENC2 DCS WR"] + \
        bandwidth_metrics_dict["VENC3 DCS WR"]
    bandwidth_metrics_dict["MEDIA DCS"] = sum([
        bandwidth_metrics_dict["ISP DCS RD"], bandwidth_metrics_dict["ISP DCS WR"],
        bandwidth_metrics_dict["STRM CODEC DCS RD"], bandwidth_metrics_dict["STRM CODEC DCS WR"],
        bandwidth_metrics_dict["PRORES DCS RD"], bandwidth_metrics_dict["PRORES DCS WR"],
        bandwidth_metrics_dict["VDEC DCS RD"], bandwidth_metrics_dict["VDEC DCS WR"],
        bandwidth_metrics_dict["VENC DCS RD"], bandwidth_metrics_dict["VENC DCS WR"],
        bandwidth_metrics_dict["JPG DCS RD"], bandwidth_metrics_dict["JPG DCS WR"],
    ])
    return bandwidth_metrics_dict


def parse_cpu_metrics(powermetrics_parse):
    e_core = []
    p_core = []
    cpu_metrics = powermetrics_parse["processor"]
    cpu_metric_dict = {}
    # cpu_clusters
    cpu_clusters = cpu_metrics["clusters"]
    cluster_names = [c["name"] for c in cpu_clusters]
    # M5-era chips use S-Cluster (Super) + P-Clusters (Performance) instead of
    # E-Cluster (Efficiency) + P-Cluster (Performance).  Map S→P and P→E
    # so the rest of the code (and the UI) keeps working.
    has_s_cluster = any(n.startswith("S") for n in cluster_names)

    def _classify(cluster_name):
        """Return ('E', e_core) or ('P', p_core) for a given cluster name."""
        first = cluster_name[0]
        if has_s_cluster:
            # S-Cluster = highest perf → 'P', P*-Cluster = lower perf → 'E'
            if first == 'S':
                return 'P-Cluster', p_core
            else:
                return 'E-Cluster', e_core
        else:
            # Classic layout: E-Cluster → 'E', P-Cluster → 'P'
            if first == 'E':
                return 'E-Cluster', e_core
            else:
                return 'P-Cluster', p_core

    e_mapped_clusters = []
    p_mapped_clusters = []

    for cluster in cpu_clusters:
        name = cluster["name"]
        cpu_metric_dict[name+"_freq_Mhz"] = int(cluster["freq_hz"]/(1e6))
        cpu_metric_dict[name+"_active"] = int((1 - cluster["idle_ratio"])*100)
        mapped_name, core_list = _classify(name)
        if mapped_name == 'E-Cluster':
            e_mapped_clusters.append(name)
        else:
            p_mapped_clusters.append(name)
        for cpu in cluster["cpus"]:
            core_list.append(cpu["cpu"])
            cpu_metric_dict[mapped_name + str(cpu["cpu"]) + "_freq_Mhz"] = int(cpu["freq_hz"] / (1e6))
            cpu_metric_dict[mapped_name + str(cpu["cpu"]) + "_active"] = int((1 - cpu["idle_ratio"]) * 100)
    cpu_metric_dict["e_core"] = e_core
    cpu_metric_dict["p_core"] = p_core
    cpu_metric_dict["has_s_cluster"] = has_s_cluster

    # Aggregate cluster metrics using the mapped cluster names
    if "E-Cluster_active" not in cpu_metric_dict:
        if e_mapped_clusters:
            cpu_metric_dict["E-Cluster_active"] = int(
                sum(cpu_metric_dict[n + "_active"] for n in e_mapped_clusters) / len(e_mapped_clusters))
        else:
            cpu_metric_dict["E-Cluster_active"] = 0

    if "E-Cluster_freq_Mhz" not in cpu_metric_dict:
        if e_mapped_clusters:
            cpu_metric_dict["E-Cluster_freq_Mhz"] = max(
                cpu_metric_dict[n + "_freq_Mhz"] for n in e_mapped_clusters)
        else:
            cpu_metric_dict["E-Cluster_freq_Mhz"] = 0

    if "P-Cluster_active" not in cpu_metric_dict:
        if p_mapped_clusters:
            cpu_metric_dict["P-Cluster_active"] = int(
                sum(cpu_metric_dict[n + "_active"] for n in p_mapped_clusters) / len(p_mapped_clusters))
        else:
            cpu_metric_dict["P-Cluster_active"] = 0

    if "P-Cluster_freq_Mhz" not in cpu_metric_dict:
        if p_mapped_clusters:
            cpu_metric_dict["P-Cluster_freq_Mhz"] = max(
                cpu_metric_dict[n + "_freq_Mhz"] for n in p_mapped_clusters)
        else:
            cpu_metric_dict["P-Cluster_freq_Mhz"] = 0
    # power
    cpu_metric_dict["ane_W"] = cpu_metrics["ane_energy"]/1000
    #cpu_metric_dict["dram_W"] = cpu_metrics["dram_energy"]/1000
    cpu_metric_dict["cpu_W"] = cpu_metrics["cpu_energy"]/1000
    cpu_metric_dict["gpu_W"] = cpu_metrics["gpu_energy"]/1000
    cpu_metric_dict["package_W"] = cpu_metrics["combined_power"]/1000
    return cpu_metric_dict


def parse_gpu_metrics(powermetrics_parse):
    gpu_metrics = powermetrics_parse["gpu"]
    gpu_metrics_dict = {
        "freq_MHz": int(gpu_metrics["freq_hz"]),
        "active": int((1 - gpu_metrics["idle_ratio"])*100),
    }
    return gpu_metrics_dict
