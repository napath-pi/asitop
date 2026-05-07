import unittest

from asitop.parsers import (
    parse_bandwidth_metrics,
    parse_cpu_metrics,
    parse_gpu_metrics,
    parse_thermal_pressure,
)


class ParseGpuMetricsTests(unittest.TestCase):
    def test_converts_freq_hz_to_mhz(self):
        sample = {"gpu": {"freq_hz": 1_296_000_000, "idle_ratio": 0.5}}
        result = parse_gpu_metrics(sample)
        self.assertEqual(result["freq_MHz"], 1296)
        self.assertEqual(result["active"], 50)

    def test_full_load(self):
        sample = {"gpu": {"freq_hz": 1_000_000_000, "idle_ratio": 0.0}}
        self.assertEqual(parse_gpu_metrics(sample)["active"], 100)

    def test_idle(self):
        sample = {"gpu": {"freq_hz": 0, "idle_ratio": 1.0}}
        result = parse_gpu_metrics(sample)
        self.assertEqual(result["active"], 0)
        self.assertEqual(result["freq_MHz"], 0)


class ParseCpuMetricsTests(unittest.TestCase):
    @staticmethod
    def _processor(clusters):
        return {
            "processor": {
                "ane_energy": 0,
                "cpu_energy": 0,
                "gpu_energy": 0,
                "combined_power": 0,
                "clusters": clusters,
            }
        }

    def test_classic_e_and_p_clusters(self):
        sample = self._processor([
            {
                "name": "E-Cluster",
                "freq_hz": 2_064_000_000,
                "idle_ratio": 0.5,
                "cpus": [
                    {"cpu": 0, "freq_hz": 2_064_000_000, "idle_ratio": 0.4},
                ],
            },
            {
                "name": "P-Cluster",
                "freq_hz": 3_200_000_000,
                "idle_ratio": 0.0,
                "cpus": [
                    {"cpu": 0, "freq_hz": 3_200_000_000, "idle_ratio": 0.1},
                ],
            },
        ])
        result = parse_cpu_metrics(sample)
        self.assertEqual(result["E-Cluster_freq_Mhz"], 2064)
        self.assertEqual(result["P-Cluster_freq_Mhz"], 3200)
        self.assertEqual(result["E-Cluster_active"], 50)
        self.assertEqual(result["P-Cluster_active"], 100)
        self.assertFalse(result["has_s_cluster"])

    def test_multi_die_layout_synthesizes_aggregate_via_per_core_average(self):
        sample = self._processor([
            {
                "name": "E0-Cluster",
                "freq_hz": 2_000_000_000,
                "idle_ratio": 0.5,
                "cpus": [{"cpu": 0, "freq_hz": 2_000_000_000, "idle_ratio": 0.4}],
            },
            {
                "name": "P0-Cluster",
                "freq_hz": 3_000_000_000,
                "idle_ratio": 0.5,
                "cpus": [{"cpu": 0, "freq_hz": 3_000_000_000, "idle_ratio": 0.1}],
            },
        ])
        result = parse_cpu_metrics(sample)
        self.assertEqual(result["E-Cluster_active"], 60)
        self.assertEqual(result["P-Cluster_active"], 90)
        self.assertEqual(result["E-Cluster_freq_Mhz"], 2000)
        self.assertEqual(result["P-Cluster_freq_Mhz"], 3000)

    def test_s_cluster_layout_sets_has_s_cluster_flag(self):
        sample = self._processor([
            {
                "name": "S-Cluster",
                "freq_hz": 4_000_000_000,
                "idle_ratio": 0.0,
                "cpus": [{"cpu": 0, "freq_hz": 4_000_000_000, "idle_ratio": 0.0}],
            },
            {
                "name": "P-Cluster",
                "freq_hz": 2_000_000_000,
                "idle_ratio": 0.5,
                "cpus": [{"cpu": 0, "freq_hz": 2_000_000_000, "idle_ratio": 0.5}],
            },
        ])
        result = parse_cpu_metrics(sample)
        self.assertTrue(result["has_s_cluster"])
        self.assertEqual(result["e_core"], [0])
        self.assertEqual(result["p_core"], [0])


class ParseThermalPressureTests(unittest.TestCase):
    def test_returns_value(self):
        self.assertEqual(
            parse_thermal_pressure({"thermal_pressure": "Nominal"}),
            "Nominal",
        )


class ParseBandwidthMetricsTests(unittest.TestCase):
    @staticmethod
    def _wrap(entries):
        return {"bandwidth_counters": entries}

    def test_missing_keys_default_to_zero(self):
        result = parse_bandwidth_metrics(self._wrap([]))
        for key in ("PCPU DCS RD", "GFX DCS RD", "DCS RD", "MEDIA DCS"):
            self.assertEqual(result[key], 0)

    def test_values_are_converted_from_bytes_to_gb(self):
        result = parse_bandwidth_metrics(self._wrap([
            {"name": "GFX DCS RD", "value": 2_000_000_000},
            {"name": "GFX DCS WR", "value": 500_000_000},
        ]))
        self.assertAlmostEqual(result["GFX DCS RD"], 2.0)
        self.assertAlmostEqual(result["GFX DCS WR"], 0.5)

    def test_pcpu_aggregation_sums_per_die_counters(self):
        result = parse_bandwidth_metrics(self._wrap([
            {"name": "PCPU0 DCS RD", "value": 1_000_000_000},
            {"name": "PCPU1 DCS RD", "value": 2_000_000_000},
            {"name": "PCPU2 DCS RD", "value": 3_000_000_000},
            {"name": "PCPU3 DCS RD", "value": 4_000_000_000},
        ]))
        self.assertAlmostEqual(result["PCPU DCS RD"], 10.0)

    def test_media_dcs_aggregates_all_media_engines(self):
        result = parse_bandwidth_metrics(self._wrap([
            {"name": "ISP DCS RD", "value": 1_000_000_000},
            {"name": "STRM CODEC DCS WR", "value": 1_000_000_000},
            {"name": "PRORES DCS RD", "value": 1_000_000_000},
            {"name": "VDEC DCS WR", "value": 1_000_000_000},
            {"name": "VENC0 DCS RD", "value": 1_000_000_000},
            {"name": "JPG0 DCS WR", "value": 1_000_000_000},
        ]))
        self.assertAlmostEqual(result["MEDIA DCS"], 6.0)

    def test_unknown_counter_names_are_ignored(self):
        result = parse_bandwidth_metrics(self._wrap([
            {"name": "BOGUS COUNTER", "value": 999_999_999_999},
            {"name": "GFX DCS RD", "value": 1_000_000_000},
        ]))
        self.assertAlmostEqual(result["GFX DCS RD"], 1.0)
        self.assertNotIn("BOGUS COUNTER", result)


if __name__ == "__main__":
    unittest.main()
