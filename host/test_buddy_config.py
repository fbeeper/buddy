import unittest

import buddy_config


class BuddyConfigTests(unittest.TestCase):
    def test_clock_line_formats_and_validates(self):
        self.assertEqual(
            buddy_config.clock_line(11, 58, 0, 120.0),
            "CLOCK 11 58 0 120.0",
        )
        with self.assertRaises(buddy_config.ConfigError):
            buddy_config.clock_line(24, 0, 0, 120.0)
        with self.assertRaises(buddy_config.ConfigError):
            buddy_config.clock_line(0, 60, 0, 120.0)
        with self.assertRaises(buddy_config.ConfigError):
            buddy_config.clock_line(0, 0, 0, 0.0)

    def test_clock_style_line_formats_and_validates(self):
        self.assertEqual(buddy_config.clock_style_line("arcs"), "CSTYLE arcs")
        self.assertEqual(buddy_config.clock_style_line("dots"), "CSTYLE dots")
        self.assertEqual(
            buddy_config.clock_style_line("dotted-arcs"),
            "CSTYLE dotted-arcs",
        )
        with self.assertRaises(buddy_config.ConfigError):
            buddy_config.clock_style_line("worms")

    def test_parser_exposes_only_configuration_commands(self):
        parser = buddy_config.build_parser()
        self.assertEqual(parser.parse_args(["clock-style", "dots"]).command,
                         "clock-style")
        self.assertEqual(parser.parse_args(["clock", "1", "2", "3"]).command,
                         "clock")


if __name__ == "__main__":
    unittest.main()
