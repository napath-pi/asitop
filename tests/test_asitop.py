import subprocess
import unittest
from unittest import mock

from asitop.asitop import (
    _avg_window_maxlen,
    _positive_int,
    _terminate_powermetrics_process,
    build_parser,
    clip_text,
    compact_title,
    resolve_terminal_kind,
    sanitize_terminal_kind,
)


class AsitopTests(unittest.TestCase):
    def test_clip_text_truncates_with_ascii_ellipsis(self):
        self.assertEqual(clip_text("abcdef", 5), "ab...")

    def test_clip_text_respects_short_widths(self):
        self.assertEqual(clip_text("abcdef", 3), "abc")

    def test_clip_text_returns_empty_for_zero_width(self):
        self.assertEqual(clip_text("abc", 0), "")

    def test_clip_text_returns_empty_for_negative_width(self):
        self.assertEqual(clip_text("abc", -5), "")

    def test_clip_text_passes_through_when_width_meets_or_exceeds_length(self):
        self.assertEqual(clip_text("abcdef", 6), "abcdef")
        self.assertEqual(clip_text("abcdef", 100), "abcdef")

    def test_clip_text_handles_empty_input(self):
        self.assertEqual(clip_text("", 5), "")

    def test_show_cores_flag_is_false_by_default(self):
        args = build_parser().parse_args([])
        self.assertFalse(args.show_cores)

    def test_show_cores_flag_enables_core_mode(self):
        args = build_parser().parse_args(["--show_cores"])
        self.assertTrue(args.show_cores)

    def test_sanitize_terminal_kind_fixes_ghostty_typo(self):
        self.assertEqual(sanitize_terminal_kind("xterm-ghossty"), "xterm-ghostty")

    def test_resolve_terminal_kind_falls_back_to_xterm_256color(self):
        attempted = []

        def fake_setupterm(kind, _fd):
            attempted.append(kind)
            if kind == "xterm-ghostty":
                raise RuntimeError("missing terminfo")

        resolved = resolve_terminal_kind("xterm-ghossty", setupterm=fake_setupterm)

        self.assertEqual(resolved, "xterm-256color")
        self.assertEqual(attempted[:2], ["xterm-ghostty", "xterm-256color"])


class CompactTitleTests(unittest.TestCase):
    def test_joins_parts_with_spaces(self):
        self.assertEqual(compact_title("CPU", "100%", "3.2GHz"), "CPU 100% 3.2GHz")

    def test_single_part(self):
        self.assertEqual(compact_title("solo"), "solo")

    def test_empty_yields_empty_string(self):
        self.assertEqual(compact_title(), "")

    def test_stringifies_non_string_parts(self):
        self.assertEqual(compact_title("freq", 1296, "MHz"), "freq 1296 MHz")


class PositiveIntTests(unittest.TestCase):
    def test_accepts_positive_integer(self):
        self.assertEqual(_positive_int("3"), 3)

    def test_rejects_zero(self):
        with self.assertRaises(Exception):
            _positive_int("0")

    def test_rejects_negative(self):
        with self.assertRaises(Exception):
            _positive_int("-1")

    def test_rejects_non_integer(self):
        with self.assertRaises(Exception):
            _positive_int("abc")


class CliValidationTests(unittest.TestCase):
    def test_build_parser_rejects_zero_interval(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--interval", "0"])

    def test_build_parser_rejects_negative_interval(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--interval", "-1"])

    def test_build_parser_rejects_zero_avg(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--avg", "0"])

    def test_build_parser_accepts_default_interval_and_avg(self):
        args = build_parser().parse_args([])
        self.assertEqual(args.interval, 1)
        self.assertEqual(args.avg, 30)


class AvgWindowMaxlenTests(unittest.TestCase):
    def test_default_settings_yield_thirty(self):
        self.assertEqual(_avg_window_maxlen(30, 1), 30)

    def test_avg_smaller_than_interval_clamps_to_one(self):
        self.assertEqual(_avg_window_maxlen(1, 2), 1)

    def test_equal_avg_and_interval_yields_one(self):
        self.assertEqual(_avg_window_maxlen(2, 2), 1)

    def test_typical_ratio(self):
        self.assertEqual(_avg_window_maxlen(60, 2), 30)


class TerminatePowermetricsProcessTests(unittest.TestCase):
    def test_handles_none(self):
        _terminate_powermetrics_process(None)

    def test_skips_when_process_already_exited(self):
        process = mock.MagicMock()
        process.poll.return_value = 0
        _terminate_powermetrics_process(process)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_terminates_running_process(self):
        process = mock.MagicMock()
        process.poll.return_value = None
        process.wait.return_value = 0
        _terminate_powermetrics_process(process, wait_seconds=1)
        process.terminate.assert_called_once()
        process.wait.assert_called_with(timeout=1)
        process.kill.assert_not_called()

    def test_kills_process_on_terminate_timeout(self):
        process = mock.MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="powermetrics", timeout=1),
            0,
        ]
        _terminate_powermetrics_process(process, wait_seconds=1)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    def test_swallows_unexpected_exceptions(self):
        process = mock.MagicMock()
        process.poll.return_value = None
        process.terminate.side_effect = OSError("already gone")
        _terminate_powermetrics_process(process)


if __name__ == "__main__":
    unittest.main()
