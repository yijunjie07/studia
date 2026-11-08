"""Continuous per-character colors shared by both terminal renderers."""
import colorsys
import math
import os
import random
import time


class NameAnimation:
    def __init__(self):
        self.started = time.monotonic()
        self.seed = random.uniform(0, math.tau)

    def colors(self, text):
        t = time.monotonic() - self.started
        # Integral of a positive, irregular velocity: no jumps or pauses.
        flow = (145 * t + 55 / 1.37 * (math.cos(self.seed) - math.cos(t * 1.37 + self.seed))
                + 35 / 2.13 * (math.cos(1.7) - math.cos(t * 2.13 + 1.7)))
        result = []
        for i, char in enumerate(text):
            hue = flow + i * 76 + 27 * math.sin(t * 1.61 + self.seed + i * 2.4) + 14 * math.sin(t * .73 + i)
            wave = (1 + math.sin(t * 2.8 - i * .85 + .4 * math.sin(t * .91))) / 2
            hit = wave ** 5
            rgb = colorsys.hls_to_rgb((hue % 360) / 360, .60 + hit * .22, 1 - hit * .18)
            result.append(('#' + ''.join(f'{round(channel * 255):02x}' for channel in rgb), char))
        return result


def terminal_color_depth():
    """Use true color when advertised, retaining explicit terminal overrides."""
    from prompt_toolkit.output import ColorDepth
    override = ColorDepth.from_env()
    if override is not None:
        return override
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return ColorDepth.DEPTH_24_BIT
    return None
