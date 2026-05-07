import os
import pathlib
import plistlib
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from asitop.utils import (
    cleanup_powermetrics_files,
    convert_to_GB,
    get_powermetrics_dir,
    get_powermetrics_path,
    get_ram_metrics_dict,
    get_soc_info,
    parse_powermetrics,
    run_powermetrics_process,
)


def _plist_payload(timestamp="ts1"):
    return {
        "thermal_pressure": "Nominal",
        "timestamp": timestamp,
        "processor": {
            "ane_energy": 100,
            "cpu_energy": 200,
            "gpu_energy": 300,
            "combined_power": 600,
            "clusters": [
                {
                    "name": "E-Cluster",
                    "freq_hz": 2_000_000_000,
                    "idle_ratio": 0.5,
                    "cpus": [
                        {"cpu": 0, "freq_hz": 2_000_000_000, "idle_ratio": 0.5},
                    ],
                },
                {
                    "name": "P-Cluster",
                    "freq_hz": 3_000_000_000,
                    "idle_ratio": 0.0,
                    "cpus": [
                        {"cpu": 0, "freq_hz": 3_000_000_000, "idle_ratio": 0.0},
                    ],
                },
            ],
        },
        "gpu": {"freq_hz": 1_296_000_000, "idle_ratio": 0.5},
    }


class UtilsTests(unittest.TestCase):
    def test_get_powermetrics_path_uses_per_user_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(get_powermetrics_path("123", base_dir=tmpdir))
            self.assertEqual(path.parent, pathlib.Path(tmpdir) / f"asitop-{os.getuid()}")
            self.assertEqual(path.name, "powermetrics-123.plist")

    def test_cleanup_powermetrics_files_ignores_missing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(get_powermetrics_path("123", base_dir=tmpdir))
            path.write_text("x")

            real_remove = os.remove

            def flaky_remove(target):
                real_remove(target)
                raise FileNotFoundError(target)

            with mock.patch("asitop.utils.os.remove", side_effect=flaky_remove):
                cleanup_powermetrics_files(base_dir=tmpdir)

            self.assertFalse(path.exists())

    def test_get_powermetrics_dir_creates_dir_with_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(get_powermetrics_dir(base_dir=tmpdir))
            self.assertTrue(path.is_dir())
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o700)


class ConvertToGBTests(unittest.TestCase):
    def test_one_gibibyte(self):
        self.assertEqual(convert_to_GB(1024 ** 3), 1.0)

    def test_rounds_to_one_decimal(self):
        self.assertEqual(convert_to_GB(int(1.55 * 1024 ** 3)), 1.5)

    def test_zero(self):
        self.assertEqual(convert_to_GB(0), 0.0)


class ParsePowermetricsTests(unittest.TestCase):
    def _write_plists(self, plists, tmpdir):
        path = pathlib.Path(tmpdir) / "sample.plist"
        with open(path, "wb") as f:
            for i, p in enumerate(plists):
                if i:
                    f.write(b"\x00")
                f.write(plistlib.dumps(p))
        return str(path)

    def test_parses_latest_plist_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_plists(
                [_plist_payload("first"), _plist_payload("second")],
                tmp,
            )
            result = parse_powermetrics(path=path)
            self.assertNotEqual(result, False)
            cpu, gpu, thermal, bw, ts = result
            self.assertEqual(thermal, "Nominal")
            self.assertEqual(ts, "second")
            self.assertEqual(gpu["freq_MHz"], 1296)
            self.assertIsNone(bw)

    def test_falls_back_to_previous_segment_when_last_is_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sample.plist"
            with open(path, "wb") as f:
                f.write(plistlib.dumps(_plist_payload("good")))
                f.write(b"\x00")
                f.write(b"<<not a valid plist>>")
            result = parse_powermetrics(path=str(path))
            self.assertNotEqual(result, False)
            self.assertEqual(result[-1], "good")

    def test_returns_false_when_only_segment_is_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sample.plist"
            with open(path, "wb") as f:
                f.write(b"junk-only")
            self.assertEqual(parse_powermetrics(path=str(path)), False)

    def test_returns_false_when_file_missing(self):
        self.assertEqual(
            parse_powermetrics(path="/nonexistent/asitop-test.plist"),
            False,
        )


class GetRamMetricsDictTests(unittest.TestCase):
    def _patch_psutil(self, *, total, available, swap_total, swap_used):
        vmem = mock.MagicMock(total=total, available=available)
        smem = mock.MagicMock(total=swap_total, used=swap_used)
        return mock.patch.multiple(
            "asitop.utils.psutil",
            virtual_memory=mock.MagicMock(return_value=vmem),
            swap_memory=mock.MagicMock(return_value=smem),
        )

    def test_swap_off_branch_yields_none_swap_percent(self):
        gib = 1024 ** 3
        with self._patch_psutil(total=16 * gib, available=8 * gib, swap_total=0, swap_used=0):
            result = get_ram_metrics_dict()
        self.assertEqual(result["total_GB"], 16.0)
        self.assertEqual(result["used_GB"], 8.0)
        self.assertEqual(result["free_percent"], 50)
        self.assertIsNone(result["swap_free_percent"])

    def test_swap_on_branch_computes_swap_percent(self):
        gib = 1024 ** 3
        with self._patch_psutil(total=16 * gib, available=4 * gib,
                                swap_total=8 * gib, swap_used=2 * gib):
            result = get_ram_metrics_dict()
        self.assertEqual(result["used_GB"], 12.0)
        self.assertEqual(result["swap_used_GB"], 2.0)
        self.assertEqual(result["swap_free_percent"], 25)


class GetSocInfoTests(unittest.TestCase):
    def _patch(self, *, name, e_cores=4, p_cores=4, gpu_cores=10):
        return mock.patch.multiple(
            "asitop.utils",
            get_cpu_info=mock.MagicMock(return_value={
                "machdep.cpu.brand_string": name,
                "machdep.cpu.core_count": str(e_cores + p_cores),
            }),
            get_core_counts=mock.MagicMock(return_value={
                "hw.perflevel0.logicalcpu": p_cores,
                "hw.perflevel1.logicalcpu": e_cores,
            }),
            get_gpu_cores=mock.MagicMock(return_value=gpu_cores),
        )

    def test_known_chip_uses_spec_table(self):
        with self._patch(name="Apple M5"):
            info = get_soc_info()
        self.assertEqual(info["name"], "Apple M5")
        self.assertEqual(info["cpu_max_power"], 30)
        self.assertEqual(info["gpu_max_power"], 25)
        self.assertEqual(info["cpu_max_bw"], 153)
        self.assertEqual(info["e_core_count"], 4)
        self.assertEqual(info["p_core_count"], 4)
        self.assertEqual(info["gpu_core_count"], 10)

    def test_unknown_chip_falls_back_to_default_spec(self):
        with self._patch(name="Apple M99 Hypothetical"):
            info = get_soc_info()
        self.assertEqual(info["cpu_max_power"], 20)
        self.assertEqual(info["gpu_max_power"], 20)
        self.assertEqual(info["cpu_max_bw"], 70)
        self.assertEqual(info["gpu_max_bw"], 70)

    def test_m4_max_uses_published_bandwidth(self):
        with self._patch(name="Apple M4 Max"):
            info = get_soc_info()
        self.assertEqual(info["cpu_max_bw"], 546)
        self.assertEqual(info["gpu_max_power"], 70)


class RunPowermetricsProcessTests(unittest.TestCase):
    def _capture_popen(self):
        captured = {}
        fake_process = mock.MagicMock()

        def fake_popen(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return fake_process

        return captured, fake_process, fake_popen

    def test_uses_devnull_for_stdin_and_stdout(self):
        captured, fake_process, fake_popen = self._capture_popen()
        with mock.patch("asitop.utils.subprocess.Popen", side_effect=fake_popen), \
                mock.patch("asitop.utils.cleanup_powermetrics_files"):
            result = run_powermetrics_process("123")

        self.assertIs(result, fake_process)
        self.assertIs(captured["kwargs"]["stdin"], subprocess.DEVNULL)
        self.assertIs(captured["kwargs"]["stdout"], subprocess.DEVNULL)

    def test_command_includes_required_powermetrics_flags(self):
        captured, _, fake_popen = self._capture_popen()
        with mock.patch("asitop.utils.subprocess.Popen", side_effect=fake_popen), \
                mock.patch("asitop.utils.cleanup_powermetrics_files"):
            run_powermetrics_process("ts42", nice=5, interval=2000)

        argv = captured["args"][0]
        self.assertEqual(argv[0], "sudo")
        self.assertIn("nice", argv)
        self.assertIn("powermetrics", argv)
        self.assertIn("--samplers", argv)
        self.assertIn("cpu_power,gpu_power,thermal", argv)
        self.assertIn("-o", argv)
        self.assertIn("-f", argv)
        self.assertIn("plist", argv)
        self.assertIn("-i", argv)
        self.assertIn("2000", argv)
        self.assertIn("5", argv)

    def test_command_writes_plist_to_per_user_temp_path(self):
        captured, _, fake_popen = self._capture_popen()
        with mock.patch("asitop.utils.subprocess.Popen", side_effect=fake_popen), \
                mock.patch("asitop.utils.cleanup_powermetrics_files"):
            run_powermetrics_process("ts99")

        argv = captured["args"][0]
        output_path = argv[argv.index("-o") + 1]
        self.assertTrue(output_path.endswith("powermetrics-ts99.plist"))
        self.assertIn(f"asitop-{os.getuid()}", output_path)

    def test_calls_cleanup_before_starting(self):
        captured, _, fake_popen = self._capture_popen()
        with mock.patch("asitop.utils.subprocess.Popen", side_effect=fake_popen), \
                mock.patch("asitop.utils.cleanup_powermetrics_files") as cleanup:
            run_powermetrics_process("ts1")
        cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
