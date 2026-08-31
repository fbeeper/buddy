# Third-party notices

The repository-level `LICENSE` applies to original project code. The
components and assets below remain under their own licenses and are not
relicensed by it.

## LVGL 8.1.0

- Component: Light and Versatile Graphics Library (LVGL), version 8.1.0
- Copyright: Copyright (c) 2021 LVGL Kft
- Source: https://github.com/lvgl/lvgl/tree/v8.1.0
- License: MIT
- Local license: `lib/lvgl/LICENCE.txt`

The vendored LVGL tree also contains third-party implementation components
and generated font data with their own notices, including TLSF, Qrcodegen,
LodePNG, TJpgDec, gifdec, NXP GPU support, Montserrat, Font Awesome, DejaVu,
and Unscii. Their copyright and license notices are retained in the relevant
source files. No endorsement by those authors or projects is implied.

The unused `arial.ttf` and unidentified `korean.ttf` files shipped in the
upstream tree have deliberately been removed from this copy.

## JetBrains Mono

- Component: JetBrains Mono Regular, version 2.304, ASCII glyph subset
- Copyright: Copyright 2020 The JetBrains Mono Project Authors
- Source: https://github.com/JetBrains/JetBrainsMono/tree/v2.304
- License: SIL Open Font License 1.1
- Local license: `licenses/JetBrainsMono-OFL-1.1.txt`
- Generated artifact: `firmware/src/buddy_font_mono14.c`
- Source TTF SHA-256: `a0bf60ef0f83c5ed4d7a75d45838548b1f6873372dfac88f71804491898d138f`

The embedded LVGL font was generated from the official
`fonts/ttf/JetBrainsMono-Regular.ttf` using `lv_font_conv` 1.5.3 with a
14-pixel, 4-bpp, uncompressed U+0020-U+007E glyph range. The generated font
remains under the SIL Open Font License 1.1.

## Waveshare board support

Portions of `lib/Config`, `lib/LCD`, `lib/QMI8658`, and the original board
demo scaffolding originated in Waveshare example code for its round LCD
boards. Existing author and permission notices are retained in those files.
The base RP2350-LCD-1.28 sample was distributed from Waveshare's product wiki:

- Original sample distribution: https://www.waveshare.com/wiki/RP2350-LCD-1.28

The `lib/Config` files and original demo scaffolding contain MIT permission
text. The LCD and QMI8658 driver portions are redistributed under Apache
License 2.0. They are not relicensed by this project's repository-level MIT
license.

### QMI8658 IMU driver

- Local component: `lib/QMI8658`
- Copyright/author attribution: Waveshare team (retained in the source lineage)
- Original board-code provenance: https://github.com/waveshareteam/RP2040-Touch-LCD-1.28/tree/main/c/lib/QMI8658
- Explicit license basis: Waveshare's official `sensor/qmi8658` component,
  including its component-local `license.txt`
- Pinned licensed component: https://github.com/waveshareteam/Waveshare-ESP32-components/tree/9c772a150234f47725eec7398b55ce9960c1635d/sensor/qmi8658
- Pinned license evidence: https://github.com/waveshareteam/Waveshare-ESP32-components/blob/9c772a150234f47725eec7398b55ce9960c1635d/sensor/qmi8658/license.txt
- License: Apache License 2.0
- Local license: `licenses/Apache-2.0.txt`

The local `QMI8658.c` and `QMI8658.h` match the Waveshare RP2040 1.28-inch
board versions by Git blob identity. Waveshare also publishes its maintained
QMI8658 component with an adjacent Apache-2.0 license, which is the explicit
Waveshare licensing basis recorded here.

### GC9A01 LCD driver

- Local component: `lib/LCD`
- Copyright/author attribution: Waveshare team (retained in the source files)
- Original sample distribution: https://www.waveshare.com/wiki/RP2350-LCD-1.28
- Explicit license basis: Waveshare's official `esp_lcd_gc9a01` component for
  its 240x240 1.28-inch round LCD, including its component-local `license.txt`
- Pinned licensed component: https://github.com/waveshareteam/ESP32-S3-DualEye-Touch-LCD-1.28/tree/f16371ca7b7d4e17de6d6f6ea293981b37c0ca51/example/ESP32-S3-DualEye-Touch-LCD-1.28/ESP-IDF-5.5.1/01_Text_Number/components/esp_lcd_gc9a01
- Pinned license evidence: https://github.com/waveshareteam/ESP32-S3-DualEye-Touch-LCD-1.28/blob/f16371ca7b7d4e17de6d6f6ea293981b37c0ca51/example/ESP32-S3-DualEye-Touch-LCD-1.28/ESP-IDF-5.5.1/01_Text_Number/components/esp_lcd_gc9a01/license.txt
- License: Apache License 2.0
- Local license: `licenses/Apache-2.0.txt`

The licensed reference uses ESP-IDF transport while this project uses the
Pico SDK transport in `lib/Config`; the controller-facing GC9A01 driver logic
and its local adaptations remain identified as the Apache-2.0 Waveshare
driver portion. The component-local license is cited deliberately: the
DualEye repository does not need a repository-wide license for that adjacent
license file to govern this component.

## Dog photograph

- Work: dog photograph embedded as RGB565 pixel data in
  `firmware/src/ImageData.c`
- Copyright: Copyright (c) 2026 fbeeper
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- License text: https://creativecommons.org/licenses/by/4.0/legalcode

You may share and adapt the photograph, including commercially, provided you
give appropriate credit, link to the license, and indicate whether changes
were made. A suitable credit is: **Dog photograph © 2026 fbeeper, licensed
under CC BY 4.0.** No endorsement is implied.
