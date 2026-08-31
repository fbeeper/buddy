#include "BuddyStatusTile.h"

#include "BuddyData.h"
#include "DEV_Config.h"
#include "pico/stdlib.h"

#define BACKLIGHT_NORMAL_PERCENT 100u
#define BACKLIGHT_ALERT_MIN_PERCENT 20u
#define BACKLIGHT_PULSE_PERIOD_MS 1400u
#define BACKLIGHT_UPDATE_INTERVAL_MS 20u

static lv_obj_t *session_rows[BUDDY_MAX_ROWS];
static lv_obj_t *relay_offline_label;
static bool relay_offline_was_visible;
static bool backlight_was_active;
static uint32_t pulse_started_ms;
static uint32_t last_backlight_update_ms;

lv_obj_t *BuddyStatusTile_Create(lv_obj_t *tileview)
{
    lv_obj_t *tile = lv_tileview_add_tile(tileview, 0, 1, LV_DIR_TOP);
    lv_obj_set_style_bg_color(tile, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(tile, LV_OPA_COVER, 0);

    lv_obj_t *panel = lv_obj_create(tile);
    lv_obj_set_size(panel, 166, 146);
    lv_obj_align(panel, LV_ALIGN_CENTER, 0, 3);
    lv_obj_set_style_radius(panel, 14, 0);
    lv_obj_set_style_pad_all(panel, 14, 0);
    lv_obj_set_style_bg_color(panel, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(panel, 0, 0);
    lv_obj_clear_flag(panel, LV_OBJ_FLAG_SCROLLABLE);

    LV_FONT_DECLARE(lv_font_buddy_mono_14);
    for (int i = 0; i < BUDDY_MAX_ROWS; i++) {
        session_rows[i] = lv_label_create(panel);
        lv_obj_set_width(session_rows[i], 138);
        lv_label_set_long_mode(session_rows[i], LV_LABEL_LONG_CLIP);
        lv_obj_align(session_rows[i], LV_ALIGN_TOP_LEFT, 0, i * 20);
        lv_obj_set_style_text_font(session_rows[i], &lv_font_buddy_mono_14, 0);
        lv_label_set_text(session_rows[i], "");
    }

    relay_offline_label = lv_label_create(tile);
    lv_label_set_text(relay_offline_label, ":(");
    lv_obj_set_style_text_font(relay_offline_label, &lv_font_buddy_mono_14, 0);
    lv_obj_set_style_text_color(relay_offline_label,
                                lv_palette_main(LV_PALETTE_RED), 0);
    lv_obj_align(relay_offline_label, LV_ALIGN_BOTTOM_MID, 0, -40);
    lv_obj_add_flag(relay_offline_label, LV_OBJ_FLAG_HIDDEN);
    relay_offline_was_visible = false;

    backlight_was_active = false;
    BuddyStatusTile_Refresh();
    return tile;
}

void BuddyStatusTile_Refresh(void)
{
    for (int i = 0; i < BUDDY_MAX_ROWS; i++) {
        const BuddyRow *data = BuddyData_GetRow(i);
        if (data == NULL || session_rows[i] == NULL) continue;
        lv_label_set_text(session_rows[i], data->text);
        if (data->text[0])
            lv_obj_set_style_text_color(session_rows[i],
                                        lv_color_hex(data->color), 0);
    }
}

void BuddyStatusTile_UpdateRelayStatus(void)
{
    if (relay_offline_label == NULL) return;
    bool offline = !BuddyData_IsRelayOnline();
    if (offline == relay_offline_was_visible) return;
    relay_offline_was_visible = offline;
    if (offline)
        lv_obj_clear_flag(relay_offline_label, LV_OBJ_FLAG_HIDDEN);
    else
        lv_obj_add_flag(relay_offline_label, LV_OBJ_FLAG_HIDDEN);
}

void BuddyStatusTile_UpdateBacklight(void)
{
    uint32_t now_ms = to_ms_since_boot(get_absolute_time());
    bool active = BuddyData_IsAlertActive();
    if (!active) {
        if (backlight_was_active) DEV_SET_PWM(BACKLIGHT_NORMAL_PERCENT);
        backlight_was_active = false;
        return;
    }

    if (!backlight_was_active) {
        backlight_was_active = true;
        pulse_started_ms = now_ms;
        last_backlight_update_ms = now_ms - BACKLIGHT_UPDATE_INTERVAL_MS;
    }
    if (now_ms - last_backlight_update_ms < BACKLIGHT_UPDATE_INTERVAL_MS) return;
    last_backlight_update_ms = now_ms;

    const uint32_t half_period_ms = BACKLIGHT_PULSE_PERIOD_MS / 2u;
    const uint32_t range =
        BACKLIGHT_NORMAL_PERCENT - BACKLIGHT_ALERT_MIN_PERCENT;
    uint32_t phase_ms =
        (now_ms - pulse_started_ms) % BACKLIGHT_PULSE_PERIOD_MS;
    uint32_t brightness = phase_ms < half_period_ms
        ? BACKLIGHT_NORMAL_PERCENT - (range * phase_ms) / half_period_ms
        : BACKLIGHT_ALERT_MIN_PERCENT
            + (range * (phase_ms - half_period_ms)) / half_period_ms;
    DEV_SET_PWM((uint8_t)brightness);
}
